import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

from twikit.client.client import Client

from src.utils.common_util import TaskCounter
from config import settings
from ...account.twitter import TwitterClientManager
from ...account.twitter.get_account import AccountPool
from ...notifier.dingtalk import DingTalkClient


async def _get_ca(tweet_text):
    # 正则表达式：匹配仅包含字母和数字的地址，假设长度在30到50之间
    pattern = r"\b[A-Za-z0-9]{30,50}\b"
    # 查找所有匹配项
    matches = re.findall(pattern, tweet_text)
    # 返回结果
    return matches


async def _search_words_maker(ca_list):
    search_words = ''
    for ca in ca_list:
        if search_words == '':
            search_words = search_words + ca
        else:
            search_words = search_words + ' or ' + ca
    return search_words


async def _trigger_actions(context: dict):
    logging.info(f"📢 准备钉钉通知。")
    """触发后续动作"""
    # 发送钉钉通知
    # 初始化客户端 (参数从配置读取)
    client = DingTalkClient(
        app_key=settings.DINGTALK['client_id'],
        app_secret=settings.DINGTALK['client_secret'],
    )
    logging.info(f"📢 钉钉客户端创建成功。")
    # 发送Markdown消息
    await client.send_message(
        msg_type="sampleMarkdown",
        content={
            "title": f"""🔔 新代币监控警报""",
            "text": f"""
### <font color="#2E86C1">📝 基础信息</font>

- **代币名称**: `{context['name']}`
- **代币符号**: `{context['symbol']}`
- **合约地址**: [{context['mint']}](solscan地址链接) 🔗

---

### <font color="#2E86C1">💹 资金动态</font>

- **初始投入**: <font color="green">{context['initialBuy']:.2f} SOL</font> 🌱
- **当前市值**: <font color="red">{context['marketCapSol']:.2f} SOL</font> 📉

---

### <font color="#2E86C1">📢 推特动态</font>

[🔗 原文链接](https://x.com/{context['social']['user']['screen_name']}/status/{context['social']['id']})  
├─ 📝 **内容**: {context['social']['text']}   
├─ ❤️ {context['social']['metrics']['likes']} 点赞  
├─ 🔄 {context['social']['metrics']['retweets']} 转发  
├─ 👁️ {context['social']['metrics']['view_count']} 浏览  
└─🕒 {context['social']['created_at']}  

👤 **用户信息**  
├─ 账号: @{context['social']['user']['screen_name']}  
└─认证: {'✅ 蓝V' if context['social']['user']['verified'] else '❌ 未认证'}  

---

<font color="gray">⏱️ 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>

"""
        })
    logging.info(f"📢 钉钉已通知。")


async def _process_token(context: dict):
    """代币处理流水线"""
    try:
        logging.info(f'🏃 开始处理代币{context}')
        # TODO 规则引擎评估
        # if self.rule_engine.evaluate(context):
        #     logging.info(f"🔥 检测到符合规则的代币: {context['address']}")
        #     await self._trigger_actions(context)

        # 暂时不走规则，直接钉钉通知
        await _trigger_actions(context)

    except Exception as e:
        logging.error(f"处理流水线异常: {context['address']} | {str(e)}")


async def search_tweets(client: Client, query: str, product: str, retries: int = 3) -> list:
    """
    异步搜索推文（带重试机制）
    :param client: 推特客户端
    :param query: 搜索关键词
    :param product: 搜索模式
    :param retries: 重试次数
    :return: 推文列表
    """
    for attempt in range(1, retries + 1):
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
                query, validated_product,
            )

            # 格式化结果
            return [
                {
                    "id": tweet.id,
                    "text": tweet.text,
                    "created_at": tweet.created_at_datetime,
                    "user": {
                        "name": tweet.user.name,
                        "screen_name": tweet.user.screen_name,
                        "verified": tweet.user.verified
                    },
                    "metrics": {
                        "likes": tweet.favorite_count,
                        "retweets": tweet.retweet_count,
                        "replies": tweet.reply_count,
                        "view_count": tweet.view_count
                    }
                }
                for tweet in search_result
            ]

        except Exception as e:
            if 'Rate limit exceeded' in str(e):
                logging.error(f'f"❌ 搜索失败，当前账号已达到速率限制！')
                return []
            if attempt == retries:
                raise RuntimeError(f"❌ 搜索失败: {query} ({str(e)})") from e

            retry_delay = min(2 ** attempt, 60)  # 指数退避上限60秒
            logging.warning(f"⚠️ 搜索请求失败: {query} | 第{attempt}次重试 ({retry_delay}s后)")
            await asyncio.sleep(retry_delay)

    return []  # 确保所有路径都有返回值


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
                            f'当前搜索任务已清空，销毁当前任务。ca_list：{len(self.ca_list)}-【{self.ca_list}】，token_list{len(self.token_list)}-【self.token_list】')
                        await self.account_pool.release(self.account, True)
                        break  # 退出循环，触发 finally 回调
        except Exception as e:
            logging.error(f'❌ 搜索任务协程在运行时发生错误【{e}】', exc_info=True)
            await self.account_pool.release(self.account, False)
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
            tweets = await search_tweets(self.client, str(search_words), "Latest")
            # 搜到帖子后就处理帖子
            if len(tweets) > 0:
                cas_set = set(current_ca_list)
                for t in tweets:
                    # 获取文本中的CA内容
                    tcas = await _get_ca(t['text'])
                    for tca in tcas:
                        logging.info(f'🔍️ 当前搜索到的推特帖子内容为【{t["text"]}】')
                        if tca in cas_set:
                            # 对于搜索到的CA帖子，返回格式化数据。
                            # 安全获取匹配项
                            matched_item = next(
                                (item for item in self.token_list
                                 if item.get("mint") == tca),
                                None  # 找不到时返回 None
                            )

                            if matched_item is None:
                                logging.warning(
                                    f'⚠️ 未找到匹配的 token，CA: {tca}，可能是一个CA有多个推文，在前一个推文触发时已将该CA移出列表。')
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
                                    # 交易类型（create/swap等）
                                    "txType": data["txType"],
                                    # 初始购买金额（SOL）
                                    "initialBuy": data["initialBuy"],
                                    # 当前交易SOL金额
                                    "solAmount": data["solAmount"],
                                    # 绑定曲线公钥
                                    "bondingCurveKey": data["bondingCurveKey"],
                                    # 绑定曲线中的代币总量
                                    "vTokensInBondingCurve": data["vTokensInBondingCurve"],
                                    # 绑定曲线中的SOL总量
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
                                    # 社交媒体数据（异步获取）
                                    "social": t
                                }
                                logging.info(f"📺 CA[{tca}]，捕获推文: {t['text']}")
                                # 处理搜索到帖子的CA
                                await _process_token(context)
                                # 删除已处理的CA
                                if tca in remaining_ca:
                                    remaining_ca.remove(tca)
                                    # 删除已处理的token信息
                                    self.token_list = [item for item in self.token_list if item.get("mint") != tca]
                        else:
                            logging.warning(f"⚠️ 当前推特中的CA【{tca}】不在CA监控名单中，请检查程序逻辑！")
            else:
                logging.info(f'🈚️ 当前搜索任务中所有CA都没有相关推文，CA列表：【{current_ca_list}】')
            return remaining_ca
        except Exception as e:
            logging.error(f"❌ 社交媒体数据获取失败: {str(e)}", exc_info=True)
            return remaining_ca
