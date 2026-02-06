"""
Feature: file_watcher  
Scenario: realtime_incremental_analysis
Description: 在 IDE 中编辑代码时,实时反馈代码质量

文件监听器 - 监听文件变更并触发增量分析
"""

from pathlib import Path
from typing import Callable, Optional, List
import time
import threading


class FileWatcher:
    """
    简单的文件监听器
    
    实现场景: 在 IDE 中编辑代码时,实时反馈代码质量
    
    特性:
    - 监听文件变更
    - 触发回调函数
    - 轻量级实现 (不依赖watchdog)
    """
    
    def __init__(
        self,
        directory: Path,
        pattern: str = "**/*.py",
        callback: Optional[Callable[[Path], None]] = None
    ):
        """
        初始化文件监听器
        
        Args:
            directory: 监听的目录
            pattern: 文件匹配模式
            callback: 文件变更时的回调函数
        """
        self.directory = directory
        self.pattern = pattern
        self.callback = callback
        self.file_mtimes: dict[str, float] = {}
        self.running = False
        self.thread: Optional[threading.Thread] = None
    
    def start(self, interval: float = 1.0):
        """
        开始监听
        
        Args:
            interval: 检查间隔 (秒)
        """
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._watch_loop, args=(interval,))
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """停止监听"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
    
    def _watch_loop(self, interval: float):
        """监听循环"""
        # 初始化文件修改时间
        self._scan_files()
        
        while self.running:
            time.sleep(interval)
            self._check_changes()
    
    def _scan_files(self):
        """扫描所有文件"""
        if not self.directory.exists():
            return
        
        for file_path in self.directory.glob(self.pattern):
            if file_path.is_file():
                try:
                    mtime = file_path.stat().st_mtime
                    self.file_mtimes[str(file_path)] = mtime
                except:
                    pass
    
    def _check_changes(self):
        """检查文件变更"""
        if not self.directory.exists():
            return
        
        current_files = set()
        
        # 检查修改和新增
        for file_path in self.directory.glob(self.pattern):
            if not file_path.is_file():
                continue
            
            file_str = str(file_path)
            current_files.add(file_str)
            
            try:
                mtime = file_path.stat().st_mtime
                old_mtime = self.file_mtimes.get(file_str)
                
                if old_mtime is None:
                    # 新文件
                    self.file_mtimes[file_str] = mtime
                    self._trigger_callback(file_path, "created")
                elif mtime > old_mtime:
                    # 文件修改
                    self.file_mtimes[file_str] = mtime
                    self._trigger_callback(file_path, "modified")
            except:
                pass
        
        # 检查删除
        deleted_files = set(self.file_mtimes.keys()) - current_files
        for file_str in deleted_files:
            del self.file_mtimes[file_str]
            self._trigger_callback(Path(file_str), "deleted")
    
    def _trigger_callback(self, file_path: Path, event_type: str):
        """触发回调"""
        if self.callback:
            try:
                self.callback(file_path)
            except Exception as e:
                print(f"Callback error: {e}")


# 便捷函数
def watch_directory(
    directory: Path,
    callback: Callable[[Path], None],
    pattern: str = "**/*.py",
    interval: float = 1.0
) -> FileWatcher:
    """
    监听目录变更
    
    Args:
        directory: 要监听的目录
        callback: 变更回调函数
        pattern: 文件匹配模式
        interval: 检查间隔
    
    Returns:
        FileWatcher: 监听器实例
    """
    watcher = FileWatcher(directory, pattern, callback)
    watcher.start(interval)
    return watcher
