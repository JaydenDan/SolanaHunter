# 环境变量配置系统说明

## 概述

项目已更新为使用环境变量配置系统，所有配置都从`.env`文件或系统环境变量中加载。这样做的好处是：

1. 提高安全性，敏感信息不会提交到代码仓库
2. 更灵活的配置方式，无需修改代码即可更改配置
3. 符合12-Factor应用程序的最佳实践
4. 不同环境（开发、测试、生产）可以使用不同的配置

## 使用方法

### 1. 创建配置文件

项目根目录已提供`.env.example`文件作为模板，请复制一份并重命名为`.env`：

```bash
cp .env.example .env
```

然后根据需要修改`.env`文件中的配置项。

### 2. 访问配置项

在代码中，通过以下方式访问配置项：

```python
from config import get_config

# 获取整个配置对象
all_config = get_config()

# 获取特定配置项
redis_host = get_config('REDIS.host')
mysql_user = get_config('MYSQL.user')

# 提供默认值
redis_port = get_config('REDIS.port', 6379)
```

### 3. 数据库配置

Redis和MySQL管理器已更新，现在会自动从环境变量中加载配置：

```python
# Redis示例
from src.database import redis_manager

# 使用环境变量中的配置初始化
await redis_manager.init_pool()

# MySQL示例
from src.database import mysql_manager

# 使用环境变量中的配置初始化
await mysql_manager.init_pool()
```

也可以在初始化时覆盖特定配置：

```python
# 覆盖特定配置
redis_manager.__init__(host='custom-redis-host', port=6380)
mysql_manager.__init__(database='custom_database')
```

### 4. 配置项列表

以下是可用的配置项及其默认值：

#### 基本配置
- `LOG_DIR`: 日志目录，默认为项目根目录下的`logs`

#### Redis配置
- `REDIS_HOST`: Redis服务器地址，默认为`localhost`
- `REDIS_PORT`: Redis服务器端口，默认为`6379`
- `REDIS_DB`: Redis数据库索引，默认为`0`
- `REDIS_PASSWORD`: Redis密码，默认为空
- `REDIS_DECODE_RESPONSES`: 是否自动解码响应，默认为`True`
- `REDIS_MAX_CONNECTIONS`: 最大连接数，默认为`10`
- `REDIS_TIMEOUT`: 连接超时时间(秒)，默认为`5`

#### MySQL配置
- `MYSQL_HOST`: MySQL服务器地址，默认为`localhost`
- `MYSQL_PORT`: MySQL服务器端口，默认为`3306`
- `MYSQL_USER`: 用户名，默认为`root`
- `MYSQL_PASSWORD`: 密码，默认为空
- `MYSQL_DATABASE`: 数据库名，默认为空
- `MYSQL_CHARSET`: 字符集，默认为`utf8mb4`
- `MYSQL_POOL_SIZE`: 连接池大小，默认为`5`
- `MYSQL_TIMEOUT`: 连接超时时间(秒)，默认为`10`

#### Twitter API配置
- `TWITTER_COOKIE_PATH`: Twitter cookie文件路径
- `TWITTER_PROXY`: Twitter代理
- `TWITTER_ACCOUNT_FILE`: Twitter账号文件路径

#### 区块链配置
- `BLOCKCHAIN_WEBSOCKET_URL`: 区块链WebSocket URL
- `SOLANA_RPC_URL`: Solana RPC URL

#### 钉钉通知配置
- `DINGTALK_TOKEN`: 钉钉令牌
- `DINGTALK_CLIENT_ID`: 钉钉客户端ID
- `DINGTALK_CLIENT_SECRET`: 钉钉客户端密钥

#### Discord配置
- `DISCORD_TOKEN`: Discord令牌
- `DISCORD_PROXY`: Discord代理
- 多种Discord频道配置项，请参考`.env.example`文件

## 安装依赖

本配置系统需要`python-dotenv`库，请确保安装：

```bash
pip install -r requirements.txt
```

## 注意事项

1. `.env`文件不应提交到版本控制系统中，已添加到`.gitignore`
2. 如果没有找到`.env`文件，系统会使用环境变量或默认值
3. 环境变量优先级：系统环境变量 > `.env`文件 > 默认值 