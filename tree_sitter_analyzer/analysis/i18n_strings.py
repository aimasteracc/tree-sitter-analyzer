"""i18n String Detector — find user-visible strings needing internationalization.

Detects string literals inside output functions (print, raise, console.log, etc.)
and classifies them by visibility level to help teams prepare for localization.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

VIS_USER = "user_visible"
VIS_LIKELY = "likely_visible"
VIS_INTERNAL = "internal"

_SKIP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^[a-z_]+$"),
    re.compile(r"^[A-Z_]+$"),
    re.compile(r"^[0-9.\-+%eE]+$"),
    re.compile(r"^[/\\.\w:*?\"<>|]+\.\w{1,4}$"),
    re.compile(r"^[\w.\-]+@[\w.\-]+\.\w+$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}"),
    re.compile(r"^[0-9a-fA-F\-]{8,}$"),
    re.compile(r"^[$%]\{.*\}$"),
    re.compile(r"^https?://"),
    re.compile(r"^#?[0-9a-fA-F]{3,8}$"),
    re.compile(r"^\s*$"),
    re.compile(r"^\.$|^\.py$|^\.js$"),
]

_PYTHON_OUTPUT_CALLS: frozenset[str] = frozenset({
    "print", "input",
    "raise",
    "error", "warning", "info", "debug", "critical", "exception", "log",
    "write", "writelines",
    "format", "format_map",
})

_PYTHON_OUTPUT_ATTRS: frozenset[str] = frozenset({
    "error", "warning", "info", "debug", "critical", "exception", "log",
    "write",
})

_JS_OUTPUT_CALLS: frozenset[str] = frozenset({
    "log", "warn", "error", "info", "debug", "dir", "table",
    "alert", "confirm", "prompt",
    "write",
})

_JS_OUTPUT_ATTRS: frozenset[str] = frozenset({
    "log", "warn", "error", "info", "debug",
})

_JS_THROW_TYPES: frozenset[str] = frozenset({
    "Error", "TypeError", "RangeError", "SyntaxError", "ReferenceError",
    "URIError", "EvalError", "AggregateError",
})

_JAVA_OUTPUT_CALLS: frozenset[str] = frozenset({
    "println", "printf", "print", "format",
    "severe", "warning", "info", "fine", "finer", "finest",
    "append",
})

_JAVA_THROW_TYPES: frozenset[str] = frozenset({
    "Exception", "RuntimeException", "IllegalArgumentException",
    "IllegalStateException", "NullPointerException", "IOException",
    "FileNotFoundException", "SQLException", "UnsupportedOperationException",
    "IndexOutOfBoundsException", "ArrayIndexOutOfBoundsException",
    "ClassCastException", "ArithmeticException", "NumberFormatException",
    "StringBuilder", "StringBuffer",
})

_GO_OUTPUT_CALLS: frozenset[str] = frozenset({
    "Print", "Printf", "Println", "Sprint", "Sprintf", "Sprintln",
    "Fprint", "Fprintf", "Fprintln",
    "Fatal", "Fatalf", "Panic", "Panicf",
    "New", "Errorf",
})

def _nt(node: tree_sitter.Node) -> str:
    """Safely decode node text to string."""
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")

@dataclass(frozen=True)
class I18nString:
    """A single user-visible string occurrence."""

    text: str
    file_path: str
    line: int
    column: int
    visibility: str
    function_name: str
    context: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "text": self.text,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "visibility": self.visibility,
            "function_name": self.function_name,
            "context": self.context,
        }

@dataclass(frozen=True)
class I18nFileResult:
    """Detection result for a single file."""

    file_path: str
    strings: tuple[I18nString, ...]
    user_visible_count: int
    likely_visible_count: int
    internal_count: int

    def to_dict(self) -> dict[str, str | int | list[dict[str, str | int]]]:
        return {
            "file_path": self.file_path,
            "user_visible_count": self.user_visible_count,
            "likely_visible_count": self.likely_visible_count,
            "internal_count": self.internal_count,
            "strings": [s.to_dict() for s in self.strings],
        }

@dataclass(frozen=True)
class I18nSummary:
    """Summary across all analyzed files."""

    total_files: int
    total_strings: int
    user_visible_count: int
    likely_visible_count: int
    internal_count: int
    file_results: tuple[I18nFileResult, ...]

    def to_dict(self) -> dict[str, int | list[object]]:
        return {
            "total_files": self.total_files,
            "total_strings": self.total_strings,
            "user_visible_count": self.user_visible_count,
            "likely_visible_count": self.likely_visible_count,
            "internal_count": self.internal_count,
            "file_results": [r.to_dict() for r in self.file_results],
        }

def _classify_visibility(text: str) -> str:
    """Classify a string's user visibility level."""
    if len(text) <= 1:
        return VIS_INTERNAL

    for pat in _SKIP_PATTERNS:
        if pat.match(text):
            return VIS_INTERNAL

    has_space = " " in text
    has_punctuation = any(c in text for c in ".!?;:,")
    has_upper = any(c.isupper() for c in text)
    has_lower = any(c.islower() for c in text)
    word_count = len(text.split())

    if has_space and word_count >= 2 and (has_upper or has_lower):
        return VIS_USER

    if has_punctuation and has_lower:
        return VIS_USER

    if has_space and word_count >= 3:
        return VIS_LIKELY

    if has_upper and has_lower and not has_space:
        return VIS_LIKELY

    return VIS_INTERNAL

