from typing import Optional, Union, List
import logging
import discord
import asyncio

from aiohttp_socks import ProxyConnector
from discord.ext import commands

from config import settings


class DiscordBot:
    _instance: Optional["DiscordBot"] = None
    _lock = asyncio.Lock()
    _connector: Optional[ProxyConnector] = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.bot: Optional[commands.Bot] = None
        self._task: Optional[asyncio.Task] = None
        self._initialized = False

    async def init_bot(self) -> None:
        """异步初始化机器人（2.x规范）"""
        if self._initialized:
            return

        # 代理配置
        proxy_url = settings.DISCORD.get("proxy")
        if proxy_url:
            try:
                self._connector = ProxyConnector.from_url(
                    proxy_url,
                    enable_cleanup_closed=True  # 自动清理关闭连接
                )
            except ValueError as e:
                logging.error(f"❌ Discord代理配置错误: {e}")
                raise

        # 意图配置（2.x必须显式声明）
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True

        # 机器人实例化
        self.bot = commands.Bot(
            command_prefix=settings.DISCORD.get("prefix", "!"),
            intents=intents,
            connector=self._connector,
            # 2.x优化参数
            chunk_guilds_at_startup=False,
            max_messages=None  # 禁用消息缓存
        )

        # 事件监听
        @self.bot.event
        async def on_connect():
            logging.info("⌛ 正在连接Discord...")

        @self.bot.event
        async def on_ready():
            logging.info(f"✅ Discord机器人已就绪")

        # 安全启动流程
        try:
            self._task = asyncio.create_task(self._run_bot(), name="DiscordBot")
            await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60)
            self._initialized = True
        except asyncio.TimeoutError:
            logging.error("❌ Discord机器人启动超时")
            raise
        except discord.PrivilegedIntents as e:
            logging.critical(f"❌ Discord权限不足: {e}")
            raise

    async def _run_bot(self) -> None:
        """独立运行任务（带异常处理）"""
        try:
            await self.bot.start(settings.DISCORD["token"])
        except discord.LoginFailure:
            logging.critical("❌ Discord登录失败，请检查token或代理")
            self._initialized = False
            raise
        except Exception as e:
            logging.error(f"❌ Discord运行错误: {str(e)}")
            self._initialized = False
            raise

    async def send_message(
            self,
            channel_id: int,
            message: Optional[str] = None,
            embed: Optional[Union[discord.Embed, List[discord.Embed]]] = None
    ):
        """发送消息（最多重试3次）"""
        if not self.bot:
            raise RuntimeError("❌ Discord机器人未初始化")

        async with self._lock:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logging.error(f"❌ Discord频道未找到: {channel_id}")
                return

            # 内容预处理
            content = message[:2000] if message else None
            embeds = []
            if embed:
                embeds = [embed] if isinstance(embed, discord.Embed) else embed
            embeds = embeds[:10]  # 强制截断

            # 重试逻辑（仅包裹发送步骤）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await channel.send(content=content, embeds=embeds)
                    break  # 发送成功则退出循环
                except ConnectionResetError as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"⚠️ Discord消息发送失败，重试中 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(1)  # 固定间隔1秒
                    else:
                        logging.error(f"❌ Discord消息发送失败: {str(e)}")
                        raise  # 重试用尽后抛出原始异常

    async def close(self) -> None:
        """安全关闭（2.x最佳实践）"""
        if not self._initialized:
            return

        if self.bot and self.bot.is_ready():
            # 清理命令树（2.x需要显式清理）
            if hasattr(self.bot, "tree"):
                self.bot.tree.clear_commands(guild=None)

            await self.bot.close()
            logging.info("✅ Discord连接已关闭")

        if self._connector:
            await self._connector.close()

        self._initialized = False

    async def send_account_error(
            self,
            account,
            error_info: str,
            stack_trace: Optional[str] = None
    ) -> None:
        """
        推送账号错误消息到Discord
        :param account: Twitter账号对象
        :param error_info: 错误信息
        :param stack_trace: 堆栈跟踪信息（可选）
        """
        if not self.bot:
            raise RuntimeError("❌ Discord 机器人未初始化！请先调用 init_bot()")

        # 创建一个红色的embed
        embed = discord.Embed(
            title="🚨 Twitter账号异常警报",
            description=error_info,
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        # 添加账号信息
        embed.add_field(
            name="📧 账号信息",
            value=f"```\n"
                  f"邮箱: {account.email}\n"
                  f"用户名: {account.username}\n"
                  f"代理: {account.proxy.split(':')[0]}:{account.proxy.split(':')[1]}\n"
                  f"```",
            inline=False
        )

        if stack_trace:
            # 如果传入的是traceback对象，将其转换为字符串
            if hasattr(stack_trace, 'format'):
                import traceback
                stack_trace = str(stack_trace).split('\n')[-1]
            else:
                stack_trace = str(stack_trace).split('\n')[-1]
            
            embed.add_field(
                name="🔍 错误详情", 
                value=f"```python\n{stack_trace}\n```",
                inline=False
            )

        # 添加时间戳和页脚
        embed.set_footer(text="发生时间: " + discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

        # 发送消息
        await self.send_message(settings.DISCORD['channel']['system_channel'], embed=embed)

    