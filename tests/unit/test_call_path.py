"""Unit tests for call_path.py — CallPathFinder, CallChain, CallPathResult."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from tree_sitter_analyzer.call_path import (
    CallChain,
    CallPathFinder,
    CallPathResult,
    _files_in_chain,
)


def _make_cache_with_edges(tmp_path: Path, edges: list[dict]) -> MagicMock:
    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(cache_dir / "index.db")
    cache = MagicMock()
    cache._project_root = str(tmp_path)
    cache.project_root = str(tmp_path)
    cache.has_call_edges.return_value = True

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ast_call_edges ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  caller_name TEXT NOT NULL,"
        "  caller_file TEXT NOT NULL,"
        "  caller_line INTEGER NOT NULL,"
        "  callee_name TEXT NOT NULL,"
        "  callee_full TEXT NOT NULL DEFAULT '',"
        "  callee_line INTEGER NOT NULL DEFAULT 0,"
        "  callee_resolved_file TEXT NOT NULL DEFAULT '',"
        "  file_path TEXT NOT NULL,"
        "  language TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ce_callee_name ON ast_call_edges(callee_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ce_caller_name ON ast_call_edges(caller_name)"
    )
    for e in edges:
        conn.execute(
            "INSERT INTO ast_call_edges (caller_name, caller_file, caller_line,"
            "  callee_name, callee_full, callee_line, callee_resolved_file,"
            "  file_path, language)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                e["caller_name"],
                e["caller_file"],
                e.get("caller_line", 1),
                e["callee_name"],
                e.get("callee_full", e["callee_name"]),
                e.get("callee_line", 1),
                e.get("callee_resolved_file", ""),
                e["caller_file"],
                e.get("language", "python"),
            ),
        )
    conn.commit()
    cache._get_conn.return_value = conn
    return cache


# Simple linear chain: main -> foo -> bar
_LINEAR_EDGES = [
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "callee_name": "foo",
        "callee_file": "b.py",
        "callee_resolved_file": "b.py",
    },
    {
        "caller_name": "foo",
        "caller_file": "b.py",
        "callee_name": "bar",
        "callee_file": "c.py",
        "callee_resolved_file": "c.py",
    },
]

# Diamond: main -> foo, main -> baz, foo -> bar, baz -> bar
_DIAMOND_EDGES = [
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "callee_name": "foo",
        "callee_resolved_file": "b.py",
    },
    {
        "caller_name": "main",
        "caller_file": "a.py",
        "callee_name": "baz",
        "callee_resolved_file": "d.py",
    },
    {
        "caller_name": "foo",
        "caller_file": "b.py",
        "callee_name": "bar",
        "callee_resolved_file": "c.py",
    },
    {
        "caller_name": "baz",
        "caller_file": "d.py",
        "callee_name": "bar",
        "callee_resolved_file": "c.py",
    },
]


class TestCallChain:
    def test_empty_chain(self):
        chain = CallChain()
        d = chain.to_dict()
        assert d["total_hops"] == 0
        assert d["files_crossed"] == 0
        assert d["hops"] == []

    def test_chain_with_hops(self):
        chain = CallChain(
            hops=[
                {"caller": "main", "callee": "foo", "file": "a.py"},
                {"caller": "foo", "callee": "bar", "file": "b.py"},
            ],
            total_hops=2,
            files_crossed=2,
        )
        d = chain.to_dict()
        assert d["total_hops"] == 2
        assert d["files_crossed"] == 2
        assert len(d["hops"]) == 2


class TestCallPathResult:
    def test_no_paths(self):
        r = CallPathResult(source="main", target="missing")
        d = r.to_dict()
        assert d["path_count"] == 0
        assert d["truncated"] is False

    def test_with_paths(self):
        r = CallPathResult(
            source="main",
            target="bar",
            paths=[CallChain(hops=[{"a": 1}], total_hops=1, files_crossed=1)],
            data_source="sql",
        )
        d = r.to_dict()
        assert d["path_count"] == 1
        assert d["data_source"] == "sql"


class TestFilesInChain:
    def test_empty(self):
        assert _files_in_chain([]) == 0

    def test_single_file(self):
        assert _files_in_chain([{"file": "a.py"}, {"file": "a.py"}]) == 1

    def test_cross_file(self):
        assert _files_in_chain([{"file": "a.py"}, {"file": "b.py"}]) == 2


class TestCallPathFinderForward:
    def test_linear_forward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward")
        assert result.source == "main"
        assert result.target == "bar"
        assert len(result.paths) >= 1
        assert result.data_source == "sql"
        if result.paths:
            assert result.paths[0].total_hops == 2

    def test_no_path_forward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("bar", "main", direction="forward")
        assert len(result.paths) == 0

    def test_diamond_forward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _DIAMOND_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward")
        assert len(result.paths) >= 2

    def test_max_depth_respected(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward", max_depth=1)
        assert len(result.paths) == 0

    def test_max_paths_respected(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _DIAMOND_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="forward", max_paths=1)
        assert len(result.paths) <= 1


class TestCallPathFinderBackward:
    def test_linear_backward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="backward")
        assert len(result.paths) >= 1

    def test_no_path_backward(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("bar", "main", direction="backward")
        assert len(result.paths) == 0


class TestCallPathFinderBidirectional:
    def test_linear_bidirectional(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="bidirectional")
        assert len(result.paths) >= 1

    def test_diamond_bidirectional(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _DIAMOND_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "bar", direction="bidirectional")
        assert len(result.paths) >= 1

    def test_same_function(self, tmp_path):
        cache = _make_cache_with_edges(tmp_path, _LINEAR_EDGES)
        finder = CallPathFinder(str(tmp_path), cache=cache)
        result = finder.find_path("main", "main", direction="bidirectional")
        assert result.data_source == "sql"
        assert result.paths is not None


class TestCallPathFinderFallback:
    def test_no_cache_falls_back(self, tmp_path):
        cache = MagicMock()
        cache.has_call_edges.return_value = False
        cache.get_stats.return_value = {"total_files": 0}
        cache._project_root = str(tmp_path)
        cache.project_root = str(tmp_path)
        finder = CallPathFinder(str(tmp_path), cache=None)
        result = finder.find_path("nonexistent_a", "nonexistent_b")
        assert result.data_source in ("parse", "error", "unknown")


class TestCallPathFinderCLI:
    def test_cli_tool_instantiation(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

        tool = CodeGraphCallPathTool(str(tmp_path))
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_call_path"
        assert "source_function" in defn["inputSchema"]["properties"]
        assert "target_function" in defn["inputSchema"]["properties"]
        schema = tool.get_tool_schema()
        assert schema["required"] == ["source_function", "target_function"]

    def test_validate_missing_source(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

        tool = CodeGraphCallPathTool(str(tmp_path))
        try:
            tool.validate_arguments({"target_function": "bar"})
            assert False, "Should have raised"
        except ValueError as e:
            assert "source_function" in str(e)

    def test_validate_missing_target(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.call_path_tool import CodeGraphCallPathTool

        tool = CodeGraphCallPathTool(str(tmp_path))
        try:
            tool.validate_arguments({"source_function": "foo"})
            assert False, "Should have raised"
        except ValueError as e:
            assert "target_function" in str(e)
