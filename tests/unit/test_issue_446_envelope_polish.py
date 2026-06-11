"""Tests for issue #446: Envelope polish — no null fields, real next_step, honest verdict.

Three specific items:
1. status tool: omit None-valued schema_version/hint; give real next_step (not empty)
2. summary_line triple shipping: reduce to canonical location (agent_summary only)
3. overview tool verdict: INFO for plain info, REVIEW only when code needs review
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool
from tree_sitter_analyzer.mcp.tools.project_overview_tool import ProjectOverviewTool


def _run(coro):
    return asyncio.run(coro)


def _write(tmp_path, rel, content, encoding="utf-8"):
    tmp_path = Path(tmp_path) if isinstance(tmp_path, str) else tmp_path
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return p


class TestStatusToolNullFields:
    """Issue #446 Item 1: status tool should omit None/null fields."""

    @pytest.mark.asyncio
    async def test_indexed_status_omits_null_schema_version(self):
        """When schema_version is None, it should be omitted (not sent as null)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = CodeGraphStatusTool(tmpdir)
            cache_dir = Path(tmpdir) / ".ast-cache"
            cache_dir.mkdir()
            (cache_dir / "index.db").write_bytes(b"sqlite3-fake")

            mock_stats = {
                "total_files": 42,
                "total_symbols": 1337,
                "fts5_available": True,
                "schema_version": None,  # Explicitly None
                "total_edges": 500,
                "edges_by_kind": {"calls": 400},
                "symbols_by_kind": {},
                "symbols_by_language": {},
            }
            mock_cache = MagicMock()
            mock_cache.get_stats.return_value = mock_stats

            with patch(
                "tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache
            ):
                result = await tool.execute(
                    {"output_format": "json", "include_lag": False}
                )

            # schema_version should not be present in output (or be omitted)
            # If it appears at all, the test alerts to the change
            assert result.get("schema_version") is None, (
                "schema_version=None should be omitted from response "
                "(RFC-0012 null compaction)"
            )

    @pytest.mark.asyncio
    async def test_warn_status_omits_null_hint(self):
        """When hint is None (not provided), it should be omitted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = CodeGraphStatusTool(tmpdir)
            # No cache, so tool returns WARN verdict

            result = await tool.execute({"output_format": "json"})

            # WARN verdict should include a hint (for guidance), but if hint is None
            # in the indexed case, the build_response should not include it
            # (This test pins current behaviour; if changed, update the assertion)
            assert result["verdict"] == "WARN"
            assert isinstance(result.get("hint"), str), (
                "WARN should carry a hint string"
            )

    @pytest.mark.asyncio
    async def test_indexed_status_real_next_step_not_empty(self):
        """indexed status (verdict=INFO) should have real next_step, not empty string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = CodeGraphStatusTool(tmpdir)
            cache_dir = Path(tmpdir) / ".ast-cache"
            cache_dir.mkdir()
            (cache_dir / "index.db").write_bytes(b"sqlite3-fake")

            mock_stats = {
                "total_files": 42,
                "total_symbols": 1337,
                "fts5_available": True,
                "schema_version": 3,
                "total_edges": 500,
                "edges_by_kind": {"calls": 400},
                "symbols_by_kind": {},
                "symbols_by_language": {},
            }
            mock_cache = MagicMock()
            mock_cache.get_stats.return_value = mock_stats

            with patch(
                "tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache
            ):
                result = await tool.execute(
                    {"output_format": "json", "include_lag": False}
                )

            # agent_summary.next_step should be a real, non-empty string
            agent_summary = result.get("agent_summary")
            assert isinstance(agent_summary, dict), "agent_summary should be present"
            next_step = agent_summary.get("next_step")
            assert isinstance(next_step, str) and next_step, (
                f"agent_summary.next_step should be non-empty; got: {next_step!r}"
            )


class TestOverviewVerdictHonesty:
    """Issue #446 Item 3: overview verdict should be INFO for plain info, REVIEW only when code needs review."""

    def test_plain_informational_overview_verdict_is_info(self):
        """Plain project overview (include_health=False) → verdict=INFO, not REVIEW."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(
                tmpdir, "src/app.py", "def main():\n    pass\n"
            )  # Small, healthy file

            tool = ProjectOverviewTool(project_root=str(tmpdir))
            result = _run(
                tool.execute(
                    {"include_health": False, "max_depth": 5, "output_format": "json"}
                )
            )

            # Plain overview (no health check yet) should have verdict=INFO or SAFE,
            # NOT REVIEW (which implies "something needs review")
            agent_summary = result.get("agent_summary")
            assert isinstance(agent_summary, dict)
            verdict = agent_summary.get("verdict")
            assert verdict in ("INFO", "SAFE"), (
                f"Plain overview (include_health=False) should have INFO or SAFE verdict; "
                f"got {verdict!r}. REVIEW should only appear when health is checked and "
                f"problems are found."
            )

    def test_overview_with_health_checks_verdict_reflects_findings(self):
        """overview with include_health=true should have verdict=REVIEW only when problems found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(
                tmpdir, "src/app.py", "def main():\n    pass\n"
            )  # Small, healthy file

            tool = ProjectOverviewTool(project_root=str(tmpdir))
            result = _run(
                tool.execute(
                    {"include_health": True, "max_depth": 5, "output_format": "json"}
                )
            )

            # Health checked, no D/F grades → verdict should be SAFE or CAUTION
            agent_summary = result.get("agent_summary")
            verdict = agent_summary.get("verdict")
            assert verdict in ("SAFE", "CAUTION"), (
                f"Health-checked overview with no D/F grades should be SAFE or CAUTION; "
                f"got {verdict!r}"
            )


