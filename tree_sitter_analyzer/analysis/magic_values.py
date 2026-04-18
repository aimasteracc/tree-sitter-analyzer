"""Magic value detection — find hardcoded numbers, strings, URLs, and paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat

_SAFE_NUMBERS = frozenset({0, 1, -1, 2})
_SAFE_STRINGS = frozenset({"", " ", "\n", "\t", "\r\n"})
_URL_PATTERN = re.compile(r"^https?://[^\s]+|^ftp://[^\s]+", re.IGNORECASE)
_PATH_PATTERN = re.compile(r"^/[\w/.-]+|^\./[\w/.-]+|^\.\./[\w/.-]+|^[A-Za-z]:\\")
_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3,8}$")

_EXT_TO_LANG: dict[str, tuple[str, str]] = {
    ".py": ("tree_sitter_python", "language_python"),
    ".js": ("tree_sitter_javascript", "language_javascript"),
    ".ts": ("tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
    ".java": ("tree_sitter_java", "language_java"),
    ".go": ("tree_sitter_go", "language_go"),
}


@dataclass(frozen=True)
class MagicValueReference:
    """A single occurrence of a hardcoded value."""

    value: str
    file_path: str
    line: int
    column: int
    value_type: str
    context: str
    category: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "value": self.value,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "value_type": self.value_type,
            "context": self.context,
            "category": self.category,
        }


@dataclass(frozen=True)
class MagicValueUsage:
    """Aggregated usage of a specific hardcoded value."""

    value: str
    references: tuple[MagicValueReference, ...]
    file_count: int
    total_refs: int
    category: str

    def to_dict(self) -> dict[str, str | int | list[dict[str, str | int]]]:
        return {
            "value": self.value,
            "file_count": self.file_count,
            "total_refs": self.total_refs,
            "category": self.category,
            "references": [r.to_dict() for r in self.references],
        }


@dataclass(frozen=True)
class MagicValueResult:
    """Aggregated detection result."""

    file_path: str
    references: tuple[MagicValueReference, ...]
    total_count: int

    def to_dict(self) -> dict[str, str | int | list[dict[str, str | int]]]:
        return {
            "file_path": self.file_path,
            "total_count": self.total_count,
            "references": [r.to_dict() for r in self.references],
        }


def _get_context(node: Any, source: bytes) -> str:
    """Get the parent expression as context string."""
    parent = node.parent
    if parent is None:
        return str(node.text.decode("utf-8", errors="replace"))
    start = min(parent.start_byte, node.start_byte)
    end = max(parent.end_byte, node.end_byte)
    text = source[start:end].decode("utf-8", errors="replace")
    return text.strip()[:120]


def _classify_string(value: str) -> str | None:
    """Classify a string value. Returns category or None if safe."""
    if value in _SAFE_STRINGS:
        return None
    if _URL_PATTERN.match(value):
        return "hardcoded_url"
    if _PATH_PATTERN.match(value):
        return "hardcoded_path"
    if _COLOR_PATTERN.match(value):
        return "hardcoded_color"
    if len(value) >= 3:
        return "magic_string"
    return None


def _classify_number(raw: str) -> str | None:
    """Classify a numeric value. Returns category or None if safe."""
    try:
        num = float(raw)
        if num in _SAFE_NUMBERS:
            return None
        int_val = int(num)
        if int_val in _SAFE_NUMBERS and num == float(int_val):
            return None
    except ValueError:
        return None
    return "magic_number"


def _is_in_safe_context(node: Any) -> bool:
    """Check if node is in a context where values should be ignored."""
    parent = node.parent
    while parent is not None:
        pt = parent.type
        if pt in ("import_statement", "import_from_statement"):
            return True
        if pt == "expression_statement":
            for child in parent.children:
                if child.type == "string":
                    return True  # docstring
        if pt == "assignment":
            left = parent.child_by_field_name("left")
            if left is not None:
                text = left.text.decode("utf-8", errors="replace")
                if text.isupper() or text.startswith("_"):
                    return True
        parent = parent.parent
    return False


def _extract_string_content(raw: str) -> str:
    """Extract inner content from a quoted string."""
    if len(raw) < 2:
        return raw
    if raw.startswith(('"""', "'''")) and len(raw) >= 6:
        return raw[3:-3]
    for prefix in ("f\"", "f'", "r\"", "r'", "b\"", "b'", "rf\"", "rf'"):
        if raw.startswith(prefix) and len(raw) > len(prefix) + 1:
            return raw[len(prefix) : -1]
    if raw.startswith(('"', "'", "`")) and len(raw) >= 2:
        return raw[1:-1]
    return raw


def _value_type_for_category(category: str) -> str:
    """Map category to value_type."""
    mapping: dict[str, str] = {
        "magic_number": "number",
        "magic_string": "string",
        "hardcoded_url": "url",
        "hardcoded_path": "path",
        "hardcoded_color": "color",
    }
    return mapping.get(category, "string")


