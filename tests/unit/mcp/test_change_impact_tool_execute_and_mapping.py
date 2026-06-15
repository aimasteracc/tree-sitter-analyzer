"""Unit tests for change-impact MCP execute integration and test-file mapping."""

import asyncio

from tree_sitter_analyzer.mcp.tools import change_impact_tool as tool_module
from tree_sitter_analyzer.mcp.tools.utils import (
    change_impact_analysis as change_impact_tool,
)
from tree_sitter_analyzer.mcp.tools.utils import (
    change_impact_verification as verification_tool,
)


def test_execute_exposes_verification_fields_for_agents(monkeypatch):
    """The MCP tool output must include the command agents should run next."""
    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        lambda mode, project_root, scope_paths=None: ["README.md"],
    )
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        lambda mode, project_root, scope_paths=None: "README.md | 2 +-",
    )

    def fail_graph(project_root):
        raise RuntimeError("no graph")

    monkeypatch.setattr(change_impact_tool, "DependencyGraph", fail_graph)

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(tool.execute({"output_format": "json"}))

    assert result["pytest_required"] is False
    assert result["pytest_command"] == ""
    assert result["test_required"] is False
    assert result["test_runner"] == "pytest"
    assert result["default_test_command"] == "uv run pytest -q"
    assert result["test_command"] == ""
    assert result["verification_command"] == "git diff --check"
    assert result["verification_reason"] == "docs-only changes; pytest is not required"
    assert result["focused_test_command"] == ""
    assert result["verification_strategy"] == "docs_only"
    assert result["verification_steps"] == ["git diff --check"]
    # H8 / J11: agent_summary carries a ``verdict`` field. Pre-J11 the
    # default was ``CLEAN`` even when ``changed_count > 0`` — that
    # collided with the safety-tool vocabulary (``CLEAN`` means "ship
    # it"). Post-J11 a non-empty diff escalates the verdict to ``REVIEW``
    # so chained agents know the queue still has work to verify.
    # Pol3 (round-21): ``preview_limit`` + ``preview_truncated`` surface
    # whenever ``changed_preview`` is present so chained agents can tell
    # they have the full list.
    # M5 (round-26): change_impact now populates ``summary_line`` on the
    # agent_summary surface too, so the post-hook can mirror it to the
    # top level. Pre-M5 both surfaces returned ``summary_line=None``.
    assert result["agent_summary"] == {
        "risk": "unknown",
        "scope": "workspace",
        "changed_count": 1,
        "affected_count": 0,
        "tests_to_run_count": 0,
        "next_step": "Run git diff --check; pytest is not required for docs-only changes.",
        "verification_command": "git diff --check",
        "verification_strategy": "docs_only",
        "stop_condition": "docs-only change: git diff --check passes and no runtime files are added.",
        "changed_preview": ["README.md"],
        "preview_limit": 5,
        "preview_truncated": False,
        "verdict": "REVIEW",
        "summary_line": "change_impact changed=1 risk=unknown pytest_required=False",
    }


def test_execute_forwards_scope_paths_to_git_readers(monkeypatch):
    """MCP callers should get queue-scoped impact without post-filtering noise."""
    seen: dict[str, list[list[str] | None]] = {"changed_scopes": []}

    def fake_changed_files(mode, project_root, scope_paths=None):
        seen["changed_scopes"].append(scope_paths)
        return ["tree_sitter_analyzer/mcp/tools/change_impact_tool.py"]

    def fake_diff_stat(mode, project_root, scope_paths=None):
        seen["stat_scope"] = scope_paths
        return "tree_sitter_analyzer/mcp/tools/change_impact_tool.py | 1 +"

    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        fake_changed_files,
    )
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        fake_diff_stat,
    )
    monkeypatch.setattr(change_impact_tool, "_load_dependency_graph", lambda _: None)

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute(
            {
                "output_format": "json",
                "scope_paths": ["tree_sitter_analyzer/mcp/tools"],
            }
        )
    )

    assert seen["changed_scopes"] == [["tree_sitter_analyzer/mcp/tools"], []]
    assert seen["stat_scope"] == ["tree_sitter_analyzer/mcp/tools"]
    assert result["scope_paths"] == ["tree_sitter_analyzer/mcp/tools"]
    assert result["scope_filtered"] is True
    assert result["agent_summary"]["scope"] == "scoped"


