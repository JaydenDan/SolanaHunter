import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from config import settings, logging_config
from src.monitor import MonitorCore


@asynccontextmanager
async def app_lifespan():
    """正确的异步生命周期管理器"""
    monitor = MonitorCore(
        blockchain_ws=settings.BLOCKCHAIN["websocket_url"],
        rule_path=settings.PROJECT_ROOT / "config/rules.yaml"
    )

    try:
        await monitor.start()
        logging.info("✅ 监控系统启动成功")
        yield monitor  # 交出控制权
    finally:
        logging.info("🛑 开始释放资源...")
        await monitor.stop()
        logging.info("✅ 资源释放完成")


async def main():
    logging_config.setup_logging()
    logging.getLogger('main')
    logging.info("✅ 日志系统启动初始化成功")

    shutdown_event = asyncio.Event()
    # 注册系统信号
    loop = asyncio.get_running_loop()
    # 仅非Windows系统注册信号处理
    if sys.platform != 'win32':
        logging.info("💻 当前系统环境为MacOS/Linux")
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_event.set)
    else:
        logging.info("🖥︎ 当前系统环境为Windows")
        # Windows下用signal.signal处理SIGINT
        signal.signal(signal.SIGINT, lambda s, f: shutdown_event.set())

    async with app_lifespan() as monitor:
        logging.info("🚀 服务进入运行状态")
        await shutdown_event.wait()  # 保持运行直到收到终止信号
        logging.info("🛬 开始关闭流程...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("👋 用户主动终止操作")
