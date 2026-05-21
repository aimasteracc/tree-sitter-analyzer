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
    # H8: agent_summary now carries a ``verdict`` field. Default is
    # ``CLEAN`` (no scope_paths supplied, nothing to flag).
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
        "verdict": "CLEAN",
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
