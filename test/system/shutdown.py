import time
import sys

# 准备加载动画符号
spinner = ["🌑️", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
spinner2 = [" 🟢", " ⚪"]
spinner_index = 0
spinner_index2 = 0
while True:
    spinner_char = spinner[spinner_index % len(spinner)]
    spinner_index += 1
    spinner_char2 = spinner2[spinner_index2 % len(spinner2)]
    spinner_index2 += 1
    # 输出带动画的日志（使用 f-string 格式化保持简洁）
    # 使用 \r 实现行首覆盖，末尾保留空格防止残留字符
    # 使用 rich 的动态更新
    # sys.stdout.write(f"\r⌛️ 等待任务完成 ({1}/{2} 剩余) {spinner_char} ")
    sys.stdout.write(f"\r⌛️ 等待任务完成 ({1}/{2} 剩余) {spinner_char2} ")
    sys.stdout.flush()
    sys.stdout.write('\n')
    time.sleep(0.5)
