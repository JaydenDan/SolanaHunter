from abc import ABC, abstractmethod


class BaseCondition(ABC):
    @abstractmethod
    def check(self, context: dict) -> bool:
        """评估条件是否满足"""
        pass
