"""Unit tests for change-impact git helpers and verification planning."""


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
