import json
import os
from typing import List, Dict, Tuple, Set

class RuleValidator:
    """规则文件校验器"""
    
    @staticmethod
    def validate_rule_file(file_path: str) -> Tuple[bool, List[str], Set[str]]:
        """
        校验规则文件
        
        Args:
            file_path: 规则文件路径
            
        Returns:
            Tuple[bool, List[str], Set[str]]:
                - bool: 是否验证通过
                - List[str]: 错误信息列表
                - Set[str]: 规则ID集合（用于重复检查）
        """
        errors = []
        rule_ids = set()
        
        try:
            # 读取并解析JSON文件
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    errors.append(f"JSON格式错误: {str(e)}")
                    return False, errors, rule_ids
                    
            # 检查基本结构
            if not isinstance(data, dict):
                errors.append("规则文件必须是一个JSON对象")
                return False, errors, rule_ids
                
            if "rules" not in data:
                errors.append("缺少'rules'字段")
                return False, errors, rule_ids
                
            if not isinstance(data["rules"], list):
                errors.append("'rules'字段必须是一个数组")
                return False, errors, rule_ids
                
            # 校验每条规则
            for idx, rule in enumerate(data["rules"]):
                rule_errors = RuleValidator._validate_single_rule(rule, idx)
                if rule_errors:
                    errors.extend(rule_errors)
                    
                # 检查规则ID
                if "id" in rule:
                    if rule["id"] in rule_ids:
                        errors.append(f"发现重复的规则ID: {rule['id']}")
                    else:
                        rule_ids.add(rule["id"])
                        
            return len(errors) == 0, errors, rule_ids
            
        except Exception as e:
            errors.append(f"文件读取错误: {str(e)}")
            return False, errors, rule_ids
    
    @staticmethod
    def _validate_single_rule(rule: Dict, idx: int) -> List[str]:
        """校验单条规则"""
        errors = []
        
        # 检查必需字段
        required_fields = ["id", "name", "condition", "action", "enable"]
        for field in required_fields:
            if field not in rule:
                errors.append(f"规则 #{idx}: 缺少必需字段 '{field}'")
                
        # 检查字段类型
        if "enable" in rule and not isinstance(rule["enable"], bool):
            errors.append(f"规则 #{idx}: 'enable'字段必须是布尔值")
            
        # 校验条件
        if "condition" in rule:
            condition_errors = RuleValidator._validate_condition(rule["condition"], idx)
            errors.extend(condition_errors)
            
        # 校验动作
        if "action" in rule:
            action_errors = RuleValidator._validate_action(rule["action"], idx)
            errors.extend(action_errors)
            
        return errors
    
    @staticmethod
    def _validate_condition(condition: Dict, rule_idx: int) -> List[str]:
        """校验条件配置"""
        errors = []
        
        if not isinstance(condition, dict):
            errors.append(f"规则 #{rule_idx}: condition必须是一个对象")
            return errors
            
        if "type" not in condition:
            errors.append(f"规则 #{rule_idx}: condition缺少'type'字段")
            return errors
            
        condition_type = condition["type"]
        
        # 校验逻辑操作符
        if condition_type in ["and", "or"]:
            if "conditions" not in condition:
                errors.append(f"规则 #{rule_idx}: {condition_type}操作符缺少'conditions'字段")
            elif not isinstance(condition["conditions"], list):
                errors.append(f"规则 #{rule_idx}: {condition_type}操作符的'conditions'必须是数组")
            else:
                for sub_condition in condition["conditions"]:
                    errors.extend(RuleValidator._validate_condition(sub_condition, rule_idx))
                    
        # 校验not操作符
        elif condition_type == "not":
            if "condition" not in condition:
                errors.append(f"规则 #{rule_idx}: not操作符缺少'condition'字段")
            else:
                errors.extend(RuleValidator._validate_condition(condition["condition"], rule_idx))
                
        # 校验比较操作符
        elif condition_type in [">", "<", "==", "!=", ">=", "<="]:
            if "field" not in condition:
                errors.append(f"规则 #{rule_idx}: 比较操作符缺少'field'字段")
            if "value" not in condition:
                errors.append(f"规则 #{rule_idx}: 比较操作符缺少'value'字段")
                
        # 校验字符串操作符
        elif condition_type in ["string_contains", "string_starts_with"]:
            if "source_field" not in condition:
                errors.append(f"规则 #{rule_idx}: 字符串操作符缺少'source_field'字段")
            if "value" not in condition and "target_field" not in condition:
                errors.append(f"规则 #{rule_idx}: 字符串操作符必须包含'value'或'target_field'字段")
                
        # 校验存在性检查
        elif condition_type in ["exists", "not_exists"]:
            if "field" not in condition:
                errors.append(f"规则 #{rule_idx}: 存在性检查缺少'field'字段")
                
        # 校验范围检查
        elif condition_type == "in_range":
            if "field" not in condition:
                errors.append(f"规则 #{rule_idx}: 范围检查缺少'field'字段")
            if "min" not in condition or "max" not in condition:
                errors.append(f"规则 #{rule_idx}: 范围检查缺少'min'或'max'字段")
                
        # 校验列表操作符
        elif condition_type == "in_list":
            if "field" not in condition:
                errors.append(f"规则 #{rule_idx}: 列表操作符缺少'field'字段")
            if "values" not in condition or not isinstance(condition["values"], list):
                errors.append(f"规则 #{rule_idx}: 列表操作符的'values'必须是数组")
                
        else:
            errors.append(f"规则 #{rule_idx}: 不支持的条件类型 '{condition_type}'")
            
        return errors
    
    @staticmethod
    def _validate_action(action: Dict, rule_idx: int) -> List[str]:
        """校验动作配置"""
        errors = []
        
        if not isinstance(action, dict):
            errors.append(f"规则 #{rule_idx}: action必须是一个对象")
            return errors
            
        if "type" not in action:
            errors.append(f"规则 #{rule_idx}: action缺少'type'字段")
            
        if action.get("type") != "notify":
            errors.append(f"规则 #{rule_idx}: 目前只支持'notify'类型的动作")
            
        if "channel" not in action:
            errors.append(f"规则 #{rule_idx}: action缺少'channel'字段")
        
        # 校验transaction字段 - 如果存在则必须是布尔值
        if "transaction" in action and not isinstance(action["transaction"], bool):
            errors.append(f"规则 #{rule_idx}: action的'transaction'字段必须是布尔值")
            
        return errors


