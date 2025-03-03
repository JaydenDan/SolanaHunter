import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import httpcore
from twikit.client.client import Client

from src.utils.common_util import TaskCounter
from ..rules import engine
from ...account.twitter import TwitterClientManager
from ...account.twitter.get_account import AccountPool


async def _search_words_maker(ca_list):
    search_words = ''
    for ca in ca_list:
        if search_words == '':
            search_words = search_words + ca
        else:
            search_words = search_words + ' or ' + ca
    return search_words


async def _search_tweets(client: Client, query: str, product: str) -> list:
    """
    异步搜索推文
    :param client: 推特客户端
    :param query: 搜索关键词
    :param product: 搜索模式
    :return: 推文列表
    """
    try:
        # 定义允许的 product 值列表
        ALLOWED_PRODUCTS = {'Top', 'Latest', 'Media'}

        # 调用前处理参数
        if product in ALLOWED_PRODUCTS:
            validated_product = product
        else:
            validated_product = "Latest"
            logging.warning(f"⚠️️ 当前Twitter搜索类型不合法，已默认为[Latest]")
            
        # 执行搜索
        search_result = await client.search_tweet(
            query, validated_product,  # type: ignore
        )

        # 格式化结果
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
                    "display_url": tweet.user.urls[0]['display_url'],
                    "expanded_url": tweet.user.urls[0]['expanded_url'],
                    "following_count": tweet.user.following_count,  # 关注人数
                    "favourites_count": tweet.user.favourites_count,  # 点赞/收藏数
                    "followers_count": tweet.user.followers_count,  # 粉丝总数
                    "fast_followers_count": tweet.user.fast_followers_count,  # 可能用于统计那些"活跃度更高、关注并快速与该账户产生互动"的粉丝数量
                    "normal_followers_count": tweet.user.normal_followers_count  # 普通的、未被归类为"快速互动"特征的粉丝数量
                },
                "metrics": {
                    "likes": tweet.favorite_count,
                    "retweets": tweet.retweet_count,
                    "replies": tweet.reply_count,
                    "view_count": tweet.view_count if tweet.view_count is not None else 0  # 默认为0
                }
            }
            for tweet in search_result
        ]
    except httpcore.ConnectError as e:
        logging.warning(f'🌐 网络连接失败 | {query} ({e.__class__.__name__})')
        return []
    except Exception as e:
        if 'Rate limit exceeded' in str(e):
            logging.error(f'🚫 429-账号达到限流 | {query} ({e.__class__.__name__})')
        logging.warning(f"⚠️ 搜索失败 | {query} ({e.__class__.__name__})")
        return []


class SearchTask:
    def __init__(self, twitter_config: dict, on_finish_callback):
        self._task_counter = TaskCounter()
        self.ca_list = []
        self.token_list = []
        self.lock = asyncio.Lock()
        self.on_finish_callback = on_finish_callback
        self.task = asyncio.create_task(self.run())

        if not Path(twitter_config['account_file_path']).exists():
            raise FileNotFoundError(f"Twitter账号文件路径无效: {twitter_config['account_file_path']}")
        self.account_file_path = twitter_config['account_file_path']
        self.account_pool = AccountPool(twitter_config['account_file_path'])  # 假设AccountPool的__init__是同步的
        self.client_manager = TwitterClientManager()
        self.account = None  # 异步获取的账号占位
        self.client = None  # 异步初始化的客户端占位

    async def initialize_client(self):
        logging.info(f'🏹 开始初始化Twikit Client...')
        self.account = await self.account_pool.acquire()
        self.client = await self.client_manager.get_client(
            email=self.account.email,
            username=self.account.username,
            password=self.account.password,
            proxy=self.account.proxy  # 使用类初始化时的proxy参数
        )
        logging.info(f'🎯Twikit Client初始化完毕!')

    async def add_ca(self, token: dict):
        async with self.lock:
            if len(self.ca_list) < 10:
                # 单独保存一份ca列表
                self.ca_list.append(token["mint"])
                # 保存一份代币信息列表
                self.token_list.append({
                    "mint": token['mint'],
                    "token": token,
                    "start_time": datetime.now()
                })
                return True
            return False

    async def run(self):
        """执行搜索任务"""
        try:
            logging.info(f'🔛 开始执行一个搜索任务...')
            await self.initialize_client()
            while True:
                # 20s 执行一次
                await asyncio.sleep(20)
                async with self.lock:  # 1. 获取异步锁
                    # 1. 获取并清空当前 CA 列表
                    current_ca = self.ca_list.copy()  # 2. 复制当前CA列表
                    self.ca_list.clear()  # 3. 清空原始列表

                    # 2. 检查并移除超时 CA（新增逻辑）
                    now = datetime.now()
                    # 找出超时（>600秒）的 CA
                    logging.info(f'🆑 正在清理的搜索任务列表中的超时CA')
                    expired_mints = [
                        t["mint"] for t in self.token_list
                        if (now - t["start_time"]).total_seconds() > 600
                    ]
                    # 同时从 token_list 和当前 CA 列表中移除
                    self.token_list = [
                        t for t in self.token_list
                        if t["mint"] not in expired_mints
                    ]
                    current_ca = [
                        ca for ca in current_ca
                        if ca not in expired_mints
                    ]

                # 3. 处理当前 CA（注意：这里已经不在 lock 中，使用副本数据）
                remaining_ca_list = []
                if current_ca:
                    # 在推特搜索当前CA
                    remaining_ca_list = await self._monitor_social_data(current_ca)

                # 4. 合并剩余 CA（需要再次加锁）
                async with self.lock:
                    self.ca_list.extend(remaining_ca_list)
                    # 检查是否需要销毁任务（列表完全空时）
                    if not self.ca_list and not self.token_list:
                        logging.info(
                            f'🏁 当前搜索任务已清空，销毁当前任务。ca_list：{len(self.ca_list)}-【{self.ca_list}】，token_list{len(self.token_list)}-【{self.token_list}】')
                        await self.account_pool.release_account(self.account, True)
                        break  # 退出循环，触发 finally 回调
        except Exception as e:
            logging.error(f'❌ 搜索任务协程在运行时发生错误【{e}】', exc_info=True)
            await self.account_pool.release_account(self.account, False)
        finally:
            # 通知管理器移除本任务
            logging.info(f'📝 关闭一个搜索协程并将账号释放...')
            await self.on_finish_callback(self)

    async def _monitor_social_data(self, current_ca_list: list):
        """监控CA的推特帖子，然后对有帖子的CA进行操作"""
        remaining_ca = current_ca_list.copy()
        try:
            if not current_ca_list:
                return []
            # 生成搜索关键字
            search_words = await _search_words_maker(current_ca_list)
            # 搜索帖子
            tweets = await _search_tweets(self.client, str(search_words), "Latest")

            if len(tweets) > 0:
                cas_set = set(current_ca_list)
                # # 把数据交给通知规则处理器，把剩余的ca保存到self
                remaining_ca, self.token_list = await engine.notify_process(tweets=tweets, cas_set=cas_set, token_list=self.token_list, remaining_ca=remaining_ca)
            else:
                logging.info(f'🈚️ 当前搜索任务中所有CA都没有相关推文，CA列表：【{current_ca_list}】')
            return remaining_ca
        except Exception as e:
            logging.error(f"❌ 社交媒体数据获取失败: {str(e)}", exc_info=True)
            return remaining_ca
