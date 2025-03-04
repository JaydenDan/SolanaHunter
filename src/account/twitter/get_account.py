import asyncio
import logging
from typing import Optional, List
from datetime import datetime

import discord
import pandas as pd
from dataclasses import dataclass
from config import settings
from src.notifier.discord.bot import DiscordBot
from src.account.twitter.get_client import TwitterClientManager


@dataclass
class TwitterAccount:
    email: str
    password: str
    username: str
    proxy: str
    in_use: bool = False
    disabled: bool = False


class AccountPool:
    _instance = None

    def __new__(cls, excel_path: str):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, excel_path: str):
        if self._initialized:
            return
        self.excel_path = excel_path
        self._accounts: List[TwitterAccount] = []  # 单一账户列表
        self._lock = asyncio.Lock()
        self.client_manager = TwitterClientManager()
        self._init_accounts()
        self._maintenance_task = None
        self._start_maintenance_coroutine()
        self._initialized = True

    def _init_accounts(self):
        """从Excel加载账户数据"""
        df = pd.read_excel(self.excel_path)
        for _, row in df.iloc[::-1].iterrows():
            account = TwitterAccount(
                email=row['email'],
                username=row['username'],
                password=row['password'],
                proxy=row['residential_proxy'],
            )
            self._accounts.append(account)

    async def acquire(self) -> Optional[TwitterAccount]:
        """获取可用账户"""
        async with self._lock:
            for account in self._accounts:
                if not account.in_use and not account.disabled:
                    account.in_use = True
                    logging.info(f'🧲 获取到Twitter账号【{account.email}】')
                    return account
            
            logging.error(f'🚨 没有可用的账号！')
            return None

    async def release_account(self, account: TwitterAccount, success: bool = True):
        """释放账户"""
        async with self._lock:
            account.in_use = False
            if not success:
                account.disabled = True
                logging.warning(f'⚠️ Twitter账号【{account.email}】已失效，等待维护检查！')
            else:
                logging.info(f'📥 已释放Twitter账号【{account.email}】')

    async def _send_status_report(self):
        """发送账号状态报告到Discord"""
        try:
            # 统计账号状态
            total_accounts = len(self._accounts)
            in_use = sum(1 for acc in self._accounts if acc.in_use)
            disabled = sum(1 for acc in self._accounts if acc.disabled)
            available = sum(1 for acc in self._accounts if not acc.in_use and not acc.disabled)

            # 创建概览embed
            discord_bot = DiscordBot()
            overview_embed = discord.Embed(
                title="📊 Twitter账号池状态报告",
                description=f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                color=discord.Color.blue()
            )

            overview_embed.add_field(
                name="📈 统计概览",
                value=f"```\n"
                      f"总账号数: {total_accounts}\n"
                      f"使用中: {in_use}\n"
                      f"不可用: {disabled}\n"
                      f"可用: {available}\n"
                      f"```",
                inline=False
            )

            # 发送概览信息
            await discord_bot.send_message(
                settings.DISCORD['channel']['system_channel'],
                embed=overview_embed
            )

            # 按状态分组处理账号详情（不包括可用账号）
            status_groups = {
                "🔴 不可用账号": [acc for acc in self._accounts if acc.disabled],
                "🟡 使用中账号": [acc for acc in self._accounts if acc.in_use]
            }

            # 分组发送账号详情
            for status_title, accounts in status_groups.items():
                if not accounts:
                    continue

                # 将账号分成更小的批次（每批最多5个账号）
                for i in range(0, len(accounts), 5):
                    batch = accounts[i:i + 5]
                    
                    details_embed = discord.Embed(
                        title=f"{status_title} ({i//5 + 1}/{(len(accounts) + 4)//5})",
                        color=discord.Color.blue()
                    )

                    for acc in batch:
                        # 简化每个账号的显示信息
                        details_embed.add_field(
                            name=f"📧 {acc.username}",
                            value=f"```\n"
                                  f"邮箱: {acc.email}\n"
                                  f"代理: {acc.proxy.split(':')[0]}:{acc.proxy.split(':')[1]}\n"
                                  f"```",
                            inline=False
                        )

                    await discord_bot.send_message(
                        settings.DISCORD['channel']['system_channel'],
                        embed=details_embed
                    )
                    # 添加短暂延迟避免触发Discord限制
                    await asyncio.sleep(1)

        except Exception as e:
            logging.error(f"❌ 发送状态报告失败: {str(e)}", exc_info=True)

    async def _account_maintenance_loop(self):
        """账号维护循环"""
        while True:
            await asyncio.sleep(600)  # 10分钟 = 600秒
            try:
                logging.info("🔄 开始账号维护检查...")
                
                # 获取需要检查的账号列表副本
                accounts_to_check = []
                async with self._lock:
                    # 只复制需要检查的不可用账号
                    accounts_to_check = [account for account in self._accounts if account.disabled]
                
                if not accounts_to_check:
                    logging.info("✅ 没有需要维护的账号")
                    await self._send_status_report()
                    continue

                # 在副本上进行维护检查
                recovered_accounts = []
                for account in accounts_to_check:
                    logging.info(f"🔍 测试不可用账号: {account.email}")
                    if await self._test_account(account):
                        recovered_accounts.append(account)
                        logging.info(f"✅ 账号测试通过，将恢复可用: {account.email}")
                    else:
                        logging.info(f"❌ 账号仍不可用: {account.email}")

                # 如果有恢复的账号，更新主列表中对应账号的状态
                if recovered_accounts:
                    async with self._lock:
                        for account in self._accounts:
                            if account in recovered_accounts:
                                account.disabled = False
                                logging.info(f"✅ 账号状态已更新为可用: {account.email}")

                # 发送状态报告
                await self._send_status_report()
                
            except Exception as e:
                logging.error(f"❌ 账号维护过程发生错误: {str(e)}", exc_info=True)

    async def health_check(self):
        """健康检查"""
        async with self._lock:
            # 仅用于检查账号状态，不再需要移除操作
            disabled_count = sum(1 for acc in self._accounts if acc.disabled)
            logging.info(f"健康检查: 总计{len(self._accounts)}个账号，{disabled_count}个不可用")

    def _start_maintenance_coroutine(self):
        """启动账号维护协程"""
        if not self._maintenance_task:
            self._maintenance_task = asyncio.create_task(self._account_maintenance_loop(), name="账号维护协程")
            logging.info("✅ 账号维护协程已启动")

    async def _test_account(self, account: TwitterAccount) -> bool: # 要改
        """
        测试账号是否可用
        :param account: Twitter账号对象
        :return: 测试是否通过
        """
        try:
            # 获取客户端并尝试登录
            client = await self.client_manager.get_client(
                email=account.email,
                username=account.username,
                password=account.password,
                proxy=account.proxy
            )

            # 尝试执行一次搜索操作
            try:
                await client.search_tweet("elon", "Latest")
                logging.info(f"✅ 账号【{account.email}】测试通过")
                return True
            except Exception as e:
                logging.warning(f"❌ 账号【{account.email}】搜索测试失败: {str(e)}", exc_info=True)
                return False

        except Exception as e:
            logging.error(f"❌ 账号【{account.email}】获取Twikit Client失败: {str(e)}", exc_info=True)
            return False
