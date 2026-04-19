"""Missing Break Detector.

Detects switch/case statements with missing break/return/throw,
causing unintentional fall-through:
  - missing_break: case without terminating statement (medium)

Supports JavaScript/TypeScript, Java. Go and Python switches
do not have fall-through by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"

ISSUE_MISSING_BREAK = "missing_break"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_MISSING_BREAK: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_MISSING_BREAK: "Case statement without break/return/throw — unintentional fall-through",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_MISSING_BREAK: "Add break, return, or throw to prevent fall-through.",
}

# Switch statement node types per language
_SWITCH_TYPES: dict[str, frozenset[str]] = {
    ".js": frozenset({"switch_statement"}),
    ".jsx": frozenset({"switch_statement"}),
    ".ts": frozenset({"switch_statement"}),
    ".tsx": frozenset({"switch_statement"}),
    ".java": frozenset({"switch_expression", "switch_statement"}),
}

# Case clause node types per language
_CASE_TYPES: dict[str, frozenset[str]] = {
    ".js": frozenset({"switch_case", "switch_default"}),
    ".jsx": frozenset({"switch_case", "switch_default"}),
    ".ts": frozenset({"switch_case", "switch_default"}),
    ".tsx": frozenset({"switch_case", "switch_default"}),
    ".java": frozenset({"switch_block_statement_group", "case_constant"}),
}

# Terminating statement types
_TERMINATOR_TYPES: frozenset[str] = frozenset({
    "break_statement",
    "return_statement",
    "throw_statement",
    "continue_statement",
    "yield_statement",
    "yield_expression",
})

# Comment node types for fallthrough detection
_COMMENT_NODE_TYPES: frozenset[str] = frozenset({
    "comment",
})

_FALLTHROUGH_PATTERNS: frozenset[str] = frozenset({
    "fallthrough", "fall through", "falls through",
    "FALLTHROUGH", "FALL THROUGH",
    "no break", "NO BREAK",
    "intentional", "INTENTIONAL",
})


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class MissingBreakIssue:
    line_number: int
    issue_type: str
    severity: str
    description: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class MissingBreakResult:
    total_switches: int
    total_cases: int
    issues: tuple[MissingBreakIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_switches": self.total_switches,
            "total_cases": self.total_cases,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _has_terminator(node: tree_sitter.Node) -> bool:
    """Check if a node tree contains a terminating statement."""
    if node.type in _TERMINATOR_TYPES:
        return True
    for child in node.children:
        if _has_terminator(child):
            return True
    return False


def _has_fallthrough_comment(node: tree_sitter.Node) -> bool:
    """Check if a case body contains a fallthrough comment."""
    text = _safe_text(node).lower()
    for pattern in _FALLTHROUGH_PATTERNS:
        if pattern.lower() in text:
            return True
    return False


def _has_comment_between(
    body_node: tree_sitter.Node,
    case_a: tree_sitter.Node,
    case_b: tree_sitter.Node,
) -> bool:
    """Check if there's a fallthrough comment between two cases."""
    a_end = case_a.end_point[0]
    b_start = case_b.start_point[0]

    for child in body_node.children:
        if child.type in _COMMENT_NODE_TYPES:
            comment_line = child.start_point[0]
            if a_end <= comment_line <= b_start:
                text = _safe_text(child).lower()
                for pattern in _FALLTHROUGH_PATTERNS:
                    if pattern.lower() in text:
                        return True
    return False


def _analyze_switch_js(
    switch_node: tree_sitter.Node,
    issues: list[MissingBreakIssue],
) -> int:
    """Analyze a JS/TS switch statement for missing breaks."""
    cases: list[tree_sitter.Node] = []
    body_node: tree_sitter.Node | None = None

    for child in switch_node.children:
        if child.type == "switch_body":
            body_node = child
            for gc in child.children:
                if gc.type in ("switch_case", "switch_default"):
                    cases.append(gc)
        elif child.type in ("switch_case", "switch_default"):
            cases.append(child)

    case_count = len(cases)
    for idx, case_node in enumerate(cases):
        is_last = idx == case_count - 1
        if is_last:
            continue

        # Check for fallthrough comment between this case and the next
        if body_node is not None and _has_comment_between(body_node, case_node, cases[idx + 1]):
            continue

        if _has_terminator(case_node):
            continue

        issues.append(MissingBreakIssue(
            line_number=case_node.start_point[0] + 1,
            issue_type=ISSUE_MISSING_BREAK,
            severity=_SEVERITY_MAP[ISSUE_MISSING_BREAK],
            description=_DESCRIPTIONS[ISSUE_MISSING_BREAK],
        ))

    return case_count


def _analyze_switch_java(
    switch_node: tree_sitter.Node,
    issues: list[MissingBreakIssue],
) -> int:
    """Analyze a Java switch statement for missing breaks."""
    case_count = 0

    # Java switch can have switch_block_statement_group nodes
    groups: list[tree_sitter.Node] = []
    for child in switch_node.children:
        if child.type == "switch_block":
            for gc in child.children:
                if gc.type == "switch_block_statement_group":
                    groups.append(gc)
                elif gc.type in ("switch_label", "case"):
                    case_count += 1

    if groups:
        case_count = len(groups)
        for idx, group in enumerate(groups):
            is_last = idx == case_count - 1
            if is_last:
                continue
            if _has_fallthrough_comment(group):
                continue
            if _has_terminator(group):
                continue

            issues.append(MissingBreakIssue(
                line_number=group.start_point[0] + 1,
                issue_type=ISSUE_MISSING_BREAK,
                severity=_SEVERITY_MAP[ISSUE_MISSING_BREAK],
                description=_DESCRIPTIONS[ISSUE_MISSING_BREAK],
            ))

    return case_count


class MissingBreakAnalyzer(BaseAnalyzer):
    """Analyzes code for missing break statements in switch/case."""

    SUPPORTED_EXTENSIONS: set[str] = {
        ".js", ".jsx", ".ts", ".tsx", ".java",
    }

    def analyze_file(self, file_path: Path | str) -> MissingBreakResult:
        path = Path(file_path)
        if not path.exists():
            return MissingBreakResult(
                total_switches=0,
                total_cases=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return MissingBreakResult(
                total_switches=0,
                total_cases=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> MissingBreakResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return MissingBreakResult(
                total_switches=0,
                total_cases=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        switch_types = _SWITCH_TYPES.get(ext, frozenset())
        issues: list[MissingBreakIssue] = []
        total_switches = 0
        total_cases = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_switches, total_cases

            if node.type in switch_types:
                total_switches += 1
                if ext in (".js", ".jsx", ".ts", ".tsx"):
                    total_cases += _analyze_switch_js(node, issues)
                elif ext == ".java":
                    total_cases += _analyze_switch_java(node, issues)
                return  # Don't recurse into switch

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return MissingBreakResult(
            total_switches=total_switches,
            total_cases=total_cases,
            issues=tuple(issues),
            file_path=str(path),
        )
