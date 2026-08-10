"""Unit tests for change-impact MCP execute integration and test-file mapping."""

import asyncio

from tests.unit._diff_snapshot_support import install_fake_snapshot_materializer
from tree_sitter_analyzer.diff_snapshot_capture import ChangedFile
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
        tool.execute(
            {
                "output_format": "json",
                "agent_summary_only": True,
                # Use default profile so this test stays focused on agent_summary_only
                # behaviour, independent of the MCP resource_profile default (#731).
                "resource_profile": "default",
            }
        )
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
    result = asyncio.run(
        tool.execute(
            {
                "output_format": "json",
                # Use default profile to isolate test-only fast-path behaviour from
                # the MCP resource_profile default change (#731).
                "resource_profile": "default",
            }
        )
    )

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


def test_find_test_files_disambiguates_constraint_evaluator_by_subsystem():
    """A generic evaluator stem must not cross into the Hyphae subsystem."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/constraints/evaluator.py"],
        {
            "tests/unit/hyphae/test_evaluator.py",
            "tests/unit/test_constraint_dsl.py",
        },
    )

    # Dogfood 2026-07-22: change-impact previously selected only Hyphae here.
    assert mapping["tree_sitter_analyzer/constraints/evaluator.py"] == [
        "tests/unit/test_constraint_dsl.py"
    ]


def test_find_test_files_does_not_export_repository_specific_family_aliases():
    """Project-local aliases must not invent coverage in external source trees."""
    mapping = change_impact_tool._find_test_files(
        [
            "src/constraints/evaluator.py",
            "src/edge_extractors/python.py",
            "src/test_discovery_stems.py",
        ],
        {
            "tests/test_change_impact_tool_execute_and_mapping.py",
            "tests/test_constraint_dsl.py",
            "tests/test_registry.py",
        },
    )

    assert mapping["src/constraints/evaluator.py"] == [
        change_impact_tool.AUTO_DISCOVER_TEST_HINT
    ]
    assert mapping["src/edge_extractors/python.py"] == [
        change_impact_tool.AUTO_DISCOVER_TEST_HINT
    ]
    assert mapping["src/test_discovery_stems.py"] == [
        change_impact_tool.AUTO_DISCOVER_TEST_HINT
    ]


def test_find_test_files_preserves_dunder_module_identity():
    """A package initializer must not match an unrelated plain init module."""
    mapping = change_impact_tool._find_test_files(
        ["src/api/__init__.py"],
        {"tests/unit/worker/test_init.py"},
    )

    assert mapping["src/api/__init__.py"] == [
        change_impact_tool.AUTO_DISCOVER_TEST_HINT
    ]


def test_find_test_files_keeps_same_stem_with_matching_subsystem():
    """A same-stem test remains valid when its subsystem path also matches."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/hyphae/evaluator.py"],
        {
            "tests/unit/hyphae/test_evaluator.py",
            "tests/unit/test_constraint_dsl.py",
        },
    )

    assert mapping["tree_sitter_analyzer/hyphae/evaluator.py"] == [
        "tests/unit/hyphae/test_evaluator.py"
    ]


def test_find_test_files_keeps_direct_match_when_tests_omit_subsystem_path():
    """A lone direct match remains useful when no affinity match exists."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/core/engine.py"],
        {
            "tests/unit/test_engine.py",
        },
    )

    assert mapping["tree_sitter_analyzer/core/engine.py"] == [
        "tests/unit/test_engine.py"
    ]


def test_find_test_files_preserves_unscoped_exact_module_test():
    """Generic subsystem tests must not replace an exact root-level test."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/languages/lang_extension_map.py"],
        {
            "tests/unit/languages/test_python_plugin.py",
            "tests/unit/languages/test_queries_module_contract.py",
            "tests/unit/test_lang_extension_map.py",
        },
    )

    assert mapping["tree_sitter_analyzer/languages/lang_extension_map.py"] == [
        "tests/unit/test_lang_extension_map.py"
    ]


def test_find_test_files_does_not_expand_subsystem_for_exact_match():
    """A formatter module match must not pull in every formatter test."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/formatters/json_formatter.py"],
        {
            "tests/unit/formatters/test_csv_formatter.py",
            "tests/unit/formatters/test_markdown_formatter.py",
            "tests/unit/test_json_formatter.py",
        },
    )

    assert mapping["tree_sitter_analyzer/formatters/json_formatter.py"] == [
        "tests/unit/test_json_formatter.py"
    ]


def test_find_test_files_preserves_unscoped_direct_stem_variants():
    """Root-level direct variants must remain beside the exact module test."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/ast_cache.py"],
        {
            "tests/unit/test_ast_cache.py",
            "tests/unit/test_ast_cache_build_state.py",
            "tests/unit/test_ast_cache_utf8_bug.py",
            "tests/unit/test_cache_manager.py",
        },
    )

    assert mapping["tree_sitter_analyzer/ast_cache.py"] == [
        "tests/unit/test_ast_cache.py",
        "tests/unit/test_ast_cache_build_state.py",
        "tests/unit/test_ast_cache_utf8_bug.py",
    ]


def test_find_test_files_keeps_normalized_exact_beside_raw_variant():
    """Raw contextual identity must not hide a normalized primary suite."""
    mapping = change_impact_tool._find_test_files(
        ["src/FooBar.py"],
        {
            "tests/test_FooBar_windows.py",
            "tests/test_foo_bar.py",
        },
    )

    assert mapping["src/FooBar.py"] == [
        "tests/test_FooBar_windows.py",
        "tests/test_foo_bar.py",
    ]


def test_find_test_files_uses_path_specific_edge_extractor_family():
    """A Java edge extractor maps only to its existing path-specific suite."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/mcp/utils/edge_extractors/java.py"],
        {
            "tests/unit/formatters/test_formatter_registry.py",
            "tests/unit/mcp/edge_extractors/test_registry.py",
            "tests/unit/mcp/test_project_summary_pagerank.py",
            "tests/unit/test_tool_registry.py",
        },
    )

    assert mapping["tree_sitter_analyzer/mcp/utils/edge_extractors/java.py"] == [
        "tests/unit/mcp/test_project_summary_pagerank.py"
    ]


def test_find_test_files_disambiguates_direct_matches_alongside_family_matches():
    """A family match must not bypass filtering of unrelated direct matches."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/languages/lua_plugin/extractor.py"],
        {
            "tests/unit/languages/test_lua_plugin.py",
            "tests/unit/test_import_extractors.py",
            "tests/unit/test_symbol_extractors.py",
            "tests/unit/mcp/test_element_extractors.py",
        },
    )

    assert mapping["tree_sitter_analyzer/languages/lua_plugin/extractor.py"] == [
        "tests/unit/languages/test_lua_plugin.py"
    ]


