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
                proxy=self.account.proxy,
                totp_secret=self.account.totp_secret
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
            if len(self.token_list) < 10:
                self.token_list.append(token)
                return True
            return False

    async def run(self):
        """执行搜索任务"""
        try:
            await self.initialize_client()
            logging.info(f'🔛 搜索任务已启动, 使用账号: {self.account.email}')
            while True:
                # 1. 清理过期mint和token, 放在暂停前是为了不浪费时间
                if not self.client:
                    raise Exception(f'❌ 客户端初始化失败, 无法继续搜索')
                async with self.lock:
                    # 清理过期token
                    now = datetime.now()
                    valid_token_list = []
                    for token in self.token_list:
                        try:
                            # 检查是否过期并直接过滤
                            if (now - token["detect_time"]).total_seconds() < 580:
                                valid_token_list.append(token)
                        except Exception as e:
                            logging.error(f"❌ 清理超时CA失败: {str(e)}", exc_info=True)
                            logging.error(f"❌ 当前token_list: {self.token_list}")
                            logging.error(f"❌ 当前token: {token}")
                            # 出错时保留该token
                            valid_token_list.append(token)
                    self.token_list = valid_token_list
                await asyncio.sleep(20)
                # 2. 监控社交媒体数据
                async with self.lock:
                    await self._monitor_social_data()
                    if not self.token_list:
                        logging.info(f'🏁 搜索任务已完成, 释放账号: {self.account.email}')
                        await self.account_pool.release_account(self.account, True)
                        break
        except Exception as e:
            logging.error(f'❌ 搜索任务运行错误: {str(e)} 剩余Token已回滚到待处理队列')
            # 只传递原始token列表
            await self.on_error_callback(self.token_list)
            await self.account_pool.release_account(self.account, False)
        finally:
            await self.on_finish_callback(self, self.account.email)

    async def _monitor_social_data(self):
        """监控CA的推特帖子, 然后对有帖子的CA进行操作"""
        try:
            if not self.token_list:
                return []
            
            # 创建查找映射和集合，避免重复查询
            token_map = {token["mint"]: token for token in self.token_list}
            mint_set = set(token_map.keys())
            
            # 要删除的mint集合
            processed_mints = set()
            
            # 生成搜索关键字
            search_words = await _search_words_maker(list(mint_set))
            
            # 搜索帖子
            tweets = await self._search_tweets(str(search_words), "Latest")
            
            # 遍历搜索到的帖子
            for tweet in tweets:
                # 分离帖子中的ca
                tweet_mint_list = common_util.get_mint_in_tweet(tweet['text'])
                
                # 过滤出我们关心的且尚未处理的mint
                relevant_mints = [m for m in tweet_mint_list if m in mint_set and m not in processed_mints]
                
                if not relevant_mints:
                    continue
                    
                logging.info(f'🔍️ 当前搜索到的推特帖子内容为:\n【{tweet["text"]}】')
                
                # 一次处理一个推文中的所有相关mint
                for tweet_mint in relevant_mints:
                    data = token_map.get(tweet_mint)
                    
                    if not data:
                        logging.warning(f'⚠️ 未找到匹配的 token, CA: {tweet_mint}')
                        continue
                        
                    logging.debug(f'CA反搜索到的数据【{data}】')
                    
                    context = {
                        # 交易签名（唯一标识）
                        "signature": data["signature"],
                        # 代币合约地址
                        "mint": data["mint"],
                        # 交易者公钥
                        "traderPublicKey": data["traderPublicKey"],
                        # DEV创业次数
                        "entrepreneurial_attempts_count": data["entrepreneurial_attempts_count"],
                        # 相同代币符号数量
                        "symbol_count": data["symbol_count"],
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
                        "social": tweet  # 注意这里改为tweet而不是t
                    }
                    
                    await to_notify_token(context)
                    processed_mints.add(tweet_mint)
            
            # 批量删除已处理的tokens
            if processed_mints:
                self.token_list = [token for token in self.token_list 
                                  if token.get("mint") not in processed_mints]
                
        except Exception as e:
            logging.error(f"❌ 社交媒体数据获取失败: {str(e)}", exc_info=True)

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
                return False
                
            await to_notify_account_error(self.account, error_name, error_info)
            logging.info(f'🔄 开始更换账号... (第{retry_count+1}次尝试)')
            
            # 释放旧账号(标记为不可用)
            await self.account_pool.release_account(self.account, False)

            # 获取新账号
            self.account = await self.account_pool.acquire()
            if not self.account:
                return

            # 创建新客户端
            self.client = await self.client_manager.get_client(
                email=self.account.email,
                username=self.account.username,
                password=self.account.password,
                proxy=self.account.proxy,
                totp_secret=self.account.totp_secret
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