def test_execute_adds_queue_ledger_for_scoped_dirty_worktree(monkeypatch):
    """Scoped change-impact should report dirty files outside the queue."""

    def fake_changed_files(mode, project_root, scope_paths=None):
        if scope_paths:
            return ["tree_sitter_analyzer/mcp/tools/change_impact_tool.py"]
        return [
            "tree_sitter_analyzer/mcp/tools/change_impact_tool.py",
            "tree_sitter_analyzer/other_user_change.py",
        ]

    monkeypatch.setattr(tool_module, "_get_changed_files", fake_changed_files)
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        lambda mode, project_root, scope_paths=None: (
            "tree_sitter_analyzer/mcp/tools/change_impact_tool.py | 1 +"
        ),
    )
    monkeypatch.setattr(change_impact_tool, "_load_dependency_graph", lambda _: None)

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute(
            {
                "output_format": "json",
                "agent_summary_only": True,
                "scope_paths": ["tree_sitter_analyzer/mcp/tools"],
            }
        )
    )

    assert result["queue_ledger"]["scoped_changed_count"] == 1
    assert result["queue_ledger"]["out_of_scope_changed_count"] == 1
    assert result["queue_ledger"]["out_of_scope_changed_preview"] == [
        "tree_sitter_analyzer/other_user_change.py"
    ]
    assert "out_of_scope_dirty=1" in result["queue_ledger"]["handoff"]
    assert result["agent_summary"]["queue_ledger"] == result["queue_ledger"]
    assert result["agent_summary"]["scope_hint"] == (
        "Scoped queue has 1 changed file(s); "
        "1 out-of-scope dirty file(s) remain untouched."
    )


def test_execute_supports_agent_summary_only(monkeypatch):
    """MCP callers can avoid the large changed/affected/test mapping payload."""
    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        lambda mode, project_root, scope_paths=None: [
            "tree_sitter_analyzer/cli_main.py"
        ],
    )
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        lambda mode, project_root, scope_paths=None: (
            "tree_sitter_analyzer/cli_main.py | 1 +"
        ),
    )
    monkeypatch.setattr(change_impact_tool, "_load_dependency_graph", lambda _: None)

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute({"output_format": "json", "agent_summary_only": True})
    )

    assert result["agent_summary_only"] is True
    assert result["changed_count"] == 1
    assert result["verification_command"] == "uv run pytest -q"
    assert "changed_files" not in result
    assert "affected_files" not in result
    assert "test_mapping" not in result


def test_execute_test_only_diff_skips_expensive_analysis(monkeypatch):
    """Changed test files are exact targets; no graph/cache walk is needed."""
    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        lambda mode, project_root, scope_paths=None: ["tests/unit/test_fast.py"],
    )
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        lambda mode, project_root, scope_paths=None: "tests/unit/test_fast.py | 1 +",
    )

    def fail_expensive_path(*args, **kwargs):
        raise AssertionError("test-only change-impact should not scan the project")

    monkeypatch.setattr(
        change_impact_tool, "_load_dependency_graph", fail_expensive_path
    )
    monkeypatch.setattr(change_impact_tool, "_ensure_ast_cache", fail_expensive_path)
    monkeypatch.setattr(
        change_impact_tool,
        "compute_call_graph_impact",
        fail_expensive_path,
    )

    tool = tool_module.ChangeImpactTool()
    result = asyncio.run(tool.execute({"output_format": "json"}))

    assert result["analysis_fast_path"] == "test_only"
    assert result["risk_level"] == "low"
    assert result["affected_count"] == 0
    assert result["tests_to_run"] == ["tests/unit/test_fast.py"]
    assert result["verification_command"] == (
        "uv run pytest tests/unit/test_fast.py -q"
    )
    assert result["file_impacts"] == [
        {
            "file": "tests/unit/test_fast.py",
            "direct_dependents": [],
            "total_affected": 0,
            "test_only": True,
        }
    ]