def test_find_test_files_supports_java_test_suffix():
    """Java's FooTest convention must remain a direct module match."""
    mapping = change_impact_tool._find_test_files(
        ["src/main/java/example/Foo.java"],
        {
            "tests/FooTest.java",
            "tests/BarTest.java",
        },
    )

    assert mapping["src/main/java/example/Foo.java"] == ["tests/FooTest.java"]


def test_find_test_files_supports_dotted_javascript_and_typescript_tests():
    """Dotted .test/.spec names must survive flat-layout disambiguation."""
    mapping = change_impact_tool._find_test_files(
        ["src/foo/bar.js", "src/foo/baz.ts"],
        {
            "tests/bar.test.js",
            "tests/baz.spec.ts",
            "tests/quux.test.js",
        },
    )

    assert mapping["src/foo/bar.js"] == ["tests/bar.test.js"]
    assert mapping["src/foo/baz.ts"] == ["tests/baz.spec.ts"]


def test_find_test_files_preserves_flat_variants_for_nested_modules():
    """Nested source directories must not hide flat direct-stem variants."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/engine.py"],
        {
            "tests/unit/test_engine.py",
            "tests/unit/test_engine_errors.py",
            "tests/unit/test_other_engines.py",
        },
    )

    assert mapping["src/core/engine.py"] == [
        "tests/unit/test_engine.py",
        "tests/unit/test_engine_errors.py",
    ]


def test_find_test_files_maps_changed_test_to_itself_in_mixed_diff():
    """A changed test remains an exact target when runtime files also change."""
    mapping = change_impact_tool._find_test_files(
        ["src/foo.py", "tests/unit/test_foo.py"],
        {
            "tests/unit/test_foo.py",
            "tests/unit/test_bar.py",
        },
    )

    assert mapping["src/foo.py"] == ["tests/unit/test_foo.py"]
    assert mapping["tests/unit/test_foo.py"] == ["tests/unit/test_foo.py"]


def test_find_test_files_matches_context_prefixed_module_stem():
    """Package context may prefix a module stem at identifier boundaries."""
    mapping = change_impact_tool._find_test_files(
        [
            "tree_sitter_analyzer/cache/build_state.py",
            "tree_sitter_analyzer/mcp/_tool_registry.py",
        ],
        {
            "tests/unit/test_ast_cache_build_state.py",
            "tests/unit/test_tool_registry.py",
            "tests/unit/test_other_build_states.py",
        },
    )

    assert mapping["tree_sitter_analyzer/cache/build_state.py"] == [
        "tests/unit/test_ast_cache_build_state.py"
    ]
    assert mapping["tree_sitter_analyzer/mcp/_tool_registry.py"] == [
        "tests/unit/test_tool_registry.py"
    ]


def test_find_test_files_keeps_direct_tests_when_affinity_is_too_broad():
    """A large CLI fallback must not replace a small direct candidate set."""
    cli_tests = {f"tests/unit/cli/test_cli_case_{index}.py" for index in range(21)}
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/cli/agent_workflow.py"],
        {
            "tests/unit/mcp/test_agent_workflow_tool.py",
            "tests/unit/demos/test_agent_workflow_comparison_demo.py",
            *cli_tests,
        },
    )

    assert mapping["tree_sitter_analyzer/cli/agent_workflow.py"] == [
        "tests/unit/demos/test_agent_workflow_comparison_demo.py",
        "tests/unit/mcp/test_agent_workflow_tool.py",
    ]


def test_find_test_files_preserves_monorepo_package_scope():
    """Nested package test roots must not make sibling tests unscoped."""
    mapping = change_impact_tool._find_test_files(
        [
            "packages/a/core/config.py",
            "packages/a/src/config.py",
            "packages/a/src/core/config.py",
        ],
        {
            "packages/a/tests/test_config.py",
            "packages/b/tests/test_config.py",
        },
    )

    assert mapping["packages/a/core/config.py"] == ["packages/a/tests/test_config.py"]
    assert mapping["packages/a/src/config.py"] == ["packages/a/tests/test_config.py"]
    assert mapping["packages/a/src/core/config.py"] == [
        "packages/a/tests/test_config.py"
    ]


def test_find_test_files_uses_lone_source_parent_as_affinity():
    """Package-relative source paths retain their only available scope."""
    mapping = change_impact_tool._find_test_files(
        ["constraints/evaluator.py"],
        {
            "tests/unit/constraints/test_evaluator.py",
            "tests/unit/hyphae/test_evaluator.py",
        },
    )

    assert mapping["constraints/evaluator.py"] == [
        "tests/unit/constraints/test_evaluator.py"
    ]


def test_find_test_files_treats_smoke_as_unscoped_test_tier():
    """A smoke tier must not let a source-affine but unrelated test win."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/engine.py"],
        {
            "tests/smoke/test_engine.py",
            "tests/unit/core/test_other.py",
        },
    )

    assert mapping["src/core/engine.py"] == ["tests/smoke/test_engine.py"]


