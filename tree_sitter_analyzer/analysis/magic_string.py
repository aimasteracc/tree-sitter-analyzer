"""Magic String Detector.

Detects hardcoded string literals that should be extracted to named
constants. Complements magic_values which detects magic numbers.

Issues detected:
  - magic_string: hardcoded string literal in function body
  - repeated_string: same string appears 3+ times

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_MAGIC_STRING = "magic_string"
ISSUE_REPEATED_STRING = "repeated_string"

_MIN_STRING_LENGTH = 3
_REPEAT_THRESHOLD = 3

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_MAGIC_STRING: SEVERITY_LOW,
    ISSUE_REPEATED_STRING: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_MAGIC_STRING: "Hardcoded string literal should be extracted to a named constant",
    ISSUE_REPEATED_STRING: "String appears multiple times, extract to a shared constant",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_MAGIC_STRING: "Extract this string to a named constant at the module or class level",
    ISSUE_REPEATED_STRING: "Define a constant for this repeated string to ensure consistency and easier maintenance",
}

_SKIP_PARENT_TYPES: frozenset[str] = frozenset({
    "import_statement", "import_from_statement", "import_declaration",
    "decorator", "type_annotation", "type_hint",
})

_STRING_TYPES: frozenset[str] = frozenset({
    "string_literal", "string", "interpreted_string_literal",
    "raw_string_literal", "template_string",
})

_FUNCTION_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".jsx": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".ts": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".tsx": frozenset({"function_declaration", "method_definition", "arrow_function"}),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}

@dataclass(frozen=True)
class MagicStringIssue:
    """A single magic string issue."""

    line_number: int
    issue_type: str
    description: str
    severity: str
    string_value: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "description": self.description,
            "severity": self.severity,
            "string_value": self.string_value,
            "suggestion": self.suggestion,
        }

@dataclass(frozen=True)
class MagicStringResult:
    """Aggregated magic string analysis result."""

    total_functions: int
    total_strings: int
    issues: tuple[MagicStringIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_functions": self.total_functions,
            "total_strings": self.total_strings,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }

def _get_string_text(
    node: tree_sitter.Node, content: bytes
) -> str:
    """Extract string text, stripping quotes."""
    text = content[node.start_byte:node.end_byte].decode(
        "utf-8", errors="replace"
    )
    if len(text) >= 2 and text[0] in ('"', "'", "`"):
        if text.startswith('"""') or text.startswith("'''"):
            return text[3:-3]
        if text.startswith("`") and text.endswith("`"):
            return text[1:-1]
        return text[1:-1]
    return text

def _should_skip(node: tree_sitter.Node) -> bool:
    """Check if a string node should be skipped (in import, decorator, etc)."""
    parent = node.parent
    while parent is not None:
        if parent.type in _SKIP_PARENT_TYPES:
            return True
        parent = parent.parent
    return False

class MagicStringAnalyzer(BaseAnalyzer):
    """Analyzes code for magic string literals."""

    def analyze_file(self, file_path: Path | str) -> MagicStringResult:
        path = Path(file_path)
        if not path.exists():
            return MagicStringResult(
                total_functions=0,
                total_strings=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return MagicStringResult(
                total_functions=0,
                total_strings=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> MagicStringResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return MagicStringResult(
                total_functions=0,
                total_strings=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        func_types = _FUNCTION_TYPES.get(ext, frozenset())

        all_strings: list[tuple[int, str]] = []
        total_functions = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_functions

            if node.type in func_types:
                total_functions += 1
                self._collect_strings(node, content, all_strings)
                return

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        issues: list[MagicStringIssue] = []
        string_counter: Counter[str] = Counter(
            s for _, s in all_strings
        )
        reported_repeated: set[str] = set()

        for line, text in all_strings:
            if len(text) < _MIN_STRING_LENGTH:
                continue
            if string_counter[text] >= _REPEAT_THRESHOLD:
                if text not in reported_repeated:
                    reported_repeated.add(text)
                    issues.append(MagicStringIssue(
                        line_number=line,
                        issue_type=ISSUE_REPEATED_STRING,
                        description=f'String "{text[:50]}" appears {string_counter[text]} times',
                        severity=SEVERITY_MEDIUM,
                        string_value=text[:80],
                    ))
            else:
                issues.append(MagicStringIssue(
                    line_number=line,
                    issue_type=ISSUE_MAGIC_STRING,
                    description=_DESCRIPTIONS[ISSUE_MAGIC_STRING],
                    severity=SEVERITY_LOW,
                    string_value=text[:80],
                ))

        return MagicStringResult(
            total_functions=total_functions,
            total_strings=len(all_strings),
            issues=tuple(issues),
            file_path=str(path),
        )

    def _collect_strings(
        self,
        func_node: tree_sitter.Node,
        content: bytes,
        results: list[tuple[int, str]],
    ) -> None:
        """Collect string literals from a function body."""

        def visit_inner(node: tree_sitter.Node) -> None:
            if node.type in _STRING_TYPES:
                if not _should_skip(node):
                    text = _get_string_text(node, content)
                    if len(text) >= _MIN_STRING_LENGTH:
                        results.append(
                            (node.start_point[0] + 1, text)
                        )
                return

            for child in node.children:
                visit_inner(child)

        body = func_node.child_by_field_name("body")
        if body is not None:
            visit_inner(body)
