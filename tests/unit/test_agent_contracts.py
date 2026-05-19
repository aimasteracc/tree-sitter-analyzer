"""Contracts that keep agent-facing workflows stable."""

from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path

import tomllib
from hypothesis import settings as hypothesis_settings

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
    _assert_pytest_runtime_contract(
        config["pytest"]["addopts"],
        config["pytest"]["filterwarnings"],
    )


def test_pyproject_pytest_runtime_contract_mirror_is_locked() -> None:
    """pyproject's mirror config must not weaken the default pytest contract."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    pytest_options = data["tool"]["pytest"]["ini_options"]
    _assert_pytest_runtime_contract(
        pytest_options["addopts"],
        pytest_options["filterwarnings"],
    )


def _assert_pytest_runtime_contract(
    addopts: str | list[str],
    warning_filters: str | list[str],
) -> None:
    if isinstance(addopts, str):
        addopts_list = addopts.split()
    else:
        addopts_list = addopts
    if isinstance(warning_filters, str):
        warning_filter_list = [
            line.strip() for line in warning_filters.splitlines() if line.strip()
        ]
    else:
        warning_filter_list = warning_filters
    required = {
        "--numprocesses=auto",
        "--dist=loadfile",
        "--timeout=180",
        "--session-timeout=300",
        "--benchmark-disable",
    }

    missing = [option for option in sorted(required) if option not in addopts_list]
    assert missing == []
    assert warning_filter_list[0] == "error"
    assert "ignore::DeprecationWarning" not in warning_filter_list
    assert "ignore::PendingDeprecationWarning" not in warning_filter_list


def test_pytest_runtime_dependencies_are_declared() -> None:
    """The runtime contract depends on xdist and timeout being installed."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    dependency_groups = data["dependency-groups"]
    dev_dependencies = set(dependency_groups["dev"])

    assert "pytest-xdist>=3.8.0" in dev_dependencies
    assert "pytest-timeout>=2.4.0" in dev_dependencies


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
        for line_number, line in enumerate(path.read_text().splitlines(), start=1)
        if bare_pytest_command.match(line.strip()) or bare_pytest_code_span.search(line)
    ]

    assert bare_pytest_lines == []


def test_hypothesis_deadlines_are_disabled_for_parallel_suite_stability() -> None:
    """xdist load variance is bounded by pytest-timeout, not Hypothesis deadlines."""
    assert hypothesis_settings.default.deadline is None


def test_default_sustained_load_check_stays_fast_and_configurable() -> None:
    """Default performance checks use short configurable waits."""
    path = PROJECT_ROOT / "tests/integration/test_phase7_performance_integration.py"
    module = ast.parse(path.read_text())
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("DEFAULT_")
    }

    assert constants["DEFAULT_SUSTAINED_LOAD_ITERATIONS"] <= 20
    assert constants["DEFAULT_SUSTAINED_LOAD_INTERVAL_SECONDS"] <= 0.1
    assert constants["DEFAULT_SCALABILITY_RECOVERY_SECONDS"] <= 0.1
    assert constants["DEFAULT_RESOURCE_CLEANUP_SETTLE_SECONDS"] <= 0.1
    assert constants["DEFAULT_MEMORY_EFFICIENCY_FILES"] <= 10

    source = path.read_text()
    assert "TSA_SUSTAINED_LOAD_ITERATIONS" in source
    assert "TSA_SUSTAINED_LOAD_INTERVAL_SECONDS" in source
    assert "TSA_SCALABILITY_RECOVERY_SECONDS" in source
    assert "TSA_RESOURCE_CLEANUP_SETTLE_SECONDS" in source
    assert "TSA_MEMORY_EFFICIENCY_FILES" in source
    assert "while time.time() - start_time" not in source
    assert "asyncio.sleep(1)" not in source


def test_phase7_suite_simulated_work_stays_fast_and_configurable() -> None:
    """Summary-style integration checks should not spend seconds sleeping."""
    path = PROJECT_ROOT / "tests/integration/test_phase7_integration_suite.py"
    module = ast.parse(path.read_text())
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }

    assert constants["DEFAULT_PHASE7_SUITE_SIMULATION_SECONDS"] <= 0.05

    source = path.read_text()
    assert "TSA_PHASE7_SUITE_SIMULATION_SECONDS" in source
    assert "asyncio.sleep(0.2)" not in source
    assert "asyncio.sleep(0.15)" not in source
    assert "asyncio.sleep(0.1)" not in source


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
        "list_agent_skills": ("main", "--agent-skills"),
        "get_agent_workflow": ("main", "--agent-workflow"),
        "advise_parser_readiness": ("main", "--parser-readiness"),
        "get_project_overview": ("main", "--overview"),
        "check_project_health": ("main", "--project-health"),
        "check_file_health": ("main", "--file-health"),
        "analyze_dependencies": ("main", "--dependencies"),
        "analyze_change_impact": ("main", "--change-impact"),
        "refactoring_suggestions": ("main", "--refactor"),
        "safe_to_edit": ("main", "--safe-to-edit"),
        "smart_context": ("main", "--smart-context"),
        "symbol_lineage": ("main", "--symbol-lineage"),
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


def test_agent_docs_require_change_impact_verification_command() -> None:
    """Future agents should follow change-impact's verification command."""
    docs = {
        "AGENTS.md": (PROJECT_ROOT / "AGENTS.md").read_text(),
        "CLAUDE.md": (PROJECT_ROOT / "CLAUDE.md").read_text(),
    }

    for path, text in docs.items():
        assert "verification_command" in text, path
        assert "pytest_required" in text, path
        assert "--change-impact --format json" in text, path


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
