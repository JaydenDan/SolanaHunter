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

### 条件格式说明

condition 必须是一个对象，包含以下结构：

1. 单一条件：
```json
{
    "type": "比较操作符",
    "field": "要比较的字段",
    "value": "比较的值"
}
```

2. 逻辑组合条件：
```json
{
    "type": "逻辑操作符",
    "conditions": [
        {
            "type": "比较操作符",
            "field": "字段1",
            "value": "值1"
        },
        {
            "type": "比较操作符",
            "field": "字段2",
            "value": "值2"
        }
    ]
}
```

❌ 错误示例 - condition不能直接是数组：
```json
{
    "id": "wrong_rule",
    "name": "错误的规则",
    "enable": true,
    "condition": [  // 错误！condition不能是数组
        {
            "type": ">",
            "field": "solAmount",
            "value": 10
        },
        {
            "type": "exists",
            "field": "social"
        }
    ],
    "action": {
        "type": "notify",
        "channel": "telegram"
    }
}
```

✅ 正确示例 - 使用逻辑操作符组合多个条件：
```json
{
    "id": "correct_rule",
    "name": "正确的规则",
    "enable": true,
    "condition": {  // 正确！使用and/or操作符组合多个条件
        "type": "and",
        "conditions": [
            {
                "type": ">",
                "field": "solAmount",
                "value": 10
            },
            {
                "type": "exists",
                "field": "social"
            }
        ]
    },
    "action": {
        "type": "notify",
        "channel": "telegram"
    }
}
```

### 条件组合说明

1. 如果需要组合多个条件，必须使用逻辑操作符（and/or/not）：
   - `and`: 所有子条件都满足
   - `or`: 任一子条件满足
   - `not`: 对单个条件取反

2. 逻辑操作符可以嵌套使用：
```json
{
    "type": "or",
    "conditions": [
        {
            "type": "and",
            "conditions": [
                {
                    "type": ">",
                    "field": "solAmount",
                    "value": 10
                },
                {
                    "type": "exists",
                    "field": "social"
                }
            ]
        },
        {
            "type": ">",
            "field": "marketCapSol",
            "value": 1000
        }
    ]
}
```

3. `not` 操作符的特殊格式：
```json
{
    "type": "not",
    "condition": {  // 注意：not使用condition而不是conditions
        "type": "exists",
        "field": "social"
    }
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

## 数据格式说明

规则引擎处理的数据格式如下：

```json
{
    "signature": "交易签名（唯一标识）",
    "mint": "代币合约地址",
    "traderPublicKey": "交易者公钥",
    "dev_balance": "开发者余额",
    "entrepreneurial_attempts_count": "DEV创业次数",
    "symbol_count": "相同代币符号数量",
    "name_count": "相同代币名称数量",
    "txType": "交易类型（create/swap等）",
    "initialBuy": "初始购买金额（SOL）",
    "solAmount": "当前交易SOL金额",
    "bondingCurveKey": "弹性定价模型合约地址",
    "vTokensInBondingCurve": "盘子代币存量",
    "vSolInBondingCurve": "盘子SOL存量",
    "marketCapSol": "市值（SOL计价）",
    "name": "代币名称",
    "symbol": "代币符号",
    "uri": "代币元数据URI",
    "pool": "所属交易池",
    "detect_time": "检测时间",
    "social": {  // 可选字段，社交媒体数据
        "id": "推文ID",
        "text": "推文内容",
        "created_at": "发布时间（UTC+8）",
        "user": {
            "name": "用户名称",
            "screen_name": "用户屏幕名",
            "description": "用户简介",
            "verified": "是否认证",
            "is_blue_verified": "是否蓝V认证",
            "display_url": "显示URL",
            "expanded_url": "展开URL",
            "following_count": "关注数",
            "favourites_count": "点赞数",
            "followers_count": "总粉丝数",
            "fast_followers_count": "快速粉丝数",
            "normal_followers_count": "普通粉丝数"
        },
        "metrics": {
            "likes": "点赞数",
            "retweets": "转发数",
            "replies": "回复数",
            "view_count": "浏览数"
        }
    }
}
```

### 字段说明

#### 基础字段
- `signature`: 交易签名，用作唯一标识
- `mint`: 代币合约地址
- `traderPublicKey`: 交易者公钥
- `dev_balance`: 开发者余额
- `entrepreneurial_attempts_count`: DEV创业次数
- `txType`: 交易类型，如create、swap等
- `initialBuy`: 初始购买金额（SOL）
- `solAmount`: 当前交易SOL金额
- `bondingCurveKey`: Bonding Curve（弹性定价模型）的合约地址
- `vTokensInBondingCurve`: 盘子中的代币存量
- `vSolInBondingCurve`: 盘子中的SOL存量
- `marketCapSol`: 市值（SOL计价）
- `name`: 代币名称
- `symbol`: 代币符号
- `uri`: 代币元数据URI
- `pool`: 所属交易池
- `detect_time`: 检测时间

#### 社交媒体数据（可选）
`social`对象包含推特相关数据，此字段可能不存在。当编写规则时，建议先检查social字段是否存在。

##### 用户信息
- `user.name`: 用户名称
- `user.screen_name`: 用户屏幕名（@后的名称）
- `user.description`: 用户简介
- `user.verified`: 是否认证
- `user.is_blue_verified`: 是否蓝V认证
- `user.following_count`: 关注数
- `user.followers_count`: 总粉丝数
- `user.fast_followers_count`: 快速粉丝数
- `user.normal_followers_count`: 普通粉丝数

##### 推文指标
- `metrics.likes`: 点赞数
- `metrics.retweets`: 转发数
- `metrics.replies`: 回复数
- `metrics.view_count`: 浏览数

### 规则编写示例

1. 检查高价值交易：
```json
{
    "id": "high_value_trade",
    "name": "高价值交易检测",
    "enable": true,
    "condition": {
        "type": "and",
        "conditions": [
            {
                "type": ">",
                "field": "solAmount",
                "value": 10
            }
        ]
    },
    "action": {
        "type": "notify",
        "channel": "telegram"
    }
}
```

2. 检查高影响力用户交易：
```json
{
    "id": "influencer_trade",
    "name": "高影响力用户交易检测",
    "enable": true,
    "condition": {
        "type": "and",
        "conditions": [
            {
                "type": "exists",
                "field": "social"
            },
            {
                "type": ">",
                "field": "social.user.followers_count",
                "value": 10000
            }
        ]
    },
    "action": {
        "type": "notify",
        "channel": "telegram"
    }
}
```

### 注意事项

1. 在使用social相关字段时，务必先检查social字段是否存在：
```json
{
    "type": "exists",
    "field": "social"
}
```

2. 访问嵌套字段时使用点号（.）：
```json
"social.user.followers_count"
"social.metrics.view_count"
```

3. 数值比较时注意数据类型：
- 金额相关字段（solAmount、marketCapSol等）为浮点数
- 计数相关字段（followers_count、view_count等）为整数

4. 时间字段（detect_time、social.created_at）为ISO格式的字符串