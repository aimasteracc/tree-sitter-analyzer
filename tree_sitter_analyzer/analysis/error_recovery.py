"""
Error recovery mechanism for code analysis.

Provides graceful degradation when analysis operations encounter errors.
Returns partial results instead of failing completely.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

BINARY_THRESHOLD = 0.3

CLASS_PATTERN = re.compile(
    r"\b(?:public|private|protected|abstract|final|static)\s+class\s+(\w+)"
)
METHOD_PATTERN = re.compile(
    r"\b(?:public|private|protected|static|abstract|final|synchronized)\s+"
    r"(?:[\w<>\[\],\s]+)\s+(\w+)\s*\("
)
INTERFACE_PATTERN = re.compile(
    r"\b(?:public|private|protected)\s+interface\s+(\w+)"
)
ENUM_PATTERN = re.compile(
    r"\b(?:public|private|protected)\s+enum\s+(\w+)"
)


def _is_binary(content: bytes) -> bool:
    """Detect if content appears to be binary."""
    if not content:
        return False
    text_chars = set(range(32, 127)) | {9, 10, 13}
    non_text = sum(1 for b in content[:8192] if b not in text_chars)
    return (non_text / min(len(content), 8192)) > BINARY_THRESHOLD


class ErrorRecovery:
    """Graceful degradation wrapper for code analysis."""

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root)

    def analyze_with_fallback(self, file_path: str) -> dict[str, Any]:
        """Analyze a file with fallback strategies on error."""
        path = Path(file_path)
        if not path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "recovery_mode": True,
            }

        try:
            content = path.read_bytes()
        except OSError as e:
            return {
                "success": False,
                "error": f"Cannot read file: {e}",
                "recovery_mode": True,
            }

        if _is_binary(content):
            return {
                "success": True,
                "is_binary": True,
                "recovery_mode": True,
                "file_path": file_path,
                "message": "Binary file detected, no analysis available.",
            }

        text = content.decode("utf-8", errors="replace")
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)

        if not text.strip():
            return {
                "success": True,
                "recovery_mode": True,
                "file_path": file_path,
                "lines": lines,
                "classes": [],
                "methods": [],
                "message": "Empty file.",
            }

        try:
            result = self._try_treesitter_analysis(path)
            if result.get("success"):
                return result
        except Exception as e:
            logger.debug(f"Tree-sitter analysis failed: {e}")

        return self._regex_fallback(file_path, text, lines)

    def _try_treesitter_analysis(self, path: Path) -> dict[str, Any]:
        """Try full tree-sitter analysis."""
        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
            AnalyzeCodeStructureTool,
        )

        tool = AnalyzeCodeStructureTool(project_root=str(self.project_root))
        result = asyncio.run(
            tool.execute({"file_path": str(path), "format_type": "compact"})
        )
        return dict(result)

    def _regex_fallback(
        self, file_path: str, text: str, lines: int
    ) -> dict[str, Any]:
        """Regex-based extraction when tree-sitter fails."""
        classes: list[dict[str, Any]] = []
        for match in CLASS_PATTERN.finditer(text):
            classes.append({"name": match.group(1), "line": text[:match.start()].count("\n") + 1})
        for match in INTERFACE_PATTERN.finditer(text):
            classes.append({"name": match.group(1), "line": text[:match.start()].count("\n") + 1})
        for match in ENUM_PATTERN.finditer(text):
            classes.append({"name": match.group(1), "line": text[:match.start()].count("\n") + 1})

        methods: list[dict[str, Any]] = []
        for match in METHOD_PATTERN.finditer(text):
            methods.append({"name": match.group(1), "line": text[:match.start()].count("\n") + 1})

        return {
            "success": True,
            "recovery_mode": True,
            "file_path": file_path,
            "lines": lines,
            "classes": classes,
            "methods": methods,
            "message": "Analysis performed via regex fallback (tree-sitter parse error).",
        }
