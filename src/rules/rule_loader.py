import os
import json
import logging

class RuleLoader:
    """规则加载器，从JSON文件加载规则"""
    
    def load_rules(self, rules_dir):
        """从目录加载所有规则"""
        rules = []
        
        # 确保目录存在
        if not os.path.exists(rules_dir):
            logging.error(f"❌ 规则目录不存在: {rules_dir}")
            return rules
        
        logging.info(f"📂 开始加载规则目录: {rules_dir}")
        
        # 查找所有JSON文件
        json_files = [f for f in os.listdir(rules_dir) if f.endswith('.json')]
        logging.info(f"📄 找到 {len(json_files)} 个JSON规则文件")
        
        for filename in json_files:
            file_path = os.path.join(rules_dir, filename)
            
            try:
                # 读取并解析JSON
                with open(file_path, 'r', encoding='utf-8') as f:
                    rule_data = json.load(f)
                
                # 检查规则格式
                if 'rules' not in rule_data:
                    logging.warning(f"⚠️ 文件 {filename} 格式错误，缺少'rules'字段")
                    continue
                
                # 获取规则列表
                file_rules = rule_data.get('rules', [])
                
                # 添加到总规则列表
                rules.extend(file_rules)
                
                logging.info(f"✅ 从 {filename} 加载了 {len(file_rules)} 条规则")
                
            except json.JSONDecodeError as e:
                logging.error(f"❌ 文件 {filename} JSON解析错误: {str(e)}")
            except Exception as e:
                logging.error(f"❌ 加载文件 {filename} 失败: {str(e)}")
        
        logging.info(f"📊 总共加载了 {len(rules)} 条规则")
        return rules
    
    def validate_rule(self, rule):
        """验证规则格式是否正确"""
        required_fields = ['id', 'name', 'condition', 'action', 'enable']
        
        for field in required_fields:
            if field not in rule:
                return False, f"缺少必填字段: {field}"
        
        # 验证条件格式
        valid, message = self._validate_condition(rule['condition'])
        if not valid:
            return False, f"条件格式错误: {message}"
        
        # 验证动作格式
        if rule['action'].get('type') != 'notify':
            return False, "仅支持notify类型的动作"
        
        if 'channel' not in rule['action']:
            return False, "动作缺少channel字段"
        
        return True, "验证通过"
    
    def _validate_condition(self, condition):
        """验证条件格式"""
        if not isinstance(condition, dict) or 'type' not in condition:
            return False, "条件必须是包含type字段的对象"
        
        condition_type = condition['type']
        
        # 逻辑操作符验证
        if condition_type in ['and', 'or']:
            if 'conditions' not in condition or not isinstance(condition['conditions'], list):
                return False, f"{condition_type}操作符必须包含conditions数组"
            
            for sub_condition in condition['conditions']:
                valid, message = self._validate_condition(sub_condition)
                if not valid:
                    return False, message
        
        elif condition_type == 'not':
            if 'condition' not in condition:
                return False, "not操作符必须包含condition字段"
            
            return self._validate_condition(condition['condition'])
        
        # 其他验证逻辑...
        
        return True, "验证通过"