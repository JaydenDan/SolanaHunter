import asyncio
import logging

from datetime import datetime, timedelta
from pathlib import Path
import httpcore
import httpx
from socksio import ProtocolError
from twikit import AccountSuspended, Unauthorized, TooManyRequests

from src.notifier.notification_processor import to_notify_account_error, to_notify_token
from src.utils import common_util
from src.utils.common_util import TaskCounter

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
                await self._reinitialize_client(error_name='Twikit Client初始化为None', error_info="", retry_count=0)
            
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
            await self.initialize_client()
            logging.info(f'🔛 搜索任务已启动, 使用账号: {self.account.email}')
            while True:
                await asyncio.sleep(20)
                async with self.lock:
                    current_ca = self.mint_list.copy()
                    self.mint_list.clear()

                    now = datetime.now()
                    expired_mints = []
                    for t in self.token_list:
                        try:
                            if (now - t["token"]["detect_time"]).total_seconds() > 600:
                                expired_mints.append(t["mint"])
                        except Exception as e:
                            logging.error(f"❌ 清理超时CA失败: {str(e)}", exc_info=True)
                            logging.error(f"❌ 当前token_list: {self.token_list}")
                            logging.error(f"❌ 当前token: {t}")
                            expired_mints = []
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
            logging.error(f'❌ 搜索任务运行错误: {str(e)} 剩余Token已回滚到待处理队列')
            # 只传递原始token列表
            original_tokens = [t["token"] for t in self.token_list]
            await self.on_error_callback(original_tokens)
            await self.account_pool.release_account(self.account, False)
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
            mint_set = set(current_mint_list)
            for t in tweets:
                tweet_mint_list = common_util.get_mint_in_tweet(t['text'])
                for tweet_mint in tweet_mint_list:
                    logging.info(f'🔍️ 当前搜索到的推特帖子内容为:\n【{t["text"]}】')
                    if tweet_mint in mint_set:
                        # 根据mint在token_list中查找token完整信息
                        matched_item = next(
                            (item for item in self.token_list
                             if item.get("mint") == tweet_mint),
                            None  # 找不到时返回 None
                        ) 
                        if matched_item is None:
                            logging.warning(f'⚠️ 未找到匹配的 token, CA: {tweet_mint}, 可能是一个CA有多个推文, 在前一个推文触发时已将该CA移出列表。')
                            continue  # 跳过或执行其他逻辑
                        data = matched_item['token']
                        logging.info(f'CA反搜索到的数据【{data}】')
                        if data:
                            context = {
                                # 交易签名（唯一标识）
                                "signature": data["signature"],
                                # 代币合约地址
                                "mint": data["mint"],
                                # 交易者公钥
                                "traderPublicKey": data["traderPublicKey"],
                                "dev_balance": data["dev_balance"],
                                # DEV创业次数
                                "entrepreneurial_attempts_count": data["entrepreneurial_attempts_count"],
                                # 交易类型（create/swap等）
                                "txType": data["txType"],
                                # 初始购买金额（SOL）
                                "initialBuy": data["initialBuy"],
                                # 当前交易SOL金额
                                "solAmount": data["solAmount"],
                                # 该代币采用的 Bonding Curve (弹性定价模型) 的合约地址。Bonding Curve 通过数学公式决定代币的价格。
                                "bondingCurveKey": data["bondingCurveKey"],
                                # 盘子代币存量
                                "vTokensInBondingCurve": data["vTokensInBondingCurve"],
                                # 盘子SOL存量
                                "vSolInBondingCurve": data["vSolInBondingCurve"],
                                # 市值（SOL计价）
                                "marketCapSol": data["marketCapSol"],
                                # 代币名称
                                "name": data["name"],
                                # 代币符号
                                "symbol": data["symbol"],
                                # 代币元数据URI
                                "uri": data["uri"],
                                # 所属交易池
                                "pool": data["pool"],
                                # 检测时间
                                "detect_time": data["detect_time"],  
                                # 社交媒体数据（异步获取）
                                "social": t
                            }
                            await to_notify_token(context)
                            if tweet_mint in remaining_mint:
                                remaining_mint.remove(tweet_mint)
                                # 删除已处理的token信息
                                self.token_list = [item for item in self.token_list if item.get("mint") != tweet_mint]
                    else:
                        logging.warning(f"⚠️ 当前推特中的CA【{tweet_mint}】不在CA监控名单中, 请检查程序逻辑！")
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
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
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
                            "display_url": tweet.user.urls[0]['display_url'] if tweet.user.urls and tweet.user.urls[0].get('display_url') else '----',
                            "expanded_url": tweet.user.urls[0]['expanded_url'] if tweet.user.urls and tweet.user.urls[0].get('expanded_url') else '----',
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
                retry_count += 1
                # 计算等待时间（指数退避策略）
                base_time = 1  # 基础等待时间（秒）
                wait_time = base_time * (2 ** retry_count)  # 2^1=2, 2^2=4, 2^3=8
                
                # 不同类型错误输出不同日志
                if isinstance(e, (httpx.ConnectError, httpcore.ConnectError)):
                    logging.warning(f'🌐 网络连接失败({e.__class__.__name__}): {str(e)}, 重试次数: {retry_count}/{max_retries}, {wait_time}秒后重试')
                elif isinstance(e, ProtocolError):
                    logging.warning(f'🌐 代理连接失败(ProtocolError): {str(e)}, 重试次数: {retry_count}/{max_retries}, {wait_time}秒后重试')
                elif isinstance(e, (httpcore.ConnectTimeout, httpx.ConnectTimeout)):
                    logging.warning(f'🌐 连接超时({e.__class__.__name__}): {str(e)}, 重试次数: {retry_count}/{max_retries}, {wait_time}秒后重试')
                elif isinstance(e, (httpx.ReadTimeout, httpcore.ReadTimeout)):
                    logging.warning(f'🌐 读取超时({e.__class__.__name__}): {str(e)}, 重试次数: {retry_count}/{max_retries}, {wait_time}秒后重试')
                
                if retry_count >= max_retries:
                    logging.error(f'🔄 已达到最大重试次数({max_retries})，搜索推文失败')
                    return []
                await asyncio.sleep(wait_time)
            except (AccountSuspended, TooManyRequests, Unauthorized) as e:
                if isinstance(e, TooManyRequests):
                    logging.warning(f'🚫 账号【{self.account.email}】达到限流-429')
                elif isinstance(e, AccountSuspended):
                    logging.warning(f'🚫 账号【{self.account.email}】被暂停使用')
                elif isinstance(e, Unauthorized):
                    logging.warning(f'🚫 账号【{self.account.email}】未授权-401')
                await self._reinitialize_client(error_name=str(e.__class__.__name__), error_info=str(e), retry_count=0)
                return []
            except Exception as e:
                if "AttributeError: 'ClientTransaction' object has no attribute 'key'" in str(e):
                    logging.warning(f'🚫 账号【{self.account.email}】疑似封禁-AttributeError')
                    await self._reinitialize_client(error_name=str(e.__class__.__name__), error_info=str(e), retry_count=0)
                elif "Forbidden" in str(e) or "403" in str(e):
                    logging.warning(f'🚫 账号【{self.account.email}】账号被禁止访问-403')
                    await self._reinitialize_client(error_name=str(e.__class__.__name__), error_info=str(e), retry_count=0)
                else:
                    logging.error(f"❌ 搜索失败: {str(e)}")
                    raise Exception(f' 未预先处理的错误') from e
                return []

    async def _reinitialize_client(self, error_name: str, error_info: str, retry_count=0):
        """重新初始化客户端(更换账号)"""
        try:
            # 最大换号次数限制
            if retry_count >= 3:
                logging.error(f'🚫 已达到最大换号次数(3次)，无法继续获取新账号')
                raise Exception(f'❌ 已达到最大换号次数(3次)，无法继续获取新账号')
                
            await to_notify_account_error(self.account, error_name, error_info)
            logging.info(f'🔄 开始更换账号... (第{retry_count+1}次尝试)')
            
            # 释放旧账号(标记为不可用)
            await self.account_pool.release_account(self.account, False)

            # 获取新账号
            self.account = await self.account_pool.acquire()
            if not self.account:
                raise Exception(f'❌ 无法获取新账号')

            # 创建新客户端
            self.client = await self.client_manager.get_client(
                email=self.account.email,
                username=self.account.username,
                password=self.account.password,
                proxy=self.account.proxy
            )
            if not self.client:
                return await self._reinitialize_client(error_name='Twikit Client初始化为None', error_info="", retry_count=retry_count+1)
            else:
                # 更新当前协程的名字
                current_task = asyncio.current_task()
                if current_task:
                    original_name = current_task.get_name()
                    new_name = await self._task_counter.get_name(self.account.email.split('@')[0])
                    current_task.set_name(new_name)
                    logging.info(f'✅ 账号更换成功, 新账号: {self.account.email}, 协程名称更新为: {new_name}, 原协程名称: {original_name}')
                return True
        except Exception as e:
            logging.warning(f'🚫 账号【{self.account.email}】换号失败, 尝试继续换号, 错误信息: {str(e)}', exc_info=True)
            return await self._reinitialize_client(error_name=str(e.__class__.__name__), error_info=str(e.__traceback__), retry_count=retry_count+1)
