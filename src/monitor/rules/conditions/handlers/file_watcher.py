import logging
from watchdog.events import FileSystemEventHandler
from pathlib import Path


class RuleFileHandler(FileSystemEventHandler):
    """配置文件变更处理器"""

    def __init__(self, config_path: Path, reload_callback):
        self.config_path = Path(config_path).resolve()
        self.reload_callback = reload_callback
        self.logger = logging.getLogger(__name__)

    def on_modified(self, event):
        """处理文件修改事件"""
        if Path(event.src_path).resolve() == self.config_path:
            self.logger.info("检测到配置文件变更")
            self.reload_callback()

    def on_created(self, event):
        """处理文件创建事件（防止文件被替换）"""
        if Path(event.src_path).resolve() == self.config_path:
            self.logger.warning("配置文件被重新创建")
            self.reload_callback()