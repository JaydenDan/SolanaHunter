from datetime import datetime
import json
import logging
import copy
from typing import Optional, Any, Dict

from src.database.redis.redis_manager import RedisManager
from src.rules.rule_engine import RuleEngine

# 初始化Redis管理器
redis_manager = RedisManager()

# 自定义JSON编码器
class ComplexEncoder(json.JSONEncoder):
    """处理复杂对象的JSON编码器，支持datetime和自定义类"""
    
    def default(self, obj):
        # 处理datetime对象
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        
        # 处理TwitterAccount和其他dataclass
        if hasattr(obj, '__dataclass_fields__') or hasattr(obj, '__dict__'):
            # 获取对象属性并过滤掉内部/私有属性
            attributes = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):  # 过滤掉内部属性
                    attributes[key] = value
            return attributes
            
        # 处理其他复杂对象
        try:
            # 尝试转换为字典
            return dict(obj)
        except (TypeError, ValueError):
            # 如果无法转换为字典，则返回字符串表示
            return str(obj)

# 安全的JSON序列化函数
def safe_json_dumps(data: Any) -> str:
    """使用自定义编码器安全地序列化任何数据结构"""
    return json.dumps(data, cls=ComplexEncoder)

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
        
        # 评估规则 - 直接使用原始token_data，不修改原始数据
        triggered_rules = await rule_engine.evaluate(token_data)

        # 记录触发的规则
        for rule in triggered_rules:
            # 构建通知内容
            notification = {
                "token_data": token_data,  # 直接使用原始数据
                "rule_id": rule["rule_id"],
                "rule_name": rule["rule_name"],
                "channel": rule["channel"],
            }
            
            # 如果存在交易结果，添加到通知中
            if "transaction_result" in rule:
                notification["transaction_result"] = rule["transaction_result"]
                # 记录交易结果
                transaction_status = rule["transaction_result"].get("status", "未知")
                logging.info(f"代币交易: {token_data['mint']} - 状态: {transaction_status} - 规则: {rule['rule_id']}")
            
            # 将通知内容序列化为JSON，使用自定义编码器处理复杂对象
            notification_json = safe_json_dumps(notification)

            # 使用Redis管理器将通知内容推送到Redis队列
            await redis_manager.lpush("discord:token:notifications", notification_json)
            logging.info(f"Token: {token_data['mint']} 触发规则: ID: {rule['rule_id']}, 名称: {rule['rule_name']}, 动作: {rule['action']}")

    except Exception as e:
        logging.error(f"处理推特数据时出错: {str(e)}", exc_info=True)

async def to_notify_account_error(account, error_name: str, error_info: Optional[str] = None):
    """
    推送账号错误消息到Redis, 等待Discord机器人处理
    :param account: Twitter账号对象
    :param error_name: 错误名称
    :param error_info: 错误信息 
    """
    try:
        error_last_line = error_info.strip().split('\n')[-1] if error_info else "无详细信息"
        
        # 构建错误通知
        notification = {
            "account": account,  # 直接使用账号对象
            "error_name": error_name,
            "error_info": error_last_line,
            "timestamp": datetime.now()  # 直接使用datetime对象
        }
        
        # 使用自定义编码器序列化，处理TwitterAccount和datetime对象
        notification_json = safe_json_dumps(notification)
        
        await redis_manager.lpush("discord:account:error:notifications", notification_json)
        
        # 日志记录 - 从account中安全地获取email
        account_email = getattr(account, "email", "未知账号")
        logging.info(f"账号错误消息已推送到Redis: {account_email} - {error_name} - {error_last_line}")
    
    except Exception as e:
        logging.error(f"❌ 发送账号错误通知失败: {str(e)}", exc_info=True)

async def to_notify_account_report(accounts):
    """
    推送账号状态报告到Redis, 等待Discord机器人处理
    :param accounts: 账号列表
    """
    try:
        # 创建报告内容 - 预先将账号按状态分类
        report_content = {
            "total_accounts": len(accounts),
            # 保留完整的账号对象列表
            "accounts": accounts,
            # 按状态分类的账号列表
            "in_use_accounts": [acc for acc in accounts if getattr(acc, "in_use", False)],
            "disabled_accounts": [acc for acc in accounts if getattr(acc, "disabled", False)],
            "available_accounts": [acc for acc in accounts if not getattr(acc, "in_use", False) and not getattr(acc, "disabled", False)],
            # 分类计数
            "in_use_count": sum(1 for acc in accounts if getattr(acc, "in_use", False)),
            "disabled_count": sum(1 for acc in accounts if getattr(acc, "disabled", False)),
            "available_count": sum(1 for acc in accounts if not getattr(acc, "in_use", False) and not getattr(acc, "disabled", False)),
            "timestamp": datetime.now()  # 直接使用datetime对象
        }
        
        # 使用自定义编码器序列化，处理TwitterAccount和datetime对象
        report_json = safe_json_dumps(report_content)
        
        await redis_manager.lpush("discord:account:report:notifications", report_json)
        logging.info(f"✅ 账号状态报告已推送到Redis: 总计 {len(accounts)} 个账号，可用：{report_content['available_count']}，使用中：{report_content['in_use_count']}，禁用：{report_content['disabled_count']}")
        
    except Exception as e:
        logging.error(f"❌ 发送账号状态报告到Redis失败: {str(e)}", exc_info=True)
