"""增量分析和缓存工具"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class ChangeDetectorTool(BaseTool):
    """文件变更检测工具"""

    def __init__(self):
        super().__init__()
        self._file_states: dict[str, dict[str, Any]] = {}

    def get_name(self) -> str:
        return "change_detector"

    def get_description(self) -> str:
        return "Detect file changes in directory (added, modified, deleted)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to detect",
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to detect (e.g. ['.py', '.js'])",
                },
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = Path(arguments["directory"])
        extensions = arguments.get("extensions", [".py"])

        if not directory.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}

        # 扫描当前文件状态
        current_states: dict[str, dict[str, Any]] = {}
        for ext in extensions:
            for file_path in directory.rglob(f"*{ext}"):
                if file_path.is_file():
                    stat = file_path.stat()
                    current_states[str(file_path)] = {
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                        "hash": self._compute_hash(file_path),
                    }

        # 检测变更
        added = []
        modified = []
        deleted = []

        # 检测新增和修改
        for path, state in current_states.items():
            if path not in self._file_states:
                added.append(path)
            elif state["hash"] != self._file_states[path]["hash"]:
                modified.append(path)

        # 检测删除
        for path in self._file_states:
            if path not in current_states:
                deleted.append(path)

        # 更新状态
        self._file_states = current_states

        return {
            "success": True,
            "changes": {
                "added": added,
                "modified": modified,
                "deleted": deleted,
            },
            "total_files": len(current_states),
        }

    def _compute_hash(self, file_path: Path) -> str:
        """计算文件哈希"""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()


class CacheManagerTool(BaseTool):
    """缓存管理工具"""

    def __init__(self):
        super().__init__()
        self._cache: dict[str, Any] = {}

    def get_name(self) -> str:
        return "cache_manager"

    def get_description(self) -> str:
        return "Manage analysis result cache (set, get, delete, clear)"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["set", "get", "delete", "clear"],
                    "description": "Cache operation type",
                },
                "key": {
                    "type": "string",
                    "description": "Cache key",
                },
                "value": {
                    "type": "object",
                    "description": "Cache value (for set operation only)",
                },
            },
            "required": ["operation"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        operation = arguments["operation"]

        if operation == "set":
            key = arguments.get("key")
            value = arguments.get("value")
            if not key:
                return {"success": False, "error": "Missing key parameter"}
            self._cache[key] = {"value": value, "timestamp": time.time()}
            return {"success": True, "message": f"Cache set: {key}"}

        elif operation == "get":
            key = arguments.get("key")
            if not key:
                return {"success": False, "error": "Missing key parameter"}
            cache_entry = self._cache.get(key)
            if cache_entry:
                return {
                    "success": True,
                    "value": cache_entry["value"],
                    "timestamp": cache_entry["timestamp"],
                }
            return {"success": True, "value": None}

        elif operation == "delete":
            key = arguments.get("key")
            if not key:
                return {"success": False, "error": "Missing key parameter"}
            if key in self._cache:
                del self._cache[key]
                return {"success": True, "message": f"Cache deleted: {key}"}
            return {"success": True, "message": f"Cache not found: {key}"}

        elif operation == "clear":
            count = len(self._cache)
            self._cache.clear()
            return {"success": True, "message": f"Cleared {count} cache entries"}

        return {"success": False, "error": f"Unknown operation: {operation}"}


class IncrementalAnalyzerTool(BaseTool):
    """增量分析工具"""

    def __init__(self):
        super().__init__()
        self._change_detector = ChangeDetectorTool()
        self._cache_manager = CacheManagerTool()

    def get_name(self) -> str:
        return "incremental_analyzer"

    def get_description(self) -> str:
        return "Incremental analysis: analyze only changed files, use cache for unchanged files"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to analyze",
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to analyze",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force re-analyze all files (ignore cache)",
                },
            },
            "required": ["directory"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        directory = Path(arguments["directory"])
        force = arguments.get("force", False)

        if not directory.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}

        # 检测变更
        changes_result = self._change_detector.execute(arguments)
        if not changes_result["success"]:
            return changes_result

        changes = changes_result["changes"]

        # 如果强制分析，分析所有文件
        if force:
            files_to_analyze = list(Path(directory).rglob("*.py"))
        else:
            # 只分析变更的文件
            files_to_analyze = [
                Path(f) for f in changes["added"] + changes["modified"]
            ]

        # 分析文件
        analyzed_files = []
        for file_path in files_to_analyze:
            # 这里简化处理，实际应该调用真正的分析工具
            analysis_result = self._analyze_file(file_path)
            analyzed_files.append(str(file_path))

            # 缓存结果
            cache_key = f"analysis:{file_path}"
            self._cache_manager.execute(
                {"operation": "set", "key": cache_key, "value": analysis_result}
            )

        return {
            "success": True,
            "analyzed_files": analyzed_files,
            "cache_hit": len(analyzed_files) == 0 and not force,
            "changes": changes,
        }

    def _analyze_file(self, file_path: Path) -> dict[str, Any]:
        """分析单个文件（简化版）"""
        try:
            content = file_path.read_text(encoding="utf-8")
            return {
                "file": str(file_path),
                "lines": len(content.splitlines()),
                "size": len(content),
            }
        except Exception as e:
            return {"file": str(file_path), "error": str(e)}
