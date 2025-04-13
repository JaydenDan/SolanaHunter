import logging
import os
from datetime import datetime
import aiohttp  # 导入aiohttp库
import json
import asyncio
from config.config_loader import get_config

from src.rules.rule_loader import RuleLoader
from src.rules.watcher import RuleWatcher


class RuleEngine:
    """增强的规则引擎，支持复杂条件判断（单例模式）"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False  # 添加初始化标志
        return cls._instance
    
    def __init__(self):
        # 检查是否已初始化
        if getattr(self, '_initialized', False):
            return
            
        self.rules = []
        self.rules_dir = None  # 添加规则目录属性
        self.loader = RuleLoader()
        self.watcher = RuleWatcher(self._on_rules_changed)
        self._initialized = True  # 标记为已初始化
        
    def initialize(self, rules_dir):
        """初始化规则引擎"""
        # 确保规则目录是绝对路径
        self.rules_dir = os.path.abspath(rules_dir)
        
        logging.info(f"🔧 初始化规则引擎，规则目录: {self.rules_dir}")
        
        # 加载规则文件
        self.rules = self.loader.load_rules(self.rules_dir)
        logging.info(f"📚 已加载 {len(self.rules)} 条规则")
        
        # 启动文件监控
        self.watcher.start_watching(self.rules_dir)
        logging.info("👀 规则文件监控已启动")
    
    def _on_rules_changed(self, modified_files):
        """规则文件变更处理（同步方法）"""
        # 确保复杂的错误处理不会阻断主要功能
        try:
            # 输出修改的文件列表
            modified_files_list = list(modified_files)
            logging.info(f"🔄 检测到规则文件变更，开始重新加载规则: {modified_files_list}")
            
            # 记录旧规则数量
            old_rules_count = len(self.rules)
            
            # 重新加载规则
            self.rules = self.loader.load_rules(self.rules_dir)
            
            # 记录新规则数量
            new_rules_count = len(self.rules)
            
            # 输出更新结果
            logging.info(f"📊 规则更新完成: {old_rules_count} -> {new_rules_count} 条规则")
        except Exception as e:
            logging.error(f"❌ 规则更新失败: {str(e)}", exc_info=True)
    
    async def evaluate(self, token_data):
        """评估代币是否需要通知及通知渠道"""
        results = []
        
        for rule in self.rules:
            # 跳过不适用的规则
            if not rule.get("enable", False):
                continue
                
            # 评估规则条件
            if self._evaluate_condition(rule["condition"], token_data):
                result = {
                    "rule_name": rule["name"],
                    "rule_id": rule["id"],
                    "action": rule["action"],
                    "channel": rule["action"].get("channel")
                }
                
                # 检查是否需要执行交易
                if rule["action"].get("transaction", False):
                    # 执行交易操作
                    transaction_result = await self._execute_transaction(token_data, rule)
                    result["transaction_result"] = transaction_result
                
                results.append(result)
                
        return results
    
    def _evaluate_condition(self, condition, data):
        """评估条件，支持复杂的嵌套逻辑和字段比较"""
        condition_type = condition["type"]
        
        # 逻辑操作符
        if condition_type == "and":
            return all(self._evaluate_condition(cond, data) for cond in condition["conditions"])
        elif condition_type == "or":
            return any(self._evaluate_condition(cond, data) for cond in condition["conditions"])
        elif condition_type == "not":
            return not self._evaluate_condition(condition["condition"], data)
        
        # 比较操作符
        elif condition_type == ">":
            return self._get_field_value(data, condition["field"], 0) > condition["value"]
        elif condition_type == "<":
            return self._get_field_value(data, condition["field"], 0) < condition["value"]
        elif condition_type == "==":
            return self._get_field_value(data, condition["field"]) == condition["value"]
        elif condition_type == "!=":
            return self._get_field_value(data, condition["field"]) != condition["value"]
        elif condition_type == ">=":
            return self._get_field_value(data, condition["field"], 0) >= condition["value"]
        elif condition_type == "<=":
            return self._get_field_value(data, condition["field"], 0) <= condition["value"] 
        
        # 字符串操作符
        elif condition_type == "string_contains":
            source_value = str(self._get_field_value(data, condition["source_field"], "")).lower()
            
            if "value" in condition:
                target_value = str(condition["value"]).lower()
            else:
                target_value = str(self._get_field_value(data, condition["target_field"], "")).lower()
                
            return target_value in source_value
        
        elif condition_type == "string_starts_with":
            source_value = str(self._get_field_value(data, condition["source_field"], "")).lower()
            
            if "value" in condition:
                target_value = str(condition["value"]).lower()
            else:
                target_value = str(self._get_field_value(data, condition["target_field"], "")).lower()
                
            return source_value.startswith(target_value)
        
        # 存在性检查
        elif condition_type == "exists":
            return self._field_exists(data, condition["field"])
        elif condition_type == "not_exists":
            return not self._field_exists(data, condition["field"])
        
        # 数值范围检查
        elif condition_type == "in_range":
            value = self._get_field_value(data, condition["field"], 0)
            return condition["min"] <= value <= condition["max"]
        
        # 列表操作符
        elif condition_type == "in_list":
            value = self._get_field_value(data, condition["field"])
            return value in condition["values"]
        
        # 默认返回False
        return False
    
    def _get_field_value(self, data, field_path, default=None):
        """从嵌套字典中获取字段值，支持点表示法"""
        if not field_path:
            return default
            
        parts = field_path.split('.')
        value = data
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
                
        return value
    
    def _field_exists(self, data, field_path):
        """检查字段是否存在，支持点表示法"""
        parts = field_path.split('.')
        value = data
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return False
                
        return True
    
    async def _execute_transaction(self, token_data, rule):
        """异步执行代币交易操作
        
        Args:
            token_data: 代币数据
            rule: 触发的规则
            
        Returns:
            Dict: 交易结果信息
        """
        try:
            # 从环境变量获取API URL和密钥
            api_url = f"{get_config('TRANSACTION_API.url')}/register"
            api_key = get_config("TRANSACTION_API.key")
            
            if not api_url or not api_key:
                raise ValueError("环境变量中缺少TRANSACTION_API_URL或TRANSACTION_API_KEY配置")
            
            # 获取代币地址
            token_address = token_data.get("mint")
            if not token_address:
                raise ValueError("代币数据中缺少mint字段")
                
            # 构建请求数据
            request_data = {
                "token": token_address
            }
            
            # 设置请求头
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": api_key
            }
            
            # 记录开始调用API
            logging.info(f"🔄 开始调用交易API: 代币 {token_address}，规则 {rule['id']}")
            
            # 调用API
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=request_data, headers=headers) as response:
                    response_status = response.status
                    response_text = await response.text()
                    
                    # 检查响应状态
                    if response_status == 200:
                        logging.info(f"✅ 交易API调用成功: 代币 {token_address}")
                    else:
                        logging.error(f"❌ 交易API调用失败: 状态码 {response_status}, 响应 {response_text}")

        except Exception as e:
            logging.error(f"❌ 执行交易调用失败: {str(e)}", exc_info=True)