"""Contracts that keep agent-facing workflows stable."""

from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

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


def test_package_and_mcp_versions_are_aligned() -> None:
    """Release prep must keep package and MCP server versions in lockstep."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    project_version = data["project"]["version"]
    package_init = (PROJECT_ROOT / "tree_sitter_analyzer" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert data["tool"]["mcp"]["server_version"] == project_version
    assert f'__version__ = "{project_version}"' in package_init


def test_ast_cache_call_edge_extraction_does_not_depend_on_call_graph() -> None:
    """ASTCache and CallGraph must share extraction helpers without a back-edge."""
    path = PROJECT_ROOT / "tree_sitter_analyzer" / "_ast_extraction.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert "call_graph" not in imports
    assert "tree_sitter_analyzer.call_graph" not in imports


def test_callee_resolution_algorithm_has_single_shared_home() -> None:
    """CallGraph/CrossFile/Synapse may expose APIs, but not bespoke algorithms."""
    call_graph = (PROJECT_ROOT / "tree_sitter_analyzer" / "call_graph.py").read_text(
        encoding="utf-8"
    )
    cross_file = (
        PROJECT_ROOT / "tree_sitter_analyzer" / "cross_file_resolver.py"
    ).read_text(encoding="utf-8")
    synapse_context = (
        PROJECT_ROOT / "tree_sitter_analyzer" / "synapse_resolver" / "_context.py"
    ).read_text(encoding="utf-8")

    assert "def _resolve_callee_from_cache" not in call_graph
    assert "CalleeResolver(" in call_graph
    assert "CalleeResolver(" in cross_file
    assert "CalleeResolver(" in synapse_context


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
        # 600s ceiling: the suite passes in ~5 min on CI but the
        # old 300s budget left zero headroom and caused intermittent
        # session-timeout kills on slower runners.
        "--session-timeout=600",
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


def test_local_runtime_artifacts_are_gitignored_without_global_results_trap() -> None:
    """Dogfood/cache output must stay local without hiding every results dir."""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {
        line.strip()
        for line in gitignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ".ast-cache/" in lines
    assert "**/.ast-cache/" in lines
    assert ".omm/" in lines
    assert "ruvector.db" in lines
    assert "/results/" in lines
    assert "results/" not in lines
    assert "benchmarks/codegraph_compare/results/*" in lines
    assert "!benchmarks/codegraph_compare/results/.gitkeep" in lines


def test_reusable_test_workflow_has_job_timeout() -> None:
    """The CI matrix must fail fast instead of hanging forever on runner stalls."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")

    for job_name in ("test-matrix-pr", "test-matrix-full"):
        test_matrix = re.search(
            rf"(?ms)^  {job_name}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
            text,
        )

        assert test_matrix is not None, job_name
        assert re.search(
            r"(?m)^    timeout-minutes:\s*15\s*$",
            test_matrix.group("body"),
        ), job_name


def test_pr_ci_uses_fast_matrix_while_release_keeps_full_matrix() -> None:
    """PRs should get fast feedback; release/hotfix keep exhaustive validation."""
    reusable_text = (
        PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    ).read_text(encoding="utf-8")
    ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    release_text = (
        PROJECT_ROOT / ".github" / "workflows" / "release-automation.yml"
    ).read_text(encoding="utf-8")
    hotfix_text = (
        PROJECT_ROOT / ".github" / "workflows" / "hotfix-automation.yml"
    ).read_text(encoding="utf-8")

    assert "matrix-profile:" in reusable_text
    assert "test-matrix-pr:" in reusable_text
    assert "test-matrix-full:" in reusable_text
    assert "if: inputs.matrix-profile == 'pr'" in reusable_text
    assert "if: inputs.matrix-profile == 'full'" in reusable_text

    pr_matrix = re.search(
        r"(?ms)^  test-matrix-pr:\n(?P<body>.*?)(?=^  test-matrix-full:)",
        reusable_text,
    )
    assert pr_matrix is not None
    pr_body = pr_matrix.group("body")
    assert pr_body.count("python-version:") == 4
    assert 'python-version: "3.10"' not in pr_body
    assert 'python-version: "3.12"' not in pr_body
    assert 'python-version: "3.13"' in pr_body
    assert "windows-latest" in pr_body
    assert "macos-latest" in pr_body

    assert "github.event_name == 'pull_request' && 'pr' || 'full'" in ci_text
    assert 'matrix-profile: "full"' in release_text
    assert 'matrix-profile: "full"' in hotfix_text


def test_ci_full_language_suite_runs_once_per_reusable_test_matrix() -> None:
    """Exhaustive language golden tests must not run on every OS/Python axis."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")

    assert (
        '-m "not requires_ripgrep and not requires_fd and not slow and not e2e"' in text
    )
    assert (
        '-m "not requires_ripgrep and not requires_fd and not slow and not e2e and not full_language"'
        in text
    )


def test_standalone_coverage_workflow_is_manual_only() -> None:
    """Avoid duplicate full coverage runs; reusable-test owns PR/push coverage."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "test-coverage.yml"
    text = workflow.read_text(encoding="utf-8")

    on_block = re.search(r"(?ms)^on:\n(?P<body>.*?)(?=^env:|\Z)", text)
    assert on_block is not None
    body = on_block.group("body")

    assert "workflow_dispatch:" in body
    assert re.search(r"(?m)^  pull_request:", body) is None
    assert re.search(r"(?m)^  push:", body) is None


def test_all_language_golden_tests_are_tier_marked() -> None:
    """All-language suites need an explicit marker so CI can tier them."""
    marker = "pytestmark = pytest.mark.full_language"
    paths = [
        PROJECT_ROOT / "tests" / "golden" / "test_golden_corpus.py",
        PROJECT_ROOT / "tests" / "regression" / "test_plugin_golden_masters.py",
    ]

    for path in paths:
        assert marker in path.read_text(encoding="utf-8"), path


def test_agent_docs_lock_ci_test_tier_contract() -> None:
    """Agents should preserve the CI split between focused and exhaustive gates."""
    agents_text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "CI Test Tier Contract" in agents_text
    assert "full_language" in agents_text
    assert "reusable-test.yml" in agents_text
    assert "test-coverage.yml" in agents_text
    assert "manual-only" in agents_text
    assert "matrix-profile: pr" in agents_text
    assert "matrix-profile: full" in agents_text


def test_ci_route_job_controls_expensive_optional_jobs() -> None:
    """Main CI should route slow optional jobs instead of always running them."""
    ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "route:" in ci_text
    assert "python3 scripts/ci_route.py" in ci_text
    assert "run_e2e_smoke" in ci_text
    assert "run_regression" in ci_text
    assert "run_sql_platform_compat" in ci_text
    assert "check_optional" in ci_text


def test_expensive_workflows_are_not_direct_pr_push_duplicates() -> None:
    """Regression and SQL compatibility run through CI routing, not twice."""
    for workflow_name in ("regression-tests.yml", "sql-platform-compat.yml"):
        text = (PROJECT_ROOT / ".github" / "workflows" / workflow_name).read_text(
            encoding="utf-8"
        )
        on_block = re.search(r"(?ms)^on:\n(?P<body>.*?)(?=^env:|^jobs:|\Z)", text)
        assert on_block is not None
        body = on_block.group("body")

        assert "workflow_call:" in body, workflow_name
        assert re.search(r"(?m)^  pull_request:", body) is None, workflow_name
        assert re.search(r"(?m)^  push:", body) is None, workflow_name


