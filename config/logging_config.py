import logging
import colorlog
import asyncio
from typing import Optional


def setup_logging(level=logging.INFO):
    """配置带颜色分级的日志系统"""

    formatter = colorlog.ColoredFormatter(
        (
            "%(log_color)s%(asctime)s "
            "[%(levelname).4s] "
            "[%(module)5.5s] "  # 模块名硬截断到10字符
            "[%(task_name)15.15s]: "  # 任务名称（通过Filter注入）
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

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(TaskNameFilter())  # 关键：注入 task_name

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


class TaskNameFilter(logging.Filter):
    """向日志记录中添加当前异步任务名称"""

    def filter(self, record) -> bool:
        task: Optional[asyncio.Task] = asyncio.current_task()
        record.task_name = task.get_name() if task else "main"
        return True
