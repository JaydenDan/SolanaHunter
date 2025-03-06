import asyncio
import logging

from datetime import datetime, timedelta
from pathlib import Path
import httpcore
import httpx
from socksio import ProtocolError
from twikit import AccountSuspended, Unauthorized

from src.notifier.discord.bot import DiscordBot
from src.utils.common_util import TaskCounter
from ..rules import engine
from ...account.twitter import TwitterClientManager
from ...account.twitter.get_account import AccountPool, TwitterAccount


async def _search_words_maker(mint_list):
    search_words = ''
    for ca in mint_list:
        if search_words == '':
            search_words = search_words + ca
        else:
            search_words = search_words + ' or ' + ca
    return search_words


class SearchTask:
    def __init__(self, twitter_config: dict, on_finish_callback, on_error_callback, account: TwitterAccount):
        self._task_counter = TaskCounter()
        self.mint_list = []
        self.token_list = []
        self.lock = asyncio.Lock()
        self.on_finish_callback = on_finish_callback
        self.on_error_callback = on_error_callback
        if not Path(twitter_config['account_file_path']).exists():
            raise FileNotFoundError(f"Twitter账号文件路径无效: {twitter_config['account_file_path']}")
        self.account_file_path = twitter_config['account_file_path']
        self.account_pool = AccountPool(twitter_config['account_file_path'])
        self.client_manager = TwitterClientManager()
        self.account = account
        self.client = None

    async def initialize_client(self):
        logging.info(f'🏹 开始初始化Twikit Client...')

        try:
            self.client = await self.client_manager.get_client(
                email=self.account.email,
                username=self.account.username,
                password=self.account.password,
                proxy=self.account.proxy
            )
            if not self.client:
                # 重新初始化
                await self._reinitialize_client(error_info='Twikit Client初始化为None', stack_trace="代理验证未通过")
            logging.info(f'🎯Twikit Client初始化完毕! 加载账号: {self.account.email}')
            return
        except AccountSuspended as e:
            # 抛出错误来源提供的信息
            raise e
        except Exception as e:
            # 其他异常直接抛出
            raise Exception(f'❌ 初始化客户端失败, 当前search_task将被放弃。') from e

    async def add_token(self, token: dict):
        async with self.lock:
            if len(self.mint_list) < 10:
                # 单独保存一份ca列表
                self.mint_list.append(token["mint"])
                # 保存一份代币信息列表
                self.token_list.append({
                    "mint": token['mint'],
                    "token": token,
                })
                return True
            return False

    async def run(self):
        """执行搜索任务"""
        try:
            while True:
                try:
                    await self.initialize_client()
                    break
                except AccountSuspended as e:
                    logging.warning(f'🚫 账号初始化失败, 尝试更换账号重新初始化')
                    success = await self._reinitialize_client(error_info=str(e.__class__.__name__), stack_trace=e.__traceback__)
                    if not success:
                        raise Exception(f'❌ 初始化客户端失败, 无法获取可用账号。') from e
                except Exception as e:
                    raise Exception(f'❌ 初始化客户端失败, 当前search_task将被放弃。') from e

            logging.info(f'🔛 搜索任务已启动, 使用账号: {self.account.email}')
            while True:
                await asyncio.sleep(20)
                async with self.lock:
                    current_ca = self.mint_list.copy()
                    self.mint_list.clear()

                    now = datetime.now()
                    expired_mints = [
                        t["mint"] for t in self.token_list
                        if (now - t['token']["detect_time"]).total_seconds() > 600
                    ]
                    if expired_mints:
                        logging.info(f'🆑 清理{len(expired_mints)}个超时CA')
                    self.token_list = [
                        t for t in self.token_list
                        if t["mint"] not in expired_mints
                    ]
                    current_ca = [
                        ca for ca in current_ca
                        if ca not in expired_mints
                    ]

                remaining_mint_list = []
                if current_ca:
                    remaining_mint_list = await self._monitor_social_data(current_ca)

                async with self.lock:
                    self.mint_list.extend(remaining_mint_list)
                    if not self.mint_list and not self.token_list:
                        logging.info(f'🏁 搜索任务已完成, 释放账号: {self.account.email}')
                        await self.account_pool.release_account(self.account, True)
                        break
        except Exception as e:
            logging.error(f'❌ 搜索任务运行错误: {str(e)}, 剩余Token已回滚到待处理队列', exc_info=True)
            await self.on_error_callback(self.token_list)
            await self.account_pool.release_account(self.account, False)
            await self.on_error_callback(self.token_list)
        finally:
            await self.on_finish_callback(self, self.account.email)

    async def _monitor_social_data(self, current_mint_list: list):
        """监控CA的推特帖子, 然后对有帖子的CA进行操作"""
        remaining_mint = current_mint_list.copy()
        try:
            if not current_mint_list:
                return []
            # 生成搜索关键字
            search_words = await _search_words_maker(current_mint_list)
            # 搜索帖子
            tweets = await self._search_tweets(str(search_words), "Latest")

            if len(tweets) > 0:
                mint_set = set(current_mint_list)
                remaining_mint, self.token_list = await engine.notify_process(
                    tweets=tweets,
                    mint_set=mint_set,
                    token_list=self.token_list,
                    remaining_mint=remaining_mint
                )
            return remaining_mint
        except Exception as e:
            logging.error(f"❌ 社交媒体数据获取失败: {str(e)}", exc_info=True)
            return remaining_mint

    async def _search_tweets(self, query: str, product: str) -> list:
        """
        异步搜索推文
        :param query: 搜索关键词
        :param product: 搜索模式
        :return: 推文列表
        """
        try:
            ALLOWED_PRODUCTS = {'Top', 'Latest', 'Media'}
            validated_product = product if product in ALLOWED_PRODUCTS else "Latest"

            search_result = await self.client.search_tweet(
                query, validated_product,
            )

            return [
                {
                    "id": tweet.id,
                    "text": tweet.text,
                    "created_at": tweet.created_at_datetime + timedelta(hours=8),
                    "user": {
                        "name": tweet.user.name,
                        "screen_name": tweet.user.screen_name,
                        "description": tweet.user.description,
                        "verified": tweet.user.verified,
                        "is_blue_verified": tweet.user.is_blue_verified,
                        "display_url": tweet.user.urls[0]['display_url'] if tweet.user.urls and tweet.user.urls[0].get(
                            'display_url') else '----',
                        "expanded_url": tweet.user.urls[0]['expanded_url'] if tweet.user.urls and tweet.user.urls[
                            0].get('expanded_url') else '----',
                        "following_count": tweet.user.following_count,
                        "favourites_count": tweet.user.favourites_count,
                        "followers_count": tweet.user.followers_count,
                        "fast_followers_count": tweet.user.fast_followers_count,
                        "normal_followers_count": tweet.user.normal_followers_count
                    },
                    "metrics": {
                        "likes": tweet.favorite_count,
                        "retweets": tweet.retweet_count,
                        "replies": tweet.reply_count,
                        "view_count": tweet.view_count if tweet.view_count is not None else 0
                    }
                }
                for tweet in search_result
            ]
        except (httpx.ConnectError, httpcore.ConnectError, ProtocolError, httpcore.ConnectTimeout, httpx.ConnectTimeout, httpx.ReadTimeout, httpcore.ReadTimeout) as e:
            # 不同类型错误输出不同日志
            if isinstance(e, (httpx.ConnectError, httpcore.ConnectError)):
                logging.warning(f'🌐 网络连接失败({e.__class__.__name__}): {str(e)}')
            elif isinstance(e, ProtocolError):
                logging.warning(f'🌐 代理连接失败(ProtocolError): {str(e)}')
            elif isinstance(e, (httpcore.ConnectTimeout, httpx.ConnectTimeout)):
                logging.warning(f'🌐 连接超时({e.__class__.__name__}): {str(e)}')
            elif isinstance(e, (httpx.ReadTimeout, httpcore.ReadTimeout)):
                logging.warning(f'🌐 读取超时({e.__class__.__name__}): {str(e)}')
            return []
        except AccountSuspended as e:
            if 'Rate limit exceeded' in str(e):
                logging.warning(f'🚫 账号【{self.account.email}】达到限流-429')
                await self._reinitialize_client(error_name=str(e.__class__.__name__), error_info=str(e))
        except Exception as e:
            if "AttributeError: 'ClientTransaction' object has no attribute 'key'" in str(e):
                logging.warning(f'🚫 账号【{self.account.email}】疑似封禁-AttributeError')
                await self._reinitialize_client(error_name=str(e.__class__.__name__), error_info=str(e))
            if "Forbidden" in str(e) or "403" in str(e):
                logging.warning(f'🚫 账号【{self.account.email}】账号被禁止访问-403')
                await self._reinitialize_client(error_name=str(e.__class__.__name__), error_info=str(e))
            logging.error(f"❌ 搜索失败: {str(e)}", exc_info=True)
        return []

    async def _reinitialize_client(self, error_name: str, error_info: str):
        """重新初始化客户端(更换账号)"""
        try:
            bot = DiscordBot()
            await bot.send_account_error(self.account, error_name, error_info)
            logging.info(f'🔄 开始更换账号...')
            # 释放旧账号(标记为不可用)
            await self.account_pool.release_account(self.account, False)

            # 获取新账号
            self.account = await self.account_pool.acquire()
            if not self.account:
                raise Exception("❌ 无法获取新账号")

            # 创建新客户端
            self.client = await self.client_manager.get_client(
                email=self.account.email,
                username=self.account.username,
                password=self.account.password,
                proxy=self.account.proxy
            )
            if not self.client:
                await self._reinitialize_client(error_info='Twikit Client初始化为None', stack_trace="代理验证未通过")
            # 更新当前协程的名字
            current_task = asyncio.current_task()
            if current_task:
                original_name = current_task.get_name()
                new_name = await self._task_counter.get_name(self.account.email.split('@')[0])
                current_task.set_name(new_name)
                logging.info(f'✅ 账号更换成功, 新账号: {self.account.email}, 协程名称更新为: {new_name}')
            return True
        except AccountSuspended as e:
            logging.warning(f'🚫 账号【{self.account.email}】换号失败, 尝试继续换号')
            await self._reinitialize_client(error_info=str(e.__class__.__name__), stack_trace=str(e.__traceback__))
            return False
        except Exception as e:
            logging.error(f'❌ 更换账号失败: {str(e)}')
            return False