def test_benchmarks_are_path_filtered_for_pr_and_push() -> None:
    """Benchmarks should not run for unrelated PRs."""
    text = (PROJECT_ROOT / ".github" / "workflows" / "benchmarks.yml").read_text(
        encoding="utf-8"
    )

    assert "paths:" in text
    assert "tests/benchmarks/**" in text
    assert "tree_sitter_analyzer/ast_cache.py" in text


def test_bandit_security_scan_is_blocking_and_configured() -> None:
    """The reusable quality workflow must not paper over Bandit failures."""
    text = (PROJECT_ROOT / ".github" / "workflows" / "reusable-quality.yml").read_text(
        encoding="utf-8"
    )
    security_job = re.search(
        r"(?ms)^  security:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        text,
    )

    assert security_job is not None
    body = security_job.group("body")

    assert "continue-on-error" not in body
    assert "bandit -c pyproject.toml -r tree_sitter_analyzer/" in body
    assert "|| true" not in body
    assert 'exit "$BANDIT_STATUS"' in body


def test_gitflow_documentation_is_present() -> None:
    """The GitFlow mandate must remain documented + machine-enforced.

    Three artifacts are required so the rule survives both casual edits
    and CI bypass attempts:
      1. ``GITFLOW.md`` at repo root — the source of truth.
      2. ``AGENTS.md`` references it from the "GitFlow Branching Mandate"
         section so any agent reading AGENTS.md sees the rule.
      3. ``.github/workflows/gitflow-guard.yml`` enforces head→base
         naming on every PR — the CI safety net.

    If you intentionally restructure how GitFlow is documented, update
    this test in the same commit and explain why in the PR description.
    """
    gitflow_md = PROJECT_ROOT / "GITFLOW.md"
    agents_md = PROJECT_ROOT / "AGENTS.md"
    guard_yml = PROJECT_ROOT / ".github" / "workflows" / "gitflow-guard.yml"

    assert gitflow_md.exists(), "GITFLOW.md must exist at repo root"
    assert agents_md.exists(), "AGENTS.md must exist at repo root"
    assert guard_yml.exists(), (
        ".github/workflows/gitflow-guard.yml must exist — the CI "
        "enforcement layer for the GitFlow branching mandate"
    )

    agents_text = agents_md.read_text(encoding="utf-8")
    assert "GitFlow Branching Mandate" in agents_text, (
        "AGENTS.md must contain a 'GitFlow Branching Mandate' section "
        "linking to GITFLOW.md"
    )
    assert "GITFLOW.md" in agents_text, (
        "AGENTS.md's GitFlow section must link to GITFLOW.md by name"
    )

    guard_text = guard_yml.read_text(encoding="utf-8")
    # The guard must check both main and develop as protected bases,
    # otherwise an agent could open a stray PR against either branch.
    for required_check in ("main", "develop", "release/v", "hotfix/"):
        assert required_check in guard_text, (
            f"gitflow-guard.yml must reference {required_check!r} in its "
            "validation logic — see AGENTS.md 'GitFlow Branching Mandate'"
        )


def test_gitflow_guard_does_not_allow_bot_prs_to_main() -> None:
    """Bot branch shortcuts must not bypass the protected main release flow."""
    guard_text = (
        PROJECT_ROOT / ".github" / "workflows" / "gitflow-guard.yml"
    ).read_text(encoding="utf-8")
    bot_case = re.search(
        r"(?ms)dependabot/\*\|renovate/\*\|github-actions/\*\).*?;;",
        guard_text,
    )

    assert bot_case is not None
    body = bot_case.group(0)
    assert '[ "${BASE}" = "main" ]' in body
    assert "Bot PRs to main MUST come from release/v* or hotfix/*" in body
    assert "exit 0" in body


def test_release_and_hotfix_prs_use_gitflow_branch_heads() -> None:
    """Release/hotfix automation must open main PRs from GitFlow branches."""
    release_text = (
        PROJECT_ROOT / ".github" / "workflows" / "release-automation.yml"
    ).read_text(encoding="utf-8")
    hotfix_text = (
        PROJECT_ROOT / ".github" / "workflows" / "hotfix-automation.yml"
    ).read_text(encoding="utf-8")

    for workflow_name, text, trigger in (
        ("release-automation.yml", release_text, "release/v*"),
        ("hotfix-automation.yml", hotfix_text, "hotfix/*"),
    ):
        assert trigger in text, workflow_name
        assert "--base main" in text, workflow_name
        assert '--head "${GITHUB_REF_NAME}"' in text, workflow_name

    assert "release-to-main" not in release_text
    assert "hotfix-to-main" not in hotfix_text


