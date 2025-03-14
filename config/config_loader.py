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
        
        # Redis配置
        "REDIS": {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6379")),
            "db": int(os.getenv("REDIS_DB", "0")),
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
            "cookie_path": os.getenv("TWITTER_COOKIE_PATH", str(PROJECT_ROOT / "twitter_cookies.txt")),
            "proxy": os.getenv("TWITTER_PROXY", "http://127.0.0.1:7890"),
            "account_file_path": os.getenv("TWITTER_ACCOUNT_FILE", str(PROJECT_ROOT / "twitter_account.xlsx")),
        },
        
        # 区块链监听配置
        "BLOCKCHAIN": {
            "websocket_url": os.getenv("BLOCKCHAIN_WEBSOCKET_URL", "wss://pumpportal.fun/api/data"),
        },
        
        # 区块链RPC配置
        "BLOCKCHAIN_RPC": {
            "solana_official_rpc_url": os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
        },
        
        # 钉钉通知配置
        "DINGTALK": {
            "token": os.getenv("DINGTALK_TOKEN", ""),
            "client_id": os.getenv("DINGTALK_CLIENT_ID", ""),
            "client_secret": os.getenv("DINGTALK_CLIENT_SECRET", ""),
        },
        
        # Discord配置
        "DISCORD": {
            "token": os.getenv("DISCORD_TOKEN", ""),
            "proxy": os.getenv("DISCORD_PROXY", "http://localhost:7890"),
            "channel": {
                "test_channel": int(os.getenv("DISCORD_CHANNEL_TEST", "0")),
                "all_twitter": int(os.getenv("DISCORD_CHANNEL_ALL_TWITTER", "0")),
                "founder_twitter": int(os.getenv("DISCORD_CHANNEL_FOUNDER_TWITTER", "0")),
                "1000~3000_fans": int(os.getenv("DISCORD_CHANNEL_1000_3000_FANS", "0")),
                "3000~5000_fans": int(os.getenv("DISCORD_CHANNEL_3000_5000_FANS", "0")),
                "5000~10000_fans": int(os.getenv("DISCORD_CHANNEL_5000_10000_FANS", "0")),
                "10000+_fans": int(os.getenv("DISCORD_CHANNEL_10000_PLUS_FANS", "0")),
                "system_channel": int(os.getenv("DISCORD_CHANNEL_SYSTEM", "0")),
                "start_as_launch_without_twitter": int(os.getenv("DISCORD_CHANNEL_START_LAUNCH", "0")),
                "has_score_channel": int(os.getenv("DISCORD_CHANNEL_HAS_SCORE", "0")),
                "dev_balance_50": int(os.getenv("DISCORD_CHANNEL_DEV_BALANCE_50", "0")),
                "dev_balance_20_twitter": int(os.getenv("DISCORD_CHANNEL_DEV_BALANCE_20", "0")),
            },
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