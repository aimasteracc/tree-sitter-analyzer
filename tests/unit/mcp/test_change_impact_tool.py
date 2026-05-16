"""Unit tests for change impact analysis helpers."""

from tree_sitter_analyzer.mcp.tools import change_impact_tool


def test_diff_mode_includes_untracked_files(monkeypatch):
    """Default diff mode should include untracked files in changed_files."""

    def fake_run_git(args, cwd=None):
        if args == ["diff", "--name-only"]:
            return 0, "tree_sitter_analyzer/health_scorer.py\n"
        if args == ["ls-files", "--others", "--exclude-standard"]:
            return 0, "tree_sitter_analyzer/_health_scorer_helpers.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(change_impact_tool, "_run_git", fake_run_git)

    changed = change_impact_tool._get_changed_files("diff", "/repo")

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

    monkeypatch.setattr(change_impact_tool, "_run_git", fake_run_git)

    changed = change_impact_tool._get_changed_files("diff", "/repo")

    assert changed == ["tree_sitter_analyzer/new_tool.py"]


def test_staged_mode_keeps_staged_semantics(monkeypatch):
    """Staged mode should only report staged files."""
    calls = []

    def fake_run_git(args, cwd=None):
        calls.append(args)
        if args == ["diff", "--cached", "--name-only"]:
            return 0, "tree_sitter_analyzer/cli_main.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(change_impact_tool, "_run_git", fake_run_git)

    changed = change_impact_tool._get_changed_files("staged", "/repo")

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

    monkeypatch.setattr(change_impact_tool, "_run_git", fake_run_git)

    diff_stat = change_impact_tool._get_diff_stat("diff", "/repo")

    assert "tree_sitter_analyzer/health_scorer.py" in diff_stat
    assert "Untracked files:" in diff_stat
    assert "tree_sitter_analyzer/_health_scorer_helpers.py" in diff_stat


def test_build_pytest_command_quotes_paths():
    """Fast validation command should be directly runnable in a shell."""
    command = change_impact_tool._build_pytest_command(
        ["tests/unit/test_health_scorer.py", "tests/unit/path with space.py"]
    )

    assert command == (
        "uv run pytest tests/unit/test_health_scorer.py "
        "'tests/unit/path with space.py' -q"
    )


def test_build_pytest_command_falls_back_to_full_suite():
    """No mapped tests should still produce a valid validation command."""
    assert change_impact_tool._build_pytest_command([]) == "uv run pytest -q"
