# Solana Hunter 规则引擎

一个功能强大的规则引擎系统，支持复杂的条件判断和实时规则更新。

## 功能特点

- 🔄 支持实时规则文件更新
- 🎯 支持复杂的条件判断逻辑
- 📦 基于JSON的规则配置
- 🛡️ 内置规则验证机制
- 🔍 支持嵌套字段访问
- 🚀 高性能规则评估

## 规则文件格式

规则文件必须是JSON格式，存放在规则目录下。每个规则文件的基本结构如下：

```json
{
    "rules": [
        {
            "id": "rule_001",
            "name": "示例规则",
            "enable": true,
            "condition": {
                // 条件配置
            },
            "action": {
                "type": "notify",
                "channel": "telegram"
            }
        }
    ]
}
```

### 规则字段说明

- `id`: 规则唯一标识符
- `name`: 规则名称
- `enable`: 是否启用规则
- `condition`: 规则条件配置
- `action`: 规则触发后的动作

### 条件类型

规则引擎支持以下条件类型：

#### 1. 逻辑操作符

```json
{
    "type": "and",
    "conditions": [
        // 子条件列表
    ]
}
```

- `and`: 所有子条件都满足
- `or`: 任一子条件满足
- `not`: 条件取反

#### 2. 比较操作符

```json
{
    "type": ">",
    "field": "price",
    "value": 100
}
```

支持的操作符：
- `>`: 大于
- `<`: 小于
- `==`: 等于
- `!=`: 不等于
- `>=`: 大于等于
- `<=`: 小于等于

#### 3. 字符串操作符

```json
{
    "type": "string_contains",
    "source_field": "name",
    "value": "Test"
}
```

- `string_contains`: 字符串包含
- `string_starts_with`: 字符串开头匹配

#### 4. 存在性检查

```json
{
    "type": "exists",
    "field": "social.twitter"
}
```

- `exists`: 字段存在
- `not_exists`: 字段不存在

#### 5. 数值范围检查

```json
{
    "type": "in_range",
    "field": "price",
    "min": 10,
    "max": 100
}
```

#### 6. 列表操作符

```json
{
    "type": "in_list",
    "field": "category",
    "values": ["NFT", "Token"]
}
```

### 规则示例

以下是一个完整的规则示例：

```json
{
    "rules": [
        {
            "id": "high_value_token",
            "name": "高价值代币提醒",
            "enable": true,
            "condition": {
                "type": "and",
                "conditions": [
                    {
                        "type": ">",
                        "field": "price",
                        "value": 1000
                    },
                    {
                        "type": "exists",
                        "field": "social.twitter"
                    }
                ]
            },
            "action": {
                "type": "notify",
                "channel": "telegram"
            }
        }
    ]
}
```

## 使用方法

1. 创建规则目录（例如：`rules/`）
2. 在规则目录中创建JSON规则文件
3. 初始化规则引擎：

```python
from src.rules.rule_engine import RuleEngine

# 初始化规则引擎
engine = RuleEngine()
engine.initialize("rules/")

# 评估数据
token_data = {
    "price": 1500,
    "social": {
        "twitter": "@example"
    }
}

results = engine.evaluate(token_data)
```

## 注意事项

1. 规则文件修改后会自动重新加载，无需重启应用
2. 确保规则JSON格式正确，否则可能导致加载失败
3. 建议为每个规则指定一个唯一的ID
4. 使用`enable`字段来控制规则的启用/禁用状态
5. 复杂条件可以通过嵌套逻辑操作符来实现 