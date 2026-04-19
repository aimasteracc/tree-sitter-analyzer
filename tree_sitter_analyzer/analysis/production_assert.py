"""Production Assert Detector.

Detects assert statements in non-test code. Assert statements are
stripped when Python runs with -O (optimize mode), making them
unreliable for data validation or invariant checking in production.

Issue types:
  - production_assert: assert statement in non-test code
  - assert_with_message: assert with side-effect message (still stripped)

Supports Python only.
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
SEVERITY_LOW = "low"

ISSUE_PRODUCTION_ASSERT = "production_assert"
ISSUE_ASSERT_WITH_MESSAGE = "assert_with_message"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_PRODUCTION_ASSERT: (
        "Assert statement in non-test code is stripped by python -O"
    ),
    ISSUE_ASSERT_WITH_MESSAGE: (
        "Assert with message expression may have side effects, "
        "still stripped by python -O"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_PRODUCTION_ASSERT: (
        "Replace with if/not check and raise, or use a proper "
        "validation library."
    ),
    ISSUE_ASSERT_WITH_MESSAGE: (
        "Replace with if/not check and raise ValueError or "
        "RuntimeError with the message."
    ),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


_TEST_PATH_INDICATORS: set[str] = {
    "test_",
    "tests",
    "_test.",
    "_tests",
    "conftest",
    "spec_",
}


_TEST_DIR_NAMES: set[str] = {"tests", "test", "spec", "specs", "__tests__"}


def _is_test_path(file_path: str) -> bool:
    path = Path(file_path)
    filename = path.name.lower()
    if filename.startswith("test_") or filename.startswith("spec_"):
        return True
    if filename.endswith("_test.py") or filename.endswith("_test.ts"):
        return True
    if filename == "conftest.py":
        return True
    if path.parent.name.lower() in _TEST_DIR_NAMES:
        return True
    return False


@dataclass(frozen=True)
class ProductionAssertIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
        }


@dataclass
class ProductionAssertResult:
    file_path: str
    total_asserts: int
    issues: list[ProductionAssertIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_asserts": self.total_asserts,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class ProductionAssertAnalyzer(BaseAnalyzer):
    """Detects assert statements in non-test code."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> ProductionAssertResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return ProductionAssertResult(
                file_path=str(path),
                total_asserts=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ProductionAssertResult(
                file_path=str(path),
                total_asserts=0,
            )

        if _is_test_path(str(path)):
            return ProductionAssertResult(
                file_path=str(path),
                total_asserts=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        total = 0
        issues: list[ProductionAssertIssue] = []

        stack: list[tree_sitter.Node] = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "assert_statement":
                total += 1
                has_message = False
                named_children = [
                    c for c in node.children if c.is_named
                ]
                if len(named_children) > 1:
                    has_message = True

                issue_type = (
                    ISSUE_ASSERT_WITH_MESSAGE
                    if has_message
                    else ISSUE_PRODUCTION_ASSERT
                )
                severity = (
                    SEVERITY_MEDIUM
                    if has_message
                    else SEVERITY_LOW
                )
                issues.append(ProductionAssertIssue(
                    line=node.start_point[0] + 1,
                    issue_type=issue_type,
                    severity=severity,
                    description=_DESCRIPTIONS[issue_type],
                    suggestion=_SUGGESTIONS[issue_type],
                    context=_txt(node),
                ))
            else:
                for child in node.children:
                    stack.append(child)

        return ProductionAssertResult(
            file_path=str(path),
            total_asserts=total,
            issues=issues,
        )
