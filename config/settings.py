from pathlib import Path

# 基本配置
PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

# Twitter API配置
TWITTER = {
    "cookie_path": str(PROJECT_ROOT / "twitter_cookies.txt"),
    "proxy": "http://127.0.0.1:7890",  # 代理设置
    "account_file_path": str(PROJECT_ROOT / "twitter_account.xlsx")
}

# 区块链监听配置
BLOCKCHAIN = {
    "websocket_url": "wss://pumpportal.fun/api/data"
}

# 钉钉通知配置
DINGTALK = {
    "token": "465646247fa1c550eeda6475e411661e3f5bb44bb24a8663a9b9751e3f67d102",
    "client_id": "dingpeuoicagx1l58xhq",
    "client_secret": "SNEzbvO_yPtzcaFmJG5d_D3VggRSJ7cxeLfS_iPmQPocVtsFEhuE-MXVqtGOeZvr"
}

DISCORD = {
    "token": "MTM0NTI0NTkyMTk0ODIwNTA3Nw.GC19fL.sWOdoZcQ1h0Z395mBjoI2r7hGDU-yek0Y6IPjk",
    "proxy": "http://localhost:7890",  # 代理地址
    "channel": {
        "test_channel": 1345764680274149386,
        "all_twitter": 1345252024413065322,
        "founder_twitter": 1345252024413065323,
        "1000~3000_fans": 1345829917472063609,
        "3000~5000_fans": 1345830387854741646,
        "5000~10000_fans": 1345831194050302033,
        "10000+_fans": 1345831926191358004,
        "system_channel": 1346201432814129194,
        "start_as_launch_without_twitter": 1347601435742965922
    },
    
}
