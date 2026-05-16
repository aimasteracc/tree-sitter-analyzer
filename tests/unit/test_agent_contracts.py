"""Contracts that keep agent-facing workflows stable."""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import tomllib

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}


def test_default_pytest_runtime_contract_is_locked() -> None:
    """The default full suite must stay parallel and bounded under 5 minutes."""
    config = configparser.ConfigParser()
    config.read(PROJECT_ROOT / "pytest.ini")
    addopts = config["pytest"]["addopts"]
    warning_filters = config["pytest"]["filterwarnings"]

    required = {
        "--numprocesses=auto",
        "--dist=loadfile",
        "--timeout=180",
        "--session-timeout=300",
        "--benchmark-disable",
    }

    missing = [option for option in sorted(required) if option not in addopts]
    assert missing == []
    assert "error" in warning_filters
    assert "ignore::DeprecationWarning" not in warning_filters
    assert "ignore::PendingDeprecationWarning" not in warning_filters


def test_pytest_runtime_dependencies_are_declared() -> None:
    """The runtime contract depends on xdist and timeout being installed."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    dependency_groups = data["dependency-groups"]
    dev_dependencies = set(dependency_groups["dev"])

    assert "pytest-xdist>=3.8.0" in dev_dependencies
    assert "pytest-timeout>=2.4.0" in dev_dependencies


def test_registered_mcp_tools_have_cli_parity() -> None:
    """Every registered MCP tool must have a documented CLI access path."""
    parser = create_argument_parser()
    main_cli_options = {
        option for action in parser._actions for option in action.option_strings
    }

    with (PROJECT_ROOT / "pyproject.toml").open("rb") as f:
        scripts = tomllib.load(f)["project"]["scripts"]

    tool_to_cli = {
        "check_code_scale": ("main", "--metrics-only"),
        "analyze_code_structure": ("main", "--structure"),
        "extract_code_section": ("main", "--partial-read"),
        "query_code": ("main", "--query-key"),
        "list_files": ("script", "list-files"),
        "search_content": ("script", "search-content"),
        "find_and_grep": ("script", "find-and-grep"),
        "get_project_overview": ("main", "--overview"),
        "check_project_health": ("main", "--project-health"),
        "check_file_health": ("main", "--file-health"),
        "analyze_dependencies": ("main", "--dependencies"),
        "analyze_change_impact": ("main", "--change-impact"),
        "refactoring_suggestions": ("main", "--refactor"),
        "safe_to_edit": ("main", "--safe-to-edit"),
        "smart_context": ("main", "--smart-context"),
    }

    tool_names = {name for name, _tool in _create_tool_registry(str(PROJECT_ROOT))[0]}
    assert tool_names == set(tool_to_cli)

    missing_main_flags = [
        cli_name
        for tool_name, (kind, cli_name) in tool_to_cli.items()
        if tool_name in tool_names
        and kind == "main"
        and cli_name not in main_cli_options
    ]
    missing_scripts = [
        cli_name
        for tool_name, (kind, cli_name) in tool_to_cli.items()
        if tool_name in tool_names and kind == "script" and cli_name not in scripts
    ]

    assert missing_main_flags == []
    assert missing_scripts == []


def test_warning_prone_python_api_patterns_are_blocked() -> None:
    """Keep future agents from reintroducing known Python 3.14 warning sources."""
    blocked_patterns = {
        r"\basyncio\.iscoroutinefunction\(": "use inspect.iscoroutinefunction()",
        r"\bdatetime\.utcnow\(": "use datetime.now(UTC)",
        r"\blang_obj\.query\(": "use tree_sitter.Query(language, query)",
        r"\byaml_language\.query\(": "use tree_sitter.Query(language, query)",
        r"\blanguage\.query\(": "use tree_sitter.Query(language, query)",
    }

    violations: list[str] = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in SKIPPED_SCAN_DIRS for part in path.parts):
            continue

        text = path.read_text(encoding="utf-8")
        for pattern, replacement in blocked_patterns.items():
            for match in re.finditer(pattern, text):
                line_number = text.count("\n", 0, match.start()) + 1
                relative_path = path.relative_to(PROJECT_ROOT)
                violations.append(
                    f"{relative_path}:{line_number} matches {pattern}; {replacement}"
                )

    assert violations == []
