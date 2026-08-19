"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import re
import subprocess
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


def test_warning_prone_python_api_patterns_are_blocked() -> None:
    """Keep future agents from reintroducing known Python 3.14 warning sources."""
    blocked_patterns = {
        "asyncio.iscoroutinefunction(": "use inspect.iscoroutinefunction()",
        "datetime.utcnow(": "use datetime.now(UTC)",
        "lang_obj.query(": "use tree_sitter.Query(language, query)",
        "yaml_language.query(": "use tree_sitter.Query(language, query)",
        "language.query(": "use tree_sitter.Query(language, query)",
    }

    grep_command = ["git", "grep", "-n", "-F"]
    for pattern in blocked_patterns:
        grep_command.extend(["-e", pattern])
    grep_command.extend(["--", "tree_sitter_analyzer"])
    result = subprocess.run(
        grep_command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr

    violations = result.stdout.splitlines()
    untracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "tree_sitter_analyzer",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    for rel in untracked.stdout.splitlines():
        path = PROJECT_ROOT / rel
        if path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, replacement in blocked_patterns.items():
            if pattern in text:
                violations.append(f"{rel} matches {pattern}; {replacement}")

    assert violations == []


def _load_codemap_surface():
    """Import scripts/codemap_surface.py, the gate's static surface extractor."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "codemap_surface", PROJECT_ROOT / "scripts" / "codemap_surface.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codemap_sync_gate_sees_every_registered_mcp_tool() -> None:
    """The gate's static extractor must see the registry exactly, not approximately.

    A ``count > 0`` self-check is not a guarantee: a tree whose only match is a
    stale docstring mention passes it while the detector is functionally dead.
    Exact set equality is the guarantee.
    """
    cs = _load_codemap_surface()
    static_names = cs.extract_mcp_names(
        (PROJECT_ROOT / cs.MCP_REGISTRY).read_text(encoding="utf-8")
    )
    runtime_names = {name for name, _ in _create_tool_registry(str(PROJECT_ROOT))[0]}

    assert static_names == runtime_names


def test_codemap_sync_gate_sees_every_cli_flag() -> None:
    """Every option string the real parser exposes must be visible to the gate.

    argparse synthesises ``-h``/``--help`` with no defining source line, so those
    are the only permitted difference.
    """
    cs = _load_codemap_surface()
    static_flags: set[str] = set()
    for path in sorted((PROJECT_ROOT / cs.CLI_PREFIX).rglob("*.py")):
        static_flags |= cs.extract_cli_flags(path.read_text(encoding="utf-8"))
    runtime_flags = {
        s for a in create_argument_parser()._actions for s in a.option_strings
    }

    assert runtime_flags - static_flags == set(cs.ARGPARSE_IMPLICIT_FLAGS)


def test_codemap_sync_gate_watches_the_whole_cli_flag_surface() -> None:
    """Zero add_argument flags under cli/** may fall outside the watched filter.

    Before the gate repair, 82 of 405 add_argument calls were unwatched: the
    find-and-grep / list-files / search-content console scripts, all documented
    entry points in docs/CODEMAPS/cli.md. Coverage, not count, is the invariant
    that would have caught that.
    """
    cs = _load_codemap_surface()
    watched_root = (PROJECT_ROOT / cs.CLI_PREFIX).resolve()
    unwatched: list[str] = []
    for path in sorted((PROJECT_ROOT / "tree_sitter_analyzer" / "cli").rglob("*.py")):
        if path.resolve().is_relative_to(watched_root):
            continue
        if cs.extract_cli_flags(path.read_text(encoding="utf-8")):
            unwatched.append(str(path.relative_to(PROJECT_ROOT)))

    assert unwatched == []


def test_cli_codemap_flag_count_matches_the_real_parser() -> None:
    """docs/CODEMAPS/cli.md's flag count is the CI net for a CLI-side gate bypass.

    AGENTS.md claims a CI safety net exists behind the local escape hatch. That was
    true for mcp-tools.md and false for cli.md, which had no CI check at all, so a
    CLI-side bypass was unrecoverable. This is that net. The codemap drifted to 295
    against a real 324 while the gate was dead.
    """
    codemap = (PROJECT_ROOT / "docs" / "CODEMAPS" / "cli.md").read_text(
        encoding="utf-8"
    )
    match = re.search(r"\((\d+) unique flags total", codemap)
    assert match is not None, "docs/CODEMAPS/cli.md must state '(N unique flags total'"
    documented = int(match.group(1))

    actual = len(
        {
            s
            for a in create_argument_parser()._actions
            for s in a.option_strings
            if s.startswith("--")
        }
    )

    assert documented == actual
