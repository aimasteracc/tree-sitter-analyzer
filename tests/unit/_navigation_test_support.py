"""导航测试的共享项目构造器，避免测试主页重复膨胀。"""

import sqlite3
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool
from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

INDEXED_SOURCE = "def target():\n    return 'INDEXED_MARKER'\n"
MOVED_SOURCE = "# MOVED_MARKER\n\ndef target():\n    return 'CURRENT_MARKER'\n"


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
