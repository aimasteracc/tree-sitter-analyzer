"""Documentation contracts — every CLI example in our docs must parse.

If a doc shows ``uv run tree-sitter-analyzer --foo bar``, the parser must
accept ``--foo``. This catches doc drift (flag was renamed, doc didn't
catch up) at CI time instead of at user-frustration time.

Mirrors the pattern from ``tests/unit/test_agent_contracts.py`` —
agent-facing doc invariants enforced as tests.
"""

from __future__ import annotations

import re
from pathlib import Path

from tree_sitter_analyzer.cli_main import create_argument_parser

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# All docs we sweep for CLI examples. Missing files are silently skipped
# (e.g., AGENTS.md may not exist in every branch yet).
DOC_PATHS = [
    PROJECT_ROOT / "CLAUDE.md",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "docs" / "TESTING.md",
    PROJECT_ROOT / "docs" / "developer_guide.md",
]

# Docs that MUST contain at least one CLI example. These are the canonical
# CLI-reference docs — README is the user-facing entry point. Keeping this
# list narrow avoids forcing fake CLI examples into prose-only docs.
DOCS_REQUIRING_CLI_EXAMPLES = [
    PROJECT_ROOT / "README.md",
]

# Match ``uv run tree-sitter-analyzer ...`` or bare ``tree-sitter-analyzer ...``
# Capture the rest of the line so we can extract long-form flags.
# Require trailing whitespace or end-of-line so we don't match
# ``tree-sitter-analyzer[mcp]`` (a package extra, not a CLI invocation).
_CLI_LINE = re.compile(
    r"(?:uv\s+run\s+)?tree-sitter-analyzer(?:\s+|$)([^\n`]*)",
)
# Long-form flag (``--foo`` or ``--foo-bar``).
_FLAG = re.compile(r"--[a-z][a-z0-9-]*")


def _iter_cli_lines() -> list[tuple[Path, int, str]]:
    """Yield ``(path, line_number, tail_after_command)`` for every CLI
    invocation in the documented docs that exist on disk."""
    out: list[tuple[Path, int, str]] = []
    for path in DOC_PATHS:
        if not path.exists():
            continue
        for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _CLI_LINE.search(line)
            if match:
                out.append((path, ln, match.group(1).strip()))
    return out


def test_documented_cli_flags_exist_in_parser() -> None:
    """Every --flag mentioned in our docs must be a registered argparse
    option. Catches doc drift the moment a flag is renamed or removed."""
    parser = create_argument_parser()
    valid_flags = {
        opt
        for action in parser._actions
        for opt in action.option_strings
        if opt.startswith("--")
    }
    invalid: list[tuple[Path, int, str]] = []
    for path, ln, tail in _iter_cli_lines():
        for flag in _FLAG.findall(tail):
            if flag not in valid_flags:
                invalid.append((path, ln, flag))
    assert invalid == [], (
        "These doc examples reference --flags the parser does not accept "
        "(rename the doc or restore the flag):\n"
        + "\n".join(
            f"  {path.relative_to(PROJECT_ROOT)}:{ln} -> {flag}"
            for path, ln, flag in invalid
        )
    )


def test_canonical_cli_reference_doc_has_examples() -> None:
    """Guard against the canonical CLI-reference doc(s) going empty.
    If README.md ever stops mentioning ``tree-sitter-analyzer``, users
    lose their entry-point cheat sheet — fail loudly."""
    sparse: list[str] = []
    for path in DOCS_REQUIRING_CLI_EXAMPLES:
        if not path.exists():
            sparse.append(f"MISSING: {path.relative_to(PROJECT_ROOT)}")
            continue
        examples = [tail for p, _, tail in _iter_cli_lines() if p == path]
        if not examples:
            sparse.append(f"NO CLI EXAMPLES: {path.relative_to(PROJECT_ROOT)}")
    assert sparse == [], (
        "These canonical CLI-reference docs have ZERO "
        f"tree-sitter-analyzer CLI examples — users get no concrete "
        f"reference: {sparse}"
    )
