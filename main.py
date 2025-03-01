import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from config import settings, logging_config
from src.monitor import MonitorCore


@asynccontextmanager
async def app_lifespan():
    """正确的异步生命周期管理器"""
    logging_config.setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("✅ 日志系统初始化完成")
    monitor = MonitorCore(
        blockchain_ws=settings.BLOCKCHAIN["websocket_url"],
        rule_path=settings.PROJECT_ROOT / "config/rules.yaml"
    )

    try:
        await monitor.start()
        logger.info("✅ 监控系统启动成功")
        yield monitor  # 交出控制权
    finally:
        logger.info("🛑 开始释放资源...")
        await monitor.stop()
        logger.info("✅ 资源释放完成")


async def main():
    shutdown_event = asyncio.Event()

    # 注册系统信号
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    async with app_lifespan() as monitor:
        logging.info("🚀 服务进入运行状态")
        await shutdown_event.wait()  # 保持运行直到收到终止信号
        logging.info("🛬 开始关闭流程...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("👋 用户主动终止操作")
