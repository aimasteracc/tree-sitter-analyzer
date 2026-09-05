"""Tests for tree_sitter_analyzer.mcp.tools.pulse_tool.

Covers: PulseTool, PulseBatchTool, GetProjectSchemaTool execute() paths,
error handling, and batch truncation.
Target coverage: ~80-88% of pulse_tool.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.pulse_tool import (
    GetProjectSchemaTool,
    PulseBatchTool,
    PulseTool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_cache(conn):
    """Return a MagicMock that satisfies the cache.get_conn() contract."""
    fake = MagicMock()
    fake.get_conn.return_value = conn
    return fake


def _seed_symbol(conn, name: str, file_path: str = "a.py", language: str = "python") -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, 1, 10),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# PulseTool
# ---------------------------------------------------------------------------

async def test_pulse_get_cache_raises_returns_error():
    """_get_cache() raises → execute() returns success=False with the error message."""
    tool = PulseTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("not set"))

    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "not set" in result["error"]


async def test_pulse_symbol_not_found(ast_cache_conn):
    """Empty DB → query_pulse returns None → success=False with descriptive message."""
    tool = PulseTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "fn" in result["error"]
    assert "a.py" in result["error"]


async def test_pulse_query_raises_returns_error(ast_cache_conn, monkeypatch):
    """query_pulse raises → execute() returns success=False with 'pulse query failed'."""
    tool = PulseTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.pulse_tool.query_pulse",
        MagicMock(side_effect=RuntimeError("db error")),
    )
    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "pulse query failed" in result["error"]


# ---------------------------------------------------------------------------
# PulseBatchTool
# ---------------------------------------------------------------------------

async def test_pulse_batch_truncates_targets(ast_cache_conn):
    """Targets exceeding max_symbols get truncated; warning appended."""
    tool = PulseBatchTool(project_root=None)
    fake_cache = _make_fake_cache(ast_cache_conn)
    tool._get_cache = MagicMock(return_value=fake_cache)

    targets = [{"file": f"f{i}.py", "symbol": f"fn{i}"} for i in range(5)]
    result = await tool.execute({"targets": targets, "max_symbols": 3})

    assert result["success"] is True
    warnings = [r for r in result["results"] if isinstance(r, dict) and "warning" in r]
    assert len(warnings) == 1
    assert "2 targets truncated" in warnings[0]["warning"]


async def test_pulse_batch_get_cache_raises():
    """_get_cache() raises → execute() returns success=False."""
    tool = PulseBatchTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("no root"))

    result = await tool.execute({"targets": [{"file": "a.py", "symbol": "fn"}]})
    assert result["success"] is False
    assert "no root" in result["error"]


# ---------------------------------------------------------------------------
# GetProjectSchemaTool
# ---------------------------------------------------------------------------

async def test_get_project_schema_get_cache_raises():
    """_get_cache() raises → execute() returns success=True with indexed=False."""
    tool = GetProjectSchemaTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("no root"))

    result = await tool.execute({})
    assert result["success"] is True
    assert result["result"]["indexed"] is False


async def test_get_project_schema_empty_db(ast_cache_conn):
    """Empty DB (0 symbols) → indexed=False."""
    tool = GetProjectSchemaTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute({})
    assert result["success"] is True
    assert result["result"]["indexed"] is False
