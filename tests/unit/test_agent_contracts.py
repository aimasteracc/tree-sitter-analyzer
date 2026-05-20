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
        "code_patterns": ("main", "--code-patterns"),
        "codegraph_call_graph": ("main", "--call-graph"),
        "ast_cache": ("main", "--ast-cache"),
        "detect_routes": ("main", "--detect-routes"),
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


# ---------------------------------------------------------------------------
# Plugin Architecture Contracts
# ---------------------------------------------------------------------------

PLUGINS_DIR = PROJECT_ROOT / "tree_sitter_analyzer" / "languages"


def _discover_plugin_files() -> list[tuple[str, Path]]:
    """Return [(language_name, path), ...] for all plugin files."""
    result = []
    for p in sorted(PLUGINS_DIR.iterdir()):
        if p.name.startswith("_") or p.name.startswith(".") or p.name == "__init__.py":
            continue
        if p.is_file() and p.suffix == ".py" and p.name.endswith("_plugin.py"):
            result.append((p.stem.replace("_plugin", ""), p))
        elif p.is_dir() and p.name.endswith("_plugin"):
            plugin_py = p / "plugin.py"
            if plugin_py.exists():
                result.append((p.stem.replace("_plugin", ""), plugin_py))
    return result


def test_every_plugin_class_inherits_language_plugin() -> None:
    """All XxxPlugin classes must inherit from LanguagePlugin (not ElementExtractor)."""

    violations = []
    for _lang, path in _discover_plugin_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
                base_names = [
                    b.id if isinstance(b, ast.Name) else getattr(b, "attr", "?")
                    for b in node.bases
                ]
                if "ElementExtractor" in base_names:
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} "
                        f"{node.name} inherits ElementExtractor (should only inherit LanguagePlugin)"
                    )
    assert violations == [], "\n".join(violations)


def test_extract_elements_returns_dict() -> None:
    """extract_elements on any class must return dict[str, list[Any]], not list."""
    violations = []
    for _lang, path in _discover_plugin_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "extract_elements":
                ret = node.returns
                if ret is None:
                    continue
                ret_str = ast.unparse(ret)
                if ret_str.startswith("list") and "dict" not in ret_str:
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} "
                        f"extract_elements returns {ret_str} (must be dict[str, list[...]])"
                    )
    assert violations == [], "\n".join(violations)


def test_plugin_has_required_abstract_methods() -> None:
    """Each plugin must implement: get_language_name, get_file_extensions, create_extractor, analyze_file."""
    REQUIRED = {
        "get_language_name",
        "get_file_extensions",
        "create_extractor",
        "analyze_file",
    }
    violations = []
    for _lang, path in _discover_plugin_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
                methods = {
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                missing = REQUIRED - methods
                if missing:
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} "
                        f"{node.name} missing methods: {missing}"
                    )
    assert violations == [], "\n".join(violations)


def test_no_new_single_file_plugins_in_languages_root() -> None:
    """Prevent adding new single-file plugins. New languages must use package structure.

    Existing single-file plugins are grandfathered; this test only blocks NEW ones.
    """
    GRANDFATHERED = {
        "c_plugin.py",
        "cpp_plugin.py",
        "csharp_plugin.py",
        "css_plugin.py",
        "go_plugin.py",
        "html_plugin.py",
        "java_plugin.py",
        "kotlin_plugin.py",
        "php_plugin.py",
        "ruby_plugin.py",
        "rust_plugin.py",
        "swift_plugin.py",
        "yaml_plugin.py",
    }
    single_file_plugins = {
        p.name
        for p in PLUGINS_DIR.iterdir()
        if p.is_file() and p.suffix == ".py" and p.name.endswith("_plugin.py")
    }
    new_plugins = single_file_plugins - GRANDFATHERED
    assert not new_plugins, (
        f"New single-file plugins detected: {new_plugins}. "
        f"Use languages/<lang>_plugin/ package structure instead."
    )