def test_change_impact_result_uses_complete_mapped_tests_for_verification(monkeypatch):
    """Display limits must not silently drop tests from the runnable command."""

    class FakeGraph:
        def nodes(self):
            return {
                "tree_sitter_analyzer/feature.py",
                *{f"tests/unit/test_feature_{index:02d}.py" for index in range(32)},
            }

        def dependents_of(self, file_path):
            return []

    class FakeBlastRadius:
        def __init__(self, graph):
            self.graph = graph

        def forward(self, file_path):
            return {file_path}

    monkeypatch.setattr(
        change_impact_tool, "_load_dependency_graph", lambda _: FakeGraph()
    )
    monkeypatch.setattr(change_impact_tool, "BlastRadius", FakeBlastRadius)

    result = change_impact_tool._build_change_impact_result(
        change_impact_tool.ChangeImpactRequest(
            mode="diff",
            changed_files=["tree_sitter_analyzer/feature.py"],
            diff_stat="",
            project_root="/repo",
            include_tests=True,
        )
    )

    assert len(result["tests_to_run"]) == 30
    assert result["tests_to_run_count"] == 32
    assert result["tests_to_run_omitted_count"] == 2
    assert "tests/unit/test_feature_30.py" not in result["tests_to_run"]
    assert "tests/unit/test_feature_30.py" in result["verification_command"]
    assert "tests/unit/test_feature_31.py" in result["verification_command"]
    assert (
        result["verification_reason"] == "targeted tests cover mapped runtime changes"
    )
    assert result["agent_summary"]["verification_strategy"] == "default_for_large_diff"
    assert result["agent_summary"]["tests_to_run_count"] == 32


def test_agent_summary_warns_for_unscoped_large_dirty_worktree():
    """The compact summary should tell agents to scope very noisy diffs."""
    verification = verification_tool._build_verification_plan(
        ["tree_sitter_analyzer/runtime.py"],
        ["tests/unit/test_runtime.py"],
    )
    strategy = change_impact_tool._build_verification_strategy(
        changed_count=30,
        tests_to_run=["tests/unit/test_runtime.py"],
        verification=verification,
    )

    summary = change_impact_tool._build_agent_summary(
        change_impact_tool.AgentSummaryContext(
            risk="high",
            changed_files=[f"file_{index}.py" for index in range(30)],
            scope_paths=[],
            verification=verification,
            strategy=strategy,
            affected_count=42,
            tests_to_run_count=1,
        )
    )

    assert summary["scope_hint"] == (
        "Large dirty worktree detected; pass scope_paths or "
        "--change-impact-scope for the current queue."
    )
    assert summary["focused_test_command"] == (
        "uv run pytest tests/unit/test_runtime.py -q"
    )
    assert summary["changed_preview"] == [
        "file_0.py",
        "file_1.py",
        "file_2.py",
        "file_3.py",
        "file_4.py",
    ]


def test_find_test_files_marks_docs_as_diff_check_only():
    """Docs changes should not appear as pytest auto-discovery work."""
    mapping = change_impact_tool._find_test_files(
        ["docs/guide.md", "README.rst"],
        {"tests/unit/mcp/test_change_impact_tool.py"},
    )

    assert mapping == {
        "docs/guide.md": [verification_tool.DOCS_ONLY_TEST_HINT],
        "README.rst": [verification_tool.DOCS_ONLY_TEST_HINT],
    }


def test_find_test_files_maps_fixture_files_to_related_tests():
    """Fixture edits should run tests that name the fixture domain."""
    mapping = change_impact_tool._find_test_files(
        ["tests/fixtures/project_graph/health_project/pyproject.toml"],
        {
            "tests/unit/mcp/test_file_health_tool.py",
            "tests/unit/test_health_scorer.py",
            "tests/unit/mcp/test_change_impact_tool.py",
        },
    )

    assert mapping["tests/fixtures/project_graph/health_project/pyproject.toml"] == [
        "tests/unit/test_health_scorer.py"
    ]


