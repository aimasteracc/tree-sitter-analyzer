"""Unit tests for change impact analysis helpers."""

import asyncio

from tree_sitter_analyzer.mcp.tools import change_impact_tool as tool_module
from tree_sitter_analyzer.mcp.tools.utils import (
    change_impact_analysis as change_impact_tool,
)
from tree_sitter_analyzer.mcp.tools.utils import (
    change_impact_git,
)
from tree_sitter_analyzer.mcp.tools.utils import (
    change_impact_verification as verification_tool,
)
from tree_sitter_analyzer.mcp.tools.utils.verification_command import DefaultTestCommand


def test_diff_mode_includes_untracked_files(monkeypatch):
    """Default diff mode should include untracked files in changed_files."""

    def fake_run_git(args, cwd=None):
        if args == ["diff", "--name-only"]:
            return 0, "tree_sitter_analyzer/health_scorer.py\n"
        if args == ["ls-files", "--others", "--exclude-standard"]:
            return 0, "tree_sitter_analyzer/_health_scorer_helpers.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(change_impact_git, "_run_git", fake_run_git)

    changed = change_impact_git._get_changed_files("diff", "/repo")

    assert changed == [
        "tree_sitter_analyzer/health_scorer.py",
        "tree_sitter_analyzer/_health_scorer_helpers.py",
    ]


def test_diff_mode_deduplicates_untracked_paths(monkeypatch):
    """Duplicate git output should not duplicate changed_files entries."""

    def fake_run_git(args, cwd=None):
        if args == ["diff", "--name-only"]:
            return 0, "tree_sitter_analyzer/new_tool.py\n"
        if args == ["ls-files", "--others", "--exclude-standard"]:
            return 0, "tree_sitter_analyzer/new_tool.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(change_impact_git, "_run_git", fake_run_git)

    changed = change_impact_git._get_changed_files("diff", "/repo")

    assert changed == ["tree_sitter_analyzer/new_tool.py"]


def test_diff_mode_accepts_scope_pathspecs(monkeypatch):
    """Agents can narrow noisy dirty worktrees to the current queue scope."""
    calls = []

    def fake_run_git(args, cwd=None):
        calls.append(args)
        if args == [
            "diff",
            "--name-only",
            "--",
            "tree_sitter_analyzer/mcp/tools",
        ]:
            return 0, "tree_sitter_analyzer/mcp/tools/change_impact_tool.py\n"
        if args == [
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "tree_sitter_analyzer/mcp/tools",
        ]:
            return 0, "tree_sitter_analyzer/mcp/tools/utils/change_impact_git.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(change_impact_git, "_run_git", fake_run_git)

    changed = change_impact_git._get_changed_files(
        "diff",
        "/repo",
        ["tree_sitter_analyzer/mcp/tools"],
    )

    assert changed == [
        "tree_sitter_analyzer/mcp/tools/change_impact_tool.py",
        "tree_sitter_analyzer/mcp/tools/utils/change_impact_git.py",
    ]
    assert calls == [
        ["diff", "--name-only", "--", "tree_sitter_analyzer/mcp/tools"],
        [
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "tree_sitter_analyzer/mcp/tools",
        ],
    ]


def test_staged_mode_keeps_staged_semantics(monkeypatch):
    """Staged mode should only report staged files."""
    calls = []

    def fake_run_git(args, cwd=None):
        calls.append(args)
        if args == ["diff", "--cached", "--name-only"]:
            return 0, "tree_sitter_analyzer/cli_main.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(change_impact_git, "_run_git", fake_run_git)

    changed = change_impact_git._get_changed_files("staged", "/repo")

    assert changed == ["tree_sitter_analyzer/cli_main.py"]
    assert ["ls-files", "--others", "--exclude-standard"] not in calls


def test_diff_stat_mentions_untracked_files(monkeypatch):
    """Diff stat should make untracked files visible to agents."""

    def fake_run_git(args, cwd=None):
        if args == ["diff", "--stat"]:
            return 0, " tree_sitter_analyzer/health_scorer.py | 10 +++++-----"
        if args == ["ls-files", "--others", "--exclude-standard"]:
            return 0, "tree_sitter_analyzer/_health_scorer_helpers.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(change_impact_git, "_run_git", fake_run_git)

    diff_stat = change_impact_git._get_diff_stat("diff", "/repo")

    assert "tree_sitter_analyzer/health_scorer.py" in diff_stat
    assert "Untracked files:" in diff_stat
    assert "tree_sitter_analyzer/_health_scorer_helpers.py" in diff_stat


