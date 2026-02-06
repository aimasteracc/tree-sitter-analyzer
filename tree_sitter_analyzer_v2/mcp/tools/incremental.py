"""Incremental analysis and cache tools"""

import hashlib
import time
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class ChangeDetectorTool(BaseTool):
    """File change detection tool"""

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

        # Scan current file states
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

        # Detect changes
        added = []
        modified = []
        deleted = []

        # Detect added and modified
        for path, state in current_states.items():
            if path not in self._file_states:
                added.append(path)
            elif state["hash"] != self._file_states[path]["hash"]:
                modified.append(path)

        # Detect deleted
        for path in self._file_states:
            if path not in current_states:
                deleted.append(path)

        # Update state
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
        """Calculate file hash"""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()


class CacheManagerTool(BaseTool):
    """Cache management tool"""

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
    """Incremental analysis tool"""

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

        # Detect changes
        changes_result = self._change_detector.execute(arguments)
        if not changes_result["success"]:
            return changes_result

        changes = changes_result["changes"]

        # If force analyze, analyze all files
        if force:
            files_to_analyze = list(Path(directory).rglob("*.py"))
        else:
            # Only analyze changed files
            files_to_analyze = [
                Path(f) for f in changes["added"] + changes["modified"]
            ]

        # Analyze files
        analyzed_files = []
        for file_path in files_to_analyze:
            # Simplified handling, should call real analysis tool in production
            analysis_result = self._analyze_file(file_path)
            analyzed_files.append(str(file_path))

            # Cache results
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
        """Analyze single file (simplified version)"""
        try:
            content = file_path.read_text(encoding="utf-8")
            return {
                "file": str(file_path),
                "lines": len(content.splitlines()),
                "size": len(content),
            }
        except Exception as e:
            return {"file": str(file_path), "error": str(e)}
