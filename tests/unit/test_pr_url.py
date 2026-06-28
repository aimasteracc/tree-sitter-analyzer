"""Tests for PR URL analysis feature (pr_url.py and change_impact_tool integration)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
    TOOL_SCHEMA,
    ChangeImpactTool,
)
from tree_sitter_analyzer.pr_url import (
    ParsedPRUrl,
    check_gh_available,
    fetch_pr_changed_files,
    fetch_pr_diff,
    fetch_pr_diff_stat,
    parse_pr_url,
)


class TestParsePRUrl:
    def test_standard_https_url(self):
        result = parse_pr_url("https://github.com/owner/repo/pull/42")
        assert result is not None
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.pr_number == 42

    def test_http_url(self):
        result = parse_pr_url("http://github.com/acme/project/pull/7")
        assert result is not None
        assert result.owner == "acme"
        assert result.repo == "project"
        assert result.pr_number == 7

    def test_url_with_trailing_files(self):
        result = parse_pr_url("https://github.com/owner/repo/pull/42/files")
        assert result is not None
        assert result.pr_number == 42

    def test_url_with_trailing_slash(self):
        result = parse_pr_url("https://github.com/owner/repo/pull/42/")
        assert result is not None
        assert result.pr_number == 42

    def test_api_url(self):
        result = parse_pr_url("https://api.github.com/repos/owner/repo/pulls/123")
        assert result is not None
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.pr_number == 123

    def test_url_with_whitespace(self):
        result = parse_pr_url("  https://github.com/o/r/pull/1  ")
        assert result is not None
        assert result.pr_number == 1

    def test_invalid_url_returns_none(self):
        assert parse_pr_url("https://github.com/owner/repo") is None
        assert parse_pr_url("not-a-url") is None
        assert parse_pr_url("") is None

    def test_issue_url_not_matched(self):
        assert parse_pr_url("https://github.com/owner/repo/issues/42") is None


class TestParsedPRUrl:
    def test_slug(self):
        pr = ParsedPRUrl(owner="acme", repo="project", pr_number=5)
        assert pr.slug == "acme/project"

    def test_url(self):
        pr = ParsedPRUrl(owner="acme", repo="project", pr_number=5)
        assert pr.url == "https://github.com/acme/project/pull/5"

    def test_frozen(self):
        pr = ParsedPRUrl(owner="acme", repo="project", pr_number=5)
        with pytest.raises(AttributeError):
            pr.owner = "other"


class TestFetchPRChangedFiles:
    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_success(self, mock_gh):
        mock_gh.return_value = (0, "src/a.py\nsrc/b.py\n")
        pr = ParsedPRUrl("owner", "repo", 1)
        result = fetch_pr_changed_files(pr)
        assert result == ["src/a.py", "src/b.py"]
        mock_gh.assert_called_once_with(
            ["pr", "diff", "1", "--repo", "owner/repo", "--name-only"]
        )

    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_failure_returns_empty(self, mock_gh):
        mock_gh.return_value = (1, "")
        pr = ParsedPRUrl("owner", "repo", 1)
        assert fetch_pr_changed_files(pr) == []

    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_empty_output(self, mock_gh):
        mock_gh.return_value = (0, "")
        pr = ParsedPRUrl("owner", "repo", 1)
        assert fetch_pr_changed_files(pr) == []


class TestFetchPRDiffStat:
    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_success(self, mock_gh):
        mock_gh.return_value = (0, "src/a.py | 10 +++---\n2 files changed")
        pr = ParsedPRUrl("owner", "repo", 1)
        assert "src/a.py" in fetch_pr_diff_stat(pr)

    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_failure_returns_empty(self, mock_gh):
        mock_gh.return_value = (1, "")
        assert fetch_pr_diff_stat(ParsedPRUrl("o", "r", 1)) == ""


class TestFetchPRDiff:
    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_success(self, mock_gh):
        mock_gh.return_value = (0, "diff --git a/foo b/foo\n--- a/foo\n+++ b/foo")
        pr = ParsedPRUrl("owner", "repo", 1)
        assert "diff --git" in fetch_pr_diff(pr)

    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_failure_returns_empty(self, mock_gh):
        mock_gh.return_value = (1, "")
        assert fetch_pr_diff(ParsedPRUrl("o", "r", 1)) == ""


class TestCheckGhAvailable:
    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_available(self, mock_gh):
        mock_gh.return_value = (0, "")
        assert check_gh_available() is True

    @patch("tree_sitter_analyzer.pr_url._run_gh")
    def test_not_available(self, mock_gh):
        mock_gh.return_value = (1, "error")
        assert check_gh_available() is False


class TestToolSchemaIncludesPRUrl:
    def test_schema_has_pr_url(self):
        assert "pr_url" in TOOL_SCHEMA["properties"]

    def test_schema_mode_includes_pr(self):
        assert "pr" in TOOL_SCHEMA["properties"]["mode"]["enum"]


class TestChangeImpactToolPRUrlValidation:
    def test_validate_accepts_pr_mode(self, tmp_path):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        assert tool.validate_arguments(
            {"mode": "pr", "pr_url": "https://github.com/o/r/pull/1"}
        )

    def test_validate_rejects_bad_mode(self, tmp_path):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        with pytest.raises(ValueError, match="mode must be"):
            tool.validate_arguments({"mode": "invalid"})


class TestChangeImpactToolPRUrlExecute:
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.check_gh_available",
        return_value=True,
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.fetch_pr_diff_stat",
        return_value="src/a.py | 5 ++",
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.fetch_pr_changed_files",
        return_value=["src/a.py", "src/b.py"],
    )
    def test_pr_url_analysis_returns_pr_metadata(
        self, mock_files, mock_stat, mock_gh, tmp_path
    ):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute(
                {
                    "pr_url": "https://github.com/owner/repo/pull/42",
                    "include_tests": False,
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True
        assert result["pr_url"] == "https://github.com/owner/repo/pull/42"
        assert result["pr_number"] == 42
        assert result["repo"] == "owner/repo"

    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.check_gh_available",
        return_value=True,
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.fetch_pr_diff_stat",
        return_value="src/a.py | 5 ++",
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.fetch_pr_changed_files",
        return_value=["src/a.py"],
    )
    def test_pr_url_with_scope_filters_files(
        self, mock_files, mock_stat, mock_gh, tmp_path
    ):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute(
                {
                    "pr_url": "https://github.com/owner/repo/pull/42",
                    "scope_paths": ["src/a.py"],
                    "include_tests": False,
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True

    def test_pr_url_invalid_url(self, tmp_path):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute(
                {
                    "pr_url": "not-a-url",
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is False
        assert "Invalid GitHub PR URL" in result["error"]

    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.check_gh_available",
        return_value=False,
    )
    def test_pr_url_gh_not_available(self, mock_gh, tmp_path):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute(
                {
                    "pr_url": "https://github.com/owner/repo/pull/42",
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is False
        assert "gh CLI" in result["error"]

    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.check_gh_available",
        return_value=True,
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.fetch_pr_changed_files",
        return_value=[],
    )
    def test_pr_url_no_changes(self, mock_files, mock_gh, tmp_path):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute(
                {
                    "pr_url": "https://github.com/owner/repo/pull/42",
                    "output_format": "json",
                }
            )
        )
        assert result["pr_url"] == "https://github.com/owner/repo/pull/42"
        assert result["pr_number"] == 42

    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.check_gh_available",
        return_value=True,
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.fetch_pr_diff_stat",
        return_value="a.py | 1 +",
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.change_impact_tool.fetch_pr_changed_files",
        return_value=["a.py"],
    )
    def test_pr_url_agent_summary_only(self, mock_files, mock_stat, mock_gh, tmp_path):
        # Perf note (2026-05-23): project_root="/tmp" used to scan the entire
        # /tmp tree during dependency-graph construction (~22s on CI boxes
        # with build artifacts in /tmp). Use the pytest tmp_path fixture
        # for a clean empty directory — keeps the test contract (PR URL
        # parses, mocked git wins) but in O(1) instead of O(/tmp).
        tool = ChangeImpactTool(project_root=str(tmp_path))
        result = asyncio.run(
            tool.execute(
                {
                    "pr_url": "https://github.com/owner/repo/pull/42",
                    "agent_summary_only": True,
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True
        assert "agent_summary" in result

    def test_pr_url_auto_mode_override(self):
        parsed = parse_pr_url("https://github.com/owner/repo/pull/42")
        assert parsed is not None