def test_find_test_files_excludes_conftest_from_runnable_targets():
    """conftest.py can affect tests, but should not appear as a pytest target."""
    mapping = change_impact_tool._find_test_files(
        ["tests/conftest.py"],
        {"tests/conftest.py", "tests/unit/core/test_conftest_query.py"},
    )

    assert mapping["tests/conftest.py"] == ["tests/unit/core/test_conftest_query.py"]


def test_find_test_files_does_not_treat_source_test_prefix_as_test():
    """Source modules named test_*.py are not direct pytest targets."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/mcp/tools/utils/test_discovery.py"],
        {
            "tree_sitter_analyzer/mcp/tools/utils/test_discovery.py",
            "tests/unit/mcp/test_test_discovery.py",
        },
    )

    assert mapping["tree_sitter_analyzer/mcp/tools/utils/test_discovery.py"] == [
        "tests/unit/mcp/test_test_discovery.py"
    ]


def test_find_test_files_maps_python_plugin_internals_to_package_tests():
    """Language plugin internals should map to package-level test files."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/languages/sql_plugin/extractor.py"],
        {
            "tree_sitter_analyzer/languages/sql_plugin/extractor.py",
            "tests/unit/languages/test_sql_plugin_coverage_80.py",
            "tests/unit/languages/test_sql_plugin_enhanced.py",
            "tests/unit/languages/test_python_plugin.py",
        },
    )

    assert mapping["tree_sitter_analyzer/languages/sql_plugin/extractor.py"] == [
        "tests/unit/languages/test_sql_plugin_coverage_80.py",
        "tests/unit/languages/test_sql_plugin_enhanced.py",
    ]


def test_find_test_files_maps_extracted_analysis_modules_to_family_tests():
    """Extracted analysis modules should map to their parent tool tests."""
    mapping = change_impact_tool._find_test_files(
        [
            "tree_sitter_analyzer/mcp/tools/utils/change_impact_analysis.py",
            "tree_sitter_analyzer/mcp/tools/utils/change_impact_git.py",
            "tree_sitter_analyzer/mcp/tools/utils/change_impact_verification.py",
        ],
        {
            "tree_sitter_analyzer/mcp/tools/utils/change_impact_analysis.py",
            "tree_sitter_analyzer/mcp/tools/utils/change_impact_git.py",
            "tree_sitter_analyzer/mcp/tools/utils/change_impact_verification.py",
            "tests/unit/mcp/test_change_impact_tool.py",
            "tests/unit/mcp/test_verification_command.py",
        },
    )

    assert mapping[
        "tree_sitter_analyzer/mcp/tools/utils/change_impact_analysis.py"
    ] == ["tests/unit/mcp/test_change_impact_tool.py"]
    assert mapping["tree_sitter_analyzer/mcp/tools/utils/change_impact_git.py"] == [
        "tests/unit/mcp/test_change_impact_tool.py"
    ]
    assert mapping[
        "tree_sitter_analyzer/mcp/tools/utils/change_impact_verification.py"
    ] == ["tests/unit/mcp/test_change_impact_tool.py"]


