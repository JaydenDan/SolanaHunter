import asyncio
import logging
from datetime import datetime

from config.config_loader import get_config
from src.account.twitter.get_account import AccountPool
from .task import SearchTask
from src.utils.common_util import TaskCounter


class SearchTaskManager:
    def __init__(self):
        self.search_tasks = []
        self.manager_lock = asyncio.Lock()

        # 新增以下状态管理
        self._pending_token = []  # CA等待队列
        self._is_creating_task = False  # 创建状态锁
        self._pending_lock = asyncio.Lock()  # CA队列操作锁
        self._task_counter = TaskCounter()
        self.account_pool = AccountPool(get_config('TWITTER.account_file_path'))

    # 处理新代币
    async def add_new_token(self, token):
        """
        处理新代币：
        1. 尝试添加到现有任务
        2. 如果无法添加, 则加入待处理队列
        3. 如果当前没有正在创建的任务, 则触发新任务创建
        """
        # 尝试添加到现有任务
        async with self.manager_lock:
            for task in self.search_tasks:
                if await task.add_token(token):
                    logging.info(f'✅ Token【{token["mint"]}】已添加到现有搜索任务, 监听时间: {token["detect_time"]}')
                    return
        # 无法添加到现有任务, 加入待处理队列
        async with self._pending_lock:
            self._pending_token.append(token)
            pending_token_length = len(self._pending_token)
        # 如果没有正在创建的任务, 则触发新任务创建
        if not self._is_creating_task:
            logging.info(f'🟢 Token【{token["mint"]}】触发新任务创建 (当前队列长度: {pending_token_length})')
            self._is_creating_task = True
            # 使用create_task避免阻塞当前方法
            task_name = await self._task_counter.get_name("创建搜索任务")
            asyncio.create_task(self._create_new_task_with_retry(), name=task_name)
        else:
            logging.info(f'📋 Token【{token["mint"]}】已添加到等待队列 (当前队列长度: {pending_token_length}, 正在创建任务中)...')

    async def _create_new_task_with_retry(self):
        """
        创建新的搜索任务：
        1. 从待处理队列中获取最多10个Token
        2. 获取账号, 创建任务对象
        3. 将Token添加到新任务中
        4. 处理未能添加的Token(回滚到待处理队列)
        5. 启动新任务
        """
        try:
            # 从待处理队列中获取最多10个CA
            batch = []
            async with self._pending_lock:
                # 获取前10个CA
                batch = self._pending_token[:10]
                # 从待处理队列中移除这些CA
                self._pending_token = self._pending_token[10:]
            
            batch_size = len(batch)
            if batch_size == 0:
                logging.warning(f'⚠️ 待处理队列为空, 取消创建新任务')
                async with self._pending_lock:
                    self._is_creating_task = False
                return
            
            logging.info(f'🔄 开始处理待处理队列中的 {batch_size} 个CA')
            
            # 获取账号

            account = await self.account_pool.acquire()
            
            if not account:
                logging.error("❌ 无法获取账号, 回滚CA到待处理队列")
                # 回滚CA到待处理队列
                await self.recover_token(batch)
                # 重置创建状态标志
                async with self._pending_lock:
                    self._is_creating_task = False
                return
            
            logging.info(f'✅ 已获取账号: {account.email}')
            
            # 创建新任务对象
            new_task = SearchTask(get_config('TWITTER'), self.remove_task, self.recover_token, account)
            
            # 将CA添加到新任务中
            token_added = []
            token_add_failed = []
            
            for token in batch:
                if len(new_task.mint_list) < 10:
                    # 添加到新任务
                    new_task.mint_list.append(token["mint"])
                    new_task.token_list.append({
                        "mint": token['mint'],
                        "token": token,
                    })
                    token_added.append(token)
                else:
                    # 任务已满, 剩余的CA加入失败列表, 理论上不会发生
                    token_add_failed.append(token)
            
            # 处理未能添加的CA, 理论上不会发生
            if token_add_failed:
                await self.recover_token(token_add_failed)
                logging.info(f'⚠️ {len(token_add_failed)} 个Token无法添加到当前任务, 已回滚到待处理队列')
            
            # 如果没有成功添加任何CA, 则释放账号并返回, 理论上不会发生
            if not token_added:
                logging.warning(f'⚠️ 没有Token被添加到新任务, 释放账号并取消创建')
                await self.account_pool.release_account(account, True)
                # 重置创建状态标志
                async with self._pending_lock:
                    self._is_creating_task = False
                return
            
            # 启动新任务
            try:
                # 获取任务名称, 只取@符号前的部分
                task_name = await self._task_counter.get_name(account.email.split('@')[0])
                # 创建异步任务
                asyncio.create_task(new_task.run(), name=task_name)
                # 将新任务添加到任务列表
                async with self.manager_lock:
                    self.search_tasks.append(new_task)
                logging.info(f'✅ 已创建并启动新任务【{task_name}】, 成功加载 {len(token_added)}/{batch_size} 个Token')
            except Exception as e:
                logging.error(f'❌ 启动搜索任务失败：{e}', exc_info=True)
                # 回滚已添加的CA
                await self.recover_token(token_added)
                # 释放账号
                await self.account_pool.release_account(account, False)
        except Exception as e:
            logging.error(f"❌ 任务创建过程发生错误: {e}", exc_info=True)
            # 确保回滚所有Token
            if 'batch' in locals():
                await self.recover_token(batch)
        finally:
            # 重置创建状态标志
            async with self.manager_lock:
                self._is_creating_task = False
            # 检查是否还有待处理的Token, 等待下一个新代币触发
            async with self._pending_lock:
                if self._pending_token:
                    token_count = len(self._pending_token)
                    logging.info(f'📝 等待队列中还有 {token_count} 个Token待处理, 等待下一个新代币触发创建')

    async def recover_token(self, token_to_recover):
        """恢复Token到等待队列"""
        async with self._pending_lock:
            self._pending_token = token_to_recover + self._pending_token

    async def remove_task(self, task_to_remove, task_email):
        try:
            self.search_tasks.remove(task_to_remove)
            logging.info(f'📴 已关闭搜索协程【{task_email}】')
        except ValueError:
            logging.warning(f'⚠️ 尝试移除不存在的任务: {task_to_remove}')

    async def recycle_token(self, token_to_recycle):
        """回收CA到等待列表"""
        async with self._pending_lock:
            self._pending_token_list = token_to_recycle + self._pending_token_list

