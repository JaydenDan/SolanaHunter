import asyncio
from collections import defaultdict


class TaskCounter:
    _instance = None  # 类属性保存唯一实例

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            # 初始化实例属性
            cls._instance._counters = defaultdict(int)
            cls._instance._locks = defaultdict(asyncio.Lock)
        return cls._instance  # 总是返回同一个实例

    async def get_name(self, prefix: str) -> str:
        async with self._locks[prefix]:
            self._counters[prefix] += 1
            return f"{prefix}-{self._counters[prefix]}"