class MagicValueDetector:
    """Detect hardcoded magic values in source code."""

    _NUM_QUERIES: dict[str, str] = {
        "python": "(integer) @num (float) @num",
        "javascript": "(number) @num",
        "typescript": "(number) @num",
        "tsx": "(number) @num",
        "java": "(decimal_integer_literal) @num (decimal_floating_point_literal) @num",
        "go": "(int_literal) @num (float_literal) @num",
    }
    _STR_QUERIES: dict[str, str] = {
        "python": "(string) @str",
        "javascript": "(string) @str (template_string) @str",
        "typescript": "(string) @str (template_string) @str",
        "tsx": "(string) @str (template_string) @str",
        "java": "(string_literal) @str",
        "go": "(interpreted_string_literal) @str (raw_string_literal) @str",
    }

    def __init__(self, language_name: str = "python") -> None:
        self.language_name = language_name
        self._language: Any = None
        self._parser: Any = None
        self._load_language(language_name)

    def _load_language(self, language_name: str) -> None:
        """Load tree-sitter language and parser."""
        import tree_sitter

        lang_map = {
            "python": ("tree_sitter_python", "language"),
            "javascript": ("tree_sitter_javascript", "language"),
            "typescript": ("tree_sitter_typescript", "language_typescript"),
            "tsx": ("tree_sitter_typescript", "language_tsx"),
            "java": ("tree_sitter_java", "language"),
            "go": ("tree_sitter_go", "language"),
        }
        entry = lang_map.get(language_name)
        if entry is None:
            raise ValueError(f"Unsupported language: {language_name}")
        module_name, func_name = entry
        mod = __import__(module_name)
        func = getattr(mod, func_name)
        self._language = tree_sitter.Language(func())
        self._parser = tree_sitter.Parser(self._language)

    def detect(self, file_path: str | Path) -> MagicValueResult:
        """Detect magic values in a single file."""
        file_path = Path(file_path)
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        root = tree.root_node
        references: list[MagicValueReference] = []
        references.extend(self._detect_numbers(root, source, str(file_path)))
        references.extend(self._detect_strings(root, source, str(file_path)))
        return MagicValueResult(
            file_path=str(file_path),
            references=tuple(references),
            total_count=len(references),
        )

    def detect_directory(self, dir_path: str | Path) -> list[MagicValueResult]:
        """Detect magic values across all files in a directory."""
        dir_path = Path(dir_path)
        results: list[MagicValueResult] = []
        extensions = set(_EXT_TO_LANG.keys())
        for f in sorted(dir_path.rglob("*")):
            if f.suffix in extensions and f.is_file():
                try:
                    results.append(self.detect(f))
                except Exception:
                    pass
        return results

    def group_by_value(
        self, results: list[MagicValueResult]
    ) -> list[MagicValueUsage]:
        """Group references by their value across all results."""
        buckets: dict[str, list[MagicValueReference]] = {}
        for result in results:
            for ref in result.references:
                buckets.setdefault(ref.value, []).append(ref)
        usages: list[MagicValueUsage] = []
        for value, refs in sorted(buckets.items()):
            files = {r.file_path for r in refs}
            usages.append(
                MagicValueUsage(
                    value=value,
                    references=tuple(refs),
                    file_count=len(files),
                    total_refs=len(refs),
                    category=refs[0].category,
                )
            )
        return usages

    def filter_by_category(
        self, results: list[MagicValueResult], categories: set[str]
    ) -> list[MagicValueResult]:
        """Filter results to only include specified categories."""
        filtered: list[MagicValueResult] = []
        for result in results:
            refs = [r for r in result.references if r.category in categories]
            if refs:
                filtered.append(
                    MagicValueResult(
                        file_path=result.file_path,
                        references=tuple(refs),
                        total_count=len(refs),
                    )
                )
        return filtered

    def _detect_numbers(
        self, root: Any, source: bytes, file_path: str
    ) -> list[MagicValueReference]:
        """Detect hardcoded numeric values."""
        query_str = self._NUM_QUERIES.get(self.language_name, "(integer) @num")
        matches = TreeSitterQueryCompat.execute_query(
            self._language, query_str, root
        )
        references: list[MagicValueReference] = []
        for node, _capture_name in matches:
            raw = node.text.decode("utf-8", errors="replace")
            category = _classify_number(raw)
            if category is None:
                continue
            if _is_in_safe_context(node):
                continue
            references.append(
                MagicValueReference(
                    value=raw,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    value_type="number",
                    context=_get_context(node, source),
                    category=category,
                )
            )
        return references

    def _detect_strings(
        self, root: Any, source: bytes, file_path: str
    ) -> list[MagicValueReference]:
        """Detect hardcoded string values (including URLs, paths, colors)."""
        query_str = self._STR_QUERIES.get(self.language_name, "(string) @str")
        matches = TreeSitterQueryCompat.execute_query(
            self._language, query_str, root
        )
        references: list[MagicValueReference] = []
        for node, _capture_name in matches:
            raw = node.text.decode("utf-8", errors="replace")
            inner = _extract_string_content(raw)
            category = _classify_string(inner)
            if category is None:
                continue
            if _is_in_safe_context(node):
                continue
            references.append(
                MagicValueReference(
                    value=inner,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    value_type=_value_type_for_category(category),
                    context=_get_context(node, source),
                    category=category,
                )
            )
        return references
