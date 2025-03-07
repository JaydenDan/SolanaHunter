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
        self._interaction_handler_registered = False

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
            
        # 添加交互事件处理器（只注册一次）
        if not self._interaction_handler_registered:
            @self.bot.event
            async def on_interaction(interaction: discord.Interaction):
                if interaction.type == discord.InteractionType.component:
                    custom_id = interaction.data.get("custom_id", "")
                    # 处理查看交易发起人完整地址
                    if custom_id.startswith("view_address_"):
                        address = custom_id.replace("view_address_", "")
                        # 回复一个临时消息（只有点击的用户可见）
                        await interaction.response.send_message(
                            f"{address}", 
                            ephemeral=True  # 只有交互用户可见
                        )
                    # 处理复制代币地址
                    elif custom_id.startswith("copy_token_"):
                        token_address = custom_id.replace("copy_token_", "")
                        await interaction.response.send_message(
                            f"{token_address}", 
                            ephemeral=True  # 只有交互用户可见
                        )
            self._interaction_handler_registered = True

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
            embed: Optional[Union[discord.Embed, List[discord.Embed]]] = None,
            trader_address: Optional[str] = None,
            mint_address: Optional[str] = None
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
            
            # 创建交互视图
            view = None
            if trader_address or mint_address:
                view = discord.ui.View(timeout=None)
                
                # 添加代币地址复制按钮（如果提供了代币地址）
                if mint_address:
                    view.add_item(
                        discord.ui.Button(
                            label="复制代币地址",
                            style=discord.ButtonStyle.primary,  # 使用不同样式
                            custom_id=f"copy_token_{mint_address}"
                        )
                    )
                
                # 添加查看发起地址按钮（如果提供了交易者地址）
                if trader_address:
                    view.add_item(
                        discord.ui.Button(
                            label="查看完整发起地址",
                            style=discord.ButtonStyle.secondary,
                            custom_id=f"view_address_{trader_address}"
                        )
                    )

            # 重试逻辑（仅包裹发送步骤）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await channel.send(content=content, embeds=embeds, view=view)
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
            error_name: str,
            error_info: Optional[str] = None
    ) -> None:
        """
        推送账号错误消息到Discord
        :param account: Twitter账号对象
        :param error_name: 错误名称
        :param error_info: 错误信息 
        """
        if not self.bot:
            raise RuntimeError("❌ Discord 机器人未初始化！请先调用 init_bot()")

        # 创建一个红色的embed
        embed = discord.Embed(
            title="🚨 Twitter账号异常警报",
            description=error_name,
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

        if error_info:
            # 获取最后一行内容
            last_line = error_info.strip().split('\n')[-1]
            embed.add_field(
                name="🔍 错误详情", 
                value=f"```python\n{last_line}\n```",
                inline=False
            )

        # 添加时间戳和页脚
        embed.set_footer(text="发生时间: " + discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

        # 发送消息
        await self.send_message(settings.DISCORD['channel']['system_channel'], embed=embed)

    