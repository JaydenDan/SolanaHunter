import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from config import settings, logging_config
from src.monitor import MonitorCore
from src.notifier.discord.bot import DiscordBot


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
    # 初始化日志
    logging_config.setup_logging()
    logging.getLogger('main')
    logging.info("✅ 日志系统启动初始化成功")

    # 初始化机器人
    bot = DiscordBot()
    try:
        await bot.init_bot()  # 确保初始化完成
    except Exception as e:
        logging.error(f"❌ 机器人初始化失败：{e}")
        return

    shutdown_event = asyncio.Event()
    # 注册系统信号
    loop = asyncio.get_running_loop()
    # 仅非Windows系统注册信号处理
    if sys.platform != 'win32':
        logging.info("💻 当前系统环境为MacOS/Linux")
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_event.set)
    else:
        logging.info("🖥 当前系统环境为Windows")
        # Windows下用signal.signal处理SIGINT
        signal.signal(signal.SIGINT, lambda s, f: shutdown_event.set())

    async with app_lifespan() as monitor:
        logging.info("🚀 所有组件启动 启动 启动～")
        await shutdown_event.wait()  # 保持运行直到收到终止信号
        logging.info("🛬 开始关闭流程...")


if __name__ == "__main__":
    # TODO 完成embed消息发送和模板
    # TODO 搜索任务（疑似）内存泄漏
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("👋 用户主动终止操作")

# TODO 黑名单，保存所有已经查阅过的推特发帖人，后续判断是不是二次创业 🗑️
# TODO 项目方 + 网址判断 ✅
# TODO 推文全推 + 粉丝判断 ✅
# TODO solana监控