def _extract_string_text(node: tree_sitter.Node) -> str:
    """Extract text content from a string node, stripping quotes."""
    raw = _nt(node)

    if raw.startswith(('"""', "'''")):
        return raw[3:-3]
    if raw.startswith(("rf\"", "rf'", "fr\"", "fr'")):
        return raw[3:-1]
    if raw.startswith(("f\"", "f'", "b\"", "b'", "r\"", "r'")):
        return raw[2:-1]
    if raw.startswith(('"', "'")):
        return raw[1:-1]
    return raw

def _is_in_output_context(
    string_node: tree_sitter.Node,
    lang: str,
) -> tuple[bool, str]:
    """Check if a string is inside an output function call.

    Returns (is_output, function_name).
    """
    node = string_node.parent
    while node is not None:
        result = _check_node_output(node, lang)
        if result is not None:
            return True, result
        node = node.parent
    return False, ""

def _check_node_output(node: tree_sitter.Node, lang: str) -> str | None:
    """Check a single node for output context. Returns function name or None."""
    if lang == "python":
        return _check_python_output(node)
    if lang in ("javascript", "typescript", "tsx"):
        return _check_js_output(node)
    if lang == "java":
        return _check_java_output(node)
    if lang == "go":
        return _check_go_output(node)
    return None

def _check_python_output(node: tree_sitter.Node) -> str | None:
    """Check Python output context."""
    if node.type == "call":
        func = node.child_by_field_name("function")
        if func is not None:
            if func.type == "identifier":
                name = _nt(func)
                if name in _PYTHON_OUTPUT_CALLS:
                    return name
            elif func.type == "attribute":
                attr = func.child_by_field_name("attribute")
                if attr is not None:
                    attr_name = _nt(attr)
                    if attr_name in _PYTHON_OUTPUT_ATTRS:
                        return attr_name
    elif node.type == "raise_statement":
        return "raise"
    return None

def _check_js_output(node: tree_sitter.Node) -> str | None:
    """Check JS/TS output context."""
    if node.type == "call_expression":
        func = node.child_by_field_name("function")
        if func is not None:
            if func.type == "identifier":
                name = _nt(func)
                if name in _JS_OUTPUT_CALLS:
                    return name
                if name in _JS_THROW_TYPES:
                    return f"new {name}"
            elif func.type == "member_expression":
                prop = func.child_by_field_name("property")
                if prop is not None:
                    prop_name = _nt(prop)
                    if prop_name in _JS_OUTPUT_ATTRS:
                        return prop_name
    elif node.type == "throw_statement":
        return "throw"
    return None

def _check_java_output(node: tree_sitter.Node) -> str | None:
    """Check Java output context."""
    if node.type == "method_invocation":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            name = _nt(name_node)
            if name in _JAVA_OUTPUT_CALLS:
                return name
    elif node.type == "object_creation_expression":
        type_node = node.child_by_field_name("type")
        if type_node is not None:
            type_name = _nt(type_node)
            if type_name in _JAVA_THROW_TYPES:
                return f"new {type_name}"
    elif node.type == "throw_statement":
        return "throw"
    return None

def _check_go_output(node: tree_sitter.Node) -> str | None:
    """Check Go output context."""
    if node.type == "call_expression":
        func = node.child_by_field_name("function")
        if func is not None:
            if func.type in ("identifier", "field_identifier"):
                name = _nt(func)
                if name in _GO_OUTPUT_CALLS:
                    return name
            elif func.type == "selector_expression":
                field = func.child_by_field_name("field")
                if field is not None:
                    field_name = _nt(field)
                    if field_name in _GO_OUTPUT_CALLS:
                        return field_name
    return None

