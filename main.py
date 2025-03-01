# main.py（最终正确版本）
import asyncio
import logging
from config import settings, logging_config
from src.monitor import MonitorCore


async def main():

    # 初始化日志系统（必须最先执行）
    logging_config.setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("✅ 日志系统启动初始化成功")

    logger.info("🟢 开始创建监控核心实例...")
    # 创建监控核心实例
    monitor = MonitorCore(
        blockchain_ws=settings.BLOCKCHAIN["websocket_url"],
        rule_path=settings.PROJECT_ROOT / "config/rules.yaml"
    )
    logger.info("✅ 创建监控核心实例完成...")

    try:
        # 启动监控系统（异步任务自动运行）
        logger.info("🟢 开始启动监控系统...")
        await monitor.start()
        logger.info("✅ 监控系统启动成功...")

        # 创建永久等待事件保持主循环运行
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        logger.info("🛑 接收到终止信号...")
        await monitor.stop()
        logger.info("🟢 系统安全关闭完成")


if __name__ == "__main__":
    asyncio.run(main())
    # TODO 账号在登录、搜索使用过程中，如果出现异常，不能直接结束任务，要换号继续操作。
    # TODO 钉钉需要单例Client
    # 接入其他推送平台

