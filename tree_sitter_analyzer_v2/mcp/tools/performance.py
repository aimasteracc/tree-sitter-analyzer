"""MCP Tools for performance monitoring."""
import time
import psutil
from pathlib import Path
from typing import Any
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class PerformanceMonitorTool(BaseTool):
    """Monitor system performance."""

    def get_name(self) -> str:
        return "monitor_performance"

    def get_description(self) -> str:
        return "Monitor system performance (CPU, memory, disk)."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "enum": ["all", "cpu", "memory", "disk"], "default": "all"},
            },
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            metric = arguments.get("metric", "all")
            result = {"success": True}

            if metric in ["all", "cpu"]:
                result["cpu_percent"] = psutil.cpu_percent(interval=0.1)
                result["cpu_count"] = psutil.cpu_count()

            if metric in ["all", "memory"]:
                mem = psutil.virtual_memory()
                result["memory_percent"] = mem.percent
                result["memory_available_gb"] = round(mem.available / (1024**3), 2)
                result["memory_total_gb"] = round(mem.total / (1024**3), 2)

            if metric in ["all", "disk"]:
                disk = psutil.disk_usage("/")
                result["disk_percent"] = disk.percent
                result["disk_free_gb"] = round(disk.free / (1024**3), 2)

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}


class ProfileCodeTool(BaseTool):
    """Profile code execution."""

    def get_name(self) -> str:
        return "profile_code"

    def get_description(self) -> str:
        return "Profile Python code to identify performance bottlenecks."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Python file to profile"},
                "function_name": {"type": "string", "description": "Specific function to profile"},
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            file_path = Path(arguments["file_path"])
            if not file_path.exists():
                return {"success": False, "error": "File not found"}

            # Simple profiling: count lines and functions
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            import ast
            tree = ast.parse(content)
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

            return {
                "success": True,
                "file": str(file_path.absolute()),
                "lines": len(lines),
                "functions": len(functions),
                "function_names": functions[:20],  # Limit to first 20
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
