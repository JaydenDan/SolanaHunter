from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio
import logging
import os
import time

class RuleFileHandler(FileSystemEventHandler):
    """规则文件变更处理器"""
    
    def __init__(self, callback):
        self.callback = callback
        self.modified_files = set()
        self.last_modified_time = {}  # 记录每个文件的最后修改时间
        self.debounce_interval = 1.0  # 防抖间隔，单位秒
        logging.info("🔍 规则文件变更处理器已初始化")
    
    def on_modified(self, event):
        """文件修改事件处理"""
        if event.is_directory:
            return
            
        if not event.src_path.endswith('.json'):
            return
        
        current_time = time.time()
        last_time = self.last_modified_time.get(event.src_path, 0)
        
        # 如果同一文件在防抖间隔内被多次修改，只处理最后一次
        if current_time - last_time < self.debounce_interval:
            logging.debug(f"⏱️ 文件 {event.src_path} 在防抖间隔内，忽略此次事件")
            return
            
        # 更新最后修改时间
        self.last_modified_time[event.src_path] = current_time
            
        # 添加到修改文件集合
        self.modified_files.add(event.src_path)
        logging.info(f"📝 检测到规则文件变更: {event.src_path}")
        
        # 直接调用回调
        self._call_callback()
    
    def on_created(self, event):
        """文件创建事件处理"""
        if event.is_directory:
            return
            
        if not event.src_path.endswith('.json'):
            return
        
        current_time = time.time()
        self.last_modified_time[event.src_path] = current_time
            
        # 添加到修改文件集合
        self.modified_files.add(event.src_path)
        logging.info(f"📝 检测到规则文件创建: {event.src_path}")
        
        # 直接调用回调
        self._call_callback()
    
    def on_deleted(self, event):
        """文件删除事件处理"""
        if event.is_directory:
            return
            
        if not event.src_path.endswith('.json'):
            return
            
        # 从时间记录中移除
        if event.src_path in self.last_modified_time:
            del self.last_modified_time[event.src_path]
            
        # 添加到修改文件集合（尽管文件已删除，但规则仍需更新）
        self.modified_files.add(event.src_path)
        logging.info(f"🗑️ 检测到规则文件删除: {event.src_path}")
        
        # 触发回调以重新加载规则
        self._call_callback()
    
    def on_moved(self, event):
        """文件移动事件处理"""
        # 检查源文件是否为JSON
        if not event.src_path.endswith('.json'):
            return
            
        # 检查目标文件是否为JSON
        if not event.dest_path.endswith('.json'):
            return
            
        # 更新时间记录
        if event.src_path in self.last_modified_time:
            self.last_modified_time[event.dest_path] = self.last_modified_time[event.src_path]
            del self.last_modified_time[event.src_path]
            
        # 添加源文件和目标文件到修改集合
        self.modified_files.add(event.src_path)
        self.modified_files.add(event.dest_path)
        logging.info(f"🔄 检测到规则文件移动: {event.src_path} -> {event.dest_path}")
        
        # 触发回调以重新加载规则
        self._call_callback()
    
    def _call_callback(self):
        """直接调用回调函数"""
        if not self.modified_files:
            return
            
        # 复制文件集合并清空
        files = self.modified_files.copy()
        self.modified_files.clear()
        
        try:
            logging.info(f"📣 触发规则更新回调，变更文件: {files}")
            # 同步调用回调
            self.callback(files)
            logging.info("✅ 规则更新回调执行成功")
        except Exception as e:
            logging.error(f"❌ 规则文件变更回调执行失败: {str(e)}", exc_info=True)


class RuleWatcher:
    """规则文件监控器"""
    
    def __init__(self, change_callback):
        self.change_callback = change_callback
        self.observer = None
        self.handler = None
    
    def start_watching(self, rules_dir):
        """开始监控规则目录"""
        if self.observer:
            return
        
        # 确保使用绝对路径
        abs_rules_dir = os.path.abspath(rules_dir)
        
        # 验证目录是否存在
        if not os.path.exists(abs_rules_dir):
            logging.error(f"❌ 规则目录不存在: {abs_rules_dir}")
            return
            
        # 创建事件处理器
        self.handler = RuleFileHandler(self.change_callback)
        
        # 创建观察者
        self.observer = Observer()
        self.observer.schedule(self.handler, abs_rules_dir, recursive=False)
        self.observer.start()
        
        logging.info(f"👀 开始监控规则目录: {abs_rules_dir}")
        logging.info(f"📁 当前目录中的文件: {os.listdir(abs_rules_dir)}")
    
    def stop_watching(self):
        """停止监控"""
        if self.observer:
            # 停止观察者线程
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logging.info("🛑 停止监控规则目录")