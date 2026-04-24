"""Finding suppression via inline comments.

Parses `# tsa: disable <rule>` comments from source files and provides
filtering to remove suppressed findings from analysis results.

Supported formats (language-aware):
  Python:       # tsa: disable <rule>
                # tsa: disable <rule1>, <rule2>
                # tsa: disable-all
                # tsa: enable
  JS/TS/Java:   // tsa: disable <rule>
                // tsa: disable <rule1>, <rule2>
                // tsa: disable-all
                // tsa: enable
  Go:           // tsa: disable <rule>
  Block:        /* tsa: disable <rule> */

Scope:
  - Line-level: comment on line N suppresses findings on line N+1
  - Same-line:  code followed by `# tsa: disable <rule>` suppresses that line
  - File-level: `tsa: disable-all` suppresses everything until `tsa: enable`
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

_SUPPRESSION_RE = re.compile(
    r"(?:#\s*|//\s*|\*\s*)"
    r"tsa:\s*"
    r"(disable-all|enable|disable)\s*"
    r"([^\n*#]*?)"
    r"\s*(?:\*/|$)"
)

_RULE_SPLIT_RE = re.compile(r"[,\s]+")

_COMMENT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".kt", ".rs", ".rb", ".php", ".swift", ".scala",
}


@dataclass(frozen=True)
class Suppression:
    """A parsed suppression directive."""

    rule_names: frozenset[str]
    line: int
    is_file_level: bool
    is_enable: bool


@dataclass
class SuppressionParseResult:
    """Result of parsing suppressions from a file."""

    file_path: str
    suppressions: list[Suppression] = field(default_factory=list)
    error: str | None = None

    @property
    def total_suppressions(self) -> int:
        return len([s for s in self.suppressions if not s.is_enable])

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_suppressions": self.total_suppressions,
            "suppressions": [
                {
                    "rules": sorted(s.rule_names),
                    "line": s.line,
                    "is_file_level": s.is_file_level,
                }
                for s in self.suppressions
                if not s.is_enable
            ],
        }


def parse_suppressions(file_path: Path | str) -> SuppressionParseResult:
    """Parse suppression comments from a source file."""
    path = Path(file_path)
    if not path.exists():
        return SuppressionParseResult(
            file_path=str(path), error="File not found"
        )
    if path.suffix.lower() not in _COMMENT_EXTENSIONS:
        return SuppressionParseResult(file_path=str(path))

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return SuppressionParseResult(
            file_path=str(path), error=str(exc)
        )

    suppressions: list[Suppression] = []
    for line_idx, line in enumerate(text.splitlines(), start=1):
        for match in _SUPPRESSION_RE.finditer(line):
            action = match.group(1)
            rules_str = match.group(2)

            if action == "disable-all":
                suppressions.append(
                    Suppression(
                        rule_names=frozenset(),
                        line=line_idx,
                        is_file_level=True,
                        is_enable=False,
                    )
                )
            elif action == "enable":
                suppressions.append(
                    Suppression(
                        rule_names=frozenset(),
                        line=line_idx,
                        is_file_level=True,
                        is_enable=True,
                    )
                )
            elif action == "disable" and rules_str:
                rules = frozenset(
                    r.strip()
                    for r in _RULE_SPLIT_RE.split(rules_str)
                    if r.strip()
                )
                if rules:
                    suppressions.append(
                        Suppression(
                            rule_names=rules,
                            line=line_idx,
                            is_file_level=False,
                            is_enable=False,
                        )
                    )

    return SuppressionParseResult(
        file_path=str(path), suppressions=suppressions
    )


def build_suppression_set(
    result: SuppressionParseResult,
) -> set[tuple[str, int]] | None:
    """Build a set of (rule_name, line) pairs that should be suppressed.

    Returns None for file-level suppression (all findings suppressed),
    or a set of specific (rule, target_line) pairs.

    Line-level suppressions apply to the NEXT line (standard convention).
    If the suppression is on the same line as the code (inline), it applies
    to that line too.
    """
    if not result.suppressions:
        return set()

    file_level_active = False
    specific: set[tuple[str, int]] = set()

    for sup in result.suppressions:
        if sup.is_enable:
            file_level_active = False
            continue

        if sup.is_file_level:
            file_level_active = True
            continue

        for rule in sup.rule_names:
            specific.add((rule, sup.line))
            specific.add((rule, sup.line + 1))

    if file_level_active:
        return None

    return specific


def is_suppressed(
    rule_name: str,
    line: int,
    suppression_set: set[tuple[str, int]] | None,
) -> bool:
    """Check if a specific finding is suppressed.

    suppression_set=None means file-level suppression is active (all suppressed).
    """
    if suppression_set is None:
        return True
    if not suppression_set:
        return False
    return (rule_name, line) in suppression_set


def filter_findings(
    findings: list[dict[str, Any]],
    suppression_set: set[tuple[str, int]] | None,
    rule_key: str = "finding_type",
    line_key: str = "line",
) -> list[dict[str, Any]]:
    """Filter a list of finding dicts, removing suppressed entries.

    Each finding dict must have keys matching rule_key and line_key.
    Returns a new list with suppressed findings removed.
    """
    if suppression_set is not None and not suppression_set:
        return list(findings)

    return [
        f
        for f in findings
        if not is_suppressed(
            f.get(rule_key, ""),
            f.get(line_key, 0),
            suppression_set,
        )
    ]
