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

# 钉钉通知配置（可选）
DINGTALK = {
    "token": "465646247fa1c550eeda6475e411661e3f5bb44bb24a8663a9b9751e3f67d102",
    "client_id": "dingpeuoicagx1l58xhq",
    "client_secret": "SNEzbvO_yPtzcaFmJG5d_D3VggRSJ7cxeLfS_iPmQPocVtsFEhuE-MXVqtGOeZvr"
}