import os
import logging
from pathlib import Path
from dotenv import load_dotenv

from config.logging_config import get_logger

logger = get_logger("config_loader")

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_config():
    """
    从.env文件加载配置项
    
    Returns:
        配置字典
    """
    # 加载.env文件
    if os.path.exists(ENV_FILE):
        load_dotenv(ENV_FILE)
        logger.info(f"已加载配置文件: {ENV_FILE}")
    else:
        logger.warning(f"配置文件不存在: {ENV_FILE}，将使用环境变量或默认值")
    
    # 基本配置
    config = {
        "PROJECT_ROOT": PROJECT_ROOT,
        "LOG_DIR": Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs"))),
        
        # 规则文件配置
        "RULE_FILES_DIR_PATH": os.getenv("RULE_FILES_DIR_PATH", "all_rules"),
        
        # Redis配置
        "REDIS": {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6379")),
            "db": int(os.getenv("REDIS_DB", "1")),
            "password": os.getenv("REDIS_PASSWORD", None),
            "decode_responses": os.getenv("REDIS_DECODE_RESPONSES", "True").lower() == "true",
            "max_connections": int(os.getenv("REDIS_MAX_CONNECTIONS", "10")),
            "connection_timeout": int(os.getenv("REDIS_TIMEOUT", "5")),
        },
        
        # MySQL配置
        "MYSQL": {
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", "3306")),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", ""),
            "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
            "pool_size": int(os.getenv("MYSQL_POOL_SIZE", "5")),
            "connect_timeout": int(os.getenv("MYSQL_TIMEOUT", "10")),
        },
        
        # Twitter API配置 
        "TWITTER": {
            "cookies_file_path": os.getenv("TWITTER_COOKIES_FILE_PATH", str(PROJECT_ROOT / "twitter_cookies.txt")),
            "proxy": os.getenv("TWITTER_PROXY", "http://127.0.0.1:7890"),
            "account_file_path": os.getenv("TWITTER_ACCOUNT_FILE_PATH", str(PROJECT_ROOT / "twitter_account.xlsx")),
            "account_reverse_load": os.getenv("TWITTER_ACCOUNT_REVERSE_LOAD", "False").lower() == "true",
        },
        
        # 区块链监听配置
        "BLOCKCHAIN": {
            "websocket_url": os.getenv("BLOCKCHAIN_WEBSOCKET_URL", "wss://pumpportal.fun/api/data"),
        },
        
        # 区块链RPC配置
        "BLOCKCHAIN_RPC": {
            "solana_official_rpc_url": os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
        },

        # 交易API配置
        "TRANSACTION_API": {
            "url": os.getenv("TRANSACTION_API_URL", "https://pumpportal.fun/api/transaction"),
            "key": os.getenv("TRANSACTION_API_KEY", ""),
        },
    }
    
    return config


# 全局配置对象
config = load_config()


def get_config(key=None, default=None):
    """
    获取配置项
    
    Args:
        key: 配置键，可以是点分隔的路径，如 'REDIS.host'
        default: 默认值，如果配置项不存在则返回此值
    
    Returns:
        配置值或默认值
    """
    if key is None:
        return config
    
    keys = key.split('.')
    value = config
    
    try:
        for k in keys:
            value = value[k]
        return value
    except (KeyError, TypeError):
        return default 