import asyncio
import logging
import time
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dingtalk.oauth2_1_0.client import Client as oauth2Client
from alibabacloud_dingtalk.oauth2_1_0 import models as oauth2_models


class DingTalkTokenManager:
    """钉钉令牌管理器（协程安全单例）"""
    _instance = None
    _lock = asyncio.Lock()  # 类级异步锁
    _refresh_lock = asyncio.Lock()  # 令牌刷新锁

    def __new__(cls, app_key: str, app_secret: str):
        # 生成实例唯一标识
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 初始化操作放在 __new__ 中，避免 __init__ 重复调用
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, app_key: str, app_secret: str):
        """初始化方法（协程安全）"""
        if self._initialized:
            return

        self.app_key = app_key
        self.app_secret = app_secret
        self._access_token = None
        self._expire_time = 0
        self._initialized = True

    async def get_token(self) -> str:
        """获取有效访问令牌（线程安全）"""
        current_time = time.time()
        if current_time < self._expire_time - 60:  # 提前1分钟刷新
            return self._access_token

        # 加锁确保只有一个线程执行 token 刷新
        async with self._refresh_lock:
            # 再次检查，避免其他线程已经刷新
            if current_time < self._expire_time - 60:
                return self._access_token

            config = open_api_models.Config()
            config.protocol = "https"
            config.region_id = "central"

            client = oauth2Client(config)
            req = oauth2_models.GetAccessTokenRequest(
                app_key=self.app_key,
                app_secret=self.app_secret
            )

            try:
                resp = client.get_access_token(req)
                self._access_token = resp.body.access_token
                self._expire_time = time.time() + int(resp.body.expire_in)
                logging.info("✅ 钉钉Token刷新成功")
                return self._access_token
            except Exception as e:
                logging.error(f"❌ 钉钉Token刷新失败: {e}")
                raise RuntimeError(f"钉钉Token获取失败: {e}")