"""
Feature: parallel_analysis
Scenario: large_project_analysis
Description: 分析包含 1000+ 文件的大型 Python 项目

Success Criteria:
    - files: 1000
    - max_duration_seconds: 10
    - max_memory_mb: 500
"""

from pathlib import Path
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import os


@dataclass
class AnalysisResult:
    """分析结果"""
    total_files: int = 0
    success_files: int = 0
    failed_files: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    duration: float = 0.0


class ParallelAnalyzer:
    """
    并行代码分析器
    
    实现场景: 分析包含 1000+ 文件的大型 Python 项目
    用户目标: 在 10 秒内完成全量分析
    
    特性:
    - 多线程并行处理 (I/O 密集型)
    - 进度回调
    - 内存优化
    - 错误处理
    """
    
    def __init__(self, max_workers: Optional[int] = None, use_processes: bool = False):
        """
        初始化并行分析器
        
        Args:
            max_workers: 最大工作线程/进程数,默认为 CPU 核心数 * 2
            use_processes: 是否使用进程池 (CPU密集) 而不是线程池 (I/O密集)
        """
        self.max_workers = max_workers or (os.cpu_count() or 4) * 2
        self.use_processes = use_processes
    
    def analyze_directory(
        self,
        directory: Path,
        pattern: str = "**/*.py",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> AnalysisResult:
        """
        并行分析目录中的所有文件
        
        Args:
            directory: 要分析的目录
            pattern: 文件匹配模式
            progress_callback: 进度回调函数 (current, total)
        
        Returns:
            AnalysisResult: 分析结果
        """
        import time
        
        start_time = time.time()
        result = AnalysisResult()
        
        # 检查目录是否存在
        if not directory.exists():
            return result
        
        # 收集所有文件
        files = list(directory.glob(pattern))
        result.total_files = len(files)
        
        if result.total_files == 0:
            return result
        
        # 并行分析
        if self.max_workers == 1:
            # 串行模式
            for i, file_path in enumerate(files):
                file_result = self._analyze_single_file(file_path)
                if file_result.get("success"):
                    result.success_files += 1
                    result.results.append(file_result)
                else:
                    result.failed_files += 1
                    result.errors.append(file_result.get("error", {}))
                
                if progress_callback:
                    progress_callback(i + 1, result.total_files)
        else:
            # 并行模式 - 使用线程池 (I/O 密集) 或进程池 (CPU 密集)
            ExecutorClass = ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor
            completed = 0
            
            with ExecutorClass(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_file = {
                    executor.submit(self._analyze_single_file, file_path): file_path
                    for file_path in files
                }
                
                # 收集结果
                for future in as_completed(future_to_file):
                    completed += 1
                    try:
                        file_result = future.result()
                        if file_result.get("success"):
                            result.success_files += 1
                            result.results.append(file_result)
                        else:
                            result.failed_files += 1
                            result.errors.append(file_result.get("error", {}))
                    except Exception as e:
                        result.failed_files += 1
                        result.errors.append({
                            "file": str(future_to_file[future]),
                            "error": str(e)
                        })
                    
                    if progress_callback:
                        progress_callback(completed, result.total_files)
        
        result.duration = time.time() - start_time
        return result
    
    @staticmethod
    def _analyze_single_file(file_path: Path) -> dict[str, Any]:
        """
        分析单个文件
        
        Args:
            file_path: 文件路径
        
        Returns:
            dict: 分析结果
        """
        try:
            # 读取文件
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            
            # 简单的统计分析
            lines = content.split('\n')
            non_empty_lines = [l for l in lines if l.strip()]
            
            # 统计函数和类
            functions = len([l for l in lines if l.strip().startswith('def ')])
            classes = len([l for l in lines if l.strip().startswith('class ')])
            
            return {
                "success": True,
                "file": str(file_path),
                "lines": len(lines),
                "non_empty_lines": len(non_empty_lines),
                "functions": functions,
                "classes": classes,
            }
        except Exception as e:
            return {
                "success": False,
                "error": {
                    "file": str(file_path),
                    "error": str(e)
                }
            }


# 辅助函数
def analyze_project(
    directory: Path,
    max_workers: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> AnalysisResult:
    """
    便捷函数: 分析整个项目
    
    Args:
        directory: 项目目录
        max_workers: 最大工作进程数
        progress_callback: 进度回调
    
    Returns:
        AnalysisResult: 分析结果
    """
    analyzer = ParallelAnalyzer(max_workers=max_workers)
    return analyzer.analyze_directory(directory, progress_callback=progress_callback)