def test_find_test_files_treats_system_and_acceptance_as_unscoped_tiers():
    """Conventional system tiers retain exact tests beside scoped coverage."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/engine.py"],
        {
            "tests/acceptance/test_engine.py",
            "tests/system/test_engine.py",
            "tests/unit/core/test_engine.py",
        },
    )

    assert mapping["src/core/engine.py"] == [
        "tests/acceptance/test_engine.py",
        "tests/system/test_engine.py",
        "tests/unit/core/test_engine.py",
    ]


def test_find_test_files_supports_exact_plural_subject():
    """Only an exact unscoped plural subject directly covers its module."""
    mapping = change_impact_tool._find_test_files(
        ["src/extractor.py", "src/engine.py"],
        {
            "tests/test_extractors.py",
            "tests/test_extractors_errors.py",
            "tests/test_engines.py",
            "tests/test_other_extractors.py",
            "tests/test_other_engines.py",
        },
    )

    assert mapping["src/extractor.py"] == ["tests/test_extractors.py"]
    assert mapping["src/engine.py"] == ["tests/test_engines.py"]


def test_find_test_files_preserves_outer_affinity_for_exact_direct():
    """A nearer unrelated path must not replace an exact direct test."""
    mapping = change_impact_tool._find_test_files(
        ["src/api/client/request.py"],
        {
            "tests/unit/api/test_request.py",
            "tests/unit/client/test_unrelated.py",
        },
    )

    assert mapping["src/api/client/request.py"] == ["tests/unit/api/test_request.py"]


def test_find_test_files_keeps_only_nearest_exact_subsystem_match():
    """Same-stem exact tests must resolve to the nearest source subsystem."""
    mapping = change_impact_tool._find_test_files(
        ["src/api/client/config.py"],
        {
            "tests/unit/api/test_config.py",
            "tests/unit/client/test_config.py",
        },
    )

    assert mapping["src/api/client/config.py"] == ["tests/unit/client/test_config.py"]


def test_find_test_files_normalizes_test_prefixed_subsystem_directories():
    """Test-directory aliases retain exact suites beside direct variants."""
    mapping = change_impact_tool._find_test_files(
        [
            "tree_sitter_analyzer/mcp/tools/base_tool.py",
            "tree_sitter_analyzer/mcp/utils/path_resolver.py",
        ],
        {
            "tests/unit/mcp/test_tools/test_base_tool.py",
            "tests/unit/mcp/tools/test_base_tool_output_schema.py",
            "tests/unit/mcp/test_utils/test_path_resolver.py",
            "tests/unit/mcp/utils/test_path_resolver_errors.py",
        },
    )

    assert mapping["tree_sitter_analyzer/mcp/tools/base_tool.py"] == [
        "tests/unit/mcp/test_tools/test_base_tool.py",
        "tests/unit/mcp/tools/test_base_tool_output_schema.py",
    ]
    assert mapping["tree_sitter_analyzer/mcp/utils/path_resolver.py"] == [
        "tests/unit/mcp/test_utils/test_path_resolver.py",
        "tests/unit/mcp/utils/test_path_resolver_errors.py",
    ]


def test_find_test_files_rejects_unscoped_plural_prefix_collisions():
    """Plural-prefixed suites need independent subsystem or family evidence."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/core/query.py"],
        {
            "tests/unit/core/test_queries_cpp.py",
            "tests/unit/core/test_queries_python.py",
        },
    )

    assert mapping["tree_sitter_analyzer/core/query.py"] == [
        change_impact_tool.AUTO_DISCOVER_TEST_HINT
    ]


def test_find_test_files_preserves_direct_variants_across_test_layers():
    """Direct behavioral suites remain selected outside the source subsystem."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py"],
        {
            "tests/integration/core/test_analyze_scale_tool_batch_metrics.py",
            "tests/integration/core/test_analyze_scale_tool_file_output.py",
            "tests/integration/mcp/test_tools/test_analyze_scale_tool.py",
        },
    )

    assert mapping["tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py"] == [
        "tests/integration/core/test_analyze_scale_tool_batch_metrics.py",
        "tests/integration/core/test_analyze_scale_tool_file_output.py",
        "tests/integration/mcp/test_tools/test_analyze_scale_tool.py",
    ]


def test_find_test_files_avoids_discarded_full_suite_affinity_scan(monkeypatch):
    """An ambiguous direct match must rank only relevant candidate sets."""
    candidates_seen: list[list[str]] = []
    rank_candidates = change_impact_tool._most_specific_affinity_matches

    def recording_rank(test_files, changed_file):
        candidates_seen.append(test_files)
        return rank_candidates(test_files, changed_file)

    monkeypatch.setattr(
        change_impact_tool,
        "_most_specific_affinity_matches",
        recording_rank,
    )
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/constraints/evaluator.py"],
        {
            "tests/unit/hyphae/test_evaluator.py",
            "tests/unit/test_constraint_dsl.py",
        },
    )

    assert mapping["tree_sitter_analyzer/constraints/evaluator.py"] == [
        "tests/unit/test_constraint_dsl.py"
    ]
    assert candidates_seen == [
        ["tests/unit/hyphae/test_evaluator.py"],
        ["tests/unit/test_constraint_dsl.py"],
    ]


def test_find_test_files_preserves_direct_variants_at_best_outer_affinity():
    """Nested source modules retain all direct variants at the best outer rank."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/cli/commands/find_and_grep_cli.py"],
        {
            "tests/unit/cli/test_find_and_grep_cli.py",
            "tests/unit/cli/test_find_and_grep_cli_main.py",
            "tests/unit/cli/test_find_and_grep_cli_parser.py",
            "tests/unit/cli/test_find_and_grep_cli_run.py",
        },
    )

    assert mapping["tree_sitter_analyzer/cli/commands/find_and_grep_cli.py"] == [
        "tests/unit/cli/test_find_and_grep_cli.py",
        "tests/unit/cli/test_find_and_grep_cli_main.py",
        "tests/unit/cli/test_find_and_grep_cli_parser.py",
        "tests/unit/cli/test_find_and_grep_cli_run.py",
    ]


def test_find_test_files_never_replaces_direct_test_with_affinity_fallback():
    """A mirrored directory must not make an unrelated helper replace direct."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/engine.py"],
        {
            "tests/unit/core/test_helpers.py",
            "tests/unit/slow/test_engine.py",
        },
    )

    assert mapping["src/core/engine.py"] == ["tests/unit/slow/test_engine.py"]


def test_find_test_files_keeps_exact_direct_over_directory_only_affinity():
    """A directory-only affinity is weaker than an exact direct filename."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/engine.py"],
        {
            "tests/integration/api/test_engine.py",
            "tests/unit/core/test_helpers.py",
        },
    )

    assert mapping["src/core/engine.py"] == ["tests/integration/api/test_engine.py"]


