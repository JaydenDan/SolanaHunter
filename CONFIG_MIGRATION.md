# 配置系统迁移文档

## 迁移概述

本项目已从旧的 `settings.py` 单文件配置方式迁移到了基于环境变量的 `.env` 配置方式。这种配置方式更加安全、灵活，并且符合现代应用开发的最佳实践。

## 变更内容

1. 新增了基于 `dotenv` 的配置加载模块 `config/config_loader.py`
2. 新增了 `.env` 和 `.env.example` 示例配置文件
3. 更新了各模块的配置引用方式，从直接引用 `settings` 对象改为使用 `get_config()` 函数访问配置项
4. 将配置项分组组织，方便管理和访问

## 迁移的文件

以下文件已经完成了从 `settings.py` 到新配置系统的迁移：

1. `src/notifier/discord/bot.py` - Discord 机器人配置
2. `src/notifier/dingtalk/client.py` - 钉钉客户端配置
3. `src/monitor/rules/engine.py` - 规则引擎配置
4. `src/monitor/twitter/manager.py` - Twitter 监控管理器配置
5. `main.py` - 主程序配置
6. `src/account/twitter/get_account.py` - Twitter 账号管理配置

## 使用新配置系统

1. **基本用法**

   ```python
   from config.config_loader import get_config
   
   # 获取完整配置
   all_config = get_config()
   
   # 获取特定配置项，使用点号分隔路径
   redis_host = get_config('REDIS.host')
   
   # 获取配置项并提供默认值（如果配置项不存在）
   discord_prefix = get_config('DISCORD.prefix', '!')
   ```

2. **配置项分组**

   - `REDIS` - Redis 数据库配置
   - `MYSQL` - MySQL 数据库配置
   - `TWITTER` - Twitter API 配置
   - `BLOCKCHAIN` - 区块链监听配置
   - `BLOCKCHAIN_RPC` - 区块链 RPC 配置
   - `DINGTALK` - 钉钉通知配置
   - `DISCORD` - Discord 机器人配置

3. **环境变量设置**

   在项目根目录创建一个 `.env` 文件，参考 `.env.example` 中的示例，设置所需的环境变量。例如：

   ```
   # Redis 配置
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_PASSWORD=your_password
   
   # Discord 配置
   DISCORD_TOKEN=your_discord_token
   DISCORD_PROXY=http://localhost:7890
   ```

## 原 settings.py 文件

由于所有对 `settings.py` 的引用已迁移到新配置系统，现在可以安全地删除 `settings.py` 文件。

## 注意事项

1. 确保在运行应用前已创建 `.env` 文件并设置所有必要的环境变量
2. `.env` 文件已添加到 `.gitignore`，不会被 Git 追踪，从而避免敏感信息泄露
3. 如需在新地方部署应用，请复制 `.env.example` 为 `.env` 并填入相应的值 