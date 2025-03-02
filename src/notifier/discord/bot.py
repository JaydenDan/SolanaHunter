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
                logging.info(f"✅ Proxy enabled: {proxy_url}")
            except ValueError as e:
                logging.error(f"❌ Proxy config error: {e}")
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
            logging.info("⌛ Connecting to Discord...")

        @self.bot.event
        async def on_ready():
            logging.info(f"✅ Discord 机器人已登录（通过代理）: {self.bot.user}")
            # 调试输出实际使用的出口IP
            try:
                resp = await self.bot.http._HTTPClient__session.get("https://api.ipify.org")
                ip = await resp.text()
                logging.info(f"📍 Discord Bot 出口 IP: {ip}")
            except Exception as e:
                logging.warning(f"❌ IP 检测失败: {str(e)}")

        # 安全启动流程
        try:
            self._task = asyncio.create_task(self._run_bot())
            await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60)
            self._initialized = True
        except asyncio.TimeoutError:
            logging.error("⌛ Bot startup timed out")
            raise
        except discord.PrivilegedIntents as e:
            logging.critical(f"❌ Missing privileged intents: {e}")
            raise

    async def _run_bot(self) -> None:
        """独立运行任务（带异常处理）"""
        try:
            await self.bot.start(settings.DISCORD["token"])
        except discord.LoginFailure:
            logging.critical("❌ Invalid token or proxy auth failed")
            self._initialized = False
            raise
        except Exception as e:
            logging.error(f"❌ Bot runtime error: {repr(e)}")
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
            raise RuntimeError("❌ Discord 机器人未初始化！请先调用 init_bot()")

        async with self._lock:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logging.info(f"⚠️ 频道 {channel_id} 未找到！")
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
                        logging.info(f"⚠️ 发送失败（{attempt + 1}/{max_retries}）: {e}，1秒后重试...")
                        await asyncio.sleep(1)  # 固定间隔1秒
                    else:
                        logging.info(f"❌ 最终发送失败: {e}")
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
            logging.info("🔌 Discord connection closed")

        if self._connector:
            await self._connector.close()
            logging.info("🔌 Proxy connector closed")

        self._initialized = False

    async def __aenter__(self):
        await self.init_bot()
        return self

    async def __aexit__(self, *exc):
        await self.close()
