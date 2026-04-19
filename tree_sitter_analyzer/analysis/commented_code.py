"""Commented-Out Code Detector.

Detects code that has been commented out instead of being removed or
properly version-controlled. Detects via heuristic pattern matching
on comment node content:

  - commented_assignment: lines with assignment patterns
  - commented_call: lines with function/method call patterns
  - commented_import: import/include/require statements
  - commented_declaration: function/class/variable declarations

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_ASSIGNMENT = "commented_assignment"
ISSUE_CALL = "commented_call"
ISSUE_IMPORT = "commented_import"
ISSUE_DECLARATION = "commented_declaration"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_ASSIGNMENT: SEVERITY_MEDIUM,
    ISSUE_CALL: SEVERITY_MEDIUM,
    ISSUE_IMPORT: SEVERITY_LOW,
    ISSUE_DECLARATION: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_ASSIGNMENT: "Commented-out assignment — remove or use version control",
    ISSUE_CALL: "Commented-out function call — remove or use version control",
    ISSUE_IMPORT: "Commented-out import — remove or use version control",
    ISSUE_DECLARATION: "Commented-out declaration — remove or use version control",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_ASSIGNMENT: "Delete commented-out code. Use git to recover if needed.",
    ISSUE_CALL: "Delete commented-out code. Use git to recover if needed.",
    ISSUE_IMPORT: "Delete unused import. Use git to recover if needed.",
    ISSUE_DECLARATION: "Delete commented-out declaration. Use git to recover if needed.",
}

_COMMENT_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"comment"}),
    ".js": frozenset({"comment"}),
    ".ts": frozenset({"comment"}),
    ".tsx": frozenset({"comment"}),
    ".jsx": frozenset({"comment"}),
    ".java": frozenset({"line_comment", "block_comment"}),
    ".go": frozenset({"comment"}),
}

_DELIMITER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^#\s*"), "py"),
    (re.compile(r"^//\s*"), "js_like"),
    (re.compile(r"^\s*\*\s*"), "js_block"),
    (re.compile(r"^/\*\s*"), "js_block_start"),
]

_HIGH_CONFIDENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(from\s+\S+\s+import|import\s+\w+|import\s*\{)"), ISSUE_IMPORT),
    (re.compile(r"^(require\s*\(|const\s+\w+\s*=\s*require)"), ISSUE_IMPORT),
    (re.compile(r"^using\s+\w+"), ISSUE_IMPORT),
    (re.compile(r"^(def|async\s+def)\s+\w+\s*\("), ISSUE_DECLARATION),
    (re.compile(r"^(function|const|let|var)\s+\w+\s*[=(]"), ISSUE_DECLARATION),
    (re.compile(r"^(public|private|protected|static)\s+\w+"), ISSUE_DECLARATION),
    (re.compile(r"^(func|type|interface)\s+\w+"), ISSUE_DECLARATION),
    (re.compile(r"^(class|struct)\s+\w+"), ISSUE_DECLARATION),
    (re.compile(r":=\s"), ISSUE_ASSIGNMENT),
]

_MEDIUM_CONFIDENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"=\s{1,3}[^=<>!]"), ISSUE_ASSIGNMENT),
    (re.compile(r"\w+\([^)]*\)\s*;?\s*$"), ISSUE_CALL),
    (re.compile(r"^\s*return\s+"), ISSUE_CALL),
    (re.compile(r"^\s*(if|for|while|switch|try|catch)\s*\("), ISSUE_CALL),
    (re.compile(r"\w+\.\w+\([^)]*\)"), ISSUE_CALL),
]

_NATURAL_LANGUAGE_INDICATORS: re.Pattern[str] = re.compile(
    r"^(This|The|Note|See|Check|TODO|FIXME|HACK|XXX|Bug|Fix|Issue|Ref)"
    r"[\s:]", re.IGNORECASE
)

_MIN_CODE_LENGTH = 8


def _strip_comment_delimiter(text: str) -> str:
    stripped = text.strip()
    for pattern, _kind in _DELIMITER_PATTERNS:
        new_text = pattern.sub("", stripped)
        if new_text != stripped:
            return new_text.strip()
    if stripped.startswith("/*"):
        return stripped[2:].rstrip("*/").strip()
    if stripped.startswith("*"):
        return stripped[1:].strip()
    return stripped


def _classify_line(line: str) -> str | None:
    if len(line) < _MIN_CODE_LENGTH:
        return None
    if line.endswith(".") and not line.rstrip(".").endswith(")"):
        return None
    if _NATURAL_LANGUAGE_INDICATORS.match(line):
        return None
    if line.startswith("@"):
        return None
    for pattern, issue_type in _HIGH_CONFIDENCE_PATTERNS:
        if pattern.search(line):
            return issue_type
    match_count = 0
    last_type: str | None = None
    for pattern, issue_type in _MEDIUM_CONFIDENCE_PATTERNS:
        if pattern.search(line):
            match_count += 1
            last_type = issue_type
    if match_count >= 2:
        return last_type
    return None


@dataclass(frozen=True)
class CommentedCodeItem:
    line: int
    issue_type: str
    content: str
    severity: str
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "content": self.content,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class CommentedCodeResult:
    file_path: str
    items: tuple[CommentedCodeItem, ...]
    total_count: int
    by_type: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "items": [i.to_dict() for i in self.items],
            "total_count": self.total_count,
            "by_type": self.by_type,
        }


class CommentedCodeDetector(BaseAnalyzer):
    """Detects commented-out code in source files."""

    def analyze_file(self, file_path: str) -> CommentedCodeResult:
        result = self._check_file(file_path)
        if not result:
            return CommentedCodeResult(
                file_path=file_path, items=(), total_count=0, by_type={},
            )
        path, ext = result

        try:
            lang, parser = self._get_parser(ext)
        except (ValueError, RuntimeError):
            return CommentedCodeResult(
                file_path=file_path, items=(), total_count=0, by_type={},
            )
        if parser is None:
            return CommentedCodeResult(
                file_path=file_path, items=(), total_count=0, by_type={},
            )

        node_types = _COMMENT_NODE_TYPES.get(ext)
        if not node_types:
            return CommentedCodeResult(
                file_path=file_path, items=(), total_count=0, by_type={},
            )

        source = Path(path).read_bytes()
        tree = parser.parse(source)
        items: list[CommentedCodeItem] = []
        self._walk(tree.root_node, source.decode("utf-8", errors="replace"), node_types, items)

        by_type: dict[str, int] = {}
        for item in items:
            by_type[item.issue_type] = by_type.get(item.issue_type, 0) + 1

        return CommentedCodeResult(
            file_path=file_path,
            items=tuple(items),
            total_count=len(items),
            by_type=by_type,
        )

    def _walk(
        self,
        node: tree_sitter.Node,
        source: str,
        node_types: frozenset[str],
        results: list[CommentedCodeItem],
    ) -> None:
        if node.type in node_types:
            text = source[node.start_byte:node.end_byte]
            for line_text in text.split("\n"):
                stripped = _strip_comment_delimiter(line_text)
                issue_type = _classify_line(stripped)
                if issue_type is not None:
                    results.append(CommentedCodeItem(
                        line=node.start_point[0] + 1,
                        issue_type=issue_type,
                        content=stripped[:120],
                        severity=_SEVERITY_MAP.get(issue_type, SEVERITY_LOW),
                        message=_DESCRIPTIONS.get(issue_type, "Commented-out code"),
                        suggestion=_SUGGESTIONS.get(issue_type, "Delete or use version control."),
                    ))
                    break
        for child in node.children:
            self._walk(child, source, node_types, results)
