#!/bin/sh

# 获取脚本所在目录并切换到该目录
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

echo "🔍 开始校验规则文件..."
echo

# 初始化变量
all_valid=true
all_rule_ids=""

# 遍历当前目录下的所有JSON文件
for file in *.json; do
    [ -f "$file" ] || continue
    
    echo "📝 校验文件: $file"
    
    # 检查文件格式
    if ! grep -q "^{" "$file"; then
        echo "❌ JSON格式错误"
        all_valid=false
        continue
    fi
    
    # 检查rules字段
    if ! grep -q "\"rules\"" "$file"; then
        echo "❌ 缺少'rules'字段"
        all_valid=false
        continue
    fi
    
    # 提取并检查规则ID
    for id in $(grep -o '"id"[[:space:]]*:[[:space:]]*"[^"]*"' "$file" | cut -d'"' -f4); do
        if echo "$all_rule_ids" | grep -q "$id"; then
            echo "❌ 发现重复的规则ID: $id"
            all_valid=false
        else
            all_rule_ids="$all_rule_ids $id"
        fi
    done
    
    # 检查必需字段
    for field in name condition action enable; do
        if ! grep -q "\"$field\"" "$file"; then
            echo "❌ 缺少必需字段: '$field'"
            all_valid=false
        fi
    done
    
    if [ "$all_valid" = true ]; then
        echo "✅ 验证通过"
    fi
    
    echo
done

if [ "$all_valid" = true ]; then
    echo "✨ 所有规则文件验证通过！"
else
    echo "❌ 规则文件验证失败，请修复以上错误。"
fi

echo
echo "按回车键退出..."
read dummy 