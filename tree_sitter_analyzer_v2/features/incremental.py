"""
Feature: incremental_analysis
Scenario: realtime_incremental_analysis
Description: 在 IDE 中编辑代码时,实时反馈代码质量

Success Criteria:
    - single_file_latency_ms: 100
    - cache_hit_rate: 0.95
"""

from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
import hashlib
import time
from functools import lru_cache


@dataclass
class FileAnalysisCache:
    """文件分析缓存"""
    content_hash: str
    analysis_result: Dict[str, Any]
    timestamp: float
    hit_count: int = 0


class IncrementalAnalyzer:
    """
    增量分析器
    
    实现场景: 在 IDE 中编辑代码时,实时反馈代码质量
    用户目标: 单文件变更后 <100ms 给出反馈
    
    特性:
    - LRU 缓存 (避免重复分析)
    - 内容哈希检测变更
    - 快速响应 (<100ms)
    - 高缓存命中率 (>95%)
    """
    
    def __init__(self, cache_size: int = 1000):
        """
        初始化增量分析器
        
        Args:
            cache_size: 缓存大小 (文件数)
        """
        self.cache: Dict[str, FileAnalysisCache] = {}
        self.cache_size = cache_size
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
    
    def analyze_file(self, file_path: Path, content: Optional[str] = None) -> Dict[str, Any]:
        """
        增量分析单个文件
        
        Args:
            file_path: 文件路径
            content: 文件内容 (如果为 None,从文件读取)
        
        Returns:
            Dict: 分析结果
        """
        start_time = time.time()
        self.stats["total_requests"] += 1
        
        # 读取内容
        if content is None:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "latency_ms": (time.time() - start_time) * 1000
                }
        
        # 计算内容哈希
        content_hash = self._compute_hash(content)
        file_key = str(file_path)
        
        # 检查缓存
        if file_key in self.cache:
            cached = self.cache[file_key]
            if cached.content_hash == content_hash:
                # 缓存命中
                self.stats["cache_hits"] += 1
                cached.hit_count += 1
                result = cached.analysis_result.copy()
                result["from_cache"] = True
                result["latency_ms"] = (time.time() - start_time) * 1000
                return result
        
        # 缓存未命中,执行分析
        self.stats["cache_misses"] += 1
        analysis_result = self._analyze_content(content, file_path)
        
        # 更新缓存
        self._update_cache(file_key, content_hash, analysis_result)
        
        analysis_result["from_cache"] = False
        analysis_result["latency_ms"] = (time.time() - start_time) * 1000
        return analysis_result
    
    def _compute_hash(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _analyze_content(self, content: str, file_path: Path) -> Dict[str, Any]:
        """
        分析文件内容
        
        这里实现简单的分析,实际可以集成更复杂的分析工具
        """
        lines = content.split('\n')
        non_empty_lines = [l for l in lines if l.strip()]
        
        # 统计
        functions = len([l for l in lines if l.strip().startswith('def ')])
        classes = len([l for l in lines if l.strip().startswith('class ')])
        imports = len([l for l in lines if l.strip().startswith(('import ', 'from '))])
        
        # 简单的复杂度估算
        complexity = 1
        for line in lines:
            stripped = line.strip()
            if any(keyword in stripped for keyword in ['if ', 'for ', 'while ', 'elif ', 'except ']):
                complexity += 1
        
        # 代码质量提示
        issues = []
        if len(lines) > 500:
            issues.append({"type": "warning", "message": f"File too long: {len(lines)} lines"})
        if complexity > 50:
            issues.append({"type": "warning", "message": f"High complexity: {complexity}"})
        if len(non_empty_lines) == 0:
            issues.append({"type": "info", "message": "Empty file"})
        
        return {
            "success": True,
            "file": str(file_path),
            "lines": len(lines),
            "non_empty_lines": len(non_empty_lines),
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "complexity": complexity,
            "issues": issues,
        }
    
    def _update_cache(self, file_key: str, content_hash: str, analysis_result: Dict[str, Any]):
        """更新缓存 (LRU策略)"""
        # 如果缓存已满,删除最旧的
        if len(self.cache) >= self.cache_size:
            # 找到命中次数最少的
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].hit_count)
            del self.cache[oldest_key]
        
        # 添加到缓存
        self.cache[file_key] = FileAnalysisCache(
            content_hash=content_hash,
            analysis_result=analysis_result.copy(),
            timestamp=time.time(),
            hit_count=0
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self.stats["total_requests"]
        hits = self.stats["cache_hits"]
        misses = self.stats["cache_misses"]
        
        return {
            "total_requests": total,
            "cache_hits": hits,
            "cache_misses": misses,
            "cache_hit_rate": hits / total if total > 0 else 0,
            "cache_size": len(self.cache),
        }
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }


# 便捷函数
def create_analyzer(cache_size: int = 1000) -> IncrementalAnalyzer:
    """创建增量分析器"""
    return IncrementalAnalyzer(cache_size=cache_size)