def test_release_and_hotfix_finalize_prs_do_not_mask_closed_prs() -> None:
    """A closed, unmerged finalize PR means the release/hotfix is not landed."""
    workflows = {
        "release-automation.yml": PROJECT_ROOT
        / ".github"
        / "workflows"
        / "release-automation.yml",
        "hotfix-automation.yml": PROJECT_ROOT
        / ".github"
        / "workflows"
        / "hotfix-automation.yml",
    }

    for workflow_name, workflow_path in workflows.items():
        text = workflow_path.read_text(encoding="utf-8")
        create_pr = re.search(
            r"(?ms)^      - name: Create Pull Request to main\n(?P<body>.*?)(?=^      - name:|\Z)",
            text,
        )

        assert create_pr is not None, workflow_name
        body = create_pr.group("body")
        assert "--state all" in body, workflow_name
        assert "closed without merge" in body, workflow_name
        assert "refusing to treat finalization as successful" in body, workflow_name
        assert "exit 1" in body, workflow_name
        assert "|| gh pr view" not in body, workflow_name


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
        "get_code_outline": ("main", "--outline"),
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
        "codegraph_callers": ("main", "--call-graph"),
        "codegraph_callees": ("main", "--call-graph"),
        # Tree primitives (mycelium RFC-0020/0021 parity).
        "codegraph_callee_tree": ("main", "--callee-tree"),
        "codegraph_caller_tree": ("main", "--caller-tree"),
        "codegraph_symbol_search": ("main", "--symbol-search"),
        "codegraph_resolve": ("main", "--symbol-resolve"),
        "ast_cache": ("main", "--ast-cache"),
        "ast_diff": ("main", "--ast-diff"),
        "codegraph_ast_path": ("main", "--ast-path"),
        "codegraph_overview": ("main", "--codegraph-overview"),
        "codegraph_navigate": ("main", "--codegraph-navigate"),
        # CodeGraph parity gap-closure (2026-05-24).
        "codegraph_status": ("main", "--codegraph-status"),
        "codegraph_context": ("main", "--codegraph-context"),
        "codegraph_explore": ("main", "--codegraph-explore"),
        "codegraph_query": ("main", "--codegraph-query"),
        "codegraph_impact": ("main", "--codegraph-impact"),
        "codegraph_pr_review": ("main", "--pr-review"),
        "semantic_classify": ("main", "--semantic-classify"),
        "detect_routes": ("main", "--detect-routes"),
        "codegraph_import_graph": ("main", "--import-graph"),
        "codegraph_dead_code": ("main", "--dead-code"),
        "codegraph_similarity": ("main", "--code-similarity"),
        # CodeGraph parity tools registered with codegraph_-prefixed names:
        # their CLI flags use the unprefixed form (--class-hierarchy,
        # --dependency-matrix) to keep the user-facing surface short.
        "codegraph_class_hierarchy": ("main", "--class-hierarchy"),
        "codegraph_class_inspect": ("main", "--class-inspect"),
        "codegraph_dependency_matrix": ("main", "--dependency-matrix"),
        # Feature 3 (Constraint DSL): MCP tool ``check_constraints`` ships
        # with the CLI flag ``--check-constraints`` for CLI/MCP parity.
        "check_constraints": ("main", "--check-constraints"),
        # Tools that already had CLI flags but were missing from this
        # mapping table while the server.py registry was stale. Now that
        # server.py delegates to the central registry, these come into
        # scope automatically.
        "codegraph_call_path": ("main", "--call-path"),
        "codegraph_xref": ("main", "--codegraph-xref"),
        "codegraph_sitemap": ("main", "--codegraph-sitemap"),
        "codegraph_complexity_heatmap": ("main", "--codegraph-complexity-heatmap"),
        "codegraph_visualize": ("main", "--codegraph-visualize"),
        "codegraph_uml": ("main", "--uml"),
        # PL-C sprint: the cache-management trio now has real CLI flags
        # (was ``mcp_only`` exemptions before).
        "codegraph_autoindex": ("main", "--autoindex"),
        "codegraph_full_index": ("main", "--full-index"),
        "codegraph_metrics": ("main", "--codegraph-metrics"),
        "codegraph_incremental_sync": ("main", "--incremental-sync"),
        # consolidated-only tools ported during merge of feat/autonomous-dev
        "trace_impact": ("main", "--trace-impact"),
        "modification_guard": ("main", "--modification-guard"),
        "batch_search": ("main", "--batch-search"),
        "build_project_index": ("main", "--build-project-index"),
        "check_tools": ("main", "--check-tools"),
        "decision_journal": ("main", "--decision-journal"),
        "doc_sync": ("main", "--doc-sync"),
        "codegraph_test_gap": ("main", "--test-gap"),
    }

    # ------------------------------------------------------------------
    # Wave C2 re-key: the MCP surface is now the 8 facades, NOT the 63
    # legacy tool names. ``tool_to_cli`` above is keyed by the legacy
    # CAPABILITY name (the thing that still owns a 1:1 CLI flag); the
    # parity contract is re-expressed as ``(facade, action) ↔ CLI flag``
    # via ``facade_map.LEGACY_TOOL_MAP``. The 62-row capability coverage
    # is PRESERVED (re-keyed, not deleted) per PRD §4/§5.
    # ------------------------------------------------------------------
    from tree_sitter_analyzer.mcp.facade_map import (
        FACADE_NAMES,
        LEGACY_TOOL_MAP,
        NEW_ACTION_PARITY,
        SET_PROJECT_PATH_TOOL_NAME,
    )

    registered_facades = {
        name for name, _tool in _create_tool_registry(str(PROJECT_ROOT))[0]
    }
    # 1. The registry exposes exactly the 8 facades (no legacy leakage).
    assert registered_facades == set(FACADE_NAMES)

    # 2. Every capability with a CLI flag re-keys to a live (facade, action)
    #    pair (or is the standalone set_project_path infra entry). Guards
    #    "no CLI capability lost its facade route during cutover".
    #    New-only actions (NEW_ACTION_PARITY) are also valid routes — they were
    #    never v1.x legacy names, so they live outside LEGACY_TOOL_MAP.
    unmapped_capabilities = [
        tool_name
        for tool_name in tool_to_cli
        if (
            tool_name not in LEGACY_TOOL_MAP
            and tool_name not in NEW_ACTION_PARITY
            and tool_name != SET_PROJECT_PATH_TOOL_NAME
        )
    ]
    assert unmapped_capabilities == [], (
        "These capabilities have a CLI flag but no (facade, action) route — "
        "they were dropped during the facade cutover: " + repr(unmapped_capabilities)
    )

    # 3. Every facade-routed capability keeps a CLI parity entry — re-keyed
    #    coverage stays 1:1 with the CLI surface (62-row preservation).
    missing_cli_for_route = sorted(set(LEGACY_TOOL_MAP) - set(tool_to_cli))
    assert missing_cli_for_route == [], (
        "These facade-backed capabilities have NO CLI parity entry — every "
        "(facade, action) must keep a documented CLI access path: "
        + repr(missing_cli_for_route)
    )

    # 3b. NEW_ACTION_PARITY entries also have live CLI flags (same bar as legacy).
    missing_cli_for_new_actions = [
        key
        for key, (_facade, _action, cli_flag) in NEW_ACTION_PARITY.items()
        if cli_flag not in main_cli_options
    ]
    assert missing_cli_for_new_actions == [], (
        "These new-action parity entries have NO CLI flag — every "
        "(facade, action) must keep a documented CLI access path: "
        + repr(missing_cli_for_new_actions)
    )

    # 4. The CLI flags themselves still resolve (main flag or console script).
    missing_main_flags = [
        cli_name
        for _tool_name, (kind, cli_name) in tool_to_cli.items()
        if kind == "main" and cli_name not in main_cli_options
    ]
    missing_scripts = [
        cli_name
        for _tool_name, (kind, cli_name) in tool_to_cli.items()
        if kind == "script" and cli_name not in scripts
    ]

    assert missing_main_flags == []
    assert missing_scripts == []


# ---------------------------------------------------------------------------
# Wave C2 facade-cutover contracts (PRD §5): discovery + delegation
# ---------------------------------------------------------------------------

# MCP server name used to compose the client-visible ``<server>__<tool>`` name.
# Cursor caps the composed name at 60 chars; the success metric (PRD §8) is
# ≤38 chars so even the longest facade leaves headroom.
_MCP_SERVER_NAME = "tree-sitter-analyzer"
_MAX_COMPOSED_TOOL_NAME = 38