def test_find_test_files_maps_refactoring_plan_builder_to_family_tests():
    """The precise-plan builder should not force auto-discovery."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/mcp/tools/_refactoring_plan_builder.py"],
        {
            "tree_sitter_analyzer/mcp/tools/_refactoring_plan_builder.py",
            "tests/unit/mcp/test_refactoring_suggestions_tool.py",
            "tests/unit/mcp/test_change_impact_tool.py",
        },
    )

    assert mapping["tree_sitter_analyzer/mcp/tools/_refactoring_plan_builder.py"] == [
        "tests/unit/mcp/test_refactoring_suggestions_tool.py"
    ]


def test_find_test_files_maps_extracted_search_content_modules_to_family_tests():
    """Search content helper modules should stay on targeted search tests."""
    mapping = change_impact_tool._find_test_files(
        [
            "tree_sitter_analyzer/mcp/tools/search_content_agent_summary.py",
            "tree_sitter_analyzer/mcp/tools/search_content_response_modes.py",
            "tree_sitter_analyzer/mcp/tools/search_content_validation.py",
        ],
        {
            "tests/unit/mcp/test_search_content_tool.py",
            "tests/unit/mcp/test_mcp_search_content_p1.py",
            "tests/unit/mcp/test_mcp_search_content_p2.py",
            "tests/unit/mcp/test_change_impact_tool.py",
        },
    )

    expected = [
        "tests/unit/mcp/test_mcp_search_content_p1.py",
        "tests/unit/mcp/test_mcp_search_content_p2.py",
        "tests/unit/mcp/test_search_content_tool.py",
    ]
    assert (
        mapping["tree_sitter_analyzer/mcp/tools/search_content_agent_summary.py"]
        == expected
    )
    assert (
        mapping["tree_sitter_analyzer/mcp/tools/search_content_response_modes.py"]
        == expected
    )
    assert (
        mapping["tree_sitter_analyzer/mcp/tools/search_content_validation.py"]
        == expected
    )


def test_find_test_files_maps_find_and_grep_execution_to_family_tests():
    """Execution helper modules should stay on targeted find_and_grep tests."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/mcp/tools/find_and_grep_execution.py"],
        {
            "tests/unit/cli/test_find_and_grep_cli_comprehensive.py",
            "tests/unit/core/test_find_and_grep_tool_file_output.py",
            "tests/unit/mcp/test_find_and_grep_tool.py",
            "tests/unit/mcp/test_mcp_find_and_grep_p1.py",
            "tests/unit/mcp/test_mcp_find_and_grep_p2.py",
            "tests/unit/mcp/test_change_impact_tool.py",
        },
    )

    assert mapping["tree_sitter_analyzer/mcp/tools/find_and_grep_execution.py"] == [
        "tests/unit/cli/test_find_and_grep_cli_comprehensive.py",
        "tests/unit/core/test_find_and_grep_tool_file_output.py",
        "tests/unit/mcp/test_find_and_grep_tool.py",
        "tests/unit/mcp/test_mcp_find_and_grep_p1.py",
        "tests/unit/mcp/test_mcp_find_and_grep_p2.py",
    ]


def test_validate_arguments_rejects_invalid_mode():
    """validate_arguments must raise ValueError for unknown modes."""
    tool = tool_module.ChangeImpactTool(project_root="/repo")
    raised = False
    try:
        tool.validate_arguments({"mode": "invalid_mode"})
    except ValueError as exc:
        raised = True
        assert "mode must be diff|staged|branch" in str(exc)
    assert raised, "Expected ValueError for invalid mode"


def test_validate_arguments_accepts_valid_modes():
    """validate_arguments must accept diff, staged, and branch."""
    tool = tool_module.ChangeImpactTool(project_root="/repo")
    for mode in ("diff", "staged", "branch"):
        assert tool.validate_arguments({"mode": mode}) is True


def test_validate_arguments_accepts_missing_mode():
    """validate_arguments must pass when mode key is absent."""
    tool = tool_module.ChangeImpactTool(project_root="/repo")
    assert tool.validate_arguments({}) is True


def test_validate_arguments_rejects_bad_resource_profile():
    """Invalid resource_profile values should fail at the tool boundary."""
    import pytest

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    with pytest.raises(
        ValueError,
        match=r"resource_profile must be default\|local_low_impact",
    ):
        tool.validate_arguments({"resource_profile": "laptop_melter"})


def test_execute_no_changes_returns_no_changes_result(monkeypatch):
    """execute should return no-changes result when nothing is dirty."""
    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        lambda mode, project_root, scope_paths=None: [],
    )

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(tool.execute({"output_format": "json"}))

    assert result["success"] is True
    assert result["summary"] == "No changes detected"
    assert result["scope_filtered"] is False
    assert result["scope_paths"] == []
    assert result["changed_files"] == []
    assert result["agent_summary"]["changed_count"] == 0