def test_find_test_files_keeps_exact_direct_over_scope_prefixed_filename():
    """A scope-bearing but unrelated filename cannot replace exact direct."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/engine.py"],
        {
            "tests/integration/api/test_engine.py",
            "tests/unit/test_core_helpers.py",
        },
    )

    assert mapping["src/core/engine.py"] == ["tests/integration/api/test_engine.py"]


def test_find_test_files_keeps_monorepo_package_identity_during_affinity():
    """Shared inner subsystem names must not cross package boundaries."""
    mapping = change_impact_tool._find_test_files(
        ["packages/a/src/core/config.py"],
        {
            "packages/a/tests/core/test_config.py",
            "packages/b/tests/core/test_config.py",
        },
    )

    assert mapping["packages/a/src/core/config.py"] == [
        "packages/a/tests/core/test_config.py"
    ]


def test_find_test_files_does_not_restore_sibling_package_direct_match():
    """A sibling-only direct name must fall back instead of appearing focused."""
    mapping = change_impact_tool._find_test_files(
        ["packages/a/src/core/config.py"],
        {"packages/b/tests/core/test_config.py"},
    )

    assert mapping["packages/a/src/core/config.py"] == [
        change_impact_tool.AUTO_DISCOVER_TEST_HINT
    ]
    assert (
        change_impact_tool.test_path_subsystem_affinity_rank(
            "packages/b/tests/core/test_config.py",
            "packages/a/src/core/config.py",
        )
        is None
    )


def test_package_scope_ignores_hidden_workspace_marker():
    """A hidden placeholder after packages does not declare a workspace."""
    assert change_impact_tool.test_paths_have_compatible_package_scope(
        "packages/.hidden/tests/core/test_config.py",
        "packages/a/src/core/config.py",
    )


def test_package_scope_ignores_hidden_scoped_package_name():
    """A hidden name after an npm scope is not package identity."""
    assert change_impact_tool.test_paths_have_compatible_package_scope(
        "packages/@scope/.hidden/tests/core/config.test.ts",
        "packages/@scope/.hidden/src/core/config.ts",
    )


def test_find_test_files_uses_innermost_nested_package_identity():
    """Nested workspaces use their nearest enclosing package container."""
    mapping = change_impact_tool._find_test_files(
        ["packages/a/packages/b/src/core/config.py"],
        {
            "packages/a/packages/b/tests/core/test_config.py",
            "packages/a/packages/c/tests/core/test_config.py",
        },
    )

    assert mapping["packages/a/packages/b/src/core/config.py"] == [
        "packages/a/packages/b/tests/core/test_config.py"
    ]


def test_find_test_files_retains_full_nested_package_lineage():
    """Equal inner names do not erase distinct enclosing workspaces."""
    mapping = change_impact_tool._find_test_files(
        ["packages/frontend/packages/shared/src/core/config.py"],
        {
            "packages/backend/packages/shared/tests/core/test_config.py",
            "packages/frontend/packages/shared/tests/core/test_config.py",
        },
    )

    assert mapping["packages/frontend/packages/shared/src/core/config.py"] == [
        "packages/frontend/packages/shared/tests/core/test_config.py"
    ]


def test_find_test_files_preserves_workspace_container_in_package_identity():
    """Equal workspace names under apps and packages remain distinct."""
    mapping = change_impact_tool._find_test_files(
        ["apps/shared/src/core/config.py"],
        {
            "apps/shared/tests/core/test_config.py",
            "packages/shared/tests/core/test_config.py",
        },
    )

    assert mapping["apps/shared/src/core/config.py"] == [
        "apps/shared/tests/core/test_config.py"
    ]


def test_find_test_files_preserves_scoped_npm_package_identity():
    """The package name after an npm scope participates in compatibility."""
    mapping = change_impact_tool._find_test_files(
        ["packages/@scope/a/src/core/config.ts"],
        {
            "packages/@scope/a/tests/core/config.test.ts",
            "packages/@scope/b/tests/core/config.test.ts",
        },
    )

    assert mapping["packages/@scope/a/src/core/config.ts"] == [
        "packages/@scope/a/tests/core/config.test.ts"
    ]


def test_find_test_files_keeps_central_tests_for_workspace_sources():
    """A test with no package marker remains compatible with a workspace."""
    mapping = change_impact_tool._find_test_files(
        ["packages/a/src/config.py"],
        {"tests/a/test_config.py"},
    )

    assert mapping["packages/a/src/config.py"] == ["tests/a/test_config.py"]


def test_find_test_files_excludes_top_level_package_from_affinity():
    """A package root is not a subsystem for modules directly beneath it."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/api.py"],
        {
            "tree_sitter_analyzer/__init__.py",
            "tests/integration/core/test_api.py",
            "tests/integration/core/test_api_errors.py",
            "tests/unit/test_api.py",
        },
    )

    assert mapping["tree_sitter_analyzer/api.py"] == [
        "tests/integration/core/test_api.py",
        "tests/integration/core/test_api_errors.py",
        "tests/unit/test_api.py",
    ]