def test_facade_discovery_exposes_exactly_eight_facades() -> None:
    """Discovery contract: the eager MCP surface is exactly the 8 facades.

    Guards the whole point of the cutover — if a regression re-registers the
    63 discrete tools (or drops a facade), the eager tool-definition token cost
    explodes again and Cursor/Roo break. Also enforces the ≤38-char composed
    name budget so ``tree-sitter-analyzer__<facade>`` never trips the Cursor
    60-char limit.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry
    from tree_sitter_analyzer.mcp.facade_map import FACADE_NAMES

    tools, lookup = create_tool_registry(str(PROJECT_ROOT))
    names = [name for name, _tool in tools]

    assert len(names) == 8, f"Expected exactly 8 facades, got {len(names)}: {names}"
    assert set(names) == set(FACADE_NAMES)
    assert len(lookup) == 8

    for name in names:
        composed = f"{_MCP_SERVER_NAME}__{name}"
        assert len(composed) <= _MAX_COMPOSED_TOOL_NAME, (
            f"Composed MCP tool name {composed!r} is {len(composed)} chars — "
            f"exceeds the {_MAX_COMPOSED_TOOL_NAME}-char budget (Cursor 60-char "
            "limit headroom)."
        )

    # Each facade's definition advertises its action enum so an LLM can route.
    for _name, facade in tools:
        defn = facade.get_tool_definition()
        action_schema = defn["inputSchema"]["properties"]["action"]
        assert action_schema.get("enum"), f"{_name} facade exposes no action enum"


def test_all_facade_descriptions_contain_codegraph_keyword() -> None:
    """Fix ② discoverability contract: every facade description must contain
    the keyword 'codegraph' so headless agents searching 'codegraph' via
    ToolSearch land on a TSA facade instead of falling back to 2-3 wasted turns.

    This keyword is intentional and LOCKED (CLAUDE.md §1) — do NOT remove it
    from facade descriptions or revert this test.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    _tools, lookup = create_tool_registry(str(PROJECT_ROOT))
    missing: list[str] = []
    for facade_name, facade in lookup.items():
        defn = facade.get_tool_definition()
        description = defn.get("description", "")
        if "codegraph" not in description.lower():
            missing.append(facade_name)

    assert missing == [], (
        "These facades are missing 'codegraph' in their description — agents "
        "searching for codegraph tools will not find them (fix ② regression): "
        + repr(missing)
    )


def test_facade_delegation_routes_each_action_to_expected_inner() -> None:
    """Delegation contract (PRD §5/§7): every (facade, action) reaches the
    expected inner tool instance.

    This is the verdict-envelope guard: the 9 unique-feature outputs
    (project-health A-F, smart_context, agent_summary, TOON, verdict ladder,
    ...) survive ONLY because facades delegate to the unchanged inner tools.
    If a facade ever re-implements an action inline (instead of delegating),
    or wires the wrong inner, this test fails before the envelope can drift.

    For ``action_map`` routes we assert the inner class name; for the bespoke
    routes (search.content, structure.read, nav.callers/callees — F5/R4) we
    assert the route is registered as a bespoke callable instead.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    _tools, lookup = create_tool_registry(str(PROJECT_ROOT))

    # (facade, action) -> expected inner class name. Bespoke routes use the
    # sentinel ``"<bespoke>"`` because they delegate via a closure, not an
    # action_map entry. This table is the human-readable mirror of
    # facade_map.LEGACY_TOOL_MAP keyed by route.
    expected_inner: dict[tuple[str, str], str] = {
        ("search", "symbol"): "CodeGraphSymbolSearchTool",
        ("search", "query"): "QueryTool",
        ("search", "grep"): "FindAndGrepTool",
        ("search", "batch"): "BatchSearchTool",
        ("search", "chain"): "CodeGraphQueryTool",
        ("search", "select"): "HyphaeSelectTool",
        ("search", "subscribe"): "HyphaeSubscribeTool",
        ("search", "unsubscribe"): "HyphaeUnsubscribeTool",
        ("search", "content"): "<bespoke>",
        ("nav", "navigate"): "CodeGraphNavigateTool",
        ("nav", "call_path"): "CodeGraphCallPathTool",
        ("nav", "xref"): "CodeGraphXRefTool",
        ("nav", "resolve"): "CodeGraphSymbolResolveTool",
        ("nav", "lineage"): "SymbolLineageTool",
        ("nav", "impact"): "CodeGraphImpactTool",
        ("nav", "trace"): "TraceImpactTool",
        ("nav", "context"): "<bespoke>",
        ("nav", "callers"): "<bespoke>",
        ("nav", "callees"): "<bespoke>",
        ("nav", "callee_tree"): "CodeGraphCalleeTreeTool",
        ("nav", "caller_tree"): "CodeGraphCallerTreeTool",
        # RFC-0014 Phase B: test_map is a bespoke route (closure over impact_inner).
        ("nav", "test_map"): "<bespoke>",
        # RFC-0014 Phase C: co_change is a bespoke route (async wrapper for _compute_co_change).
        ("nav", "co_change"): "<bespoke>",
        ("structure", "outline"): "GetCodeOutlineTool",
        ("structure", "analyze"): "AnalyzeCodeStructureTool",
        ("structure", "signatures"): "<bespoke>",
        ("structure", "ast_path"): "CodeGraphASTPathTool",
        ("structure", "sitemap"): "CodeGraphSitemapTool",
        ("structure", "class_tree"): "ClassHierarchyTool",
        # class_detail is a bespoke route (#804) so query/symbol→class_name aliasing works.
        ("structure", "class_detail"): "<bespoke>",
        ("structure", "explore"): "CodeGraphExploreTool",
        ("structure", "read"): "<bespoke>",
        ("health", "project"): "ProjectHealthTool",
        ("health", "file"): "FileHealthTool",
        ("health", "scale"): "AnalyzeScaleTool",
        ("health", "patterns"): "CodePatternsTool",
        ("health", "heatmap"): "CodeGraphComplexityHeatmapTool",
        ("health", "imports"): "CodeGraphImportGraphTool",
        ("health", "matrix"): "CodeGraphDependencyMatrixTool",
        ("health", "dead"): "CodeGraphDeadCodeTool",
        ("health", "routes"): "RouteDetectorTool",
        ("health", "overview"): "CodeGraphOverviewTool",
        ("health", "deps"): "DependencyAnalysisTool",
        ("health", "test_gap"): "CodeGraphTestGapTool",
        ("edit", "safe"): "SafeToEditTool",
        ("edit", "guard"): "ModificationGuardTool",
        ("edit", "impact"): "ChangeImpactTool",
        ("edit", "refactor"): "RefactoringSuggestionsTool",
        ("edit", "constraints"): "ConstraintCheckTool",
        # _PRReviewViaFacade subclasses CodeGraphPRReviewTool so facade
        # action=pr implies mode=pr (#451 Codex P1); delegation to the
        # unchanged inner execute() is preserved via super().
        ("edit", "pr"): "_PRReviewViaFacade",
        ("edit", "classify"): "SemanticClassifyTool",
        ("edit", "ast_diff"): "ASTDiffTool",
        ("project", "overview"): "ProjectOverviewTool",
        ("project", "files"): "ListFilesTool",
        ("project", "smart"): "SmartContextTool",
        ("project", "parser"): "ParserReadinessTool",
        ("project", "tools"): "CheckToolsTool",
        ("project", "metrics"): "CodeGraphMetricsTool",
        ("project", "skills"): "AgentSkillsTool",
        ("project", "workflow"): "AgentWorkflowTool",
        ("project", "journal"): "DecisionJournalTool",
        ("project", "doc_sync"): "DocSyncTool",
        ("index", "status"): "CodeGraphStatusTool",
        ("index", "cache"): "ASTCacheTool",
        ("index", "build"): "BuildProjectIndexTool",
        ("index", "full"): "CodeGraphFullIndexTool",
        ("index", "auto"): "CodeGraphAutoIndexTool",
        ("index", "sync"): "CodeGraphIncrementalSyncTool",
        ("viz", "uml"): "CodeGraphUMLTool",
        ("viz", "graph"): "CodeGraphVisualizeTool",
        ("viz", "similarity"): "CodeGraphSimilarityTool",
    }

    mismatches: list[str] = []
    for (facade_name, action), want in expected_inner.items():
        facade = lookup[facade_name]
        if want == "<bespoke>":
            if action not in facade.bespoke_map:
                mismatches.append(
                    f"{facade_name}.{action}: expected bespoke route, "
                    f"not registered in bespoke_map"
                )
            continue
        inner = facade.action_map.get(action)
        if inner is None:
            mismatches.append(
                f"{facade_name}.{action}: no action_map entry (expected {want})"
            )
            continue
        got = type(inner).__name__
        if got != want:
            mismatches.append(f"{facade_name}.{action}: routes to {got}, want {want}")

    assert mismatches == [], "Facade delegation drift:\n  " + "\n  ".join(mismatches)

    # Completeness: every action declared by a facade must be covered above —
    # otherwise a newly-added action could silently skip the delegation guard.
    declared: set[tuple[str, str]] = set()
    for facade_name, facade in lookup.items():
        for action in facade.action_map:
            declared.add((facade_name, action))
        for action in facade.bespoke_map:
            declared.add((facade_name, action))
    uncovered = sorted(declared - set(expected_inner))
    assert uncovered == [], (
        "These facade actions are not covered by the delegation table — add "
        f"them so the verdict-envelope guard stays complete: {uncovered}"
    )


def test_every_tool_declares_mcp_annotations() -> None:
    """Every registered MCP tool MUST set `annotations` in its tool definition.

    MCP spec defines 4 hints (readOnlyHint / destructiveHint / idempotentHint
    / openWorldHint) so clients (Cursor, Cline, Claude Desktop) know whether
    to show confirmation dialogs or treat the call as safe. Without these,
    every read-only `check_*` invocation could pop a "are you sure?" prompt
    — and worse, every destructive call could go through without warning.

    This test enforces:
      1. Every tool has an `annotations` key.
      2. All 4 hints are present and boolean-typed.
      3. The triple `readOnly=true` + `destructive=true` is impossible
         (mutually exclusive — would mean both safe AND destructive).
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _ = create_tool_registry(str(PROJECT_ROOT))
    required_hints = {
        "readOnlyHint",
        "destructiveHint",
        "idempotentHint",
        "openWorldHint",
    }

    missing_annotations: list[str] = []
    missing_hints: list[str] = []
    contradictions: list[str] = []
    non_bool_hints: list[str] = []

    for name, tool in tools:
        defn = tool.get_tool_definition()
        ann = defn.get("annotations")
        if ann is None:
            missing_annotations.append(name)
            continue
        gaps = required_hints - set(ann)
        if gaps:
            missing_hints.append(f"{name}: missing {sorted(gaps)}")
            continue
        non_bool = [k for k in required_hints if not isinstance(ann[k], bool)]
        if non_bool:
            non_bool_hints.append(f"{name}: non-bool {non_bool}")
            continue
        if ann["readOnlyHint"] and ann["destructiveHint"]:
            contradictions.append(name)

    assert missing_annotations == [], (
        "These tools have no `annotations` block in their definition. "
        "Add readOnlyHint/destructiveHint/idempotentHint/openWorldHint "
        f"per MCP spec: {missing_annotations}"
    )
    assert missing_hints == [], (
        f"Tools with incomplete annotation hints: {missing_hints}"
    )
    assert non_bool_hints == [], (
        f"Hints must be Python bools, not strings: {non_bool_hints}"
    )
    assert contradictions == [], (
        "Tools cannot be both readOnly AND destructive — pick one. "
        f"Offenders: {contradictions}"
    )


