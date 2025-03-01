"""
规则引擎核心模块

包含规则加载、条件评估、动态更新等核心功能
"""

# 导出核心引擎类
from .engine import RuleEngine
# 导出条件注册表
from .conditions import CONDITION_REGISTRY

__all__ = [
    # 规则引擎主类
    'RuleEngine',
    # 条件类型注册表
    'CONDITION_REGISTRY'
]

__version__ = '1.0.0'  # 模块版本

# 可选：初始化日志配置
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
