"""钉钉开放平台接口封装"""
from .client import DingTalkClient
from .token_manager import DingTalkTokenManager

__all__ = ['DingTalkClient', 'DingTalkTokenManager']