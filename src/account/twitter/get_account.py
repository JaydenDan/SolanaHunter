import asyncio
import logging
import os
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
        self._last_modified_time = 0
        self._init_accounts()
        self._maintenance_task = None
        self._excel_check_task = None
        self._auxiliary_coroutine_running = True  # 控制协程运行的标志
        self._start_maintenance_coroutine()
        self._start_excel_check_coroutine()
        self._initialized = True

    def _init_accounts(self):
        """从Excel加载账户数据"""
        if os.path.exists(self.excel_path):
            self._last_modified_time = os.path.getmtime(self.excel_path)
            df = pd.read_excel(self.excel_path)
            # 清空现有账号列表
            self._accounts.clear()
            # 正向循环（从前往后）
            for _, row in df.iterrows():
                account = TwitterAccount(
                    email=row['email'],
                    username=row['username'],
                    password=row['password'],
                    proxy=row['residential_proxy'],
                )
                self._accounts.append(account)
            logging.info(f"📊 从Excel加载了 {len(self._accounts)} 个Twitter账号")
        else:
            logging.error(f"❌ Excel文件不存在: {self.excel_path}")

    async def reload_accounts(self):
        """重新加载Excel账户数据（热更新）"""
        async with self._lock:
            logging.info(f"🔄 开始热更新Excel账号数据: {self.excel_path}")
            
            # 保存当前账号信息，以email为key
            original_accounts = {}
            for acc in self._accounts:
                original_accounts[acc.email] = {
                    'username': acc.username,
                    'password': acc.password,
                    'proxy': acc.proxy,
                    'in_use': acc.in_use,
                    'disabled': acc.disabled
                }
            
            # 重新加载Excel数据
            df = pd.read_excel(self.excel_path)
            
            # 更新最后修改时间
            self._last_modified_time = os.path.getmtime(self.excel_path)
            
            # 清空并重建账号列表
            old_count = len(self._accounts)
            self._accounts.clear()
            
            # 记录新数据中的账号email集合
            new_emails = set()
            modified_accounts = []
            added_accounts = []
            
            # 加载新账号数据并保留原状态
            for _, row in df.iterrows():
                email = row['email']
                new_emails.add(email)
                
                account = TwitterAccount(
                    email=email,
                    username=row['username'],
                    password=row['password'],
                    proxy=row['residential_proxy'],
                )
                
                # 检查是否修改了账号信息
                if email in original_accounts:
                    original = original_accounts[email]
                    # 恢复账号状态
                    account.in_use = original['in_use']
                    account.disabled = original['disabled']
                    
                    # 检查是否有字段被修改
                    changes = []
                    if account.username != original['username']:
                        changes.append(f"用户名: {original['username']} -> {account.username}")
                    if account.password != original['password']:
                        changes.append(f"密码: {'*'*6} -> {'*'*6}")  # 不显示实际密码
                    if account.proxy != original['proxy']:
                        changes.append(f"代理: {original['proxy']} -> {account.proxy}")
                    
                    if changes:
                        modified_accounts.append((email, changes))
                else:
                    # 新增的账号
                    added_accounts.append(email)
                
                self._accounts.append(account)
            
            # 找出被删除的账号
            removed_accounts = set(original_accounts.keys()) - new_emails
            
            # 收集所有变更信息到一个统一的日志消息
            log_parts = []
            new_count = len(self._accounts)
            log_parts.append(f"✅ Excel账号热更新完成: 原有 {old_count} 个账号，现有 {new_count} 个账号")
            
            # 记录被修改的账号
            if modified_accounts:
                log_parts.append(f"\n📝 共有 {len(modified_accounts)} 个账号信息被修改:")
                for email, changes in modified_accounts:
                    change_log = ", ".join(changes)
                    log_parts.append(f"  🔄 账号 {email} 更新: {change_log}")
            
            # 记录新增的账号
            if added_accounts:
                log_parts.append(f"\n➕ 共有 {len(added_accounts)} 个新账号被添加:")
                for email in added_accounts:
                    log_parts.append(f"  ✨ 新增账号: {email}")
            
            # 记录删除的账号
            if removed_accounts:
                log_parts.append(f"\n➖ 共有 {len(removed_accounts)} 个账号被删除:")
                for email in removed_accounts:
                    log_parts.append(f"  🗑️ 删除账号: {email}")
                    
            # 一次性输出所有日志信息
            logging.info("\n".join(log_parts))
            
    async def _check_excel_changes(self):
        """检查Excel文件是否有变化并自动更新"""
        while self._auxiliary_coroutine_running:  # 使用_auxiliary_coroutine_running标志控制循环
            await asyncio.sleep(5)  # 每5秒检查一次
            try:
                if not os.path.exists(self.excel_path):
                    logging.warning(f"⚠️ Excel文件不存在: {self.excel_path}")
                    continue
                    
                current_modified_time = os.path.getmtime(self.excel_path)
                if current_modified_time > self._last_modified_time:
                    logging.info(f"🔄 检测到Excel文件变化，开始自动更新: {self.excel_path}")
                    await self.reload_accounts()
            except Exception as e:
                logging.error(f"❌ 检查Excel更新时发生错误: {str(e)}", exc_info=True)

    def _start_excel_check_coroutine(self):
        """启动Excel检查协程"""
        if not self._excel_check_task:
            self._excel_check_task = asyncio.create_task(self._check_excel_changes(), name="账号池Excel更新检查任务")
            logging.info("✅ 账号池Excel更新检查任务已启动")

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
        while self._auxiliary_coroutine_running:  # 使用_auxiliary_coroutine_running标志控制循环
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
                    # 检查是否已经停止运行
                    if not self._auxiliary_coroutine_running:
                        break
                        
                    logging.info(f"🔍 测试不可用账号: {account.email}")
                    if await self._test_account(account):
                        recovered_accounts.append(account)
                        logging.info(f"✅ 账号测试通过，将恢复可用: {account.email}")
                    else:
                        logging.info(f"❌ 账号仍不可用: {account.email}")

                # 如果有恢复的账号，更新主列表中对应账号的状态
                if recovered_accounts and self._auxiliary_coroutine_running:
                    async with self._lock:
                        for account in self._accounts:
                            if account in recovered_accounts:
                                account.disabled = False
                                logging.info(f"✅ 账号状态已更新为可用: {account.email}")

                # 发送状态报告
                if self._auxiliary_coroutine_running:
                    await self._send_status_report()
                
            except Exception as e:
                logging.error(f"❌ 账号维护过程发生错误: {str(e)}", exc_info=True)

    def _start_maintenance_coroutine(self):
        """启动账号维护协程"""
        if not self._maintenance_task:
            self._maintenance_task = asyncio.create_task(self._account_maintenance_loop(), name="账号维护任务")
            logging.info("✅ 账号维护任务已启动")

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
            except Exception as e:
                logging.warning(f"❌ 账号【{account.email}】搜索测试失败: {str(e)}")
                return False

    async def close(self):
        """关闭账号池，停止所有协程任务"""
        logging.info("🛑 开始关闭Twitter账号池...")
        
        # 设置运行标志为False，通知协程循环停止
        self._auxiliary_coroutine_running = False
        
        # 取消维护协程任务
        if self._maintenance_task and not self._maintenance_task.done():
            logging.info("🛑 正在关闭账号维护协程...")
            self._maintenance_task.cancel()
            try:
                await asyncio.wait_for(self._maintenance_task, timeout=5.0)
                logging.info("✅ 账号维护协程已关闭")
            except asyncio.TimeoutError:
                logging.warning("⚠️ 关闭账号维护协程超时")
            except asyncio.CancelledError:
                logging.info("✅ 账号维护协程已取消")
            except Exception as e:
                logging.error(f"❌ 关闭账号维护协程时发生错误: {str(e)}", exc_info=True)
        
        # 取消Excel检查协程任务
        if self._excel_check_task and not self._excel_check_task.done():
            logging.info("🛑 正在关闭Excel更新检查协程...")
            self._excel_check_task.cancel()
            try:
                await asyncio.wait_for(self._excel_check_task, timeout=5.0)
                logging.info("✅ Excel更新检查协程已关闭")
            except asyncio.TimeoutError:
                logging.warning("⚠️ 关闭Excel更新检查协程超时")
            except asyncio.CancelledError:
                logging.info("✅ Excel更新检查协程已取消")
            except Exception as e:
                logging.error(f"❌ 关闭Excel更新检查协程时发生错误: {str(e)}", exc_info=True)
        
        # 清空任务引用
        self._maintenance_task = None
        self._excel_check_task = None
        
        logging.info("✅ Twitter账号池辅助协程已成功关闭")
    