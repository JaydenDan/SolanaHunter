# src/monitor/core.py（核心协调者）
import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
from .blockchain.new_token_listener import NewTokenListener
from .rules import engine
from .twitter.manager import SearchTaskManager as TwitterSearchTaskManager
from ..notifier.discord.bot import DiscordBot
from ..utils import TaskCounter
from ..account.twitter.get_account import AccountPool


class MonitorCore:
    """实时监控协调中枢"""

    def __init__(self, blockchain_ws: str, rule_path: Path):
        # 初始化组件
        self._task_counter = TaskCounter()
        self.listener = NewTokenListener(blockchain_ws)
        logging.getLogger(__name__)
        self.task_manager = TwitterSearchTaskManager()

        self._shutdown_initiated = asyncio.Event()

        # 文件监控配置

        # 状态管理
        self._running = False

    async def start(self):
        """启动实时监控系统"""
        self._running = True

        # 配置区块链监听回调
        self.listener.set_callback(self._handle_new_token)
        # 启动区块链监听（异步任务）
        task_name = await self._task_counter.get_name('CORE')
        asyncio.create_task(
            self.listener.start_listening(),
            name=task_name
        )
        logging.info("✅ 实时监控系统已启动")

    async def stop(self):
        """分阶段安全关闭（无超时）"""
        if not self._running:
            return

        self._shutdown_initiated.set()
        logging.info("🛑 关闭流程启动，停止接收新任务...")

        # 第一步：立即停止区块链监听
        self.listener.stop()
        logging.info("🛑 区块链监控已停止")

        # 第二步: 关闭账号池辅助协程
        account_pool = AccountPool("----") # 单例模式，随便传入一个参数获取实例
        await account_pool.close()
        logging.info("🛑 账号池辅助协程已关闭")

        # 第二步 等待现有任务完成
        while True:
            async with self.task_manager.manager_lock:
                active_count = len(self.task_manager.search_tasks)

            if active_count == 0:
                break

            logging.info(f"🕒 等待 {active_count} 个搜索任务结束...")
            await asyncio.sleep(1)

        # 第三步：清理基础设施
        logging.info("🛑 开始释放系统资源...")
        # 关闭账号池任务
        account_pool = AccountPool("")  # 单例模式会返回已存在的实例
        await account_pool.close()
        
        bot = DiscordBot()
        await bot.close()
        logging.info(f"🛑 Discord Bot已关闭")
        # await self._stop_file_watcher()
        # await self.task_manager.cleanup()
        self._running = False
        logging.info("✅ 系统已经正确关闭")

    async def _handle_new_token(self, message: str):
        """新代币事件处理入口"""
        try:
            # 处理订阅消息
            data = json.loads(message)
            # 系统消息处理（优先判断）
            if 'message' in data:
                logging.info(f'✅ 已成功订阅Token创建事件！')
                return
            # 数据消息处理
            elif 'signature' in data:
                data['detect_time'] = datetime.now()
                logging.info(
                    f'💰 监听到新的代币：Name=【{data["name"]}】 | Symbol=【{data["symbol"]}】 | Mint=【{data["mint"]}】'
                )
                # AP, All Push, 规则引擎中判断是SaL还是HS (Has Score) 
                asyncio.create_task(
                    engine.notify_process_all_push(data),
                    name='All_Push_' + data['symbol']
                )
                await self.task_manager.add_new_token(data)
            else:
                logging.warning("⚠️ 未知消息格式: %s", data)
        except Exception as e:
            logging.error(f"❌ 事件处理失败: {str(e)}", exc_info=True)
