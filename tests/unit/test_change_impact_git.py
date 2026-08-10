"""Tests for change_impact_git helpers — previously only indirect coverage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.diff_snapshot_capture import ChangedFile, FrozenFile
from tree_sitter_analyzer.mcp.tools.change_impact_frozen import (
    build_frozen_scope_result,
)
from tree_sitter_analyzer.mcp.tools.utils.change_impact_git import (
    _get_changed_files,
    _get_diff_stat,
    _get_untracked_files,
    _normalize_scope_paths,
    _run_git,
    _split_git_lines,
    _unique_preserve_order,
    _with_pathspec,
)


class TestRunGit:
    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="M file.py\n")
        code, out = _run_git(["status", "--short"])
        assert code == 0
        assert "file.py" in out

    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        code, out = _run_git(["status"])
        assert code == 128

    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        code, out = _run_git(["status"])
        assert code == 1


class TestSplitGitLines:
    def test_splits_lines(self):
        assert _split_git_lines("a.py\nb.py\n") == ["a.py", "b.py"]

    def test_empty(self):
        assert _split_git_lines("") == []

    def test_whitespace_only(self):
        assert _split_git_lines("  \n  \n") == []


class TestUniquePreserveOrder:
    def test_deduplicates(self):
        assert _unique_preserve_order(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_empty(self):
        assert _unique_preserve_order([]) == []


class TestNormalizeScopePaths:
    def test_none_returns_empty(self):
        assert _normalize_scope_paths(None) == []

    def test_empty_list(self):
        assert _normalize_scope_paths([]) == []

    def test_deduplicates(self):
        assert _normalize_scope_paths(["src/", "src/"]) == ["src/"]


class TestWithPathspec:
    def test_no_scope(self):
        args = ["diff", "--name-only"]
        result = _with_pathspec(args, None)
        assert result == args

    def test_with_scope(self):
        args = ["diff", "--name-only"]
        result = _with_pathspec(args, ["src/"])
        assert "--" in result
        assert "src/" in result


class TestGetUntrackedFiles:
    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git._run_git")
    def test_returns_files(self, mock_git):
        mock_git.return_value = (0, "new_file.py\n")
        files = _get_untracked_files("/src", None)
        assert "new_file.py" in files

    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git._run_git")
    def test_git_failure(self, mock_git):
        mock_git.return_value = (128, "")
        assert _get_untracked_files("/src", None) == []


class TestGetChangedFiles:
    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git._run_git")
    def test_default_mode(self, mock_git):
        # --name-only format: plain filenames, no status prefix
        mock_git.return_value = (0, "file.py\nnew.py\n")
        files = _get_changed_files("diff", "/src", None)
        assert "file.py" in files

    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git._run_git")
    def test_staged_mode(self, mock_git):
        mock_git.return_value = (0, "staged.py\n")
        files = _get_changed_files("staged", "/src", None)
        assert "staged.py" in files

    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git._run_git")
    def test_branch_mode(self, mock_git):
        mock_git.return_value = (0, "branch.py\n")
        files = _get_changed_files("branch", "/src", None)
        assert "branch.py" in files


class TestGetDiffStat:
    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git._run_git")
    def test_returns_stat(self, mock_git):
        mock_git.return_value = (
            0,
            "10 files changed, 50 insertions(+), 20 deletions(-)\n",
        )
        stat = _get_diff_stat("diff", "/src", None)
        assert "files changed" in stat

    @patch("tree_sitter_analyzer.mcp.tools.utils.change_impact_git._run_git")
    def test_git_failure(self, mock_git):
        mock_git.return_value = (128, "")
        stat = _get_diff_stat("diff", "/src", None)
        assert stat == ""


def _frozen_rename(old_path: str, new_path: str):
    record = ChangedFile(
        path=new_path,
        old_path=old_path,
        status="R",
        old_available=True,
        new_available=True,
        binary=False,
    )
    frozen = {"changed_records": [record.to_dict()]}
    snapshot = SimpleNamespace(
        files=(FrozenFile(record, b"old", b"new"),),
        inventory_paths=(old_path, new_path),
        _inventory_raw_paths=(),
    )
    return frozen, SimpleNamespace(snapshot=snapshot)


def test_frozen_rename_into_cache_reports_visible_old_side() -> None:
    # PR #1252 review 9369: a cache destination must not hide the source deletion.
    frozen, consumer = _frozen_rename("source.py", ".ast-cache/source.py")
    result, records, changed, _assessed = build_frozen_scope_result(
        frozen, consumer, "diff", [], "report"
    )
    assert records == frozen["changed_records"]
    assert changed == ["source.py"]
    assert result["changed_files"] == ["source.py"]


def test_frozen_rename_out_of_cache_reports_visible_new_side() -> None:
    # PR #1252 review 9369: the visible destination remains reportable.
    frozen, consumer = _frozen_rename(".ast-cache/source.py", "source.py")
    result, records, changed, _assessed = build_frozen_scope_result(
        frozen, consumer, "diff", [], "report"
    )
    assert records == frozen["changed_records"]
    assert changed == ["source.py"]
    assert result["changed_files"] == ["source.py"]
