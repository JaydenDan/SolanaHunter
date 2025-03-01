import asyncio
import logging
from datetime import datetime

from config import settings
from .task import SearchTask
from src.utils.common_util import TaskCounter


class SearchTaskManager:
    def __init__(self):
        self.search_tasks = []
        self.manager_lock = asyncio.Lock()

        # 新增以下状态管理
        self._pending_cas = []  # CA等待队列
        self._is_creating_task = False  # 创建状态锁
        self._pending_lock = asyncio.Lock()  # CA队列操作锁
        self._task_counter = TaskCounter()

    # 处理新代币
    async def add_new_token(self, token):
        async with self.manager_lock:
            # 尝试添加到现有任务
            for task in self.search_tasks:
                if await task.add_ca(token):
                    return
            # 所有搜索任务都已满，进入等待队列流程
            logging.info(f'🈵 当前所有搜索任务已满，已拒绝CA进入当前搜索任务协程...')
            async with self._pending_lock:
                # 如果不是正在创建新的search_task协程
                if not self._is_creating_task:
                    logging.info(f'🟢 当前CA【{token["mint"]}】正在创建新的search_task...')
                    # 第一个触发创建的CA在这会把task创建状态更新 确保状态被正确设置
                    self._is_creating_task = True
                    # 把第一个来创建task的token放到等待数组中
                    self._pending_cas.append(token)
                    task_name = await self._task_counter.get_name('S_T_No.')
                    asyncio.create_task(
                        self._create_new_task_with_retry(),
                        name=task_name
                    )
                    logging.info(f'✅ 当前CA【{token["mint"]}】完成创建新的search_task...')
                else:
                    # 后续CA进入直接等待队列
                    logging.info(f'⌛️ 当前CA【{token["mint"]}】已进入等待队列...')
                    self._pending_cas.append(token)

    async def remove_task(self, task_to_remove):
        async with self.manager_lock:
            # 安全移除任务
            logging.info(f'📴 已关闭一个搜索协程【{task_to_remove}】')
            self.search_tasks = [task for task in self.search_tasks if task != task_to_remove]

    async def _create_new_task_with_retry(self):
        """新版带批量处理能力的任务创建"""
        try:
            # 批量提取CA（最多10个）
            async with self._pending_lock:
                batch = self._pending_cas[:10]  # 取前10个
                self._pending_cas = self._pending_cas[10:]  # 保留剩余
            # 创建并初始化任务
            new_task = SearchTask(settings.TWITTER, self.remove_task)
            # 原子批量添加 ca_added：已经添加的ca列表；ca_add_failed：添加失败的ca列表
            ca_added, ca_add_failed = [], []
            async with new_task.lock:
                for idx, token in enumerate(batch):
                    if len(new_task.ca_list) < 10:
                        # 添加ca，不用task的add_ca是因为会出现死锁，而且为了避免其他协程操作
                        new_task.ca_list.append(token["mint"])
                        new_task.token_list.append({
                            "mint": token['mint'],
                            "token": token,
                            "start_time": datetime.now()
                        })
                        ca_added.append(token)
                    else:
                        # 使用当前索引分割
                        ca_add_failed = batch[idx:]
                        logging.info(f'🈵 当前search_task已满，请回收未处理CA...')
                        break
                else:
                    # 所有CA都成功添加的情况
                    ca_add_failed = []
            logging.info(
                # f'🛩️ 已成功派发等待队列中的CA【{", ".join(str(ca["mint"]) for ca in ca_added)}】'
                f'🛩️ 已成功派发等待队列中的CA【{ca_added}】'
            )
            # 回滚未添加的CA
            if ca_add_failed:
                async with self._pending_lock:
                    self._pending_cas = ca_add_failed + self._pending_cas
                    logging.info(f'♻️ 已回收未处理的CA到等待队 列，当前CA等待队列【{self._pending_cas}】')
            # 将成功添加的任务加入列表
            async with self.manager_lock:
                if ca_added:
                    self.search_tasks.append(new_task)
                    logging.info(f'✅ 已创建新任务，成功加载{len(ca_added)}个CA')
                else:
                    logging.warning(f'⚠️ 创建了一个空的搜索任务，请检查')
        except Exception as e:
            logging.error(f"❌ 任务创建失败: {e}", exc_info=True)
            # 将失败的CA放回队列
            async with self._pending_lock:
                self._pending_cas = batch + self._pending_cas
        finally:
            async with self._pending_lock:
                self._is_creating_task = False  # 确保任务结束时重置标志
            # 级联触发处理剩余CA
            if self._pending_cas:
                logging.info(f'_pending_cas中任然有被阻塞的新CA：【{len(self._pending_cas)}】-【{self._pending_cas[:30]}】，开始处理')
                async with self._pending_lock:
                    self._is_creating_task = True  # 新增此行
                task_name = await self._task_counter.get_name('S_T_No.')
                asyncio.create_task(
                    self._create_new_task_with_retry(),
                    name=task_name
                )
