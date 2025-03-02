import asyncio
import re
from collections import defaultdict


def get_ca_in_tweet(tweet_text) -> list:
    # 正则表达式：匹配仅包含字母和数字的地址，假设长度在30到50之间
    pattern = r"\b[A-Za-z0-9]{30,50}\b"
    # 查找所有匹配项
    matches = re.findall(pattern, tweet_text)
    # 返回结果
    return matches


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
