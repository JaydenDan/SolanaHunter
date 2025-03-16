import logging
import os

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
    
    def evaluate(self, token_data):
        """评估代币是否需要通知及通知渠道"""
        results = []
        # 根据数据中是否存在social对象判断作用域
        rule_scope = "with_twitter" if token_data.get("social") else "without_twitter"
        
        for rule in self.rules:
            # 跳过不适用的规则
            if not rule.get("enable", False):
                continue
                
            # 评估规则条件
            if self._evaluate_condition(rule["condition"], token_data):
                results.append({
                    "rule_name": rule["name"],
                    "rule_id": rule["id"],
                    "action": rule["action"],
                    "channel": rule["action"].get("channel")
                })
                
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