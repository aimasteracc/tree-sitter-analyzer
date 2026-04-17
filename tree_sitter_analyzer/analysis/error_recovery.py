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

__all__ = ["ErrorRecovery", "detect_encoding"]

logger = setup_logger(__name__)

BINARY_THRESHOLD = 0.3

# BOM signatures for encoding detection
_BOM_MAP: list[tuple[bytes, str]] = [
    (b"\xef\xbb\xbf", "utf-8"),       # UTF-8 BOM
    (b"\xff\xfe", "utf-16-le"),       # UTF-16 LE BOM
    (b"\xfe\xff", "utf-16-be"),       # UTF-16 BE BOM
    (b"\xff\xfe\x00\x00", "utf-32-le"),  # UTF-32 LE BOM
    (b"\x00\x00\xfe\xff", "utf-32-be"),  # UTF-32 BE BOM
]

# Fallback encodings to try after UTF-8 (in order of likelihood)
_FALLBACK_ENCODINGS: list[tuple[str, str]] = [
    ("gbk", "Chinese (GBK)"),
    ("shift_jis", "Japanese (Shift-JIS)"),
    ("euc-jp", "Japanese (EUC-JP)"),
    ("euc-kr", "Korean (EUC-KR)"),
    ("big5", "Traditional Chinese (Big5)"),
    ("iso-8859-1", "Western (Latin-1)"),
]

# Minimum ratio of common CJK characters to confirm a CJK encoding
_CJK_CONFIRM_RATIO = 0.05

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


def _has_cjk_chars(text: str, sample_size: int = 4096) -> bool:
    """Check if text contains CJK characters above the confirmation threshold."""
    sample = text[:sample_size]
    if not sample:
        return False
    cjk_ranges = (
        (0x4E00, 0x9FFF),    # CJK Unified Ideographs
        (0x3040, 0x309F),    # Hiragana
        (0x30A0, 0x30FF),    # Katakana
        (0xAC00, 0xD7AF),    # Hangul Syllables
    )
    cjk_count = sum(
        1 for ch in sample
        if any(lo <= ord(ch) <= hi for lo, hi in cjk_ranges)
    )
    return (cjk_count / len(sample)) > _CJK_CONFIRM_RATIO


def detect_encoding(content: bytes) -> tuple[str, bool]:
    """Detect the encoding of byte content.

    Returns (encoding_name, had_bom).
    Strategy: BOM check → UTF-8 strict → CJK-heuristic fallbacks → Latin-1.
    """
    if not content:
        return "utf-8", False

    # Strategy 1: BOM detection (most reliable)
    for bom, encoding in _BOM_MAP:
        if content.startswith(bom):
            return encoding, True

    # Strategy 2: Try UTF-8 strict decode
    try:
        content.decode("utf-8")
        return "utf-8", False
    except UnicodeDecodeError:
        pass

    # Strategy 3: CJK-heuristic fallbacks — try all encodings, pick the one
    # with the highest quality score. Quality = CJK ratio + kana bonus.
    # Kana (Hiragana/Katakana) characters are a strong signal for Japanese
    # encodings (shift_jis, euc-jp), helping disambiguate from GBK.
    best_encoding: str | None = None
    best_score: float = 0.0

    for encoding, _label in _FALLBACK_ENCODINGS:
        try:
            decoded = content.decode(encoding)
            sample = decoded[:4096]
            if not sample:
                continue
            cjk_count = 0
            kana_count = 0
            hangul_count = 0
            for ch in sample:
                code = ord(ch)
                if 0x4E00 <= code <= 0x9FFF:
                    cjk_count += 1
                elif 0x3040 <= code <= 0x309F:  # Hiragana
                    kana_count += 1
                elif 0x30A0 <= code <= 0x30FF:  # Katakana
                    kana_count += 1
                elif 0xAC00 <= code <= 0xD7AF:  # Hangul
                    hangul_count += 1
            total_cjk = cjk_count + kana_count + hangul_count
            ratio = total_cjk / len(sample)
            # Score: base CJK ratio + kana bonus for Japanese detection
            score = ratio + (kana_count / len(sample) if kana_count > 0 else 0)
            if score > best_score:
                best_score = score
                best_encoding = encoding
        except (UnicodeDecodeError, LookupError):
            continue

    if best_encoding is not None and best_score > _CJK_CONFIRM_RATIO:
        return best_encoding, False

    # Final fallback: UTF-8 with replacement (never fails)
    return "utf-8", False


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

        encoding, _had_bom = detect_encoding(content)
        text = content.decode(encoding, errors="replace")
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