def test_analyze_file_uses_create_extractor() -> None:
    """All analyze_file methods must use create_extractor(), not self.extractor.

    self.extractor creates hidden side-effect coupling. create_extractor()
    ensures each analysis gets a fresh, isolated extractor instance.
    """
    violations = []
    plugin_paths = []
    for p in sorted(PLUGINS_DIR.iterdir()):
        if p.name.startswith("_") or p.name.startswith(".") or p.name == "__init__.py":
            continue
        if p.is_file() and p.suffix == ".py" and p.name.endswith("_plugin.py"):
            plugin_paths.append(p)
        elif p.is_dir() and p.name.endswith("_plugin"):
            pp = p / "plugin.py"
            if pp.exists():
                plugin_paths.append(pp)
    for path in plugin_paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "analyze_file"
            ):
                body = ast.get_source_segment(source, node)
                if body and "self.extractor" in body and "create_extractor" not in body:
                    violations.append(f"{path.name}:{node.lineno}")
    assert not violations, (
        f"analyze_file uses self.extractor without create_extractor in: {violations}"
    )


def test_no_mcp_tool_overrides_set_project_path() -> None:
    """ARCH-A4 regression: ``BaseMCPTool.set_project_path`` is final by
    convention; tools that need to react to a project-root rebind must
    override :meth:`_on_project_root_changed` instead, so the dual-track
    init / rebind paths can't drift apart again.

    Each pattern this test catches has bitten the project at least once:
      * a subclass overriding set_project_path but forgetting to call
        super() (silently leaves base attributes pointing at the old root)
      * a subclass overriding both ``__init__`` AND ``set_project_path``
        with different init logic (constructor-built tools observe
        different state than rebound ones)
    """
    tools_dir = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"
    offenders: list[str] = []
    for path in sorted(tools_dir.glob("*.py")):
        if path.name == "base_tool.py":
            continue  # the base class itself is allowed to define it
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == "set_project_path"
                    ):
                        offenders.append(f"{path.name}::{node.name}.set_project_path")
    assert offenders == [], (
        "These tools override BaseMCPTool.set_project_path. Move the body "
        "into _on_project_root_changed instead (ARCH-A4):\n  " + "\n  ".join(offenders)
    )


def test_mcp_command_specs_have_resolvable_tool_classes() -> None:
    """ARCH-A2 regression: every MCP_COMMAND_SPECS entry's ``tool_attr``
    must be resolvable via ``_get_tool_class`` (i.e. present in
    ``_TOOL_CLASSES_BY_ATTR``). Adding a spec without updating the lookup
    table used to fail at runtime with ``Unknown MCP tool: …``; this test
    catches the drift at collection time."""
    from tree_sitter_analyzer.cli.commands.mcp_commands import (
        _TOOL_CLASSES_BY_ATTR,
        MCP_COMMAND_SPECS,
    )

    referenced = {spec.tool_attr for spec in MCP_COMMAND_SPECS}
    available = set(_TOOL_CLASSES_BY_ATTR)
    missing = referenced - available
    assert not missing, (
        f"MCP_COMMAND_SPECS references tool classes not registered in "
        f"_TOOL_CLASSES_BY_ATTR: {sorted(missing)}. Either add the class "
        f"to the dict in cli/commands/mcp_commands.py or remove the spec."
    )
    # Informational: don't enforce the reverse (extra classes), since a
    # tool might intentionally exist without a CLI spec (e.g. internal
    # helpers).


def test_mcp_server_module_does_not_eagerly_import_tools() -> None:
    """PERF-3 regression: ``tree_sitter_analyzer.mcp.server`` must not import
    the 23 individual tool modules at module load. Tool imports belong inside
    ``_create_tool_registry`` so callers that only touch the server module's
    surface (e.g. for help-text introspection) don't pay the cold-start tax.
    """
    source = (PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    offending: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.module:
                    if stmt.module.startswith(".tools."):
                        offending.append(stmt.module)
    assert offending == [], (
        "Top-level imports of .tools.* are forbidden in mcp/server.py "
        f"(PERF-3). Move them inside _create_tool_registry. Offenders: {offending}"
    )
