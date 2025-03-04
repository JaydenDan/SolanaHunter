import logging
import colorlog
import asyncio
from typing import Optional


def setup_logging(level=logging.INFO):
    """配置带颜色分级的日志系统"""
    
    # 设置第三方包的日志级别
    logging.getLogger('twikit').setLevel(logging.WARNING)
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)

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

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(TaskNameFilter())

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


class TaskNameFilter(logging.Filter):
    """向日志记录中添加当前异步任务名称"""

    def filter(self, record) -> bool:
        task: Optional[asyncio.Task] = asyncio.current_task()
        record.task_name = task.get_name() if task else "main"
        return True