def test_build_pytest_command_quotes_paths():
    """Fast validation command should be directly runnable in a shell."""
    command = verification_tool._build_pytest_command(
        ["tests/unit/test_health_scorer.py", "tests/unit/path with space.py"]
    )

    assert command == (
        "uv run pytest tests/unit/test_health_scorer.py "
        "'tests/unit/path with space.py' -q"
    )


def test_build_pytest_command_falls_back_to_full_suite():
    """No mapped tests should still produce a valid validation command."""
    assert verification_tool._build_pytest_command([]) == "uv run pytest -q"


def test_docs_only_verification_plan_skips_pytest():
    """Docs-only edits should not send agents into the full test suite."""
    plan = verification_tool._build_verification_plan(
        ["README.md", "docs/agent-tooling-gap-report.md", "docs/notes.txt"],
        [],
    )

    assert plan == {
        "test_required": False,
        "test_runner": "pytest",
        "default_test_command": "uv run pytest -q",
        "pytest_required": False,
        "pytest_command": "",
        "test_command": "",
        "verification_command": "git diff --check",
        "verification_reason": "docs-only changes; pytest is not required",
    }


def test_requirements_txt_is_not_treated_as_docs_only():
    """Dependency manifests can affect execution even when they are .txt files."""
    plan = verification_tool._build_verification_plan(["requirements.txt"], [])

    assert plan["pytest_required"] is True
    assert plan["verification_command"] == "uv run pytest -q"


def test_code_change_verification_plan_uses_targeted_tests():
    """Code edits should recommend the narrow mapped pytest command."""
    plan = verification_tool._build_verification_plan(
        ["tree_sitter_analyzer/cli_main.py"],
        ["tests/unit/cli/test_cli_main_module.py"],
    )

    assert plan == {
        "test_required": True,
        "test_runner": "pytest",
        "default_test_command": "uv run pytest -q",
        "pytest_required": True,
        "pytest_command": "uv run pytest tests/unit/cli/test_cli_main_module.py -q",
        "test_command": "uv run pytest tests/unit/cli/test_cli_main_module.py -q",
        "verification_command": "uv run pytest tests/unit/cli/test_cli_main_module.py -q",
        "verification_reason": "targeted tests cover mapped runtime changes",
    }


def test_code_change_with_runtime_fallback_uses_default_suite():
    """Unmapped runtime files should not be hidden by other targeted tests."""
    plan = verification_tool._build_verification_plan(
        ["tree_sitter_analyzer/cli_main.py", "tree_sitter_analyzer/runtime.py"],
        ["tests/unit/cli/test_cli_main_module.py"],
        {
            "tree_sitter_analyzer/cli_main.py": [
                "tests/unit/cli/test_cli_main_module.py"
            ],
            "tree_sitter_analyzer/runtime.py": [
                verification_tool.AUTO_DISCOVER_TEST_HINT
            ],
        },
    )

    assert plan == {
        "test_required": True,
        "test_runner": "pytest",
        "default_test_command": "uv run pytest -q",
        "pytest_required": True,
        "pytest_command": "uv run pytest -q",
        "test_command": "uv run pytest -q",
        "verification_command": "uv run pytest -q",
        "verification_reason": "unmapped runtime changes remain; run the default test command",
    }


def test_verification_strategy_recommends_focused_then_default_for_dirty_worktree():
    """Agents should get an iteration command plus a queue-boundary command."""
    plan = verification_tool._build_verification_plan(
        ["tree_sitter_analyzer/cli_main.py", "tree_sitter_analyzer/runtime.py"],
        ["tests/unit/cli/test_cli_main_module.py"],
        {
            "tree_sitter_analyzer/cli_main.py": [
                "tests/unit/cli/test_cli_main_module.py"
            ],
            "tree_sitter_analyzer/runtime.py": [
                verification_tool.AUTO_DISCOVER_TEST_HINT
            ],
        },
    )

    strategy = change_impact_tool._build_verification_strategy(
        changed_count=30,
        tests_to_run=["tests/unit/cli/test_cli_main_module.py"],
        verification=plan,
    )

    assert strategy["focused_test_command"] == (
        "uv run pytest tests/unit/cli/test_cli_main_module.py -q"
    )
    assert strategy["verification_strategy"] == "focused_then_default"
    assert strategy["verification_steps"] == [
        "uv run pytest tests/unit/cli/test_cli_main_module.py -q",
        "uv run pytest -q",
    ]
    assert (
        "Large dirty worktree detected (30 changed files)"
        in strategy["verification_hint"]
    )


