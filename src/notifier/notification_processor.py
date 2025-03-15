from datetime import datetime
import json
import logging
from typing import Optional

from src.database.redis.redis_manager import RedisManager
from src.rules.rule_engine import RuleEngine

# 初始化Redis管理器
redis_manager = RedisManager()

async def to_notify_token(token_data):
    """
    处理推特数据，通过规则引擎判断是否触发规则。

    Args:
        token_data (Dict[str, Any]): 推特数据，包含用户信息、推文内容、互动数据等。

    Returns:
        List[Dict[str, Any]]: 触发的规则列表，每个规则包含规则ID和动作信息。
    """
    try:
        # 获取规则引擎的单例实例（已在main中初始化）
        rule_engine = RuleEngine()  # 单例模式会返回已初始化的实例
        
        # 评估规则 - 直接使用原始token_data，不修改datetime格式  
        triggered_rules = rule_engine.evaluate(token_data)

        # 记录触发的规则
        for rule in triggered_rules:
            # 构建通知内容 - 为JSON序列化创建新的数据副本
            import copy
            notification_data = copy.deepcopy(token_data)
            
            # 只在JSON序列化前转换日期格式
            if isinstance(notification_data['detect_time'], datetime):
                notification_data['detect_time'] = notification_data['detect_time'].strftime('%Y-%m-%d %H:%M:%S')
            
            notification = {
                "token_data": notification_data,  # 使用转换后的数据副本
                "rule_id": rule["rule_id"],
                "rule_name": rule["rule_name"],
                "channel": rule["channel"],
            }
            # 将通知内容序列化为JSON
            notification_json = json.dumps(notification)

            # 使用Redis管理器将通知内容推送到Redis队列
            await redis_manager.lpush("discord:token:notifications", notification_json)
            logging.info(f"Token: {token_data['mint']} 触发规则: ID: {rule['rule_id']}, 名称: {rule['rule_name']}, 动作: {rule['action']}")

    except Exception as e:
        logging.error(f"处理推特数据时出错: {str(e)}")

async def to_notify_account_error(account, error_name: str, error_info: Optional[str] = None):
    """
        推送账号错误消息到Redis, 等待Discord机器人处理
        :param account: Twitter账号对象
        :param error_name: 错误名称
        :param error_info: 错误信息 
        """
    error_last_line = error_info.strip().split('\n')[-1]
    await redis_manager.lpush("discord:account:error:notifications", json.dumps({
        "account": account,
        "error_name": error_name,
        "error_info": error_last_line,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }))
    logging.info(f"账号错误消息已推送到Redis: {account.email} - {error_name} - {error_last_line}")

async def to_notify_account_report(accounts):
    """
    推送账号状态报告到Redis, 等待Discord机器人处理
    :param accounts: 账号列表
    """
    try:
        # 创建json格式状态报告内容
        report_content = {
            "total_accounts": len(accounts),
            "in_use_accounts": [{"email": acc.email, "username": acc.username} for acc in accounts if acc.in_use],
            "disabled_accounts": [{"email": acc.email, "username": acc.username} for acc in accounts if acc.disabled],
            "available_accounts": [{"email": acc.email, "username": acc.username} for acc in accounts if not acc.in_use and not acc.disabled],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        await redis_manager.lpush("discord:account:report:notifications", json.dumps(report_content))
    except Exception as e:
        logging.error(f"❌ 发送账号状态报告到Redis失败: {str(e)}", exc_info=True)
        return
