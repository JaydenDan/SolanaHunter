# src/monitor/core.py（核心协调者）
import asyncio
import json
import logging
from pathlib import Path
from watchdog.observers import Observer
from .blockchain.new_token_listener import NewTokenListener
from .twitter.manager import SearchTaskManager as TwitterSearchTaskManager
from .rules.engine import RuleEngine
from .rules.conditions.handlers.file_watcher import RuleFileHandler
from ..utils import TaskCounter


class MonitorCore:
    """实时监控协调中枢"""

    def __init__(self, blockchain_ws: str, rule_path: Path):
        # 初始化组件
        self._task_counter = TaskCounter()
        self.listener = NewTokenListener(blockchain_ws)
        self.rule_engine = RuleEngine(rule_path)
        self.logger = logging.getLogger(__name__)
        self.task_manager = TwitterSearchTaskManager()

        # 新增任务跟踪器
        self._active_tasks = set()
        self._shutdown_initiated = asyncio.Event()

        # 文件监控配置
        self.observer = Observer()
        self.observer.schedule(
            RuleFileHandler(
                config_path=rule_path.parent,
                reload_callback=self.rule_engine.reload_rules
            ),
            path=str(rule_path.parent)
        )

        # 状态管理
        self._running = False

    def _track_task(self, task: asyncio.Task):
        """自动跟踪任务生命周期"""
        self._active_tasks.add(task)
        task.add_done_callback(lambda t: self._active_tasks.discard(t))

    async def start(self):
        """启动实时监控系统"""
        self._running = True

        # 启动文件监控（同步转异步）
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.observer.start)

        # 配置区块链监听回调
        self.listener.set_callback(self._handle_new_token)
        # 启动区块链监听（异步任务）
        task_name = await self._task_counter.get_name('CORE')
        asyncio.create_task(
            self.listener.start_listening(),
            name=task_name
        )
        logging.info("🚀 实时监控系统已启动")

    async def stop(self):
        """分阶段安全关闭（无超时）"""
        if not self._running:
            return

        self._shutdown_initiated.set()
        self.logger.info("🛑 关闭流程启动，停止接收新任务...")

        # 第一步：立即停止区块链监听
        self.listener.stop()
        self.logger.info("✅ 区块链监控已停止")

        # 第二步 等待现有任务完成
        while True:
            async with self.task_manager.manager_lock:
                active_count = len(self.task_manager.search_tasks)

            if active_count == 0:
                break

            self.logger.info(f"🕒 等待 {active_count} 个搜索任务结束...")
            await asyncio.sleep(1)

        # 第三步：清理基础设施
        self.logger.info("🛑 开始释放系统资源...")
        # await self._stop_file_watcher()
        # await self.task_manager.cleanup()
        self._running = False
        self.logger.info("✅ 系统完全关闭")

    async def _handle_new_token(self, message: str):
        """新代币事件处理入口"""
        try:
            # 处理订阅消息
            data = json.loads(message)
            # 系统消息处理（优先判断）
            if 'message' in data:
                self.logger.info(f'✅ 已成功订阅Token创建事件！')
                return
            # 数据消息处理
            elif 'signature' in data:
                self.logger.info(
                    f'💰 监听到新的代币：Name=【{data["name"]}】 | Symbol=【{data["symbol"]}】 | CA=【{data["mint"]}】'
                )
                # 1. 把新代币CA丢给search_task_manager
                await self.task_manager.add_new_token(data)
            else:
                self.logger.warning("⚠️ 未知消息格式: %s", data)
        except Exception as e:
            self.logger.error(f"❌ 事件处理失败: {str(e)}", exc_info=True)
