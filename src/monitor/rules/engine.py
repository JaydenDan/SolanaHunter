import yaml
from pathlib import Path
from typing import Dict, Any
from .conditions import load_condition  # 修正函数名


class RuleEngine:
    """动态规则引擎（简化版）"""

    def __init__(self, rule_path: Path):
        self.rule_path = Path(rule_path)
        self.rules = []
        self.last_load = 0
        self.reload_rules()

    def reload_rules(self):
        """加载/重载规则配置"""
        with open(self.rule_path) as f:
            config = yaml.safe_load(f)
            # self.rules = [
            #     {
            #         'name': rule['name'],
            #         'conditions': [
            #             load_condition(cond['type'])(**cond)
            #             for cond in rule['conditions']
            #         ],
            #         'actions': rule.get('actions', [])
            #     }
            #     for rule in config['rules']
            # ]

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """评估当前上下文是否满足任意规则"""
        return any(
            all(cond.check(context) for cond in rule['conditions'])
            for rule in self.rules
        )