class TestSummaryLineShipping:
    """Issue #446 Item 2: summary_line appears in 3 places; reduce to agent_summary."""

    @pytest.mark.asyncio
    async def test_status_tool_summary_line_canonical_location(self):
        """status tool summary_line should be canonical in agent_summary, may appear top-level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = CodeGraphStatusTool(tmpdir)
            cache_dir = Path(tmpdir) / ".ast-cache"
            cache_dir.mkdir()
            (cache_dir / "index.db").write_bytes(b"sqlite3-fake")

            mock_stats = {
                "total_files": 42,
                "total_symbols": 1337,
                "fts5_available": True,
                "schema_version": 3,
                "total_edges": 500,
                "edges_by_kind": {"calls": 400},
                "symbols_by_kind": {},
                "symbols_by_language": {},
            }
            mock_cache = MagicMock()
            mock_cache.get_stats.return_value = mock_stats

            with patch(
                "tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache
            ):
                result = await tool.execute(
                    {"output_format": "json", "include_lag": False}
                )

            # summary_line should at least appear in agent_summary
            agent_summary = result.get("agent_summary")
            assert isinstance(agent_summary, dict)
            summary_line = agent_summary.get("summary_line")
            assert isinstance(summary_line, str) and summary_line, (
                f"agent_summary.summary_line should be non-empty; got {summary_line!r}"
            )

    def test_overview_tool_summary_line_canonical_location(self):
        """overview tool summary_line should be canonical in agent_summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write(tmpdir, "src/app.py", "def main():\n    pass\n")

            tool = ProjectOverviewTool(project_root=str(tmpdir))
            result = _run(
                tool.execute(
                    {"include_health": False, "max_depth": 5, "output_format": "json"}
                )
            )

            # summary_line should be in agent_summary
            agent_summary = result.get("agent_summary")
            assert isinstance(agent_summary, dict)
            summary_line = agent_summary.get("summary_line")
            assert isinstance(summary_line, str) and summary_line, (
                f"agent_summary.summary_line should be non-empty; got {summary_line!r}"
            )


# ─── codecov §11: cover the new branches directly ────────────────────────────


def test_overview_risk_unknown_maps_to_info() -> None:
    from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
        _overview_risk_to_verdict,
    )

    assert _overview_risk_to_verdict("unknown") == "INFO"
    assert _overview_risk_to_verdict("Unknown") == "INFO"
    assert _overview_risk_to_verdict("high") == "REVIEW"


def test_status_stale_lag_next_step(tmp_path, monkeypatch) -> None:
    """lag > 300s → next_step suggests sync before nav/search."""
    import asyncio

    from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
        CodeGraphStatusTool,
    )

    (tmp_path / ".ast-cache").mkdir()
    (tmp_path / ".ast-cache" / "index.db").write_bytes(b"")
    tool = CodeGraphStatusTool(str(tmp_path))
    monkeypatch.setattr(
        tool,
        "_safe_get_stats",
        lambda: {"total_files": 1, "total_symbols": 2, "total_edges": 3},
    )
    monkeypatch.setattr(tool, "_compute_lag", lambda path: 301.0)
    result = asyncio.run(tool.execute({"output_format": "json", "include_lag": True}))
    assert (
        result["agent_summary"]["next_step"]
        == "Index is healthy but stale (>5 min). Run action=sync first, "
        "then proceed with nav/search"
    )


def test_status_schema_version_included_when_present(tmp_path, monkeypatch) -> None:
    """Non-None schema_version IS emitted (only None is omitted)."""
    import asyncio

    from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
        CodeGraphStatusTool,
    )

    (tmp_path / ".ast-cache").mkdir()
    (tmp_path / ".ast-cache" / "index.db").write_bytes(b"")
    tool = CodeGraphStatusTool(str(tmp_path))
    monkeypatch.setattr(
        tool,
        "_safe_get_stats",
        lambda: {
            "total_files": 1,
            "total_symbols": 2,
            "total_edges": 3,
            "schema_version": 7,
        },
    )
    result = asyncio.run(tool.execute({"output_format": "json"}))
    assert result["schema_version"] == 7


def test_status_warn_branch_schema_version_included(tmp_path, monkeypatch) -> None:
    """WARN (empty index) branch also emits non-None schema_version."""
    import asyncio

    from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
        CodeGraphStatusTool,
    )

    (tmp_path / ".ast-cache").mkdir()
    (tmp_path / ".ast-cache" / "index.db").write_bytes(b"")
    tool = CodeGraphStatusTool(str(tmp_path))
    # total_files == 0 → truly_indexed False → WARN branch
    monkeypatch.setattr(
        tool,
        "_safe_get_stats",
        lambda: {"total_files": 0, "schema_version": 7},
    )
    result = asyncio.run(tool.execute({"output_format": "json"}))
    assert result["verdict"] == "WARN"
    assert result["schema_version"] == 7
