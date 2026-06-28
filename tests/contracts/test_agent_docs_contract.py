"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # Python 3.10 — fall back to the tomli back-port
    import tomli as tomllib
from hypothesis import settings as hypothesis_settings

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".benchmark-repos",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}


def test_agent_facing_docs_do_not_recommend_bare_pytest() -> None:
    """Agent docs should route pytest through uv for consistent environments."""
    bare_pytest_command = re.compile(r"^(?:\$\s+)?pytest(?:\s|$)")
    bare_pytest_code_span = re.compile(r"`pytest(?:\s[^`]*)?`")
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "CLAUDE.md",
        PROJECT_ROOT / "docs" / "TESTING.md",
        PROJECT_ROOT / "docs" / "developer_guide.md",
    ]
    bare_pytest_lines = [
        f"{path.relative_to(PROJECT_ROOT)}:{line_number}:{line}"
        for path in paths
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if bare_pytest_command.match(line.strip()) or bare_pytest_code_span.search(line)
    ]

    assert bare_pytest_lines == []


def test_agent_docs_require_change_impact_verification_command() -> None:
    """Future agents should follow change-impact's verification command."""
    docs = {
        "AGENTS.md": (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        "CLAUDE.md": (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
    }

    for path, text in docs.items():
        assert "verification_command" in text, path
        assert "pytest_required" in text, path
        assert "--change-impact --format json" in text, path


def test_agent_docs_require_local_patch_coverage_gate() -> None:
    """Future agents should pass local patch coverage before Codecov sees a PR."""
    script = PROJECT_ROOT / "scripts" / "check_patch_coverage.py"
    agents_text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert script.exists(), "scripts/check_patch_coverage.py must exist"
    assert "check_patch_coverage.py" in agents_text
    assert "--cov=tree_sitter_analyzer" in agents_text
    assert "--cov-report=json" in agents_text
    assert "Codecov" in agents_text


def test_agent_docs_require_dogfood_feedback_memory_loop() -> None:
    """Agents should use TSA feedback and preserve reusable findings in memory."""
    agents_text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Agent Dogfood Feedback Loop" in agents_text
    assert "tree_sitter_analyzer --change-impact --format json" in agents_text
    assert "memory_store" in agents_text
    assert "tsa/agent-feedback" in agents_text
    assert "tools_used" in agents_text
    assert "verification" in agents_text


@pytest.mark.slow_ok  # scans the Python API source for warning-prone patterns; ~5-5.5s, tips the 5s budget under Windows full-matrix load
def test_warning_prone_python_api_patterns_are_blocked() -> None:
    """Keep future agents from reintroducing known Python 3.14 warning sources."""
    blocked_patterns = {
        r"\basyncio\.iscoroutinefunction\(": "use inspect.iscoroutinefunction()",
        r"\bdatetime\.utcnow\(": "use datetime.now(UTC)",
        r"\blang_obj\.query\(": "use tree_sitter.Query(language, query)",
        r"\byaml_language\.query\(": "use tree_sitter.Query(language, query)",
        r"\blanguage\.query\(": "use tree_sitter.Query(language, query)",
    }

    newline = "\n"
    violations: list[str] = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in SKIPPED_SCAN_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath) / filename
            rel = str(path.relative_to(PROJECT_ROOT))
            text = path.read_text(encoding="utf-8")
            for pattern, replacement in blocked_patterns.items():
                for match in re.finditer(pattern, text):
                    match_start = match.start()
                    line_number = text.count(newline, 0, match_start) + 1
                    msg = f"{rel}:{line_number} matches {pattern}; {replacement}"
                    violations.append(msg)

    assert violations == []
