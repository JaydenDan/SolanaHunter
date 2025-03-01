"""
规则变更处理器模块

包含所有与规则文件监控相关的功能
"""

# 导入具体实现
from .file_watcher import RuleFileHandler

# 定义公开接口
__all__ = ['RuleFileHandler']
