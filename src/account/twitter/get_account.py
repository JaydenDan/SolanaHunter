import asyncio
import logging

import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class TwitterAccount:
    email: str
    password: str
    username: str
    proxy: str
    in_use: bool = False
    disabled: bool = False


class AccountPool:
    _instance = None  # 单例实例
    _lock = asyncio.Lock()  # 异步锁，用于协程安全

    def __new__(cls, excel_path: str):
        # 单例模式核心逻辑：确保只有一个实例
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 初始化操作放在 __new__ 中，避免 __init__ 重复调用
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, excel_path: str):
        # 单例模式下，__init__ 可能被多次调用，需通过标志位避免重复初始化
        if self._initialized:
            return
        self.excel_path = excel_path
        self._queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._init_accounts()
        self._initialized = True

    def _init_accounts(self):
        """从Excel加载账户数据"""
        df = pd.read_excel(self.excel_path)
        for _, row in df.iterrows():
            account = TwitterAccount(
                email=row['email'],
                username=row['username'],
                password=row['password'],
                proxy=row['residential_proxy'],
            )
            self._queue.put_nowait(account)

    async def acquire(self) -> Optional[TwitterAccount]:
        """获取可用账户"""
        async with self._lock:
            if self._queue.empty():
                logging.error(f'🚨 账号池为空！')
                return None

            account = await self._queue.get()
            if account.disabled:
                return await self.acquire()  # 递归获取下一个
            logging.info(f'🧲 获取到Twitter账号【{account}】')
            account.in_use = True
            return account

    async def release_account(self, account: TwitterAccount, success: bool = True):
        """释放账户"""
        async with self._lock:
            account.in_use = False
            # success标记账户能不能用（是否封禁、冻结等硬措施）
            if not success:
                account.disabled = True  # 标记失效账户
                logging.error(f'⚠️ Twitter账号【{account}】已失效，请处理！')
            else:
                await self._queue.put(account)
                logging.info(f'📥 已释放Twitter账号【{account}】')

    async def health_check(self):
        """健康检查（协程安全）"""
        async with self._lock:
            temp_queue = asyncio.Queue()
            while not self._queue.empty():
                acc = await self._queue.get()
                if not acc.disabled:
                    await temp_queue.put(acc)
            self._queue = temp_queue
