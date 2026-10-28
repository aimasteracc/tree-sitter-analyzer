"""#1834：基类名有歧义（项目里同名类不止一个）时，继承关系不得被静默丢弃。

fastapi 的 ``HTTPBearer403(HTTPBearer)`` 经 ``fastapi.security`` 的包再导出导入基类，
``openapi/models.py`` 另有同名的无关 ``HTTPBase`` / ``HTTPBearer``。第二遍解析按名字
挑候选，两者得分相同，继承边停在 ``class:HTTPBearer`` 占位；子类索引忽略 Python 占位，
基类里继承的 ``self.make_not_authenticated_error()`` 不再被记为可能分派到覆写，覆写
答 ``complete, 0``。

* 导入绑定能证明基类时（经再导出），继承边解析到正确的类；
* 证明不了时，占位按类名记入子类关系（覆写仍是可能目标），MRO 记为未知。
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from tree_sitter_analyzer.cache import unresolved
from tree_sitter_analyzer.cache.reexported_base import imported_class_file
from tree_sitter_analyzer.call_graph_self_dispatch import SubclassIndex
from tree_sitter_analyzer.class_mro import ClassKey, Hierarchy
from tree_sitter_analyzer.graph.edge_store import EdgeKind

_SCHEMA = """
CREATE TABLE ast_index (file_path TEXT, language TEXT);
CREATE TABLE ast_imports (
    file_path TEXT, module_path TEXT, local_name TEXT, alias_of TEXT,
    is_relative INTEGER, is_star INTEGER
);
CREATE TABLE ast_symbol_rows (
    id INTEGER, name TEXT, kind TEXT, file_path TEXT, language TEXT, line INTEGER
);
CREATE TABLE edges (source_node_id TEXT, target_node_id TEXT, kind TEXT);
"""

_FILES = (
    "lib/__init__.py",
    "lib/security/__init__.py",
    "lib/security/http.py",
    "lib/openapi/__init__.py",
    "lib/openapi/models.py",
    "app/tut.py",
)


def _conn(imports: list[tuple[str, str, str, str, int, int]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, 'python')", [(f,) for f in _FILES]
    )
    conn.executemany("INSERT INTO ast_imports VALUES (?, ?, ?, ?, ?, ?)", imports)
    conn.executemany(
        "INSERT INTO ast_symbol_rows VALUES (?, ?, 'class', ?, 'python', ?)",
        [
            (1, "HTTPBearer", "lib/security/http.py", 6),
            (2, "HTTPBearer", "lib/openapi/models.py", 5),
        ],
    )
    return conn


_REEXPORT = ("lib/security/__init__.py", ".http", "HTTPBearer", "HTTPBearer", 1, 0)
_IMPORT = ("app/tut.py", "lib.security", "HTTPBearer", "", 0, 0)


def test_the_binding_follows_a_package_reexport_to_the_class() -> None:
    conn = _conn([_IMPORT, _REEXPORT])

    assert imported_class_file(conn, "app/tut.py", "HTTPBearer") == (
        "lib/security/http.py"
    )
    # 泛型下标不属于名字。
    assert imported_class_file(conn, "app/tut.py", "HTTPBearer[int]") == (
        "lib/security/http.py"
    )


def test_an_unprovable_binding_is_none() -> None:
    star = ("lib/security/__init__.py", ".http", "*", "", 1, 1)
    # 再导出缺失（星号导入）、模块不在索引中、属性引用、导入环：都证明不了。
    assert (
        imported_class_file(_conn([_IMPORT, star]), "app/tut.py", "HTTPBearer") is None
    )
    missing = ("app/tut.py", "nowhere", "HTTPBearer", "", 0, 0)
    assert imported_class_file(_conn([missing]), "app/tut.py", "HTTPBearer") is None
    assert imported_class_file(_conn([_IMPORT]), "app/tut.py", "sec.HTTPBearer") is None
    loop = ("lib/security/__init__.py", "lib.security", "HTTPBearer", "", 0, 0)
    assert (
        imported_class_file(_conn([_IMPORT, loop]), "app/tut.py", "HTTPBearer") is None
    )
    assert imported_class_file(sqlite3.connect(":memory:"), "a.py", "Name") is None


def _candidates() -> list[dict[str, object]]:
    return [
        {
            "node_id": f"{path}:HTTPBearer:{line}",
            "id": ident,
            "name": "HTTPBearer",
            "kind": "class",
            "file_path": path,
            "line": line,
            "language": "python",
        }
        for ident, path, line in (
            (2, "lib/openapi/models.py", 5),
            (1, "lib/security/http.py", 6),
        )
    ]


def _extends_row(kind: str = EdgeKind.EXTENDS.value) -> dict[str, object]:
    return {
        "file_path": "app/tut.py",
        "from_node_id": "app/tut.py:HTTPBearer403:4",
        "reference_name": "HTTPBearer",
        "reference_kind": kind,
    }


def test_an_ambiguous_base_binds_to_the_reexported_class() -> None:
    chosen = unresolved._choose_candidate(
        _conn([_IMPORT, _REEXPORT]), _extends_row(), _candidates()
    )

    assert chosen is not None and chosen["file_path"] == "lib/security/http.py"


def test_an_ambiguous_base_without_a_binding_stays_unresolved() -> None:
    star = ("lib/security/__init__.py", ".http", "*", "", 1, 1)
    conn = _conn([_IMPORT, star])

    assert unresolved._choose_candidate(conn, _extends_row(), _candidates()) is None
    # 只追踪基类引用：调用引用的排序不变。
    calls = _extends_row(EdgeKind.CALLS.value)
    assert (
        unresolved._choose_candidate(_conn([_IMPORT, _REEXPORT]), calls, _candidates())
        is None
    )


def _index(extends: list[tuple[str, str]], classes: bool = True) -> SubclassIndex:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE edges (source_node_id TEXT, target_node_id TEXT, kind TEXT)"
    )
    conn.executemany("INSERT INTO edges VALUES (?, ?, 'extends')", extends)
    if classes:
        conn.execute("CREATE TABLE ast_symbol_rows (name TEXT, kind TEXT)")
        conn.executemany(
            "INSERT INTO ast_symbol_rows VALUES (?, 'class')",
            [("HTTPBearer",), ("HTTPBearer",), ("HTTPBase",)],
        )
    return SubclassIndex(SimpleNamespace(get_conn=lambda: conn))


def test_an_ambiguous_python_placeholder_keeps_the_subclass_relation() -> None:
    index = _index(
        [
            ("app/tut.py:HTTPBearer403:4", "class:HTTPBearer"),
            ("app/alias.py:Aliased:3", "class:sec.HTTPBearer[int]"),
            ("app/ext.py:Model:1", "class:pydantic.BaseModel"),
            ("lib/security/http.py:HTTPBearer:6", "lib/security/http.py:HTTPBase:1"),
        ]
    )

    assert index.subclasses("HTTPBearer") == {"HTTPBearer403", "Aliased"}
    assert index.subclasses("HTTPBase") == {"HTTPBearer", "HTTPBearer403", "Aliased"}
    # 外部基类（项目里没有同名类）不产生子类关系。
    assert index.subclasses("BaseModel") == set()
    assert index.unique_class("HTTPBase") is True
    assert index.unique_class("HTTPBearer") is False


def test_an_unreadable_class_table_keeps_the_placeholder() -> None:
    index = _index([("app/tut.py:HTTPBearer403:4", "class:HTTPBearer")], classes=False)

    # 读不到类表时无法排除：按可能处理（失败即关闭）。
    assert index.subclasses("HTTPBearer") == {"HTTPBearer403"}
    assert index.unique_class("HTTPBearer") is False
    assert _index([("app/x.py:X:1", "class:1bad")]).subclasses("1bad") == set()


def test_an_ambiguous_base_named_like_a_stdlib_class_is_not_external() -> None:
    child = ClassKey("app.py", "Child")
    near = ClassKey("app.py", "Near")
    shadow = ClassKey("lib.py", "Protocol")
    # ``Protocol`` 是标准库类且没有 ``m``；可项目里也有名为 ``Protocol`` 的类——
    # 未解析的基类可能就是它，MRO 不能算完全已知。
    ambiguous = Hierarchy(
        parents={child: ["Protocol", near], near: [], shadow: []},
        methods={near: {"m": 1}, shadow: {"m": 2}},
    )
    assert ambiguous.nearest(child, "m") == (near, False)

    plain = Hierarchy(
        parents={child: ["Protocol", near], near: []}, methods={near: {"m": 1}}
    )
    assert plain.nearest(child, "m") == (near, True)
