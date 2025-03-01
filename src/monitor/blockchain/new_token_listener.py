# src/blockchain/new_token_listener.py（增强版）
import asyncio
import websockets
import json
import logging
from src.utils import TaskCounter


async def _subscribe(ws):
    """发送订阅请求"""
    await ws.send(json.dumps({
        "method": "subscribeNewToken"
    }))


class NewTokenListener:
    """区块链实时监听器"""

    def __init__(self, ws_url: str):
        self._task_counter = TaskCounter()
        self.ws_url = ws_url
        self._callback = None
        self._running = False
        self.logger = logging.getLogger(__name__)

    def set_callback(self, callback):
        self.logger.debug('NewTokenListener开始设置回调用函数')
        """设置异步回调函数"""
        self._callback = callback
        self.logger.debug('NewTokenListener设置回调用函数完毕')

    async def start_listening(self):
        """启动带智能重连的监听"""
        self._running = True
        retry_delay = 1

        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    # 重置连接延迟
                    retry_delay = 1
                    # 阻塞，等待订阅
                    await _subscribe(ws)
                    async for message in ws:
                        if not self._running:
                            return
                        if self._callback:
                            # 监听到新代币立即创建异步任务，去处理新代币
                            task_name = await self._task_counter.get_name('H_N_T')
                            asyncio.create_task(
                                self._callback(message),
                                name=task_name
                            )
            except Exception as e:
                self.logger.warning(f"⚠️ 连接异常: {e}，{retry_delay}s后重连...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # 指数退避

    def stop(self):
        """停止监听"""
        self._running = False
