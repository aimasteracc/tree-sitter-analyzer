"""
Project Knowledge Engine - Instant project understanding system

Core Features:
1. Build project knowledge snapshot (full scan, once on init)
2. Ultra-compact format storage (<500 tokens covering entire project)
3. Incremental update mechanism (MD5-based, update only changed files)
4. Millisecond-level queries (cached reads)

Format Example:
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


# Configuration constants - flexible, no hardcoding
DEFAULT_CACHE_DIR = ".analysis"
DEFAULT_CACHE_FILE = "project_snapshot.json"
DEFAULT_MAX_FUNCTIONS = 50
IMPACT_THRESHOLD_HIGH = 20
IMPACT_THRESHOLD_MEDIUM = 10
IMPACT_WEIGHT_CALLER = 2
IMPACT_WEIGHT_CROSS_FILE = 3
IMPACT_WEIGHT_DEPTH = 1


@dataclass
class FunctionInfo:
    """Function information data structure"""
    name: str
    file: Path
    calls: List[str] = field(default_factory=list)  # Functions called
    called_by: List[str] = field(default_factory=list)  # Called by whom
    impact_score: int = 0  # Impact score
    impact_level: str = "low"  # high/medium/low


@dataclass
class ProjectSnapshot:
    """Project knowledge snapshot"""
    version: str = "1.0"
    timestamp: str = ""
    total_files: int = 0
    total_functions: int = 0
    functions: Dict[str, FunctionInfo] = field(default_factory=dict)
    file_hashes: Dict[str, str] = field(default_factory=dict)  # File MD5 cache
    
    def to_compact_format(self, max_functions: int = DEFAULT_MAX_FUNCTIONS) -> str:
        """
        Convert to ultra-compact format
        
        Args:
            max_functions: Maximum functions to include (sorted by impact)
        
        Returns:
            Compressed string (<500 tokens)
        """
        lines = [
            f"PROJECT_SNAPSHOT v{self.version} | Files:{self.total_files} | "
            f"Functions:{self.total_functions} | Updated:{self.timestamp}",
            ""
        ]
        
        # Sort by impact score
        sorted_funcs = sorted(
            self.functions.values(),
            key=lambda f: f.impact_score,
            reverse=True
        )[:max_functions]
        
        # Group by impact level
        impact_groups = {
            "high": [],
            "medium": [],
            "low": []
        }
        for func in sorted_funcs:
            impact_groups[func.impact_level].append(func)
        
        # Output grouped functions
        for level in ["high", "medium", "low"]:
            if impact_groups[level]:
                lines.append(f"# {level.upper()} IMPACT")
                for func in impact_groups[level]:
                    lines.append(self._format_function(func))
                lines.append("")
        
        return "\n".join(lines)
    
    def _format_function(self, func: FunctionInfo) -> str:
        """
        Format single function information
        
        Only shows cross-file calls to reduce noise
        """
        file_name = func.file.name
        
        # Only show cross-file calls
        calls = [c for c in func.calls if not c.startswith(file_name)]
        called_by = [c for c in func.called_by if not c.startswith(file_name)]
        
        # Limit to first 5 to keep compact
        max_display = 5
        calls_str = f"[{','.join(calls[:max_display])}]" if calls else "[]"
        called_by_str = f"[{','.join(called_by[:max_display])}]" if called_by else "[]"
        
        return f"{file_name}::{func.name} → {calls_str} ← {called_by_str} | I:{func.impact_level}"


class ProjectKnowledgeEngine:
    """
    Project Knowledge Engine - Core component for instant project understanding
    
    Key Features:
    - build_snapshot(): Build complete project snapshot
    - get_function_impact(): Get function impact analysis
    - get_hotspots(): Get hotspot functions
    - incremental_update(): Incremental cache update
    """
    
    def __init__(self, project_root: Path):
        """
        Initialize knowledge engine
        
        Args:
            project_root: Project root directory
        """
        self.project_root = Path(project_root).resolve()
        self.cache_dir = self.project_root / DEFAULT_CACHE_DIR
        self.cache_file = self.cache_dir / DEFAULT_CACHE_FILE
        self.snapshot_text_file = self.cache_dir / "knowledge_snapshot.txt"
        
        # Use refactoring analyzer for call chain analysis
        self.analyzer = RefactoringAnalyzer(max_depth=10)
        
        self.snapshot: Optional[ProjectSnapshot] = None
    
    def build_snapshot(
        self,
        pattern: str = "**/*.py",
        force: bool = False
    ) -> ProjectSnapshot:
        """
        Build project knowledge snapshot
        
        Args:
            pattern: File matching pattern
            force: Force rebuild (ignore cache)
        
        Returns:
            ProjectSnapshot: Project snapshot
        """
        # Check cache first
        if not force and self._load_from_cache():
            return self.snapshot
        
        print("Building project knowledge snapshot...")
        
        # 1. Scan all Python files
        files = list(self.project_root.glob(pattern))
        print(f"Found {len(files)} files")
        
        # 2. Analyze using RefactoringAnalyzer
        self.analyzer.analyze_directory(self.project_root, pattern)
        
        # 3. Extract function information
        functions: Dict[str, FunctionInfo] = {}
        
        # Extract function definitions from analyzer
        for func_name, file_list in self.analyzer.function_defs.items():
            for file_path in file_list:
                key = f"{file_path.name}::{func_name}"
                functions[key] = FunctionInfo(
                    name=func_name,
                    file=file_path
                )
        
        # Extract call relationships
        for file_path, calls_dict in self.analyzer.function_calls.items():
            for called_func, call_sites in calls_dict.items():
                for call_site in call_sites:
                    caller_key = f"{file_path.name}::{call_site.function_name}"
                    callee_key = f"{call_site.file.name}::{called_func}"
                    
                    # Record call relationship
                    if caller_key in functions:
                        if callee_key not in functions[caller_key].calls:
                            functions[caller_key].calls.append(callee_key)
                    
                    if callee_key in functions:
                        if caller_key not in functions[callee_key].called_by:
                            functions[callee_key].called_by.append(caller_key)
        
        # 4. Calculate impact scores
        for func in functions.values():
            func.impact_score = self._calculate_impact_score(func)
            func.impact_level = self._calculate_impact_level(func.impact_score)
        
        # 5. Calculate file hashes for incremental updates
        file_hashes = {}
        for file_path in files:
            try:
                content = file_path.read_bytes()
                file_hashes[str(file_path)] = hashlib.md5(content).hexdigest()
            except Exception:
                pass
        
        # 6. Create snapshot
        self.snapshot = ProjectSnapshot(
            timestamp=datetime.now().isoformat(),
            total_files=len(files),
            total_functions=len(functions),
            functions=functions,
            file_hashes=file_hashes
        )
        
        # 7. Save to cache
        self._save_to_cache()
        
        print(f"✅ Snapshot built: {len(functions)} functions")
        return self.snapshot
    
    def get_function_impact(self, function_name: str) -> Optional[Dict[str, Any]]:
        """
        Get function impact analysis
        
        Args:
            function_name: Function name (supports "file::func" or "func")
        
        Returns:
            Impact information dict or None if function not found
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            return None
        
        # Find function
        func_info = None
        if "::" in function_name:
            # Exact match
            func_info = self.snapshot.functions.get(function_name)
        else:
            # Fuzzy match (by function name only)
            for key, info in self.snapshot.functions.items():
                if info.name == function_name:
                    func_info = info
                    break
        
        if not func_info:
            return None
        
        # Calculate affected files
        affected_files = set()
        for caller in func_info.called_by:
            file_name = caller.split("::")[0]
            affected_files.add(file_name)
        
        return {
            "function": func_info.name,
            "file": func_info.file.name,
            "called_by": func_info.called_by,  # Use called_by for consistency
            "callees": func_info.calls,
            "impact_score": func_info.impact_score,
            "impact_level": func_info.impact_level,
            "affected_files": len(affected_files),
            "files_list": list(affected_files),
        }
    
    def get_hotspots(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """
        Get hotspot functions (most frequently called)
        
        Args:
            top_n: Return top N hotspots
        
        Returns:
            List of hotspot functions
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            return []
        
        # Sort by impact score
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
    
    def load_snapshot(self, max_functions: int = DEFAULT_MAX_FUNCTIONS) -> str:
        """
        Load snapshot in compressed text format
        
        Args:
            max_functions: Maximum functions to include
        
        Returns:
            Compressed text representation
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            return "No snapshot available. Run build_snapshot() first."
        
        return self.snapshot.to_compact_format(max_functions)
    
    def incremental_update(self, changed_files: List[Path]) -> bool:
        """
        Incremental update (re-analyze only changed files)
        
        Args:
            changed_files: List of changed files
        
        Returns:
            Whether update succeeded
        """
        if not self.snapshot:
            self._load_from_cache()
        
        if not self.snapshot:
            # No snapshot exists, do full build
            self.build_snapshot()
            return True
        
        print(f"Incremental update: {len(changed_files)} files")
        
        # Check which files actually changed (MD5)
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
            print("✅ No actual changes")
            return True
        
        print(f"Actually changed: {len(actually_changed)} files")
        
        # Rebuild snapshot (simplified: full rebuild)
        # TODO: Implement true incremental update
        self.build_snapshot(force=True)
        
        return True
    
    def _calculate_impact_score(self, func: FunctionInfo) -> int:
        """
        Calculate impact score
        
        Algorithm:
        impact_score = (callers * weight) + (cross_file_count * weight) + (depth * weight)
        
        Weights are configurable via module constants.
        """
        called_by_count = len(func.called_by)
        
        # Calculate cross-file callers
        cross_file_callers = set()
        for caller in func.called_by:
            caller_file = caller.split("::")[0]
            if caller_file != func.file.name:
                cross_file_callers.add(caller_file)
        
        # Simplified depth calculation (based on caller count)
        depth = min(len(func.called_by), 10)
        
        score = (
            called_by_count * IMPACT_WEIGHT_CALLER +
            len(cross_file_callers) * IMPACT_WEIGHT_CROSS_FILE +
            depth * IMPACT_WEIGHT_DEPTH
        )
        
        return score
    
    def _calculate_impact_level(self, score: int) -> str:
        """
        Calculate impact level based on score
        
        Uses configurable thresholds from module constants.
        """
        if score > IMPACT_THRESHOLD_HIGH:
            return "high"
        elif score > IMPACT_THRESHOLD_MEDIUM:
            return "medium"
        else:
            return "low"
    
    def _save_to_cache(self):
        """Save snapshot to cache"""
        if not self.snapshot:
            return
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON format (for programmatic access)
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
        
        # Save text format (for Agent quick access)
        compact_text = self.snapshot.to_compact_format(max_functions=DEFAULT_MAX_FUNCTIONS)
        self.snapshot_text_file.write_text(compact_text, encoding='utf-8')
        
        print(f"💾 Snapshot cached: {self.cache_file}")
    
    def _load_from_cache(self) -> bool:
        """Load snapshot from cache"""
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
            
            print(f"✅ Loaded snapshot from cache: {self.snapshot.total_functions} functions")
            return True
        except Exception as e:
            print(f"❌ Failed to load cache: {e}")
            return False


# Convenience functions for easy API access
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
    
    # Add safety recommendations
    level = impact["impact_level"]
    
    # Recommendation messages based on impact level
    recommendations = {
        "high": {
            "message": "⚠️  Caution needed: High-impact function, may affect multiple modules",
            "safe": False
        },
        "medium": {
            "message": "⚡ Medium impact: Thorough testing recommended",
            "safe": True
        },
        "low": {
            "message": "✅ Safe: Low-impact function",
            "safe": True
        }
    }
    
    rec_info = recommendations.get(level, recommendations["low"])
    
    return {
        **impact,
        "safe_to_refactor": rec_info["safe"],
        "recommendation": rec_info["message"]
    }
