"""导航测试的共享项目构造器，避免测试主页重复膨胀。"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool
from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

INDEXED_SOURCE = "def target():\n    return 'INDEXED_MARKER'\n"
MOVED_SOURCE = "# MOVED_MARKER\n\ndef target():\n    return 'CURRENT_MARKER'\n"


def reject_certified_capture(monkeypatch: Any) -> None:
    """把重建期间的认证快照捕获转换为立即失败。"""
    import tree_sitter_analyzer.index_snapshot as snapshot_owner

    monkeypatch.setattr(
        snapshot_owner,
        "certified_index_read",
        lambda _root: pytest.fail("重建期间不应捕获认证快照"),
    )


async def assert_sqlite_deadline_falls_back(
    tmp_path: Path, monkeypatch: Any, tool: Any, arguments: dict[str, Any]
) -> None:
    """SQLite 截止异常只能降级正文，不能中断公开查询。"""
    import tree_sitter_analyzer.index_snapshot as snapshot_owner

    @contextmanager
    def interrupted(_project_root):
        raise sqlite3.OperationalError("interrupted")
        yield None

    calls: list[tuple[dict[str, Any], Any, Any]] = []

    async def execute_bound(received, bound_cache, source_reader):
        calls.append((received, bound_cache, source_reader))
        return {"success": True, "fallback": True}

    monkeypatch.setattr(snapshot_owner, "certified_index_read", interrupted)
    monkeypatch.setattr(tool, "_execute_bound", execute_bound)

    result = await tool.execute(arguments)

    assert result == {"success": True, "fallback": True}
    assert calls == [(arguments, None, None)]


class FTSAndLinearCache:
    """同时提供 FTS 命中和线性后缀命中的最小缓存。"""

    fts5_available = True

    def get_conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE VIRTUAL TABLE ast_symbols_fts USING fts5(name, kind, docstring)"
        )
        conn.execute(
            "CREATE TABLE ast_symbol_rows"
            "(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, file_path TEXT,"
            " language TEXT, line INTEGER, end_line INTEGER)"
        )
        rows = (
            (1, "Service", "svc.py", 1, 10),
            (2, "UserService", "app.py", 5, 20),
        )
        for row_id, name, file_path, line, end_line in rows:
            conn.execute(
                "INSERT INTO ast_symbol_rows VALUES (?,?,?,?,?,?,?)",
                (row_id, name, "class", file_path, "python", line, end_line),
            )
            conn.execute(
                "INSERT INTO ast_symbols_fts(rowid,name,kind) VALUES (?,?,?)",
                (row_id, name, "class"),
            )
        conn.commit()
        return conn

    def _search_symbols_linear(self, query, language=None):
        return [
            {
                "name": name,
                "kind": "class",
                "file": file_path,
                "language": "python",
                "line": line,
                "end_line": end_line,
            }
            for name, file_path, line, end_line in (
                ("Service", "svc.py", 1, 10),
                ("UserService", "app.py", 5, 20),
            )
        ]


async def published_search(tmp_path: Path) -> tuple[Path, Any, Any]:
    source = tmp_path / "sample.py"
    source.write_text(INDEXED_SOURCE, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["success"] is True
    assert indexed["published"] is True
    facade = build_search_facade(str(tmp_path))
    return source, facade, facade.action_map["symbol"]


def assert_source_failure(
    result: dict[str, Any], operation: str, reason: str, freshness: str
) -> None:
    """精确断言认证失败不会泄漏任何缓存坐标。"""
    assert result == {
        "success": False,
        "error_code": "SOURCE_EVIDENCE_UNAVAILABLE",
        "error": f"{operation} source evidence unavailable: {reason}",
        "source_evidence": {
            "freshness": freshness,
            "snapshot_id": None,
            "source_generation": None,
            "reason": reason,
        },
        "verdict": "ERROR",
        "results": [],
    }


async def verify_certified_search_evidence(tmp_path: Path) -> None:
    """认证搜索必须发布非空 owner 身份和 fresh 证据。"""
    _source, facade, symbol = await published_search(tmp_path)
    result = await facade.execute({"action": "symbol", "query": "target"})
    evidence = result["source_evidence"]
    assert evidence == {
        "freshness": "fresh",
        "snapshot_id": evidence["snapshot_id"],
        "source_generation": evidence["source_generation"],
        "reason": None,
    }
    assert (evidence["snapshot_id"] is None, evidence["source_generation"] is None) == (
        False,
        False,
    )
    symbol._cache.close()


async def verify_uncertified_search_not_found(project: Path) -> None:
    """未认证空结果只能是 WARN，不能冒充 fresh NOT_FOUND。"""
    from tree_sitter_analyzer.mcp.tools.symbol_search_tool import (
        CodeGraphSymbolSearchTool,
    )

    tool = CodeGraphSymbolSearchTool(str(project))
    result = await tool.execute({"query": "missing"})
    assert (result["success"], result["verdict"], result["results"]) == (
        True,
        "WARN",
        [],
    )
    assert result["source_evidence"] == {
        "freshness": "unknown",
        "snapshot_id": None,
        "source_generation": None,
        "reason": "SOURCE_SCOPE_DESCRIPTOR_MISSING",
    }
    tool._cache.close()


async def verify_equal_length_search_rewrite_is_stale(tmp_path: Path) -> None:
    """内容摘要必须识别等长且恢复 mtime 的改写。"""
    source, facade, symbol = await published_search(tmp_path)
    before = source.stat()
    replacement = INDEXED_SOURCE.replace("target", "moved_").replace(
        "INDEXED", "CURRENT"
    )
    assert len(replacement) == len(INDEXED_SOURCE)
    source.write_text(replacement, encoding="utf-8")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    result = await facade.execute({"action": "symbol", "query": "target"})
    assert_source_failure(result, "Symbol search", "SOURCE_INDEX_MISMATCH", "stale")
    symbol._cache.close()


def assert_no_mixed_source(result: dict[str, Any]) -> None:
    """允许稳定失败或仅坐标成功，但禁止把当前正文贴到旧索引记录。"""
    if result.get("success") is False:
        assert result.get("results", []) == []
        return
    hits = [row for row in result["results"] if row["name"] == "target"]
    assert len(hits) == 1
    hit = hits[0]
    rendered = "\n".join(
        value
        for value in (
            str(hit.get("code", "")),
            str((hit.get("body") or {}).get("content", "")),
        )
        if value
    )
    assert "MOVED_MARKER" not in rendered
    assert "CURRENT_MARKER" not in rendered
    if rendered:
        assert "INDEXED_MARKER" in rendered


def build_indexed_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id):\n        return self._find_user(user_id)\n\n"
        "    def _find_user(self, user_id):\n        pass\n\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n    return svc.get_user(1)\n",
        encoding="utf-8",
    )
    (project / "utils.py").write_text(
        "def format_user(user):\n    return str(user)\n\n"
        "def validate_input(data):\n    return bool(data)\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    cache.close()
    return project


def build_many_relation_project(tmp_path: Path, relation: str) -> str:
    if relation == "callers":
        (tmp_path / "target.py").write_text(
            "def target():\n    return 42\n", encoding="utf-8"
        )
        for i in range(60):
            (tmp_path / f"caller_{i:03d}.py").write_text(
                f"from target import target\n\n\ndef fn_{i:03d}():\n    return target()\n",
                encoding="utf-8",
            )
    else:
        helpers = "\n".join(
            f"def helper_{i:03d}():\n    return {i}\n" for i in range(60)
        )
        (tmp_path / "helpers.py").write_text(helpers, encoding="utf-8")
        calls = "\n    ".join(f"helper_{i:03d}()" for i in range(60))
        imports = ", ".join(f"helper_{i:03d}" for i in range(60))
        (tmp_path / "hub.py").write_text(
            f"from helpers import {imports}\n\n\ndef hub():\n    {calls}\n",
            encoding="utf-8",
        )
    return str(tmp_path)