def test_verification_strategy_avoids_huge_focused_commands():
    """Very broad diffs should not produce copy-paste hostile focused commands."""
    plan = verification_tool._build_verification_plan(
        ["tree_sitter_analyzer/runtime.py"],
        [f"tests/unit/test_feature_{index:02d}.py" for index in range(25)],
    )

    strategy = change_impact_tool._build_verification_strategy(
        changed_count=25,
        tests_to_run=[f"tests/unit/test_feature_{index:02d}.py" for index in range(25)],
        verification=plan,
    )

    assert strategy["focused_test_command"] == ""
    assert strategy["verification_strategy"] == "default_for_large_diff"
    assert strategy["verification_steps"] == ["uv run pytest -q"]
    assert (
        "25 mapped tests exceed the focused command limit"
        in strategy["verification_hint"]
    )


def test_code_change_verification_plan_falls_back_to_default_suite():
    """Code edits without mapped tests should keep the default-suite contract."""
    plan = verification_tool._build_verification_plan(
        ["tree_sitter_analyzer/new_runtime.py"],
        [],
    )

    assert plan == {
        "test_required": True,
        "test_runner": "pytest",
        "default_test_command": "uv run pytest -q",
        "pytest_required": True,
        "pytest_command": "uv run pytest -q",
        "test_command": "uv run pytest -q",
        "verification_command": "uv run pytest -q",
        "verification_reason": "no targeted tests found; run the default test command",
    }


def test_non_pytest_default_verification_plan_uses_detected_runner():
    """Arbitrary-language projects should follow their own default test runner."""
    plan = verification_tool._build_verification_plan(
        ["internal/tool/main.go"],
        [],
        default_test_command=DefaultTestCommand("go", "go test ./..."),
    )

    assert plan == {
        "test_required": True,
        "test_runner": "go",
        "default_test_command": "go test ./...",
        "pytest_required": False,
        "pytest_command": "",
        "test_command": "go test ./...",
        "verification_command": "go test ./...",
        "verification_reason": "no targeted tests found; run the default test command",
    }


def test_build_file_impacts_without_graph_returns_fallback_rows():
    """Missing dependency graphs should still report each changed file."""
    affected, file_impacts = change_impact_tool._build_file_impacts(
        ["tree_sitter_analyzer/cli_main.py"],
        None,
    )

    assert affected == set()
    assert file_impacts == [{"file": "tree_sitter_analyzer/cli_main.py"}]


def test_no_changes_result_keeps_agent_scope_signal():
    """Empty scoped diffs should still return a useful compact summary."""
    result = change_impact_tool._build_no_changes_result(
        "diff",
        ["tree_sitter_analyzer/mcp/tools"],
    )

    assert result["agent_summary"] == {
        "risk": "none",
        "scope": "scoped",
        "changed_count": 0,
        "affected_count": 0,
        "tests_to_run_count": 0,
        "next_step": "No changes detected; no verification needed.",
        "verification_command": "",
        "stop_condition": "Working tree remains unchanged for the selected mode and scope.",
    }


