#!/bin/bash
# Solana Hunter 管理脚本
# 用法: ./hunter.sh {start|stop|force-stop|restart|force-restart|status}

# 配置
APP_NAME="Solana Hunter"
PYTHON_CMD="python3"
MAIN_SCRIPT="main.py"
PID_FILE="hunter.pid"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# 获取进程状态
get_status() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null; then
            print_message "$GREEN" "✅ $APP_NAME 正在运行 [PID: $pid]"
            return 0
        else
            print_message "$YELLOW" "⚠️ $APP_NAME 已崩溃，PID文件存在但进程不存在"
            return 1
        fi
    else
        print_message "$RED" "❌ $APP_NAME 未运行"
        return 2
    fi
}

# 启动程序
start() {
    print_message "$BLUE" "🚀 正在启动 $APP_NAME..."
    
    # 检查是否已运行
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null; then
            print_message "$YELLOW" "⚠️ $APP_NAME 已经在运行中 [PID: $pid]"
            return 1
        else
            print_message "$YELLOW" "⚠️ 检测到残留的PID文件，但进程不存在，将删除PID文件"
            rm -f "$PID_FILE"
        fi
    fi
    
    # 启动程序并将所有输出重定向到黑洞
    nohup $PYTHON_CMD $MAIN_SCRIPT > /dev/null 2>&1 &
    
    # 保存PID
    echo $! > "$PID_FILE"
    print_message "$GREEN" "✅ $APP_NAME 已成功启动 [PID: $!]"
    return 0
}

# 安全关闭
stop() {
    print_message "$BLUE" "🛑 正在安全关闭 $APP_NAME..."
    
    if [ ! -f "$PID_FILE" ]; then
        print_message "$YELLOW" "⚠️ PID文件不存在，$APP_NAME 可能未运行"
        return 1
    fi
    
    local pid=$(cat "$PID_FILE")
    if ! ps -p "$pid" > /dev/null; then
        print_message "$YELLOW" "⚠️ 进程 $pid 不存在，删除残留的PID文件"
        rm -f "$PID_FILE"
        return 1
    fi
    
    # 发送SIGINT信号（相当于Ctrl+C）来触发安全关闭流程
    kill -2 "$pid"
    
    # 等待最多30秒让程序安全关闭
    local timeout=600
    local count=0
    while ps -p "$pid" > /dev/null && [ $count -lt $timeout ]; do
        sleep 1
        ((count++))
        if [ $((count % 5)) -eq 0 ]; then
            print_message "$BLUE" "⏳ 等待程序安全关闭... ($count 秒)"
        fi
    done
    
    # 检查是否成功关闭
    if ps -p "$pid" > /dev/null; then
        print_message "$YELLOW" "⚠️ 程序在 $timeout 秒内未能安全关闭"
        return 1
    else
        rm -f "$PID_FILE"
        print_message "$GREEN" "✅ $APP_NAME 已安全关闭"
        return 0
    fi
}

# 强制关闭
force_stop() {
    print_message "$BLUE" "🔥 正在强制关闭 $APP_NAME..."
    
    if [ ! -f "$PID_FILE" ]; then
        print_message "$YELLOW" "⚠️ PID文件不存在，$APP_NAME 可能未运行"
        return 1
    fi
    
    local pid=$(cat "$PID_FILE")
    if ! ps -p "$pid" > /dev/null; then
        print_message "$YELLOW" "⚠️ 进程 $pid 不存在，删除残留的PID文件"
        rm -f "$PID_FILE"
        return 1
    fi
    
    # 发送SIGKILL信号强制终止进程
    kill -9 "$pid"
    
    # 等待进程终止
    sleep 1
    
    if ps -p "$pid" > /dev/null; then
        print_message "$RED" "❌ 无法强制终止进程 $pid"
        return 1
    else
        rm -f "$PID_FILE"
        print_message "$GREEN" "✅ $APP_NAME 已被强制终止"
        return 0
    fi
}

# 重启（安全关闭后再启动）
restart() {
    print_message "$BLUE" "🔄 正在重启 $APP_NAME..."
    
    # 先安全关闭
    stop
    
    # 短暂等待确保资源释放
    sleep 2
    
    # 启动
    start
}

# 强制重启
force_restart() {
    print_message "$BLUE" "🔄 正在强制重启 $APP_NAME..."
    
    # 强制关闭
    force_stop
    
    # 短暂等待确保资源释放
    sleep 2
    
    # 启动
    start
}

# 主程序逻辑
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    force-stop)
        force_stop
        ;;
    restart)
        restart
        ;;
    force-restart)
        force_restart
        ;;
    status)
        get_status
        ;;
    *)
        print_message "$YELLOW" "用法: $0 {start|stop|force-stop|restart|force-restart|status}"
        exit 1
        ;;
esac

exit 0 