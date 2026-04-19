"""Duplicate Dict Key Detector.

Detects duplicate keys in dictionary/object literals. In Python,
`{"a": 1, "a": 2}` silently overwrites the first value. In JS/TS,
`{a: 1, a: 2}` does the same.

Issue types:
  - duplicate_dict_key: repeated key in dictionary/object literal

Supports Python, JavaScript, TypeScript.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"

ISSUE_DUPLICATE_DICT_KEY = "duplicate_dict_key"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_DUPLICATE_DICT_KEY: (
        "Duplicate key in dictionary literal silently overwrites earlier value"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_DUPLICATE_DICT_KEY: (
        "Remove or rename the duplicate key. The last value wins silently."
    ),
}

_DICT_TYPES: dict[str, set[str]] = {
    ".py": {"dictionary"},
    ".js": {"object"},
    ".ts": {"object"},
    ".java": set(),
    ".go": set(),
}

_PAIR_TYPES: dict[str, set[str]] = {
    ".py": {"pair"},
    ".js": {"pair"},
    ".ts": {"pair", "property_identifier"},
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _get_key_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    text = raw.decode("utf-8", errors="replace")
    if node.type in {"string", "string_literal", "identifier",
                     "property_identifier", "simple_string",
                     "concatenated_string"}:
        return text
    return text[:60]


@dataclass(frozen=True)
class DuplicateDictKeyIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str
    key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
            "key": self.key,
        }


@dataclass
class DuplicateDictKeyResult:
    file_path: str
    total_dicts: int
    issues: list[DuplicateDictKeyIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_dicts": self.total_dicts,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class DuplicateDictKeyAnalyzer(BaseAnalyzer):
    """Detects duplicate keys in dictionary/object literals."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py", ".js", ".ts"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> DuplicateDictKeyResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return DuplicateDictKeyResult(
                file_path=str(path),
                total_dicts=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DuplicateDictKeyResult(
                file_path=str(path),
                total_dicts=0,
            )

        dict_types = _DICT_TYPES.get(ext, set())
        pair_types = _PAIR_TYPES.get(ext, set())
        if not dict_types:
            return DuplicateDictKeyResult(
                file_path=str(path),
                total_dicts=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total_dicts = 0
        issues: list[DuplicateDictKeyIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in dict_types:
                total_dicts += 1
                self._check_dict(node, pair_types, issues)
            for child in node.children:
                stack.append(child)

        return DuplicateDictKeyResult(
            file_path=str(path),
            total_dicts=total_dicts,
            issues=issues,
        )

    def _check_dict(
        self,
        dict_node: tree_sitter.Node,
        pair_types: set[str],
        issues: list[DuplicateDictKeyIssue],
    ) -> None:
        seen: dict[str, int] = {}
        for child in dict_node.children:
            if child.type in pair_types:
                key_node = child.child_by_field_name("key")
                if key_node is None:
                    named = [c for c in child.children if c.is_named]
                    key_node = named[0] if named else None
                if key_node is None:
                    continue

                key_text = _get_key_text(key_node)
                if key_text in seen:
                    issues.append(DuplicateDictKeyIssue(
                        line=child.start_point[0] + 1,
                        issue_type=ISSUE_DUPLICATE_DICT_KEY,
                        severity=SEVERITY_MEDIUM,
                        description=_DESCRIPTIONS[ISSUE_DUPLICATE_DICT_KEY],
                        suggestion=_SUGGESTIONS[ISSUE_DUPLICATE_DICT_KEY],
                        context=_txt(child),
                        key=key_text,
                    ))
                else:
                    seen[key_text] = child.start_point[0] + 1
