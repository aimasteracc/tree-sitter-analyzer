"""Tests for tree_sitter_analyzer.mcp.tools.tql_tool.

Covers: _cap_echo boundary values, TqlSchemaTool.execute(), TqlExecuteTool
  syntax-error path, empty selector path, _detect_index_state verdicts.
Target coverage: ~45-55% of tql_tool.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.tql_tool import (
    TqlExecuteTool,
    TqlSchemaTool,
    _cap_echo,
)

# ---------------------------------------------------------------------------
# _cap_echo
# ---------------------------------------------------------------------------

def test_cap_echo_short():
    """Selector at or below 200 chars passes through unchanged."""
    short = "x" * 200
    assert _cap_echo(short) == short


def test_cap_echo_long():
    """Selector above 200 chars is truncated with length suffix."""
    long_sel = "x" * 201
    result = _cap_echo(long_sel)
    assert result.startswith("x" * 200)
    assert "201" in result
    assert "chars total" in result


def test_cap_echo_exact_boundary():
    """Exactly 200 chars → returned unchanged."""
    exact = "a" * 200
    assert _cap_echo(exact) == exact


def test_cap_echo_one_over_boundary():
    """201 chars → truncated."""
    sel = "a" * 201
    result = _cap_echo(sel)
    assert result == "a" * 200 + "... (201 chars total)"
    assert result != sel


# ---------------------------------------------------------------------------
# TqlSchemaTool
# ---------------------------------------------------------------------------

async def test_tql_schema_execute_success():
    """TqlSchemaTool returns success=True with schema doc containing key terms."""
    tool = TqlSchemaTool()
    result = await tool.execute({})
    assert result["success"] is True
    assert ":hotspot" in result["schema"]
    assert "{n,m}" in result["schema"]


# ---------------------------------------------------------------------------
# TqlExecuteTool — validation paths
# ---------------------------------------------------------------------------

async def test_tql_execute_empty_selector():
    """Empty selector string → success=False with 'selector is required'."""
    tool = TqlExecuteTool(project_root=None)
    result = await tool.execute({"selector": ""})
    assert result["success"] is False
    assert "selector is required" in result["error"]


async def test_tql_execute_syntax_error():
    """Malformed selector → success=False before _get_cache is called."""
    tool = TqlExecuteTool(project_root=None)
    mock_cache = MagicMock()
    tool._get_cache = mock_cache

    result = await tool.execute({"selector": ":::"})
    assert result["success"] is False
    assert "TQL syntax error" in result["error"]
    # _get_cache must NOT have been called (parse fails before cache access)
    assert mock_cache.call_count == 0


# ---------------------------------------------------------------------------
# TqlExecuteTool._detect_index_state
# ---------------------------------------------------------------------------

def test_detect_index_state_empty():
    """Cache returns total_files=0 → state='empty', count=0."""
    tool = TqlExecuteTool(project_root=None)
    fake_cache = MagicMock()
    fake_cache.get_stats.return_value = {"total_files": 0}
    state, n = tool._detect_index_state(fake_cache)
    assert state == "empty"
    assert n == 0


def test_detect_index_state_missing():
    """Cache.get_stats() raises → state='missing', count=0."""
    tool = TqlExecuteTool(project_root=None)
    fake_cache = MagicMock()
    fake_cache.get_stats.side_effect = RuntimeError("no cache")
    state, n = tool._detect_index_state(fake_cache)
    assert state == "missing"
    assert n == 0


def test_detect_index_state_ready():
    """Cache returns total_files=42 → state='ready', count=42."""
    tool = TqlExecuteTool(project_root=None)
    fake_cache = MagicMock()
    fake_cache.get_stats.return_value = {"total_files": 42}
    state, n = tool._detect_index_state(fake_cache)
    assert state == "ready"
    assert n == 42
