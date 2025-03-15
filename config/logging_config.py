import logging
import colorlog
import asyncio
import os
import glob
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 由于config_loader可能会导入logging_config，
# 所以这里不能导入get_config，否则会产生循环导入问题
# 我们直接使用环境变量和默认值

def get_log_dir():
    """获取日志目录"""
    
    # 项目根目录
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    
    # 加载.env文件
    if os.path.exists(env_file):
        load_dotenv(env_file)
    
    # 获取日志目录
    log_dir = os.getenv("LOG_DIR", "logs")
    if not os.path.isabs(log_dir):
        log_dir = project_root / log_dir
    
    return Path(log_dir)


class TaskNameFilter(logging.Filter):
    """向日志记录中添加当前异步任务名称"""

    def filter(self, record) -> bool:
        try:
            task: Optional[asyncio.Task] = asyncio.current_task()
            record.task_name = task.get_name() if task else "main"
        except RuntimeError:
            # 没有运行中的事件循环时使用默认值
            record.task_name = "main"
        return True


def cleanup_old_logs(log_dir, days_to_keep=3):
    """
    清理旧的日志文件，只保留指定天数内的文件
    
    Args:
        log_dir: 日志目录
        days_to_keep: 要保留的天数
    """
    try:
        current_time = time.time()
        # 计算时间阈值（秒数）
        threshold = current_time - (days_to_keep * 24 * 60 * 60)
        
        # 获取所有日志文件
        log_files = glob.glob(os.path.join(log_dir, '*.log'))
        
        # 删除过期的日志文件
        for file_path in log_files:
            file_mtime = os.path.getmtime(file_path)
            if file_mtime < threshold:
                try:
                    os.remove(file_path)
                    print(f"删除过期日志文件: {file_path}")
                except Exception as e:
                    print(f"无法删除日志文件 {file_path}: {str(e)}")
    except Exception as e:
        print(f"清理日志文件时出错: {str(e)}")


def setup_logging(level=logging.INFO, days_to_keep=3):
    """配置带颜色分级的日志系统"""

    # 创建日志目录
    log_dir = get_log_dir()
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 清理旧日志
    cleanup_old_logs(log_dir, days_to_keep)

    formatter = colorlog.ColoredFormatter(
        (
            "%(log_color)s%(asctime)s "
            "[%(levelname).4s] "
            "[%(module)5.5s] "
            "[%(task_name)20.20s]: "
            "%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(TaskNameFilter())
    
    # 获取当前时间戳
    today = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    # INFO日志文件处理器
    info_log_file = os.path.join(log_dir, f'info_{today}.log')
    info_file_handler = RotatingFileHandler(
        info_log_file,
        maxBytes=50*1024*1024,  # 50MB
        backupCount=10,
        encoding='utf-8'
    )
    info_file_handler.setLevel(logging.INFO)
    info_file_handler.setFormatter(formatter)
    info_file_handler.addFilter(TaskNameFilter())
    
    # 错误日志文件处理器
    error_log_file = os.path.join(log_dir, f'error_{today}.log')
    error_file_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=50*1024*1024,  # 50MB
        backupCount=10,
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    error_file_handler.addFilter(TaskNameFilter())

    root_logger = logging.getLogger()
    # 清除之前的处理器
    for hdlr in root_logger.handlers[:]:
        root_logger.removeHandler(hdlr)
    
    root_logger.addHandler(console_handler)
    root_logger.addHandler(info_file_handler)
    root_logger.addHandler(error_file_handler)
    root_logger.setLevel(level)
    
    # 记录日志系统初始化
    root_logger.info(f"日志系统初始化完成，日志级别：{logging.getLevelName(level)}，日志文件将保留{days_to_keep}天")
    
    return root_logger


def get_logger(name):
    """
    获取带有指定名称的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        返回配置好的日志记录器
    """
    return logging.getLogger(name)
