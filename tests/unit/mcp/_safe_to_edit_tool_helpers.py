"""#1376：_safe_to_edit_tool_helpers 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.ast_cache import _AST_CACHE_EXTRACTOR_VERSION
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TARGET_FILE = "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"
SERVER_FILE = "tree_sitter_analyzer/mcp/server.py"


@pytest.fixture
def tool(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'sample'\n", encoding="utf-8"
    )

    target = tmp_path / TARGET_FILE
    target.parent.mkdir(parents=True)
    target.write_text(
        """
class SafeToEditTool:
    def execute(self):
        return "safe"
""".strip(),
        encoding="utf-8",
    )

    server = tmp_path / SERVER_FILE
    server.write_text(
        """
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool


def create_tool():
    return SafeToEditTool()
""".strip(),
        encoding="utf-8",
    )

    test_file = tmp_path / "tests/unit/mcp/test_safe_to_edit_tool.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_safe_to_edit_tool(): pass\n", encoding="utf-8")

    t = SafeToEditTool(str(tmp_path))
    t.set_project_path(str(tmp_path))
    return t


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# RFC-0022 P0.4: 认证轴的 index-snapshot 消费者；可移植验证门已开放。
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _close_index_snapshot_registry():
    yield
    from tree_sitter_analyzer.index_snapshot import REGISTRY

    REGISTRY.close_all()


def _indexed_project(tmp_path: Path) -> Path:
    """索引一个小项目，并返回解析后的根目录。"""
    from tree_sitter_analyzer.ast_cache import ASTCache

    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find_user(user_id)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        return {'id': user_id}\n",
        encoding="utf-8",
    )
    (project / "routes.py").write_text(
        "from app import UserService\n"
        "\n"
        "def dispatch(request):\n"
        "    return UserService().get_user(1)\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(project))
    cache.index_project(max_files=20)
    cache.close()
    return project.resolve()


def _publish_index_snapshot(project: Path, *, source_generation: str | None = None):
    """通过进程全局 registry 发布一个真实的 index.db 连接。发布能力携带真实捕获的 source generation 和完整 source scope，使消费者读取后的重新捕获能够通过；伪造 generation 会在退出时触发 SOURCE_GENERATION_MISMATCH。"""
    import sqlite3

    from tree_sitter_analyzer.index_snapshot import (
        REGISTRY,
        IndexSnapshot,
        _capture_sources_with_deadline,
    )
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    current = _capture_sources_with_deadline(str(project), scope, deadline=10**18)
    assert current.state == "exact", current.reason
    conn = sqlite3.connect(str(project / ".ast-cache" / "index.db"))
    conn.row_factory = sqlite3.Row
    snapshot = IndexSnapshot(
        None,
        current.fingerprint,
        "index-fp",
        source_generation or current.generation,
        "complete",
        None,
        str(project.resolve()),
        2,
        None,
        None,
        scope,
    )
    return REGISTRY.publish(snapshot, conn, 0)


def _snapshot_view_with_resolved_edge(caller: str, callee: str):
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "kind TEXT, file_path TEXT, callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute(
        "INSERT INTO edges VALUES ('calls', ?, '', ?)",
        (caller, callee),
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '[]')")
    return build_snapshot_file_dependency_view(conn, "app.py")


def _projection_conn(rows: list[tuple[str, object]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [(path, json.dumps(imports)) for path, imports in rows],
    )
    return conn


def _symbol_conn(raw_symbols: object) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index ("
        "file_path TEXT, symbols_json TEXT, extractor_version INTEGER)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('app.py', ?, ?)",
        (raw_symbols, _AST_CACHE_EXTRACTOR_VERSION),
    )
    return conn


def _reverse_dependency_conn(
    rows: list[tuple[object, object]],
) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path, imports_json)")
    conn.executemany("INSERT INTO ast_index VALUES (?, ?)", rows)
    return conn


class _BrokenConnection:
    def execute(self, _query: str) -> Any:
        raise sqlite3.DatabaseError("broken snapshot")


@pytest.fixture(params=[False, True])
def unreadable_index(tmp_path, monkeypatch, request):
    """准备损坏数据库，或模拟存在检查之后文件被删除。"""
    db_path = tmp_path / ".ast-cache" / "index.db"
    db_path.parent.mkdir()
    db_path.write_text("not-a-sqlite-database", encoding="utf-8")
    if request.param:
        connect = sqlite3.connect

        def remove_then_connect(*args, **kwargs):
            db_path.unlink()
            return connect(*args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", remove_then_connect)
    return tmp_path, db_path, request.param