def validate_rules_directory(rules_dir: str) -> bool:
    """
    校验整个规则目录
    
    Args:
        rules_dir: 规则目录路径
        
    Returns:
        bool: 是否全部验证通过
    """
    if not os.path.exists(rules_dir):
        print(f"❌ 规则目录不存在: {rules_dir}")
        return False
        
    all_valid = True
    all_rule_ids = set()
    
    # 遍历所有JSON文件
    for filename in os.listdir(rules_dir):
        if not filename.endswith('.json'):
            continue
            
        file_path = os.path.join(rules_dir, filename)
        print(f"\n📝 校验文件: {filename}")
        
        # 校验单个文件
        is_valid, errors, rule_ids = RuleValidator.validate_rule_file(file_path)
        
        # 检查跨文件的ID重复
        duplicate_ids = rule_ids & all_rule_ids
        if duplicate_ids:
            print(f"❌ 发现跨文件重复的规则ID: {duplicate_ids}")
            is_valid = False
            
        all_rule_ids.update(rule_ids)
        
        # 输出校验结果
        if is_valid:
            print("✅ 验证通过")
        else:
            print("❌ 验证失败:")
            for error in errors:
                print(f"   - {error}")
            all_valid = False
            
    return all_valid


if __name__ == "__main__":
    # 使用示例
    rules_dir = "all_rules/"
    print("🔍 开始校验规则文件...")
    
    if validate_rules_directory(rules_dir):
        print("\n✨ 所有规则文件验证通过！")
    else:
        print("\n❌ 规则文件验证失败，请修复以上错误。") 