def test_agent_summary_only_response_omits_noisy_details():
    """Agents can ask for only the compact decision surface."""
    result = change_impact_tool.build_agent_summary_only_response(
        {
            "success": True,
            "mode": "diff",
            "scope_paths": [],
            "scope_filtered": False,
            "agent_summary": {
                "risk": "high",
                "changed_count": 42,
                "affected_count": 120,
                "tests_to_run_count": 30,
                "next_step": "Run verification: uv run pytest -q",
                "verification_command": "uv run pytest -q",
                "verification_strategy": "default_for_large_diff",
                "stop_condition": "uv run pytest -q exits successfully.",
            },
            "changed_files": ["a.py"],
            "affected_files": ["b.py"],
            "file_impacts": [{"file": "a.py"}],
            "test_mapping": {"a.py": ["tests/test_a.py"]},
            "diff_stat": "a.py | 1 +",
            "risk_level": "high",
            "changed_count": 42,
            "affected_count": 120,
            "tests_to_run_count": 30,
            "verification_command": "uv run pytest -q",
            "focused_test_command": "",
            "verification_strategy": "default_for_large_diff",
            "verification_steps": ["uv run pytest -q"],
        }
    )

    assert result == {
        "success": True,
        "mode": "diff",
        "scope_paths": [],
        "scope_filtered": False,
        "agent_summary_only": True,
        "agent_summary": {
            "risk": "high",
            "changed_count": 42,
            "affected_count": 120,
            "tests_to_run_count": 30,
            "next_step": "Run verification: uv run pytest -q",
            "verification_command": "uv run pytest -q",
            "verification_strategy": "default_for_large_diff",
            "stop_condition": "uv run pytest -q exits successfully.",
        },
        "risk_level": "high",
        "changed_count": 42,
        "affected_count": 120,
        "tests_to_run_count": 30,
        "next_step": "Run verification: uv run pytest -q",
        "verification_command": "uv run pytest -q",
        "focused_test_command": "",
        "queue_ledger": {},
        "verification_strategy": "default_for_large_diff",
        "verification_steps": ["uv run pytest -q"],
        "stop_condition": "uv run pytest -q exits successfully.",
    }


def test_build_file_impacts_with_graph_preserves_order_and_limits_dependents(
    monkeypatch,
):
    """Graph-backed impact rows should be stable and bounded for agent output."""

    class FakeGraph:
        def dependents_of(self, file_path):
            return [f"dep_{i:02d}_{file_path}" for i in range(25, 0, -1)]

    class FakeBlastRadius:
        def __init__(self, graph):
            self.graph = graph

        def forward(self, file_path):
            return {file_path, f"affected/{file_path}"}

    monkeypatch.setattr(change_impact_tool, "BlastRadius", FakeBlastRadius)

    changed_files = ["b.py", "a.py"]
    affected, file_impacts = change_impact_tool._build_file_impacts(
        changed_files,
        FakeGraph(),
    )

    assert affected == {"b.py", "affected/b.py", "a.py", "affected/a.py"}
    assert [impact["file"] for impact in file_impacts] == changed_files
    assert file_impacts[0]["total_affected"] == 2
    assert len(file_impacts[0]["direct_dependents"]) == 20
    assert file_impacts[0]["direct_dependents"][0] == "dep_01_b.py"


def test_build_test_plan_skips_when_disabled():
    """Agents can request impact data without related test lookup."""
    test_mapping, tests_to_run = change_impact_tool._build_test_plan(
        ["tree_sitter_analyzer/cli_main.py"],
        graph=None,
        include_tests=False,
    )

    assert test_mapping == {}
    assert tests_to_run == []


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
    assert result["agent_summary"] == {
        "risk": "unknown",
        "scope": "workspace",
        "changed_count": 1,
        "affected_count": 0,
        "tests_to_run_count": 0,
        "next_step": "Run git diff --check; pytest is not required for docs-only changes.",
        "verification_command": "git diff --check",
        "verification_strategy": "docs_only",
        "stop_condition": "git diff --check passes and no runtime files are added.",
        "changed_preview": ["README.md"],
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


def test_build_test_plan_returns_sorted_runnable_tests():
    """Fallback auto-discovery markers should not become pytest targets."""

    class FakeGraph:
        def nodes(self):
            return {
                "tests/unit/mcp/test_change_impact_tool.py",
                "tests/unit/cli/test_cli_main_module.py",
                "tree_sitter_analyzer/cli_main.py",
            }

    test_mapping, tests_to_run = change_impact_tool._build_test_plan(
        [
            "tree_sitter_analyzer/cli_main.py",
            "tree_sitter_analyzer/unknown_module.py",
        ],
        FakeGraph(),
        include_tests=True,
    )

    assert test_mapping["tree_sitter_analyzer/unknown_module.py"] == [
        verification_tool.AUTO_DISCOVER_TEST_HINT
    ]
    assert tests_to_run == ["tests/unit/cli/test_cli_main_module.py"]


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