class I18nStringDetector(BaseAnalyzer):
    """Detects user-visible strings that need internationalization."""

    def _get_lang(self, ext: str) -> str:
        mapping: dict[str, str] = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
        }
        return mapping.get(ext, "")

    def analyze_file(
        self,
        file_path: str,
        min_length: int = 2,
        visibility_filter: set[str] | None = None,
    ) -> I18nFileResult:
        """Analyze a single file for i18n strings."""
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return self._empty_result(file_path)

        _, parser = self._get_parser(ext)
        if parser is None:
            return self._empty_result(file_path)

        try:
            source = path.read_bytes()
        except OSError:
            logger.exception("Failed to read %s", file_path)
            return self._empty_result(file_path)

        tree = parser.parse(source)
        lang = self._get_lang(ext)
        root = tree.root_node

        found: list[I18nString] = []
        self._walk(root, file_path, lang, min_length, visibility_filter, found)

        uv = sum(1 for s in found if s.visibility == VIS_USER)
        lv = sum(1 for s in found if s.visibility == VIS_LIKELY)
        ic = sum(1 for s in found if s.visibility == VIS_INTERNAL)

        return I18nFileResult(
            file_path=file_path,
            strings=tuple(found),
            user_visible_count=uv,
            likely_visible_count=lv,
            internal_count=ic,
        )

    @staticmethod
    def _empty_result(file_path: str) -> I18nFileResult:
        return I18nFileResult(
            file_path=file_path,
            strings=(),
            user_visible_count=0,
            likely_visible_count=0,
            internal_count=0,
        )

    def _walk(
        self,
        node: tree_sitter.Node,
        file_path: str,
        lang: str,
        min_length: int,
        visibility_filter: set[str] | None,
        results: list[I18nString],
    ) -> None:
        """Walk AST looking for string literals in output contexts."""
        string_types = {"string", "string_literal", "interpreted_string_literal", "raw_string_literal"}

        if node.type in string_types:
            text = _extract_string_text(node)
            if len(text) < min_length:
                for child in node.children:
                    self._walk(child, file_path, lang, min_length, visibility_filter, results)
                return

            is_output, func_name = _is_in_output_context(node, lang)

            if not is_output:
                for child in node.children:
                    self._walk(child, file_path, lang, min_length, visibility_filter, results)
                return

            visibility = _classify_visibility(text)

            if visibility_filter and visibility not in visibility_filter:
                for child in node.children:
                    self._walk(child, file_path, lang, min_length, visibility_filter, results)
                return

            start = node.start_point
            context = self._get_context_line(node)

            results.append(I18nString(
                text=text,
                file_path=file_path,
                line=start[0] + 1,
                column=start[1],
                visibility=visibility,
                function_name=func_name,
                context=context,
            ))
            return

        for child in node.children:
            self._walk(child, file_path, lang, min_length, visibility_filter, results)

    def _get_context_line(self, node: tree_sitter.Node) -> str:
        """Get the source line containing this node."""
        try:
            root = node
            while root.parent is not None:
                root = root.parent
            source_text = _nt(root)
            lines = source_text.split("\n")
            line_idx = node.start_point[0]
            if 0 <= line_idx < len(lines):
                return str(lines[line_idx].strip())
        except Exception:
            pass
        return ""

    def analyze_directory(
        self,
        directory: str,
        min_length: int = 2,
        visibility_filter: set[str] | None = None,
    ) -> I18nSummary:
        """Analyze all supported files in a directory."""
        dir_path = Path(directory)
        results: list[I18nFileResult] = []

        for ext in SUPPORTED_EXTENSIONS:
            for fp in dir_path.rglob(f"*{ext}"):
                if ".git" in fp.parts or "node_modules" in fp.parts:
                    continue
                result = self.analyze_file(str(fp), min_length, visibility_filter)
                if result.strings:
                    results.append(result)

        total_strings = sum(len(r.strings) for r in results)
        uv = sum(r.user_visible_count for r in results)
        lv = sum(r.likely_visible_count for r in results)
        ic = sum(r.internal_count for r in results)

        return I18nSummary(
            total_files=len(results),
            total_strings=total_strings,
            user_visible_count=uv,
            likely_visible_count=lv,
            internal_count=ic,
            file_results=tuple(results),
        )