def test_registered_mcp_tools_have_codemap_parity() -> None:
    """Every registered MCP tool must appear in `docs/CODEMAPS/mcp-tools.md`.

    The codemap is the single source of truth for the agent landing
    experience — if a tool is registered but absent from the codemap,
    agents reading AGENTS.md → the codemap will be blind to it. A
    pre-commit hook (`scripts/codemap-sync-check.sh`) catches this at
    commit time; this test is the CI safety net for `SKIP_CODEMAP_SYNC=1`
    bypasses and non-AI commits.

    Mirrors `test_registered_mcp_tools_have_cli_parity` /
    `_have_skill_parity` — same contract pattern, codemap layer.
    """
    codemap_path = PROJECT_ROOT / "docs" / "CODEMAPS" / "mcp-tools.md"
    assert codemap_path.exists(), (
        f"{codemap_path} is missing — the codemap is the single source "
        "of truth for the agent landing experience."
    )

    # Parse codemap table rows: ``| `tool_name` | ... | ... |``
    codemap_re = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")
    codemap_tools: set[str] = set()
    for line in codemap_path.read_text(encoding="utf-8").splitlines():
        m = codemap_re.match(line)
        if m:
            codemap_tools.add(m.group(1))

    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry
    from tree_sitter_analyzer.mcp.facade_map import (
        FACADE_NAMES,
        LEGACY_TOOL_MAP,
        NEW_ACTION_PARITY,
    )

    registered = {name for name, _tool in create_tool_registry(str(PROJECT_ROOT))[0]}

    # Wave C2 re-key: the codemap documents BOTH the 8 live facades (the new
    # public surface) AND the 62 legacy capability names (so agents reading
    # the codemap can still find "what happened to codegraph_callers?"). Every
    # codemap row must therefore be either a live facade or a known legacy
    # capability name — and all 8 facades must be present.
    missing_facades_in_codemap = sorted(registered - codemap_tools)
    assert missing_facades_in_codemap == [], (
        "These registered MCP facades have NO row in "
        "docs/CODEMAPS/mcp-tools.md. Add each to the table and re-stage in "
        f"the same commit: {missing_facades_in_codemap}"
    )

    allowed_codemap_names = (
        set(FACADE_NAMES) | set(LEGACY_TOOL_MAP) | set(NEW_ACTION_PARITY)
    )
    stale_in_codemap = sorted(codemap_tools - allowed_codemap_names)
    assert stale_in_codemap == [], (
        "These codemap rows reference names that are neither a live facade "
        "nor a known legacy capability (likely typo or removed tool): "
        f"{stale_in_codemap}"
    )


