#!/bin/bash

# 获取脚本所在目录并切换到该目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "🔍 开始校验规则文件..."
echo

# 初始化变量
declare -A rule_ids  # 使用关联数组存储规则ID
all_valid=true

# 检查JSON格式是否有效
validate_json() {
    if command -v jq &> /dev/null; then
        jq empty "$1" &> /dev/null
        return $?
    else
        # 如果没有jq，使用简单的格式检查
        grep -q "^{" "$1"
        return $?
    fi
}

# 检查字段是否存在
check_field() {
    local file=$1
    local field=$2
    if command -v jq &> /dev/null; then
        jq -e ".rules[].${field}" "$file" &> /dev/null
    else
        grep -q "\"${field}\"" "$file"
    fi
    return $?
}

# 提取规则ID
extract_rule_ids() {
    local file=$1
    if command -v jq &> /dev/null; then
        jq -r '.rules[].id' "$file" 2>/dev/null
    else
        grep -o '"id"[[:space:]]*:[[:space:]]*"[^"]*"' "$file" | cut -d'"' -f4
    fi
}

# 遍历当前目录下的所有JSON文件
for file in *.json; do
    [ -f "$file" ] || continue
    
    echo "📝 校验文件: $file"
    file_valid=true
    
    # 检查JSON格式
    if ! validate_json "$file"; then
        echo "❌ JSON格式错误"
        all_valid=false
        file_valid=false
        continue
    fi
    
    # 检查rules字段
    if ! check_field "$file" "rules"; then
        echo "❌ 缺少'rules'字段"
        all_valid=false
        file_valid=false
        continue
    fi
    
    # 提取并检查规则ID
    while read -r id; do
        if [[ -n "$id" ]]; then
            if [[ ${rule_ids[$id]+_} ]]; then
                echo "❌ 发现重复的规则ID: $id (在文件 ${rule_ids[$id]} 中已存在)"
                all_valid=false
                file_valid=false
            else
                rule_ids[$id]=$file
            fi
        fi
    done < <(extract_rule_ids "$file")
    
    # 检查必需字段
    for field in name condition action enable; do
        if ! check_field "$file" "$field"; then
            echo "❌ 缺少必需字段: '$field'"
            all_valid=false
            file_valid=false
        fi
    done
    
    if [[ "$file_valid" == true ]]; then
        echo "✅ 验证通过"
    fi
    
    echo
done

if [[ "$all_valid" == true ]]; then
    echo "✨ 所有规则文件验证通过！"
else
    echo "❌ 规则文件验证失败，请修复以上错误。"
fi

echo
echo "按回车键退出..."
read -p "" dummy 