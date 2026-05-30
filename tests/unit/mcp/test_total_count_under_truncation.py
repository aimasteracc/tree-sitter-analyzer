"""Regression tests for H2/H3 — total_count honesty under truncation.

H2: search_content.total_count lied when ripgrep truncated. The post-fix
contract is: when truncated=True, either total_count > displayed_count
(real total via recount pass) OR total_count_known=False.

H3: list_files.total_count lied when fd's --max-results truncated. Same
contract — truncated responses must carry an honest pre-truncation count
or an explicit total_count_known=False flag.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

# Skip the whole module on systems missing fd / rg — these are shell tools.
_FD_AVAILABLE = shutil.which("fd") is not None
_RG_AVAILABLE = shutil.which("rg") is not None


def _assert_honest_total_count(result: dict, displayed: int, total: int) -> None:
    """H2/H3 contract: truncated response must carry honest count or explicit uncertainty."""
    if result.get("total_count_known", True):
        assert total > displayed, (
            f"truncated=True but total_count={total} == displayed_count="
            f"{displayed}; total_count_known is True so this lies"
        )
    else:
        assert result.get("total_count_at_least") == displayed


def _assert_non_truncated_known(result: dict) -> None:
    """A non-truncated response must mark total_count as known and exact."""
    assert result.get("truncated") is False
    assert result.get("total_count_known") is True
    assert result["total_count"] == result["displayed_count"]


def _make_repo_with_many_def_lines(root: Path, n_files: int = 50) -> None:
    """Populate ``root`` with files that collectively contain >>1 'def' line.

    Each file gets ~40 ``def foo_i_j():`` lines so the total exceeds the
    truncation cap used in the test.
    """
    for i in range(n_files):
        f = root / f"mod_{i:03d}.py"
        lines = [f"def f_{i}_{j}():\n    return {j}\n" for j in range(40)]
        f.write_text("".join(lines))


@pytest.fixture
def big_repo() -> Path:
    """Temporary tree with many .py files and many 'def' matches."""
    with tempfile.TemporaryDirectory(prefix="h2h3_repo_") as tmp:
        root = Path(tmp)
        _make_repo_with_many_def_lines(root, n_files=50)
        yield root


# ============================================================
# H2 — search_content total_count under truncation
# ============================================================


@pytest.mark.skipif(not _RG_AVAILABLE, reason="ripgrep not installed")
class TestSearchContentTotalCountUnderTruncation:
    def test_total_count_above_displayed_when_truncated(self, big_repo: Path) -> None:
        """The recount pass should resolve a real total > displayed_count."""
        tool = SearchContentTool(project_root=str(big_repo))
        result = asyncio.run(
            tool.execute(
                {
                    "query": "def ",
                    "roots": [str(big_repo)],
                    "max_count": 100,
                    "output_format": "json",
                }
            )
        )
        assert isinstance(result, dict)
        assert result.get("truncated") is True
        displayed = int(result["displayed_count"])
        total = int(result["total_count"])
        _assert_honest_total_count(result, displayed, total)

    def test_non_truncated_response_marks_known(self, big_repo: Path) -> None:
        """When ripgrep didn't truncate, total_count_known must be True."""
        tool = SearchContentTool(project_root=str(big_repo))
        result = asyncio.run(
            tool.execute(
                {
                    "query": "this_string_definitely_does_not_exist_zzz",
                    "roots": [str(big_repo)],
                    "output_format": "json",
                }
            )
        )
        assert isinstance(result, dict)
        _assert_non_truncated_known(result)


# ============================================================
# H3 — list_files total_count under limit
# ============================================================


@pytest.mark.skipif(not _FD_AVAILABLE, reason="fd not installed")
class TestListFilesTotalCountUnderLimit:
    def test_total_count_above_displayed_when_limited(self, big_repo: Path) -> None:
        """With limit << real_total, total_count must reflect the real count."""
        tool = ListFilesTool(project_root=str(big_repo))
        result: Any = asyncio.run(
            tool.execute(
                {
                    "roots": [str(big_repo)],
                    "extensions": ["py"],
                    "limit": 3,
                    "output_format": "json",
                }
            )
        )
        assert isinstance(result, dict)
        assert result.get("truncated") is True
        displayed = int(result["displayed_count"])
        total = int(result["total_count"])
        _assert_honest_total_count(result, displayed, total)

    def test_non_truncated_response_marks_known(self, big_repo: Path) -> None:
        """Without truncation, total_count == displayed_count and known."""
        tool = ListFilesTool(project_root=str(big_repo))
        result: Any = asyncio.run(
            tool.execute(
                {
                    "roots": [str(big_repo)],
                    "extensions": ["py"],
                    "limit": 200,  # larger than the fixture file count
                    "output_format": "json",
                }
            )
        )
        assert isinstance(result, dict)
        _assert_non_truncated_known(result)