def test_find_test_files_rejects_workspace_tests_for_central_sources():
    """A central source must not claim package-specific tests as coverage."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/config.py"],
        {
            "packages/a/tests/core/test_config.py",
            "packages/b/tests/core/test_config.py",
        },
    )

    assert mapping["src/core/config.py"] == [change_impact_tool.AUTO_DISCOVER_TEST_HINT]


def test_find_test_files_ignores_workspace_markers_below_test_root():
    """A nested apps test folder remains central test organization."""
    mapping = change_impact_tool._find_test_files(
        ["src/users/config.py"],
        {"tests/apps/users/test_config.py"},
    )

    assert mapping["src/users/config.py"] == ["tests/apps/users/test_config.py"]


def test_find_test_files_filters_cross_package_family_matches():
    """Derived family coverage must not cross into a sibling package."""
    mapping = change_impact_tool._find_test_files(
        ["packages/a/src/languages/lua_plugin/extractor.py"],
        {"packages/b/tests/test_lua_plugin.py"},
    )

    assert mapping["packages/a/src/languages/lua_plugin/extractor.py"] == [
        change_impact_tool.AUTO_DISCOVER_TEST_HINT
    ]


def test_find_test_files_uses_structural_directory_as_fallback_scope():
    """A lone structural source directory still disambiguates direct tests."""
    mapping = change_impact_tool._find_test_files(
        ["src/mcp/server.py"],
        {
            "tests/unit/http/test_server.py",
            "tests/unit/mcp/test_server.py",
        },
    )

    assert mapping["src/mcp/server.py"] == ["tests/unit/mcp/test_server.py"]


def test_source_subsystem_stems_ignores_generated_directory():
    """A hidden generated directory does not become subsystem evidence."""
    assert change_impact_tool.source_subsystem_stems("src/.generated/server.py") == []


def test_find_test_files_routes_stem_helper_to_behavioral_suite():
    """Stem helper edits select both discovery and change-impact behavior tests."""
    mapping = change_impact_tool._find_test_files(
        ["tree_sitter_analyzer/mcp/tools/utils/test_discovery_stems.py"],
        {
            "tests/unit/mcp/test_change_impact_tool_execute_and_mapping.py",
            "tests/unit/mcp/test_test_discovery.py",
        },
    )

    assert mapping["tree_sitter_analyzer/mcp/tools/utils/test_discovery_stems.py"] == [
        "tests/unit/mcp/test_change_impact_tool_execute_and_mapping.py",
        "tests/unit/mcp/test_test_discovery.py",
    ]


def test_find_test_files_supports_irregular_plural_subject():
    """Common irregular plurals may directly name their singular module."""
    mapping = change_impact_tool._find_test_files(
        ["src/analysis.py", "src/query_analysis.py"],
        {
            "tests/test_analyses.py",
            "tests/test_query_analyses_errors.py",
        },
    )

    assert mapping["src/analysis.py"] == ["tests/test_analyses.py"]
    assert mapping["src/query_analysis.py"] == ["tests/test_query_analyses_errors.py"]


def test_find_test_files_supports_doubled_z_plural():
    """Terminal z stems use their conventional doubled or regular plurals."""
    mapping = change_impact_tool._find_test_files(
        ["src/buzz.py", "src/quiz.py", "src/waltz.py"],
        {
            "tests/test_buzzes.py",
            "tests/test_quizzes.py",
            "tests/test_waltzes.py",
        },
    )

    assert mapping["src/buzz.py"] == ["tests/test_buzzes.py"]
    assert mapping["src/quiz.py"] == ["tests/test_quizzes.py"]
    assert mapping["src/waltz.py"] == ["tests/test_waltzes.py"]


def test_find_test_files_prefers_case_preserving_direct_identity():
    """Normalized collisions resolve to the exact case-sensitive module name."""
    mapping = change_impact_tool._find_test_files(
        ["src/Foo.ts", "src/foo.ts"],
        {
            "tests/Foo.test.ts",
            "tests/foo.test.ts",
        },
    )

    assert mapping["src/Foo.ts"] == ["tests/Foo.test.ts"]
    assert mapping["src/foo.ts"] == ["tests/foo.test.ts"]


def test_find_test_files_supports_regular_irregular_plural_alternatives():
    """Code conventions may use regular variants of irregular English nouns."""
    mapping = change_impact_tool._find_test_files(
        ["src/index.py", "src/matrix.py", "src/person.py"],
        {
            "tests/test_indexes.py",
            "tests/test_matrixes.py",
            "tests/test_persons.py",
        },
    )

    assert mapping["src/index.py"] == ["tests/test_indexes.py"]
    assert mapping["src/matrix.py"] == ["tests/test_matrixes.py"]
    assert mapping["src/person.py"] == ["tests/test_persons.py"]


def test_find_test_files_protects_plural_direct_from_affinity_fallback():
    """A recognized plural direct match cannot be replaced by path affinity."""
    mapping = change_impact_tool._find_test_files(
        ["src/core/config.py"],
        {
            "tests/integration/api/test_configs.py",
            "tests/unit/core/test_helpers.py",
        },
    )

    assert mapping["src/core/config.py"] == ["tests/integration/api/test_configs.py"]


def test_find_test_files_preserves_subsystem_after_outer_source_root():
    """A nested app directory is a scope when src already supplied the root."""
    mapping = change_impact_tool._find_test_files(
        ["src/app/config.py"],
        {
            "tests/unit/app/test_config.py",
            "tests/unit/other/test_config.py",
        },
    )

    assert mapping["src/app/config.py"] == ["tests/unit/app/test_config.py"]


def test_find_test_files_normalizes_camel_case_subsystem_paths():
    """Source and test directory segments share module-name normalization."""
    mapping = change_impact_tool._find_test_files(
        ["src/XMLParser/config.py"],
        {
            "tests/unit/http/test_config.py",
            "tests/unit/xml_parser/test_config.py",
        },
    )

    assert mapping["src/XMLParser/config.py"] == [
        "tests/unit/xml_parser/test_config.py"
    ]


def test_find_test_files_keeps_camel_case_acronyms_intact():
    """Acronym runs normalize as words across source and test conventions."""
    mapping = change_impact_tool._find_test_files(
        ["src/XMLHttpRequest.ts"],
        {"slow/xml-http-request.test.ts"},
    )

    assert mapping["src/XMLHttpRequest.ts"] == ["slow/xml-http-request.test.ts"]
    assert (
        change_impact_tool.test_file_subject_stem("XMLHttpRequest.ts")
        == "xml_http_request"
    )


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


def test_doc_drift_hints_argument_groups_file_triggers_readme_count_check():
    """Adding a flag in cli/argument_groups/*.py must trigger README-count check (P2 #924)."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints(
        {}, ["tree_sitter_analyzer/cli/argument_groups/_analysis.py"]
    )
    assert "doc_drift_checks" in result
    assert any(
        "test_readme_counts_match_registry" in step
        for step in result["doc_drift_checks"]
    )


def test_doc_drift_hints_facade_map_triggers_facade_doc_regen():
    """Changing facade_map.py must trigger facade-actions.md regen (P2 #924)."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints({}, ["tree_sitter_analyzer/mcp/facade_map.py"])
    assert "doc_drift_checks" in result
    assert any(
        "generate_facade_actions_doc" in step for step in result["doc_drift_checks"]
    )


def test_doc_drift_hints_tool_registry_triggers_both_checks():
    """_tool_registry.py drives both README counts and facade-actions.md (P2 #924)."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints({}, ["tree_sitter_analyzer/mcp/_tool_registry.py"])
    assert any(
        "test_readme_counts_match_registry" in step
        for step in result["doc_drift_checks"]
    )
    assert any(
        "generate_facade_actions_doc" in step for step in result["doc_drift_checks"]
    )


def test_doc_drift_hints_appends_to_verification_steps():
    """doc-drift checks must appear in verification_steps, not just doc_drift_checks (P2 #924)."""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        _attach_doc_drift_hints,
    )

    result = _attach_doc_drift_hints(
        {"verification_steps": ["uv run pytest tests/unit/ -x"]},
        ["tree_sitter_analyzer/cli_main.py"],
    )
    assert len(result["verification_steps"]) == 2
    assert any(
        "test_readme_counts_match_registry" in step
        for step in result["verification_steps"]
    )


def test_pr_impact_scope_uses_filtered_records_and_finalizes(
    monkeypatch, tmp_path
) -> None:
    import asyncio
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.change_impact_tool as impact_module
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    (tmp_path / "src").mkdir()
    parsed = SimpleNamespace(
        url="https://github.com/o/r/pull/1", pr_number=1, slug="o/r"
    )
    monkeypatch.setattr(impact_module, "parse_pr_url", lambda url: parsed)
    monkeypatch.setattr(impact_module, "check_gh_available", lambda: True)
    monkeypatch.setattr(
        impact_module, "fetch_pr_changed_files", lambda value: ["src/a.py", "docs/x.md"]
    )
    monkeypatch.setattr(
        impact_module, "fetch_pr_diff_stat", lambda value: "1 file changed"
    )
    monkeypatch.setattr(
        impact_module,
        "_build_change_impact_result",
        lambda request: {
            "success": True,
            "changed_files": request.changed_files,
            "agent_summary": {"verdict": "SAFE", "summary_line": "ok"},
        },
    )

    result = asyncio.run(
        ChangeImpactTool(str(tmp_path)).execute(
            {"pr_url": parsed.url, "scope_paths": ["src"], "output_format": "json"}
        )
    )
    unscoped = asyncio.run(
        ChangeImpactTool(str(tmp_path)).execute(
            {"pr_url": parsed.url, "output_format": "json"}
        )
    )

    assert result["success"] is True
    assert unscoped["changed_files"] == ["src/a.py", "docs/x.md"]
    assert result["changed_files"] == ["src/a.py"]
    assert result["pr_number"] == 1
    assert result["verdict"] == "SAFE"


def test_name_status_parser_fails_closed_on_truncated_git_output(monkeypatch) -> None:
    import time

    import tree_sitter_analyzer.diff_snapshot_capture as snapshots
    from tree_sitter_analyzer.source_oracle import SourceOracleError

    monkeypatch.setattr(snapshots, "git_output", lambda *args, **kwargs: b"M\0")

    import pytest

    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        snapshots._rows(".", "staged", time.monotonic() + 1, 1024)


def test_create_rejects_oracle_root_identity_drift(tmp_path, monkeypatch) -> None:
    import subprocess

    import tree_sitter_analyzer.diff_snapshot_registry as snapshots
    from tree_sitter_analyzer.source_oracle import RootIdentity

    root = tmp_path
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True
    )
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *args, **kwargs: ("sg_x", RootIdentity("bad", 1, 2)),
    )

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_ROOT_MISMATCH"}


def test_name_status_deduplicates_tracked_and_untracked(monkeypatch) -> None:
    import time

    import tree_sitter_analyzer.diff_snapshot_capture as snapshots

    outputs = iter((b"A\0a.py\0", b"a.py\0"))
    monkeypatch.setattr(snapshots, "git_output", lambda *args, **kwargs: next(outputs))

    assert snapshots._rows(".", "diff", time.monotonic() + 1, 1024) == [
        ("A", None, "a.py", True)
    ]


# Source-bound response helpers are exercised here because they are part of the
# existing change-impact MCP subsystem.
def test_support_canonicalizes_nested_and_top_verdicts() -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    result = {"verdict": "CLEAN", "agent_summary": {"verdict": None}}
    support._canonicalize_change_impact_verdict(result)
    assert result == {"verdict": "SAFE", "agent_summary": {"verdict": "INFO"}}


def test_support_scope_resolution_preserves_absolute_path(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    assert support._resolve_scope_path("unused", str(tmp_path)) == tmp_path


def test_support_scope_validation_reports_only_missing_path(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    (tmp_path / "present").touch()
    assert support._scope_paths_invalid(str(tmp_path), ["present", "missing"]) == [
        "missing"
    ]


def test_support_invalid_pr_envelope_preserves_url() -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    result = support._pr_invalid_url_envelope("invalid", "json")
    assert result["error"] == "Invalid GitHub PR URL: invalid"


def test_support_unavailable_gh_envelope_preserves_parsed_url() -> None:
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    result = support._pr_gh_unavailable_envelope(
        SimpleNamespace(url="https://example/pr/1"), "json"
    )
    assert result["pr_url"] == "https://example/pr/1"


def test_support_snapshot_records_filters_malformed_values() -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    assert support._snapshot_records({"changed_records": [{"path": "a"}, "bad"]}) == [
        {"path": "a"}
    ]


def test_support_snapshot_records_rejects_nonlist() -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    assert support._snapshot_records({"changed_records": "bad"}) == []


def test_support_snapshot_records_accepts_missing_snapshot() -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    assert support._snapshot_records(None) == []


def test_support_journal_decision_upgrades_weaker_verdict(
    monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.decision_journal as journal_module
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    record = SimpleNamespace(id="one", to_dict=lambda: {"verdict": "WARN"})
    monkeypatch.setattr(
        journal_module,
        "DecisionJournal",
        lambda root: SimpleNamespace(search=lambda **kwargs: [record]),
    )
    result = {
        "verdict": "SAFE",
        "agent_summary": {"verdict": "SAFE", "next_step": "run tests"},
    }
    support._enrich_with_journal_decisions(result, str(tmp_path), ["a.py"])
    assert result["verdict"] == "WARN"
    assert result["agent_summary"]["next_step"].endswith("run tests")


def test_support_journal_never_downgrades_stronger_verdict(
    monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.decision_journal as journal_module
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    record = SimpleNamespace(id="one", to_dict=lambda: {"verdict": "REVIEW"})
    monkeypatch.setattr(
        journal_module,
        "DecisionJournal",
        lambda root: SimpleNamespace(search=lambda **kwargs: [record]),
    )
    result = {"verdict": "UNSAFE", "agent_summary": {"verdict": "UNSAFE"}}
    support._enrich_with_journal_decisions(result, str(tmp_path), ["a.py"])
    assert result["verdict"] == "UNSAFE"


def test_support_journal_failure_does_not_block_result(monkeypatch, tmp_path) -> None:
    import tree_sitter_analyzer.decision_journal as journal_module
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    monkeypatch.setattr(
        journal_module, "DecisionJournal", lambda root: (_ for _ in ()).throw(OSError())
    )
    result = {"verdict": "SAFE"}
    support._enrich_with_journal_decisions(result, str(tmp_path), ["a.py"])
    assert result == {"verdict": "SAFE"}


def test_attach_diff_snapshot_translates_missing_capture() -> None:
    tool = tool_module.ChangeImpactTool(None)
    result = tool._attach_diff_snapshot({"output_format": "json"}, "diff", True)
    assert result["error_code"] == "DIFF_SNAPSHOT_CAPTURE_ERROR"


def test_execute_snapshot_rejects_unsupported_mode() -> None:
    result = asyncio.run(
        tool_module.ChangeImpactTool(None).execute(
            {"mode": "branch", "capture_diff_snapshot": True, "output_format": "json"}
        )
    )
    assert result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_MODE"


def test_execute_snapshot_rejects_invalid_scope() -> None:
    result = asyncio.run(
        tool_module.ChangeImpactTool(None).execute(
            {
                "capture_diff_snapshot": True,
                "scope_paths": ["../bad"],
                "output_format": "json",
            }
        )
    )
    assert result["error_code"] == "DIFF_SNAPSHOT_INVALID_PATH"


def test_execute_snapshot_translates_capture_failure(monkeypatch) -> None:
    from tree_sitter_analyzer import diff_snapshot_registry as registry

    monkeypatch.setattr(
        registry.REGISTRY,
        "create",
        lambda *a: {"success": False, "error_code": "CAPTURE"},
    )
    result = asyncio.run(
        tool_module.ChangeImpactTool(None).execute(
            {"capture_diff_snapshot": True, "output_format": "json"}
        )
    )
    assert result["error_code"] == "CAPTURE"


def test_execute_snapshot_closes_lease_after_acquire_failure(monkeypatch) -> None:
    from tree_sitter_analyzer import diff_snapshot_registry as registry

    frozen = {
        "success": True,
        "diff_snapshot_id": "ds",
        "route_lease_id": "lease",
        "changed_records": [],
    }
    closed = []
    monkeypatch.setattr(registry.REGISTRY, "create", lambda *a: frozen)
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *a: (None, "ACQUIRE"))
    monkeypatch.setattr(
        registry.REGISTRY, "close_lease", lambda *a: closed.append(a) or True
    )
    result = asyncio.run(
        tool_module.ChangeImpactTool(None).execute(
            {"capture_diff_snapshot": True, "output_format": "json"}
        )
    )
    assert result["error_code"] == "ACQUIRE"
    assert closed == [("ds", "lease")]


def test_execute_snapshot_translates_strict_verification_conflict(monkeypatch) -> None:
    from types import SimpleNamespace

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    frozen = {
        "success": True,
        "diff_snapshot_id": "ds",
        "route_lease_id": "lease",
        "changed_records": [{"path": "a.py"}],
    }
    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(
            assessed_scope_paths=("a.py",), inventory_paths=("a.py",)
        ),
        release=lambda: None,
    )
    monkeypatch.setattr(registry.REGISTRY, "create", lambda *a: frozen)
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *a: (consumer, None))
    monkeypatch.setattr(registry.REGISTRY, "bind_assessed_scope", lambda *a: "CONFLICT")
    monkeypatch.setattr(registry.REGISTRY, "close_lease", lambda *a: True)
    monkeypatch.setattr(tool_module, "_get_changed_files", lambda *a, **k: ["a.py"])
    monkeypatch.setattr(tool_module, "_get_diff_stat", lambda *a, **k: {})
    result = asyncio.run(
        tool_module.ChangeImpactTool(None).execute(
            {
                "capture_diff_snapshot": True,
                "scope_paths": ["a.py"],
                "output_format": "json",
            }
        )
    )
    assert result["error_code"] == "CONFLICT"


def test_support_canonicalizer_ignores_nondict_summary() -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    result = {"verdict": 7, "agent_summary": "bad"}
    support._canonicalize_change_impact_verdict(result)
    assert result == {"verdict": 7, "agent_summary": "bad"}


def test_support_journal_ignores_empty_matches(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.decision_journal as journal_module
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    monkeypatch.setattr(
        journal_module,
        "DecisionJournal",
        lambda root: SimpleNamespace(search=lambda **kwargs: []),
    )
    result = {"verdict": "SAFE"}
    support._enrich_with_journal_decisions(result, str(tmp_path), ["a.py"])
    assert result == {"verdict": "SAFE"}


def test_support_journal_attaches_safe_match_without_upgrade(
    monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.decision_journal as journal_module
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    record = SimpleNamespace(id="one", to_dict=lambda: {"verdict": "SAFE"})
    monkeypatch.setattr(
        journal_module,
        "DecisionJournal",
        lambda root: SimpleNamespace(search=lambda **kwargs: [record]),
    )
    result = {"verdict": "SAFE"}
    support._enrich_with_journal_decisions(result, str(tmp_path), ["a.py"])
    assert result["related_decisions"] == [{"verdict": "SAFE"}]


def test_support_journal_upgrades_top_level_without_summary(
    monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.decision_journal as journal_module
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    record = SimpleNamespace(id="one", to_dict=lambda: {"verdict": "REVIEW"})
    monkeypatch.setattr(
        journal_module,
        "DecisionJournal",
        lambda root: SimpleNamespace(search=lambda **kwargs: [record]),
    )
    result = {"verdict": "SAFE"}
    support._enrich_with_journal_decisions(result, str(tmp_path), ["a.py"])
    assert result["verdict"] == "REVIEW"


def test_support_canonicalizer_preserves_nonstr_nested_verdict() -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    result = {"agent_summary": {"verdict": 7}}
    support._canonicalize_change_impact_verdict(result)
    assert result == {"agent_summary": {"verdict": 7}}


def test_support_pr_summary_only_returns_compact_decision_surface() -> None:
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools import change_impact_support as support

    result = support._finalize_pr_result(
        {
            "success": True,
            "verdict": "SAFE",
            "agent_summary": {
                "verdict": "SAFE",
                "summary_line": "one changed file",
                "next_step": "run focused test",
            },
        },
        parsed=SimpleNamespace(url="https://example/pull/1", pr_number=1, slug="o/r"),
        scope_paths=[],
        scope_paths_invalid=[],
        changed_files=["a.py"],
        agent_summary_only=True,
        output_format="json",
    )

    assert result["agent_summary_only"] is True
    assert result["summary_line"] == "one changed file"
    assert result["next_step"] == "run focused test"


def test_strict_snapshot_impact_never_calls_live_analysis(
    tmp_path, monkeypatch
) -> None:
    import subprocess

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    install_fake_snapshot_materializer(
        monkeypatch,
        tmp_path,
        records=[ChangedFile("a.py", "M", True, True, False)],
        inventory_paths=["a.py"],
    )
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 2\n")
    monkeypatch.setattr(
        tool_module,
        "_build_change_impact_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live analysis")),
    )

    result = asyncio.run(
        tool_module.ChangeImpactTool(str(tmp_path)).execute(
            {"capture_diff_snapshot": True, "output_format": "json"}
        )
    )

    assert result["affected_files_unknown"] is True
    registry.close_route_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )


def test_strict_snapshot_exception_releases_pin_and_closes_lease(monkeypatch) -> None:
    from types import SimpleNamespace

    import pytest

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    released: list[bool] = []
    closed: list[tuple[str, str]] = []
    frozen = {
        "success": True,
        "diff_snapshot_id": "ds",
        "route_lease_id": "lease",
        "changed_records": [],
    }
    consumer = SimpleNamespace(release=lambda: released.append(True))
    monkeypatch.setattr(registry.REGISTRY, "create", lambda *args: frozen)
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *args: (consumer, None))
    monkeypatch.setattr(
        registry.REGISTRY,
        "close_lease",
        lambda sid, lease: closed.append((sid, lease)) or True,
    )
    monkeypatch.setattr(
        tool_module.ChangeImpactTool,
        "_execute_frozen_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("analysis")),
    )

    with pytest.raises(RuntimeError, match="analysis"):
        asyncio.run(
            tool_module.ChangeImpactTool(None).execute(
                {"capture_diff_snapshot": True, "output_format": "json"}
            )
        )

    assert (released, closed) == ([True], [("ds", "lease")])


def test_attach_diff_snapshot_disabled_preserves_result() -> None:
    tool = tool_module.ChangeImpactTool(None)
    result = {"success": True}

    attached = tool._attach_diff_snapshot(result, "diff", False)

    assert attached == {"success": True}


def test_pr_analysis_reports_gh_unavailable(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        tool_module,
        "parse_pr_url",
        lambda url: SimpleNamespace(url=url, owner="o", repo="r", number=1),
    )
    monkeypatch.setattr(tool_module, "check_gh_available", lambda: False)

    result = tool_module.ChangeImpactTool(None)._execute_pr_analysis(
        "https://github.com/o/r/pull/1",
        True,
        "json",
        [],
        False,
    )

    assert result["error"] == "gh CLI not available or not authenticated"


def _strict_capture_repo(tmp_path, files: dict[str, str]):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True
    )


def test_strict_snapshot_root_scope_matches_all_paths(tmp_path, monkeypatch) -> None:
    # PR #1252 review thread 3746878572.
    from tree_sitter_analyzer import diff_snapshot_registry as registry

    install_fake_snapshot_materializer(
        monkeypatch,
        tmp_path,
        records=[ChangedFile("pkg/a.py", "M", True, True, False)],
        inventory_paths=["pkg/a.py"],
    )
    _strict_capture_repo(tmp_path, {"pkg/a.py": "x = 1\n"})
    (tmp_path / "pkg/a.py").write_text("x = 2\n")
    result = asyncio.run(
        tool_module.ChangeImpactTool(str(tmp_path)).execute(
            {
                "capture_diff_snapshot": True,
                "scope_paths": ["."],
                "output_format": "json",
            }
        )
    )
    assert result["changed_files"] == ["pkg/a.py"]
    assert result["scope_paths_invalid"] == []
    registry.close_route_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )


def test_strict_snapshot_rename_matches_deleted_old_scope(
    tmp_path, monkeypatch
) -> None:
    # PR #1252 review thread 3746878577.
    import subprocess

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    install_fake_snapshot_materializer(
        monkeypatch,
        tmp_path,
        records=[ChangedFile("new.py", "R", True, True, False, old_path="old.py")],
        inventory_paths=["new.py"],
    )
    _strict_capture_repo(tmp_path, {"old.py": "x = 1\n"})
    subprocess.run(["git", "mv", "old.py", "new.py"], cwd=tmp_path, check=True)
    result = asyncio.run(
        tool_module.ChangeImpactTool(str(tmp_path)).execute(
            {
                "capture_diff_snapshot": True,
                "mode": "staged",
                "scope_paths": ["old.py"],
                "output_format": "json",
            }
        )
    )
    assert result["changed_files"] == ["new.py"]
    assert result["scope_paths_invalid"] == []
    registry.close_route_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )


def test_strict_snapshot_filters_tool_cache_paths(tmp_path, monkeypatch) -> None:
    # PR #1252 review thread 3746878600.
    from tree_sitter_analyzer import diff_snapshot_registry as registry

    install_fake_snapshot_materializer(
        monkeypatch,
        tmp_path,
        records=[ChangedFile(".ast-cache/index.db", "M", True, True, False)],
        inventory_paths=[".ast-cache/index.db"],
    )
    _strict_capture_repo(tmp_path, {".ast-cache/index.db": "one\n"})
    (tmp_path / ".ast-cache/index.db").write_text("two\n")
    result = asyncio.run(
        tool_module.ChangeImpactTool(str(tmp_path)).execute(
            {"capture_diff_snapshot": True, "output_format": "json"}
        )
    )
    assert result["changed_files"] == []
    registry.close_route_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )


def test_strict_summary_only_preserves_snapshot_surface(tmp_path, monkeypatch) -> None:
    # PR #1252 review thread 3746878602.
    from tree_sitter_analyzer import diff_snapshot_registry as registry

    install_fake_snapshot_materializer(
        monkeypatch,
        tmp_path,
        records=[ChangedFile("a.py", "M", True, True, False)],
        inventory_paths=["a.py"],
    )
    _strict_capture_repo(tmp_path, {"a.py": "x = 1\n"})
    (tmp_path / "a.py").write_text("x = 2\n")
    result = asyncio.run(
        tool_module.ChangeImpactTool(str(tmp_path)).execute(
            {
                "capture_diff_snapshot": True,
                "agent_summary_only": True,
                "output_format": "json",
            }
        )
    )
    keys = (
        "diff_snapshot_id",
        "route_lease_id",
        "source_generation",
        "changed_records",
    )
    assert tuple(key in result for key in keys) == (True, True, True, True)
    registry.close_route_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )


def test_strict_early_error_uses_requested_toon_formatter() -> None:
    # PR #1252 review thread 3746878603.
    result = asyncio.run(
        tool_module.ChangeImpactTool(".").execute(
            {"capture_diff_snapshot": True, "mode": "branch", "output_format": "toon"}
        )
    )
    assert result["format"] == "toon"
    assert isinstance(result["toon_content"], str)


def test_strict_scope_response_projects_changed_records(tmp_path, monkeypatch) -> None:
    # PR #1252 review thread 3746940429.
    from tree_sitter_analyzer import diff_snapshot_registry as registry

    install_fake_snapshot_materializer(
        monkeypatch,
        tmp_path,
        records=[
            ChangedFile("a.py", "M", True, True, False),
            ChangedFile("b.py", "M", True, True, False),
        ],
        inventory_paths=["a.py", "b.py"],
    )
    _strict_capture_repo(tmp_path, {"a.py": "a = 1\n", "b.py": "b = 1\n"})
    (tmp_path / "a.py").write_text("a = 2\n")
    (tmp_path / "b.py").write_text("b = 2\n")
    result = asyncio.run(
        tool_module.ChangeImpactTool(str(tmp_path)).execute(
            {
                "capture_diff_snapshot": True,
                "scope_paths": ["a.py"],
                "scope_mode": "strict",
                "output_format": "json",
            }
        )
    )

    assert [record["path"] for record in result["changed_records"]] == ["a.py"]
    registry.close_route_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )


def test_frozen_snapshot_rejects_git_magic_scope_with_toon() -> None:
    # PR #1252 review thread 3747224326.
    result = asyncio.run(
        tool_module.ChangeImpactTool(".").execute(
            {
                "capture_diff_snapshot": True,
                "scope_paths": [":(glob)src/*.py"],
                "output_format": "toon",
            }
        )
    )

    assert result["format"] == "toon"
    assert "DIFF_SNAPSHOT_UNSUPPORTED_SCOPE" in result["toon_content"]
