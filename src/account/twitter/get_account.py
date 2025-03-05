import asyncio
import logging
from typing import Optional, List
from datetime import datetime
import os
import time

import discord
import httpcore
import httpx
import pandas as pd
from dataclasses import dataclass

from socksio import ProtocolError
from config import settings
from src.notifier.discord.bot import DiscordBot
from src.account.twitter.get_client import TwitterClientManager
from twikit import AccountSuspended


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
        self._file_monitor_task = None
        self._last_modified_time = os.path.getmtime(excel_path)
        self._start_maintenance_coroutine()
        self._start_file_monitor()
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
        # 正向循环（从前往后）
        # for _, row in df.iterrows():
        #     account = TwitterAccount(
        #         email=row['email'],
        #         username=row['username'],
        #         password=row['password'],
        #         proxy=row['residential_proxy'],
        #     )
        #     self._accounts.append(account)

    async def reload_accounts(self) -> bool:
        """
        热更新账户数据，保证：
        1. 线程安全：使用锁确保原子性
        2. 状态保持：保持现有账户状态
        3. 账户管理：添加新账户，移除不存在账户
        4. 错误处理：完整的异常处理和日志
        """
        try:
            # 确保线程安全
            async with self._lock:
                logging.info("🔄 开始热更新账户数据...")
                
                # 读取新的Excel文件
                try:
                    df = pd.read_excel(self.excel_path)
                except Exception as e:
                    logging.error(f"❌ 读取Excel文件失败: {str(e)}")
                    return False
                
                # 创建邮箱到账户的映射，保存现有状态
                existing_accounts = {acc.email: acc for acc in self._accounts}
                new_accounts = []
                new_emails = set()
                
                # 统计数据
                added_count = 0
                updated_count = 0
                removed_count = 0
                
                # 处理每个账户
                for _, row in df.iterrows():
                    email = row['email']
                    new_emails.add(email)
                    
                    if email in existing_accounts:
                        # 保持现有账户状态
                        account = existing_accounts[email]
                        # 检查每个字段的变化
                        changes = []
                        
                        if account.username != row['username']:
                            changes.append(f"用户名: {account.username} -> {row['username']}")
                            account.username = row['username']
                        
                        if account.password != row['password']:
                            changes.append(f"密码: {account.password} -> {row['password']}")
                            account.password = row['password']
                        
                        if account.proxy != row['residential_proxy']:
                            changes.append(f"代理: {account.proxy} -> {row['residential_proxy']}")
                            account.proxy = row['residential_proxy']
                        
                        if changes:
                            # 如果账户正在使用中，记录警告
                            status = []
                            if account.in_use:
                                status.append("使用中")
                            if account.disabled:
                                status.append("已禁用")
                            if not account.in_use and not account.disabled:
                                status.append("空闲")
                            status_str = f"({', '.join(status)})" if status else "未知状态"

                            if account.in_use:
                                log_lines = ["⚠️ 更新账户【%s】%s:" % (email, status_str)]
                            else:
                                log_lines = ["📝 更新账户【%s】%s:" % (email, status_str)]
                            
                            # 记录每个变更的字段
                            for i, change in enumerate(changes):
                                if i == len(changes) - 1:  # 最后一个变更
                                    log_lines.append("                                                                                                    └─ %s" % change)
                                else:
                                    log_lines.append("                                                                                                    ├─ %s" % change)
                            
                            # 合并为单条日志
                            if account.in_use:
                                logging.warning("\n".join(log_lines))
                            else:
                                logging.info("\n".join(log_lines))
                            
                            updated_count += 1
                            
                        new_accounts.append(account)
                    else:
                        # 添加新账户
                        new_account = TwitterAccount(
                            email=email,
                            username=row['username'],
                            password=row['password'],
                            proxy=row['residential_proxy']
                        )
                        new_accounts.append(new_account)
                        added_count += 1
                        logging.info(
                            "➕ 新增账户【%s】(空闲):\n"
                            "                                                                                                    ├─ 用户名: %s\n"
                            "                                                                                                    ├─ 密码: %s\n"
                            "                                                                                                    └─ 代理: %s",
                            email, row['username'], row['password'], row['residential_proxy']
                        )
                
                # 计算被移除的账户
                removed_accounts = set(existing_accounts.keys()) - new_emails
                removed_count = len(removed_accounts)
                
                # 记录被移除的账户信息
                for email in removed_accounts:
                    account = existing_accounts[email]
                    status = []
                    if account.in_use:
                        status.append("使用中")
                    if account.disabled:
                        status.append("已禁用")
                    if not account.in_use and not account.disabled:
                        status.append("空闲")
                    status_str = f"({', '.join(status)})" if status else "未知状态"
                    
                    logging.info(
                        "➖ 移除账户【%s】%s:\n"
                        "                                                                                                    ├─ 用户名: %s\n"
                        "                                                                                                    ├─ 密码: %s\n"
                        "                                                                                                    └─ 代理: %s",
                        email, status_str, account.username, account.password, account.proxy
                    )
                    
                    if account.in_use:
                        logging.warning("⚠️ 注意：移除的账户【%s】正在使用中！", email)
                
                # 更新账户列表
                self._accounts = new_accounts
                
                # 记录更新摘要
                logging.info(
                    "✅ Excel账户热更新完成！\n"
                    "📊 更新统计:\n"
                    "                                                                                                    ├─ 新增账户: %d\n"
                    "                                                                                                    ├─ 更新账户: %d\n"
                    "                                                                                                    ├─ 移除账户: %d\n"
                    "                                                                                                    ├─ 当前总数: %d\n"
                    "                                                                                                    ├─ 不可用数: %d\n"
                    "                                                                                                    └─ 使用中数: %d",
                    added_count, updated_count, removed_count,
                    len(self._accounts),
                    sum(1 for acc in self._accounts if acc.disabled),
                    sum(1 for acc in self._accounts if acc.in_use)
                )
                return True
        except Exception as e:
            logging.error(f"❌ 账户热更新失败: {str(e)}", exc_info=True)
            return False

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
            self._maintenance_task = asyncio.create_task(self._account_maintenance_loop(), name="账号池维护任务")
            logging.info("✅ 账号维护协程已启动")

    def _start_file_monitor(self):
        """启动文件监控协程"""
        if not self._file_monitor_task:
            self._file_monitor_task = asyncio.create_task(self._monitor_excel_file(), name="账号池Excel监控任务")
            logging.info("✅ 账号池Excel文件监控协程已启动")

    async def _monitor_excel_file(self):
        """监控Excel文件变化的协程"""
        while True:
            try:
                # 检查文件是否存在
                if not os.path.exists(self.excel_path):
                    logging.error(f"❌ Excel文件不存在: {self.excel_path}")
                    await asyncio.sleep(5)
                    continue

                # 获取文件最后修改时间
                current_mtime = os.path.getmtime(self.excel_path)

                # 如果文件被修改
                if current_mtime > self._last_modified_time:
                    logging.info("📝 检测到Excel文件发生变化，准备更新账号池...")
                    # 等待文件写入完成
                    await asyncio.sleep(1)
                    # 更新账号池
                    if await self.reload_accounts():
                        self._last_modified_time = current_mtime
                        logging.info("✅ 账号池已自动更新完成")
                    else:
                        logging.error("❌ 账号池自动更新失败")

                # 每5秒检查一次
                await asyncio.sleep(5)

            except Exception as e:
                logging.error(f"❌ 监控Excel文件时发生错误: {str(e)}", exc_info=True)
                await asyncio.sleep(5)  # 发生错误后等待5秒再继续

    async def _test_account(self, account: TwitterAccount) -> bool:
        """
        测试账号是否可用
        :param account: Twitter账号对象
        :return: 测试是否通过
        """
        max_retries = 3
        base_delay = 2

        for attempt in range(max_retries):
            try:
                # 获取客户端并尝试登录
                client = await self.client_manager.get_client(
                    email=account.email,
                    username=account.username,
                    password=account.password,
                    proxy=account.proxy
                )
                if client is None:
                    logging.error(f"❌ 账号【{account.email}】获取Twikit Client失败")
                    return False
                # 尝试执行一次搜索操作
                await client.search_tweet("elon", "Latest")
                logging.info(f"✅ 账号【{account.email}】测试通过")
                return True
            except AccountSuspended:
                logging.warning(f"❌ 账号【{account.email}】仍然超速，等待维护检查！")
                return False
            except (ProtocolError, httpx.ConnectError, httpcore.ConnectError, httpcore.ConnectTimeout, httpx.ConnectTimeout, httpx.ReadTimeout, httpcore.ReadTimeout) as e:
                # 根据异常类型输出不同的错误信息
                if isinstance(e, ProtocolError):
                    error_type = "代理协议"
                    error_detail = f"代理连接失败（ProtocolError）: {str(e)}"
                elif isinstance(e, (httpx.ConnectTimeout, httpcore.ConnectTimeout)):
                    error_type = "连接超时"
                    error_detail = f"连接超时（{e.__class__.__name__}）: {str(e)}"
                elif isinstance(e, (httpx.ConnectError, httpcore.ConnectError)):
                    error_type = "网络连接"
                    error_detail = f"网络连接失败（{e.__class__.__name__}）: {str(e)}"
                elif isinstance(e, (httpx.ReadTimeout, httpcore.ReadTimeout)):
                    error_type = "读取超时"
                    error_detail = f"读取超时（{e.__class__.__name__}）: {str(e)}" 
                else:
                    error_type = "网络连接"
                    error_detail = f"网络连接失败（{e.__class__.__name__}）: {str(e)}"
                
                if attempt < max_retries - 1:
                    retry_delay = base_delay * (attempt + 1)
                    logging.warning(f"❌ {error_type}错误，第 {attempt + 1} 次重试 ({retry_delay}秒后): {error_detail}")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    logging.error(f"❌ {error_type}错误，重试 {max_retries} 次后仍然失败: {error_detail}")
                    return False
            except Exception as e:
                if "You'll need to wait before trying to log in again. Some blocks are removed automatically." in str(e):
                    logging.warning(f"❌ 账号【{account.email}】账户暂时被锁定，等待维护检查！\n{str(e)}")    
                    return False
                logging.error(f"❌ 账号【{account.email}】获取Twikit Client失败: {str(e)}", exc_info=True)
                return False

    async def close(self):
        """关闭账号池，停止所有任务"""
        logging.info("📴 开始关闭账号池任务...")
        
        # 关闭维护任务
        if self._maintenance_task and not self._maintenance_task.done():
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                logging.info("✅ 账号池维护任务已停止")
            except Exception as e:
                logging.error(f"❌ 停止账号池维护任务时发生错误: {str(e)}")
            finally:
                self._maintenance_task = None

        # 关闭文件监控任务
        if self._file_monitor_task and not self._file_monitor_task.done():
            self._file_monitor_task.cancel()
            try:
                await self._file_monitor_task
            except asyncio.CancelledError:
                logging.info("✅ 账号池Excel监控任务已停止")
            except Exception as e:
                logging.error(f"❌ 停止账号池Excel监控任务时发生错误: {str(e)}")
            finally:
                self._file_monitor_task = None

        logging.info("✅ 账号池所有任务已关闭")
