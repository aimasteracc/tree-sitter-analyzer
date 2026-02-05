"""MCP Tools for security scanning."""
import ast
import re
from pathlib import Path
from typing import Any
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class SecurityScannerTool(BaseTool):
    """Scan code for security issues."""

    def get_name(self) -> str:
        return "security_scan"

    def get_description(self) -> str:
        return "Scan Python code for common security vulnerabilities."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File to scan"},
                "severity": {"type": "string", "enum": ["all", "high", "medium", "low"], "default": "all"},
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            file_path = Path(arguments["file_path"])
            if not file_path.exists():
                return {"success": False, "error": "File not found"}

            content = file_path.read_text(encoding="utf-8")
            issues = []

            # Check for hardcoded secrets
            secret_patterns = [
                (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password", "high"),
                (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key", "high"),
                (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret", "high"),
                (r'token\s*=\s*["\'][^"\']+["\']', "Hardcoded token", "high"),
            ]

            for pattern, description, severity in secret_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    line_num = content[:match.start()].count('\n') + 1
                    issues.append({
                        "type": "hardcoded_secret",
                        "description": description,
                        "severity": severity,
                        "line": line_num,
                    })

            # Check for dangerous functions
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            if node.func.id in ["eval", "exec"]:
                                issues.append({
                                    "type": "dangerous_function",
                                    "description": f"Use of {node.func.id}()",
                                    "severity": "high",
                                    "line": node.lineno,
                                })
            except Exception:
                pass

            # Filter by severity
            severity_filter = arguments.get("severity", "all")
            if severity_filter != "all":
                issues = [i for i in issues if i["severity"] == severity_filter]

            return {
                "success": True,
                "issues": issues,
                "count": len(issues),
                "file": str(file_path.absolute()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