def test_execute_no_changes_with_scope_paths(monkeypatch):
    """No-changes result should reflect scope filtering when scope_paths given."""
    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        lambda mode, project_root, scope_paths=None: [],
    )

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute(
            {
                "output_format": "json",
                "scope_paths": ["tree_sitter_analyzer/mcp"],
            }
        )
    )

    assert result["scope_paths"] == ["tree_sitter_analyzer/mcp"]
    assert result["scope_filtered"] is True
    assert result["queue_ledger"]["scoped_changed_count"] == 0
    assert result["queue_ledger"]["out_of_scope_changed_count"] == 0


def test_execute_no_changes_with_agent_summary_only(monkeypatch):
    """No-changes agent-summary-only should omit full details."""
    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        lambda mode, project_root, scope_paths=None: [],
    )

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute({"output_format": "json", "agent_summary_only": True})
    )

    assert result["agent_summary_only"] is True
    assert result["agent_summary"]["risk"] == "none"
    assert result["agent_summary"]["changed_count"] == 0
    assert "changed_files" not in result
    assert "affected_files" not in result


def test_execute_no_changes_with_scope_and_agent_summary(monkeypatch):
    """Combined scope + agent-summary-only on empty diff should work."""
    monkeypatch.setattr(
        tool_module,
        "_get_changed_files",
        lambda mode, project_root, scope_paths=None: [],
    )

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute(
            {
                "output_format": "json",
                "scope_paths": ["tree_sitter_analyzer/cli"],
                "agent_summary_only": True,
            }
        )
    )

    assert result["scope_filtered"] is True
    assert result["agent_summary_only"] is True
    assert result["queue_ledger"]["scoped_changed_count"] == 0
    assert result["queue_ledger"]["out_of_scope_changed_count"] == 0


def test_execute_strict_scope_mode_mutes_out_of_scope(monkeypatch):
    """#8: scope_mode=strict threads through execute and mutes the out-of-scope
    dirty-file list in the queue ledger while keeping an honest count."""

    def fake_changed(mode, project_root, scope_paths=None):
        # Scoped query returns only the in-scope file; the unscoped workspace
        # query returns extra dirty files outside the scope.
        if scope_paths:
            return ["src/a.py"]
        return ["src/a.py", "docs/noise.md", "tmp/scratch.py"]

    monkeypatch.setattr(tool_module, "_get_changed_files", fake_changed)
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        lambda mode, project_root, scope_paths=None: "src/a.py | 2 +-",
    )
    # Keep scope paths "valid" so the test does not depend on on-disk layout.
    monkeypatch.setattr(tool_module, "_scope_paths_invalid", lambda root, paths: [])

    def fail_graph(project_root):
        raise RuntimeError("no graph")

    monkeypatch.setattr(change_impact_tool, "DependencyGraph", fail_graph)

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute(
            {
                "output_format": "json",
                "scope_paths": ["src/"],
                "scope_mode": "strict",
            }
        )
    )

    ledger = result["queue_ledger"]
    assert ledger["scope_mode"] == "strict"
    assert ledger["scoped_changed_count"] == 1
    assert ledger["out_of_scope_changed_count"] == 2
    assert ledger["out_of_scope_changed_preview"] == []
    assert ledger["out_of_scope_muted"] is True
    # The agent_summary mirror must reflect the muted ledger too.
    assert result["agent_summary"]["queue_ledger"]["out_of_scope_muted"] is True


