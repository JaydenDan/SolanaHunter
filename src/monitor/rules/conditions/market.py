from .base import BaseCondition


class MarketCapCondition(BaseCondition):
    """市值条件判断"""

    def __init__(self, min_cap: float):
        self.min_cap = min_cap

    def check(self, context: dict) -> bool:
        return context.get('market_cap', 0) >= self.min_cap