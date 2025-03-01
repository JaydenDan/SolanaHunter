from .base import BaseCondition
from .market import MarketCapCondition
from .social import SocialActivityCondition

# 条件类型注册表
CONDITION_REGISTRY = {
    'market_cap': MarketCapCondition,
    'social_activity': SocialActivityCondition
}


def load_condition(cond_type: str) -> type[BaseCondition]:
    """根据类型名称获取条件类"""
    try:
        return CONDITION_REGISTRY[cond_type]
    except KeyError:
        raise ValueError(f"未知的条件类型: {cond_type}，可用类型: {list(CONDITION_REGISTRY.keys())}")


__all__ = ['BaseCondition', 'CONDITION_REGISTRY', 'load_condition']
