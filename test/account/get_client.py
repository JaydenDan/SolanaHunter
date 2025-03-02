import asyncio
from src.account.twitter.get_client import TwitterClientManager
from config import logging_config
import logging


async def main():
    # 初始化日志系统（必须最先执行）
    logging_config.setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("✅ 日志系统启动初始化成功")
    client_manager = TwitterClientManager()

    # 使用异步上下文管理器获取client（需要确保get_client实现正确）
    async with client_manager.get_client(
            email="hardyyyy@qq.com",
            username="jayden062901",
            password="asd001122",
            proxy="http://127.0.0.1:7890"
    ) as client:  # 需要确保get_client实现了异步上下文管理

        # 注意：根据twikit文档，search_tweet的参数可能需要调整
        tweet = await client.search_tweet(
            "CGsaXSmDcRdb1NpC1wxTuANhJb5A3y6mdPtaNjgopump 谢谢谢谢",
            "latest"  # 根据实际API要求可能需要使用枚举值
        )
        print(tweet[0].user)
        # user = await client.search_user(query="KaitoAI")
        # print(f'user')


# 正确运行异步主函数
if __name__ == "__main__":
    asyncio.run(main())
