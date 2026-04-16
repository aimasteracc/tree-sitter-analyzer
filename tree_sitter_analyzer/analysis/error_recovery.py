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

# Language-specific patterns for regex fallback
_LANG_PATTERNS: dict[str, dict[str, re.Pattern[str]]] = {
    "python": {
        "class": re.compile(r"^class\s+(\w+)", re.MULTILINE),
        "function": re.compile(r"^def\s+(\w+)", re.MULTILINE),
        "async_function": re.compile(r"^async\s+def\s+(\w+)", re.MULTILINE),
    },
    "go": {
        "function": re.compile(r"^func\s+(?:\([^)]*\)\s+)?(\w+)", re.MULTILINE),
        "type": re.compile(r"^type\s+(\w+)\s+struct", re.MULTILINE),
        "interface": re.compile(r"^type\s+(\w+)\s+interface", re.MULTILINE),
    },
    "csharp": {
        "class": re.compile(r"(?:public|internal|private|protected)?\s*class\s+(\w+)", re.MULTILINE),
        "interface": re.compile(r"(?:public|internal|private)?\s*interface\s+(\w+)", re.MULTILINE),
        "struct": re.compile(r"(?:public|internal|private)?\s*struct\s+(\w+)", re.MULTILINE),
        "record": re.compile(r"(?:public|internal|private)?\s*record\s+(\w+)", re.MULTILINE),
        "method": re.compile(r"(?:public|private|protected|internal)\s+(?:static\s+|async\s+)?(?:[\w<>\[\]?]+)\s+(\w+)\s*\(", re.MULTILINE),
    },
    "kotlin": {
        "class": re.compile(r"(?:data\s+|sealed\s+|open\s+|abstract\s+)*class\s+(\w+)", re.MULTILINE),
        "function": re.compile(r"fun\s+(?:<[^>]*>\s+)?(\w+)", re.MULTILINE),
        "object": re.compile(r"^object\s+(\w+)", re.MULTILINE),
        "interface": re.compile(r"interface\s+(\w+)", re.MULTILINE),
    },
    "rust": {
        "function": re.compile(r"(?:pub\s+)?fn\s+(\w+)", re.MULTILINE),
        "struct": re.compile(r"(?:pub\s+)?struct\s+(\w+)", re.MULTILINE),
        "trait": re.compile(r"(?:pub\s+)?trait\s+(\w+)", re.MULTILINE),
        "enum": re.compile(r"(?:pub\s+)?enum\s+(\w+)", re.MULTILINE),
    },
}

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".go": "go",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".rs": "rust",
}


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
        lang = _EXT_TO_LANG.get(Path(file_path).suffix)

        if lang and lang in _LANG_PATTERNS:
            return self._lang_specific_fallback(file_path, text, lines, lang)

        return self._java_style_fallback(file_path, text, lines)

    def _lang_specific_fallback(
        self, file_path: str, text: str, lines: int, lang: str
    ) -> dict[str, Any]:
        """Language-aware regex extraction."""
        patterns = _LANG_PATTERNS[lang]
        classes: list[dict[str, Any]] = []
        methods: list[dict[str, Any]] = []

        for ptype, pattern in patterns.items():
            for match in pattern.finditer(text):
                line_num = text[:match.start()].count("\n") + 1
                entry = {"name": match.group(1), "line": line_num}
                if ptype in ("class", "interface", "struct", "record", "type", "object", "trait", "enum"):
                    classes.append(entry)
                else:
                    methods.append(entry)

        return {
            "success": True,
            "recovery_mode": True,
            "file_path": file_path,
            "language": lang,
            "lines": lines,
            "classes": classes,
            "methods": methods,
            "message": f"Analysis performed via {lang} regex fallback (tree-sitter parse error).",
        }

    def _java_style_fallback(
        self, file_path: str, text: str, lines: int
    ) -> dict[str, Any]:
        """Default Java/C++ style regex extraction."""
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