def test_execute_strict_scope_mode_does_not_leak_into_toon(monkeypatch):
    """#8: under TOON output, strict mode must NOT serialize an out-of-scope
    filename anywhere in the response (the mute has to survive serialization)."""

    def fake_changed(mode, project_root, scope_paths=None):
        if scope_paths:
            return ["src/a.py"]
        return ["src/a.py", "docs/secret_noise.md"]

    monkeypatch.setattr(tool_module, "_get_changed_files", fake_changed)
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        lambda mode, project_root, scope_paths=None: "src/a.py | 2 +-",
    )
    monkeypatch.setattr(tool_module, "_scope_paths_invalid", lambda root, paths: [])

    def fail_graph(project_root):
        raise RuntimeError("no graph")

    monkeypatch.setattr(change_impact_tool, "DependencyGraph", fail_graph)

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute(
            {
                "output_format": "toon",
                "scope_paths": ["src/"],
                "scope_mode": "strict",
            }
        )
    )

    # Whatever the TOON envelope shape, the muted filename must appear nowhere.
    import json as _json

    blob = _json.dumps(result)
    assert "secret_noise.md" not in blob
    # RFC-0012 Phase 2: queue_ledger (non-empty dict) is stripped from the TOON
    # top level — its contents are inside toon_content. Check the toon_content:
    assert "out_of_scope_changed_count" in result["toon_content"]


def test_execute_default_scope_mode_lists_out_of_scope(monkeypatch):
    """Default scope_mode=report keeps today's behavior: out-of-scope dirty
    files are listed (not muted) — byte-parity guard for #8."""

    def fake_changed(mode, project_root, scope_paths=None):
        if scope_paths:
            return ["src/a.py"]
        return ["src/a.py", "docs/noise.md"]

    monkeypatch.setattr(tool_module, "_get_changed_files", fake_changed)
    monkeypatch.setattr(
        tool_module,
        "_get_diff_stat",
        lambda mode, project_root, scope_paths=None: "src/a.py | 2 +-",
    )
    monkeypatch.setattr(tool_module, "_scope_paths_invalid", lambda root, paths: [])

    def fail_graph(project_root):
        raise RuntimeError("no graph")

    monkeypatch.setattr(change_impact_tool, "DependencyGraph", fail_graph)

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    result = asyncio.run(
        tool.execute({"output_format": "json", "scope_paths": ["src/"]})
    )

    ledger = result["queue_ledger"]
    assert ledger["scope_mode"] == "report"
    assert ledger["out_of_scope_muted"] is False
    assert ledger["out_of_scope_changed_preview"] == ["docs/noise.md"]


def test_validate_arguments_rejects_bad_scope_mode():
    """#8: invalid scope_mode is rejected with an actionable message."""
    import pytest

    tool = tool_module.ChangeImpactTool(project_root="/repo")
    with pytest.raises(ValueError, match=r"scope_mode must be report\|strict"):
        tool.validate_arguments({"scope_mode": "nonsense"})


# ── Issue #732 — doc-drift hints ──────────────────────────────────────────────


def test_doc_drift_hints_absent_for_unrelated_files():
    """No doc_drift_checks when changed files don't touch CLI or MCP tools."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints({}, ["tree_sitter_analyzer/plugins/python.py"])
    assert "doc_drift_checks" not in result


def test_doc_drift_hints_cli_main_triggers_readme_count_check():
    """Changing cli_main.py must append the README-count test to doc_drift_checks."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints({}, ["tree_sitter_analyzer/cli_main.py"])
    assert "doc_drift_checks" in result
    assert any(
        "test_readme_counts_match_registry" in step
        for step in result["doc_drift_checks"]
    )


def test_doc_drift_hints_tool_registry_triggers_readme_count_check():
    """Changing _tool_registry.py must also append the README-count test."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints({}, ["tree_sitter_analyzer/mcp/_tool_registry.py"])
    assert any(
        "test_readme_counts_match_registry" in step
        for step in result["doc_drift_checks"]
    )


def test_doc_drift_hints_facade_tool_triggers_doc_regen():
    """Changing a facade tool must append the facade-actions.md regen step."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints(
        {}, ["tree_sitter_analyzer/mcp/tools/symbol_search_tool.py"]
    )
    assert "doc_drift_checks" in result
    assert any(
        "generate_facade_actions_doc" in step for step in result["doc_drift_checks"]
    )


def test_doc_drift_hints_util_file_not_treated_as_facade_tool():
    """Files under mcp/tools/utils/ must NOT trigger facade-actions regen."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints(
        {}, ["tree_sitter_analyzer/mcp/tools/utils/change_impact_analysis.py"]
    )
    assert "doc_drift_checks" not in result