def test_registered_mcp_tools_have_skill_parity() -> None:
    """Every registered MCP tool must appear in at least one tsa-* skill's
    ``allowed-tools`` list.

    Skills sit on top of the MCP registry as progressive-disclosure
    bundles: each skill loads only its own tool definitions on invocation,
    cutting per-turn token cost vs. exposing all tools every turn. If a
    new MCP tool ships without being added to any skill, agents lose the
    discovery + routing path for it. This test enforces the contract.

    Mirrors ``test_registered_mcp_tools_have_cli_parity`` — same idea but
    for the skill layer instead of the CLI layer.

    Wave D (G1): skill allowlists rewritten to the 8 facade names; xfail removed.
    """
    skills_dir = PROJECT_ROOT / ".claude" / "skills"
    if not skills_dir.exists():
        # Skills are an optional layer. If the project hasn't shipped any
        # skills yet, the contract degrades to "no requirement".
        return

    tool_re = re.compile(r"^\s*-\s*mcp__tree-sitter-analyzer__([a-z_]+)\s*$")
    covered: set[str] = set()
    skill_files = sorted(skills_dir.glob("tsa-*/SKILL.md"))
    for skill_path in skill_files:
        in_allowed = False
        for line in skill_path.read_text(encoding="utf-8").splitlines():
            stripped = line.rstrip()
            if stripped.startswith("allowed-tools:"):
                in_allowed = True
                continue
            if in_allowed:
                # YAML frontmatter ends at the closing `---` or when a new
                # top-level key starts (no leading space).
                if stripped == "---":
                    break
                if stripped and not stripped.startswith((" ", "\t", "-")):
                    in_allowed = False
                    continue
                match = tool_re.match(line)
                if match:
                    covered.add(match.group(1))

    # Use the central registry (``_tool_registry.create_tool_registry``)
    # as source of truth, not ``server._create_tool_registry`` which is
    # known to be stale (see Pain pass 2 / pain #26 comments in the
    # central registry). The skill layer must align with the *canonical*
    # tool list, not the historical drift in ``server.py``.
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    registered = {name for name, _tool in create_tool_registry(str(PROJECT_ROOT))[0]}

    missing_skill_coverage = sorted(registered - covered)
    typo_in_skill = sorted(covered - registered)

    assert missing_skill_coverage == [], (
        "These registered MCP tools have NO skill listing them in "
        "allowed-tools. Add each to the most appropriate tsa-* skill "
        f"under .claude/skills/: {missing_skill_coverage}"
    )
    assert typo_in_skill == [], (
        "These tools appear in a skill's allowed-tools but are NOT "
        "registered in the MCP server (likely typo or stale entry): "
        f"{typo_in_skill}"
    )
    # Guard against the skill layer being silently empty if someone moves
    # the directory: insist on at least the canonical landing skill.
    assert (skills_dir / "tsa-landing" / "SKILL.md").exists(), (
        "tsa-landing skill is missing — the cold-start landing skill is "
        "the entry point every other skill builds on."
    )
    assert len(skill_files) >= 8, (
        f"Expected at least 8 tsa-* skills, found {len(skill_files)}. The "
        "10-skill design exists so each skill stays under 12 tools — "
        "collapsing to fewer skills defeats the progressive-disclosure "
        "token savings."
    )


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
        rel = str(path.relative_to(PROJECT_ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
                base_names = [
                    b.id if isinstance(b, ast.Name) else getattr(b, "attr", "?")
                    for b in node.bases
                ]
                if "ElementExtractor" in base_names:
                    msg = f"{rel}:{node.lineno} {node.name} inherits ElementExtractor (should only inherit LanguagePlugin)"
                    violations.append(msg)
    assert violations == [], "\n".join(violations)


def test_extract_elements_returns_dict() -> None:
    """extract_elements on any class must return dict[str, list[Any]], not list."""
    violations = []
    for _lang, path in _discover_plugin_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = str(path.relative_to(PROJECT_ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "extract_elements":
                ret = node.returns
                if ret is None:
                    continue
                ret_str = ast.unparse(ret)
                if ret_str.startswith("list") and "dict" not in ret_str:
                    msg = f"{rel}:{node.lineno} extract_elements returns {ret_str} (must be dict[str, list[...]])"
                    violations.append(msg)
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
        rel = str(path.relative_to(PROJECT_ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Plugin" in node.name:
                methods = {
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                missing = REQUIRED - methods
                if missing:
                    msg = f"{rel}:{node.lineno} {node.name} missing methods: {missing}"
                    violations.append(msg)
    assert violations == [], "\n".join(violations)


def test_no_new_single_file_plugins_in_languages_root() -> None:
    """Prevent adding new single-file plugins. New languages must use package structure.

    Existing single-file plugins are grandfathered; this test only blocks NEW ones.
    """
    GRANDFATHERED = {
        "bash_plugin.py",
        "c_plugin.py",
        "cpp_plugin.py",
        "csharp_plugin.py",
        "css_plugin.py",
        "go_plugin.py",
        "html_plugin.py",
        "java_plugin.py",
        "json_plugin.py",
        "kotlin_plugin.py",
        "php_plugin.py",
        "ruby_plugin.py",
        "rust_plugin.py",
        "scala_plugin.py",
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


def test_no_mcp_tool_imports_from_cli() -> None:
    """ARCH-A1 regression: ``mcp/tools/*.py`` must not import from
    ``tree_sitter_analyzer.cli.*``. The dependency arrow goes one way:
    ``cli/`` may use ``mcp/`` tools, but ``mcp/tools/`` reaches shared
    builders via ``tree_sitter_analyzer.services`` instead.

    The shared builders live (physically) in ``cli/`` for now and are
    re-exported from ``services/``; a future sprint can do the file
    move under that boundary without changing any consumer.
    """
    tools_dir = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"
    offenders: list[str] = []
    for path in sorted(tools_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Catch both absolute and relative styles:
                #   from tree_sitter_analyzer.cli.X import …
                #   from ...cli.X import …
                if (
                    node.module.startswith("tree_sitter_analyzer.cli.")
                    or node.module.startswith("cli.")
                    or (node.level >= 1 and node.module.startswith("cli."))
                ):
                    offenders.append(f"{path.name}:{node.lineno}: from {node.module}")
                # Relative imports like ``from ...cli.X import Y`` have
                # module='cli.X' and level=3 — the .startswith check above
                # already catches them, but be explicit for readability.
    assert offenders == [], (
        "mcp/tools/* must not import from cli/* (ARCH-A1). Reach via "
        "tree_sitter_analyzer.services instead:\n  " + "\n  ".join(offenders)
    )


def _class_overrides_set_project_path(node: ast.ClassDef) -> bool:
    """Return True if the class body contains a ``set_project_path`` method."""
    return any(
        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "set_project_path"
        for item in node.body
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
        pname = path.name
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if _class_overrides_set_project_path(node):
                offenders.append(f"{pname}::{node.name}.set_project_path")
    assert offenders == [], (
        "These tools override BaseMCPTool.set_project_path. Move the body "
        "into _on_project_root_changed instead (ARCH-A4):\n  " + "\n  ".join(offenders)
    )


def test_mcp_command_specs_have_resolvable_tool_classes() -> None:
    """ARCH-A2 regression: every MCP_COMMAND_SPECS entry's ``tool_attr``
    must be resolvable via ``_get_tool_class`` (i.e. present in
    ``_TOOL_CLASS_NAMES``). Adding a spec without updating the lookup
    set used to fail at runtime with ``Unknown MCP tool: …``; this test
    catches the drift at collection time."""
    from tree_sitter_analyzer.cli.commands.mcp_commands import (
        _TOOL_CLASS_NAMES,
        MCP_COMMAND_SPECS,
    )

    referenced = {spec.tool_attr for spec in MCP_COMMAND_SPECS}
    available = set(_TOOL_CLASS_NAMES)
    missing = referenced - available
    assert not missing, (
        f"MCP_COMMAND_SPECS references tool classes not registered in "
        f"_TOOL_CLASS_NAMES: {sorted(missing)}. Either add the class name "
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


# ---------------------------------------------------------------------------
# v1.13 postmortem defenses — see docs/POSTMORTEM_v1.13.md
# ---------------------------------------------------------------------------


def test_postmortem_v1_13_doc_exists() -> None:
    """The v1.13 postmortem is the source of truth for the anti-patterns
    catalogued in AGENTS.md. If the doc gets deleted, the anti-pattern
    rules lose their explanation and become cargo-cult.
    """
    doc = PROJECT_ROOT / "docs" / "POSTMORTEM_v1.13.md"
    assert doc.exists(), (
        "docs/POSTMORTEM_v1.13.md must exist — it documents the failure "
        "modes the AGENTS.md Anti-Patterns section is defending against."
    )
    text = doc.read_text(encoding="utf-8")
    # Each numbered section is a defended failure mode. If any of these
    # headings goes away, AGENTS.md will reference a missing anchor.
    for section in (
        "Skip-and-paper-over",
        "GitFlow not enforced",
        "YAML block scalar",
        "Stale `@v1` action ref",
        "Windows PowerShell 5.1",
        "tree-sitter-c-sharp 0.23.1",
        "Python 3.10 compat",
        "Branch divergence",
        "`--maxfail=10`",
        "Squash-merged 95-commit PR",
    ):
        assert section in text, (
            f"docs/POSTMORTEM_v1.13.md must keep its {section!r} section — "
            "it's referenced by AGENTS.md Anti-Patterns."
        )


def test_agents_md_documents_v1_13_anti_patterns() -> None:
    """AGENTS.md must surface the v1.13 anti-patterns so they hit any
    agent reading it. Without this, the postmortem becomes a one-time
    read instead of a standing rule.
    """
    agents_md = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    # Section header
    assert "Anti-Patterns (from v1.13 postmortem)" in agents_md, (
        "AGENTS.md must contain an 'Anti-Patterns (from v1.13 postmortem)' "
        "section. See docs/POSTMORTEM_v1.13.md for the catalogue."
    )
    # Pointer to the doc itself
    assert "POSTMORTEM_v1.13.md" in agents_md, (
        "The Anti-Patterns section must link back to docs/POSTMORTEM_v1.13.md."
    )


def test_check_ps_ascii_script_is_present_and_pre_commit_wired() -> None:
    """The non-ASCII PowerShell guard must remain wired into pre-commit.
    Without the hook, the rule is just a script nobody runs.
    """
    script = PROJECT_ROOT / "scripts" / "check_ps_ascii.py"
    config = PROJECT_ROOT / ".pre-commit-config.yaml"
    assert script.exists(), (
        "scripts/check_ps_ascii.py must exist — it guards against the "
        "Windows PowerShell 5.1 cp1252 mojibake incident "
        "(docs/POSTMORTEM_v1.13.md sec 5)."
    )
    config_text = config.read_text(encoding="utf-8")
    assert "check_ps_ascii.py" in config_text, (
        ".pre-commit-config.yaml must wire scripts/check_ps_ascii.py "
        "into a `repo: local` hook so emoji can't sneak into Windows "
        "PowerShell blocks at commit time."
    )


def test_actionlint_is_wired_into_pre_commit() -> None:
    """actionlint catches the failure class behind PR #138 — dead
    `uses:` refs and bad GitHub Actions expression syntax. Without it,
    YAML-valid-but-Actions-invalid workflows produce phantom
    `startup_failure` runs that are nearly impossible to diagnose from
    the GH Actions UI.
    """
    config = (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "rhysd/actionlint" in config, (
        ".pre-commit-config.yaml must include the rhysd/actionlint hook — "
        "see docs/POSTMORTEM_v1.13.md sec 4."
    )


def test_no_powershell_blocks_contain_non_ascii() -> None:
    """End-to-end check at test time, complementing the pre-commit hook.
    The hook catches diffs at commit; this test catches drift in code
    that escaped via --no-verify, squash-merge, or hook-bypassed
    automation.
    """
    import importlib.util

    script = PROJECT_ROOT / "scripts" / "check_ps_ascii.py"
    spec = importlib.util.spec_from_file_location("check_ps_ascii", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The script's main() scans relative to cwd; chdir into the repo root.
    import os

    # Stash cwd OUTSIDE the chdir so we always have something to restore,
    # then put the chdir inside the try so any failure between chdir and
    # restore-cwd still runs the finally. Without this, an exception
    # raised by exec_module / glob / scan_file would leak the changed
    # cwd to the xdist worker and corrupt every subsequent test.
    cwd = os.getcwd()
    offenders: list[str] = []
    try:
        os.chdir(PROJECT_ROOT)
        spec.loader.exec_module(module)
        import glob

        yaml_paths = sorted(
            set(
                glob.glob(".github/workflows/*.yml")
                + glob.glob(".github/workflows/*.yaml")
                + glob.glob(".github/actions/**/action.yml", recursive=True)
                + glob.glob(".github/actions/**/action.yaml", recursive=True)
            )
        )
        for path in yaml_paths:
            hits = module.scan_file(path)
            for line_no, col, ln in hits:
                offenders.append(f"{path}:{line_no}:{col}: {ln.rstrip()}")
    finally:
        os.chdir(cwd)
    assert offenders == [], (
        "Found non-ASCII bytes inside `shell: powershell` run blocks. "
        "Windows PowerShell 5.1 will trip TerminatorExpectedAtEndOfString. "
        "See docs/POSTMORTEM_v1.13.md sec 5. Offenders:\n  " + "\n  ".join(offenders)
    )


def test_skips_have_tracking_references() -> None:
    """Every ``pytest.skip``/``pytest.mark.skipif`` MUST carry a tracking
    reference in its reason text — issue number, postmortem section,
    or 'tracked: ...' tag.

    Why: r34/r36 dogfood rounds revealed multiple ``skip`` calls used
    as paper-over for real product bugs. Without a tracking reference,
    the skip becomes invisible institutional debt. With one, the next
    agent can grep for it and reopen the conversation.

    Acceptable patterns in the ``reason=...`` text:
      * ``"#123"`` or ``"GH-123"`` or ``"issue 123"`` — issue tracker
      * ``"POSTMORTEM"`` — links back to a documented incident
      * ``"tracked: <something>"`` — explicit follow-up marker
      * ``"flaky"`` plus a ``# tracked`` neighbouring comment

    Pre-existing skips are grandfathered via the
    ``GRANDFATHERED_SKIPS`` allowlist. To remove an entry, fix the
    underlying bug and delete the skip — do not extend the allowlist
    without filing a tracking issue.
    """
    skip_call_re = re.compile(
        r"(?:pytest\.skip|pytest\.mark\.skipif|pytest\.mark\.skip)\b"
    )
    has_tracker = re.compile(
        r"#\d+|GH-\d+|issue\s+\d+|POSTMORTEM|tracked\s*:|TODO\b|FIXME\b|XXX\b",
        re.IGNORECASE,
    )
    tests_root = PROJECT_ROOT / "tests"
    untracked: list[str] = []

    for path in sorted(tests_root.rglob("*.py")):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if not skip_call_re.search(text):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not skip_call_re.search(line):
                continue
            # Stitch up to 8 surrounding lines so multi-line decorators
            # and split reason= strings get inspected as a unit.
            start = max(0, lineno - 4)
            end = min(len(text.splitlines()), lineno + 4)
            window = "\n".join(text.splitlines()[start:end])
            if has_tracker.search(window):
                continue
            untracked.append(f"{rel}:{lineno}: {line.strip()}")

    if untracked:
        # Ratchet pattern: ``BUDGET`` is the count at the time this
        # contract landed. The test FAILS the moment a new untracked
        # skip pushes the count above the budget. To add a new skip
        # you MUST either:
        #   (a) give the new skip a tracking reference (issue #,
        #       POSTMORTEM, or 'tracked:' tag), or
        #   (b) fix an existing untracked skip first and drop BUDGET
        #       by 1 in the same commit.
        # This lets the rule start applying immediately without a
        # big-bang cleanup PR, and forces the count to monotonically
        # shrink.
        BUDGET = 291
        msg = (
            f"{len(untracked)} pytest skip/skipif call(s) lack a tracking "
            f"reference (issue #, POSTMORTEM, or 'tracked:' tag).\n"
            f"Budget: {BUDGET}. See docs/POSTMORTEM_v1.13.md sec 1.\n"
            f"Offenders (first 20):\n  " + "\n  ".join(untracked[:20])
        )
        # Print so a green run still surfaces the count.
        print(msg)
        assert len(untracked) <= BUDGET, msg


def test_python_version_floor_is_consistent() -> None:
    """The repo's Python floor must be expressed coherently across
    pyproject.toml, ruff target-version, and mypy python_version.

    Why: the v1.13 release shipped ``from datetime import UTC`` and
    ``import tomllib`` against a ``>=3.10`` floor. Both are 3.11+
    stdlib. Local dev was on 3.14 so the bug only surfaced in CI.

    Defense: assert all three knobs agree on the floor.
    """
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    requires_python = pyproject["project"]["requires-python"]
    # Expect ">=3.10" or similar
    floor_match = re.search(r">=\s*(3\.\d+)", requires_python)
    assert floor_match, (
        f"Expected requires-python to declare a >=3.x floor; got {requires_python!r}"
    )
    floor = floor_match.group(1)
    floor_short = "py" + floor.replace(".", "")  # "py310"

    # ruff target-version
    ruff_target = pyproject.get("tool", {}).get("ruff", {}).get("target-version", "")
    if ruff_target:
        assert ruff_target == floor_short, (
            f"[tool.ruff].target-version is {ruff_target!r} but "
            f"[project].requires-python implies {floor_short!r}. "
            "See docs/POSTMORTEM_v1.13.md sec 7."
        )

    # mypy python_version
    mypy_pyver = pyproject.get("tool", {}).get("mypy", {}).get("python_version", "")
    if mypy_pyver:
        assert mypy_pyver == floor, (
            f"[tool.mypy].python_version is {mypy_pyver!r} but "
            f"[project].requires-python implies {floor!r}. "
            "See docs/POSTMORTEM_v1.13.md sec 7."
        )


def test_readme_counts_match_registry() -> None:
    """README headline numbers must match the actual registry counts.

    The v1.13.1 audit found ``README.md`` claiming "50 MCP tools" while
    the registry actually exposed 58, and "248 CLI flags" while the
    parser exposed 237. The ``tsa-codemap-sync`` hook guards
    ``docs/CODEMAPS/*.md`` but not prose docs, so drift accumulated
    silently across three locales (en/ja/zh).

    This contract closes that gap. For each headline number in any
    ``README*.md``, assert it matches the live count derived from
    source. If you change the registry, run the suite — the test will
    tell you which README lines need a refresh, and which number.
    """
    from tree_sitter_analyzer.cli_main import create_argument_parser

    # ---- Authoritative counts ---------------------------------------
    tool_count = len(_create_tool_registry(str(PROJECT_ROOT))[0])

    parser = create_argument_parser()
    long_flags = {
        s for a in parser._actions for s in a.option_strings if s.startswith("--")
    }
    flag_count = len(long_flags)

    # ---- README claims to verify ------------------------------------
    # Each entry: (file, regex that captures the integer, expected_value, human label).
    # The regex must contain a single group `(\d+)` over the number.
    claims = [
        # MCP tool counts — appear at top, in skill section, and in
        # "All N tools" sentence. Each locale has 3 mentions.
        (
            "README.md",
            re.compile(r"(\d+) MCP tools"),
            tool_count,
            "MCP tool count (en headline)",
        ),
        (
            "README.md",
            re.compile(r"triage (\d+) tools"),
            tool_count,
            "MCP tool count (en skills paragraph)",
        ),
        (
            "README.md",
            re.compile(r"All (\d+) tools read"),
            tool_count,
            "MCP tool count (en cache section)",
        ),
        (
            "README_ja.md",
            re.compile(r"(\d+) MCP ツール"),
            tool_count,
            "MCP tool count (ja headline)",
        ),
        (
            "README_ja.md",
            re.compile(r"(\d+) 個のツール"),
            tool_count,
            "MCP tool count (ja skills paragraph)",
        ),
        (
            "README_zh.md",
            re.compile(r"(\d+) 个 MCP 工具"),
            tool_count,
            "MCP tool count (zh headline)",
        ),
        (
            "README_zh.md",
            re.compile(r"(\d+) 个工具间"),
            tool_count,
            "MCP tool count (zh skills paragraph)",
        ),
        (
            "README_zh.md",
            re.compile(r"所有 (\d+) 个工具"),
            tool_count,
            "MCP tool count (zh cache section)",
        ),
        # CLI flag counts — section headers
        (
            "README.md",
            re.compile(r"### (\d+) CLI flags"),
            flag_count,
            "CLI flag count (en section)",
        ),
        (
            "README_ja.md",
            re.compile(r"### (\d+) の CLI フラグ"),
            flag_count,
            "CLI flag count (ja section)",
        ),
        (
            "README_zh.md",
            re.compile(r"### (\d+) 个 CLI flag"),
            flag_count,
            "CLI flag count (zh section)",
        ),
    ]

    failures: list[str] = []
    for filename, pattern, expected, label in claims:
        path = PROJECT_ROOT / filename
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        if match is None:
            failures.append(
                f"{filename}: {label} — pattern {pattern.pattern!r} did not match. "
                "Did the README copy change? Update the regex in this test "
                "OR restore the original wording."
            )
            continue
        found = int(match.group(1))
        if found != expected:
            failures.append(
                f"{filename}: {label} — README says {found}, registry says "
                f"{expected}. Either update the README number to {expected}, "
                "or, if this README claim is intentionally rounded, drop the "
                "specific number and update this test."
            )

    assert failures == [], "README ↔ registry drift:\n  " + "\n  ".join(failures)
