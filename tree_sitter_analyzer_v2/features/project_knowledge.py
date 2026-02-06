"""
Project Knowledge Engine - 项目知识图谱系统

核心功能:
1. 构建项目知识快照 (全量扫描, 初始化时1次)
2. 超压缩格式存储 (<500 tokens覆盖整个项目)
3. 增量更新机制 (基于MD5, 只更新变更文件)
4. 毫秒级查询 (从缓存读取)

格式示例:
PROJECT_SNAPSHOT v1.0 | Files:156 | Functions:892 | Updated:2026-02-06T12:00:00

FILE::FUNC → CALLS[func1,func2] ← CALLED_BY[func3,func4] | I:high
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tree_sitter_analyzer_v2.features.refactoring_analyzer import RefactoringAnalyzer
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    file: Path
    calls: List[str] = field(default_factory=list)  # 调用的函数
    called_by: List[str] = field(default_factory=list)  # 被谁调用
    impact_score: int = 0  # 影响度分数
    impact_level: str = "low"  # high/medium/low


@dataclass
class ProjectSnapshot:
    """项目知识快照"""
    version: str = "1.0"
    timestamp: str = ""
    total_files: int = 0
    total_functions: int = 0
    functions: Dict[str, FunctionInfo] = field(default_factory=dict)
    file_hashes: Dict[str, str] = field(default_factory=dict)  # 文件MD5缓存
    
    def to_compact_format(self, max_functions: int = 50) -> str:
        """
        转换为超压缩格式
        
        Args:
            max_functions: 最多包含多少个函数 (按影响度排序)
        
        Returns:
            压缩后的字符串 (<500 tokens)
        """
        lines = [
            f"PROJECT_SNAPSHOT v{self.version} | Files:{self.total_files} | "
            f"Functions:{self.total_functions} | Updated:{self.timestamp}",
            ""
        ]
        
        # 按影响度排序
        sorted_funcs = sorted(
            self.functions.values(),
            key=lambda f: f.impact_score,
            reverse=True
        )[:max_functions]
        
        # 分组输出
        high_impact = [f for f in sorted_funcs if f.impact_level == "high"]
        medium_impact = [f for f in sorted_funcs if f.impact_level == "medium"]
        low_impact = [f for f in sorted_funcs if f.impact_level == "low"]
        
        if high_impact:
            lines.append("# HIGH IMPACT")
            for func in high_impact:
                lines.append(self._format_function(func))
            lines.append("")
        
        if medium_impact:
            lines.append("# MEDIUM IMPACT")
            for func in medium_impact:
                lines.append(self._format_function(func))
            lines.append("")
        
        if low_impact:
            lines.append("# LOW IMPACT")
            for func in low_impact:
                lines.append(self._format_function(func))
        
        return "\n".join(lines)
    
    def _format_function(self, func: FunctionInfo) -> str:
        """格式化单个函数信息"""
        file_name = func.file.name
        
        # 只显示跨文件调用
        calls = [c for c in func.calls if not c.startswith(file_name)]
        called_by = [c for c in func.called_by if not c.startswith(file_name)]
        
        calls_str = f"[{','.join(calls[:5])}]" if calls else "[]"
        called_by_str = f"[{','.join(called_by[:5])}]" if called_by else "[]"
        
        return f"{file_name}::{func.name} → {calls_str} ← {called_by_str} | I:{func.impact_level}"


class ProjectKnowledgeEngine:
    """
    项目知识引擎
    
    核心功能:
    - build_snapshot(): 构建完整项目快照
    - get_function_impact(): 获取函数影响范围
    - get_hotspots(): 获取热点函数
    - incremental_update(): 增量更新
    """
    
    def __init__(self, project_root: Path):
        """
        初始化知识引擎
        
        Args:
            project_root: 项目根目录
        """
        self.project_root = Path(project_root).resolve()
        self.cache_dir = self.project_root / ".analysis"
        self.cache_file = self.cache_dir / "knowledge_snapshot.json"
        self.snapshot_text_file = self.cache_dir / "knowledge_snapshot.txt"
        
        self.analyzer = RefactoringAnalyzer(max_depth=10)
        self.graph_builder = CodeGraphBuilder(language="python")
        
        self.snapshot: Optional[ProjectSnapshot] = None
    
    def build_snapshot(
        self,
        pattern: str = "**/*.py",
        force: bool = False
    ) -> ProjectSnapshot:
        """
        构建项目知识快照
        
        Args:
            pattern: 文件匹配模式
            force: 强制重新构建 (忽略缓存)
        
        Returns:
            ProjectSnapshot: 项目快照
        """
        # 检查缓存
        if not force and self._load_from_cache():
            return self.snapshot
        
        print("构建项目知识快照...")
        
        # 1. 扫描所有Python文件
        files = list(self.project_root.glob(pattern))
        print(f"发现 {len(files)} 个文件")
        
        # 2. 使用RefactoringAnalyzer分析
        self.analyzer.analyze_directory(self.project_root, pattern)
        
        # 3. 提取函数信息
        functions: Dict[str, FunctionInfo] = {}
        
        # 从analyzer中提取函数定义
        for func_name, file_list in self.analyzer.function_defs.items():
            for file_path in file_list:
                key = f"{file_path.name}::{func_name}"
                functions[key] = FunctionInfo(
                    name=func_name,
                    file=file_path
                )
        
        # 提取调用关系
        for file_path, calls_dict in self.analyzer.function_calls.items():
            for called_func, call_sites in calls_dict.items():
                for call_site in call_sites:
                    caller_key = f"{file_path.name}::{call_site.function_name}"
                    callee_key = f"{call_site.file.name}::{called_func}"
                    
                    # 记录调用关系
                    if caller_key in functions:
                        if callee_key not in functions[caller_key].calls:
                            functions[caller_key].calls.append(callee_key)
                    
                    if callee_key in functions:
                        if caller_key not in functions[callee_key].called_by:
                            functions[callee_key].called_by.append(caller_key)
        
        # 4. 计算影响度
        for func in functions.values():
            func.impact_score = self._calculate_impact_score(func)
            func.impact_level = self._calculate_impact_level(func.impact_score)
        
        # 5. 计算文件哈希
        file_hashes = {}
        for file_path in files:
            try:
                content = file_path.read_bytes()
                file_hashes[str(file_path)] = hashlib.md5(content).hexdigest()
            except Exception:
                pass
        
        # 6. 创建快照
        self.snapshot = ProjectSnapshot(
            timestamp=datetime.now().isoformat(),
            total_files=len(files),
            total_functions=len(functions),
            functions=functions,
            file_hashes=file_hashes
        )
        
        # 7. 保存缓存
        self._save_to_cache()
        
        print(f"✅ 快照构建完成: {len(functions)} 个函数")
        return self.snapshot
    
    def get_function_impact(self, function_name: str) -> Optional[Dict[str, Any]]:
        """
        获取函数影响范围
        
        Args:
            function_name: 函数名 (支持 "file::func" 或 "func")
        
        Returns:
            影响信息字典
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            return None
        
        # 查找函数
        func_info = None
        if "::" in function_name:
            # 精确匹配
            func_info = self.snapshot.functions.get(function_name)
        else:
            # 模糊匹配 (只根据函数名)
            for key, info in self.snapshot.functions.items():
                if info.name == function_name:
                    func_info = info
                    break
        
        if not func_info:
            return None
        
        # 统计影响范围
        affected_files = set()
        for caller in func_info.called_by:
            file_name = caller.split("::")[0]
            affected_files.add(file_name)
        
        return {
            "function": func_info.name,
            "file": func_info.file.name,
            "callers": func_info.called_by,
            "callees": func_info.calls,
            "impact_score": func_info.impact_score,
            "impact_level": func_info.impact_level,
            "affected_files": len(affected_files),
            "files_list": list(affected_files),
        }
    
    def get_hotspots(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """
        获取热点函数 (被调用最多的N个)
        
        Args:
            top_n: 返回前N个热点
        
        Returns:
            热点函数列表
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            return []
        
        # 按影响度排序
        sorted_funcs = sorted(
            self.snapshot.functions.values(),
            key=lambda f: f.impact_score,
            reverse=True
        )[:top_n]
        
        return [
            {
                "function": f.name,
                "file": f.file.name,
                "impact_score": f.impact_score,
                "impact_level": f.impact_level,
                "called_by_count": len(f.called_by),
                "calls_count": len(f.calls),
            }
            for f in sorted_funcs
        ]
    
    def load_snapshot(self, max_functions: int = 50) -> str:
        """
        加载快照的压缩文本格式
        
        Args:
            max_functions: 最多包含多少个函数
        
        Returns:
            压缩文本
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            return "No snapshot available. Run build_snapshot() first."
        
        return self.snapshot.to_compact_format(max_functions)
    
    def incremental_update(self, changed_files: List[Path]) -> bool:
        """
        增量更新 (只重新分析变更的文件)
        
        Args:
            changed_files: 变更的文件列表
        
        Returns:
            是否更新成功
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            # 没有快照, 执行全量构建
            self.build_snapshot()
            return True
        
        print(f"增量更新: {len(changed_files)} 个文件")
        
        # 检查哪些文件真正变更了 (MD5)
        actually_changed = []
        for file_path in changed_files:
            try:
                content = file_path.read_bytes()
                new_hash = hashlib.md5(content).hexdigest()
                old_hash = self.snapshot.file_hashes.get(str(file_path))
                
                if new_hash != old_hash:
                    actually_changed.append(file_path)
                    self.snapshot.file_hashes[str(file_path)] = new_hash
            except Exception:
                pass
        
        if not actually_changed:
            print("✅ 无实质变更")
            return True
        
        print(f"实际变更: {len(actually_changed)} 个文件")
        
        # 重新构建快照 (简化版: 全量重建)
        # TODO: 实现真正的增量更新
        self.build_snapshot(force=True)
        
        return True
    
    def _calculate_impact_score(self, func: FunctionInfo) -> int:
        """
        计算影响度分数
        
        算法:
        impact_score = 被调用次数 * 2 + 调用该函数的文件数 * 3 + 调用链深度 * 1
        """
        called_by_count = len(func.called_by)
        
        # 计算跨文件调用数
        cross_file_callers = set()
        for caller in func.called_by:
            caller_file = caller.split("::")[0]
            if caller_file != func.file.name:
                cross_file_callers.add(caller_file)
        
        # 简化的深度计算 (基于调用者数量)
        depth = min(len(func.called_by), 10)
        
        score = (
            called_by_count * 2 +
            len(cross_file_callers) * 3 +
            depth * 1
        )
        
        return score
    
    def _calculate_impact_level(self, score: int) -> str:
        """计算影响等级"""
        if score > 20:
            return "high"
        elif score > 10:
            return "medium"
        else:
            return "low"
    
    def _save_to_cache(self):
        """保存快照到缓存"""
        if not self.snapshot:
            return
        
        # 确保目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存JSON格式 (用于程序读取)
        cache_data = {
            "version": self.snapshot.version,
            "timestamp": self.snapshot.timestamp,
            "total_files": self.snapshot.total_files,
            "total_functions": self.snapshot.total_functions,
            "file_hashes": self.snapshot.file_hashes,
            "functions": {
                key: {
                    "name": f.name,
                    "file": str(f.file),
                    "calls": f.calls,
                    "called_by": f.called_by,
                    "impact_score": f.impact_score,
                    "impact_level": f.impact_level,
                }
                for key, f in self.snapshot.functions.items()
            }
        }
        
        self.cache_file.write_text(
            json.dumps(cache_data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        
        # 保存文本格式 (用于Agent快速读取)
        compact_text = self.snapshot.to_compact_format(max_functions=50)
        self.snapshot_text_file.write_text(compact_text, encoding='utf-8')
        
        print(f"💾 快照已缓存: {self.cache_file}")
    
    def _load_from_cache(self) -> bool:
        """从缓存加载快照"""
        if not self.cache_file.exists():
            return False
        
        try:
            cache_data = json.loads(self.cache_file.read_text(encoding='utf-8'))
            
            functions = {}
            for key, f_data in cache_data["functions"].items():
                functions[key] = FunctionInfo(
                    name=f_data["name"],
                    file=Path(f_data["file"]),
                    calls=f_data["calls"],
                    called_by=f_data["called_by"],
                    impact_score=f_data["impact_score"],
                    impact_level=f_data["impact_level"]
                )
            
            self.snapshot = ProjectSnapshot(
                version=cache_data["version"],
                timestamp=cache_data["timestamp"],
                total_files=cache_data["total_files"],
                total_functions=cache_data["total_functions"],
                functions=functions,
                file_hashes=cache_data["file_hashes"]
            )
            
            print(f"✅ 从缓存加载快照: {self.snapshot.total_functions} 个函数")
            return True
        except Exception as e:
            print(f"❌ 加载缓存失败: {e}")
            return False


# 便捷函数
def build_project_knowledge(
    project_root: Path,
    force: bool = False
) -> ProjectSnapshot:
    """
    构建项目知识快照 (便捷函数)
    
    Args:
        project_root: 项目根目录
        force: 强制重新构建
    
    Returns:
        ProjectSnapshot
    """
    engine = ProjectKnowledgeEngine(project_root)
    return engine.build_snapshot(force=force)


def get_function_safety(
    project_root: Path,
    function_name: str
) -> Optional[Dict[str, Any]]:
    """
    获取函数重构安全性信息 (便捷函数)
    
    Args:
        project_root: 项目根目录
        function_name: 函数名
    
    Returns:
        安全性信息
    """
    engine = ProjectKnowledgeEngine(project_root)
    impact = engine.get_function_impact(function_name)
    
    if not impact:
        return None
    
    # 添加安全性建议
    level = impact["impact_level"]
    
    if level == "high":
        recommendation = "⚠️  需要谨慎: 高影响函数,可能影响多个模块"
        safe = False
    elif level == "medium":
        recommendation = "⚡ 中等影响: 建议充分测试"
        safe = True
    else:
        recommendation = "✅ 安全: 低影响函数"
        safe = True
    
    return {
        **impact,
        "safe_to_refactor": safe,
        "recommendation": recommendation
    }
