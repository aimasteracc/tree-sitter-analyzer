"""#1376：test_safe_to_edit_tool_include_dependencies 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _projection_conn
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_dependency_view_includes_c_header() -> None:
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/main.c", json.dumps([{"text": '#include "util.h"', "line": 1}])),
            ("src/util.h", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.c")

    assert view.dependencies_of("src/main.c") == ["src/util.h"]


def test_snapshot_dependency_view_rejects_uncaptured_c_include_root() -> None:
    # 唯一的清单后缀不能证明编译器 -I 搜索顺序。
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "src/main.c",
                json.dumps([{"text": '#include "project/util.h"', "line": 1}]),
            ),
            ("include/project/util.h", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.c")

    assert view.dependencies_of("src/main.c") == []


def test_snapshot_dependency_view_rejects_ambiguous_c_include_root() -> None:
    # PR #1308 review: 存在多个类似 -I 的清单匹配时不能猜测。
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "src/main.c",
                json.dumps([{"text": '#include "project/util.h"', "line": 1}]),
            ),
            ("include-one/project/util.h", "[]"),
            ("include-two/project/util.h", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.c")

    assert view.dependencies_of("src/main.c") == []


def test_snapshot_dependency_view_rejects_absolute_quoted_include() -> None:
    # PR #1308 review: 绝对 include 文本不能证明快照认证的根目录。
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "src/main.c",
                json.dumps([{"text": '#include "/project/util.h"', "line": 1}]),
            ),
            ("project/util.h", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.c")

    assert view.dependencies_of("src/main.c") == []


def test_snapshot_dependency_view_finds_c_header_dependent() -> None:
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/test_util.cpp", json.dumps([{"text": '#include "util.h"'}])),
            ("src/util.h", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/util.h")

    assert view.dependents_of("src/util.h") == ["src/test_util.cpp"]


def test_snapshot_python_import_includes_source_root_package_initializer() -> None:
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
        snapshot_stale_edges,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/pkg/__init__.py", "[]"),
            ("src/pkg/app.py", "[]"),
            ("consumer.py", json.dumps([{"text": "import pkg.app"}])),
        ],
    )
    conn.execute(
        "INSERT INTO edges VALUES (1, 'imports', 'consumer.py', 'pkg.app', '')"
    )

    view = build_snapshot_file_dependency_view(conn, "src/pkg/__init__.py")

    assert view.dependents_of("src/pkg/__init__.py") == ["consumer.py"]
    assert snapshot_stale_edges(conn, "src/pkg/__init__.py") == [
        "imports:consumer.py->src/pkg/__init__.py#1"
    ]


def test_snapshot_causal_view_includes_resolved_edges_and_stale_ids() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
        snapshot_stale_edges,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]')",
        [("app.py",), ("routes.py",), ("util.py",), ("lazy.py",)],
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
        [
            (1, "calls", "routes.py", "handler", "app.py"),
            (2, "calls", "app.py", "normalize", "util.py"),
            (3, "calls", "other.py", "normalize", "util.py"),
            (4, "imports", "lazy.py", "app", ""),
            (5, "imports", "other.py", "missing", ""),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "app.py")

    assert view.dependents_of("app.py") == ["lazy.py", "routes.py"]
    assert view.dependencies_of("app.py") == ["util.py"]
    assert snapshot_stale_edges(conn, "app.py") == [
        "calls:routes.py->app.py#1",
        "calls:app.py->util.py#2",
        "imports:lazy.py->app.py#4",
    ]


def test_snapshot_stale_edges_includes_relative_member_import() -> None:
    import json
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        snapshot_stale_edges,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("pkg/app.py", "[]"),
            ("pkg/__init__.py", "[]"),
            (
                "pkg/routes.py",
                json.dumps([{"text": "from . import app", "line": 1}]),
            ),
        ],
    )
    conn.execute("INSERT INTO edges VALUES (1, 'imports', 'pkg/routes.py', '.', '')")

    assert snapshot_stale_edges(conn, "pkg/app.py") == [
        "imports:pkg/routes.py->pkg/app.py#1"
    ]


def test_snapshot_stale_edges_includes_explicit_relative_extension() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/main.js", json.dumps([{"text": "import './util.js'"}])),
            ("src/util.js", "[]"),
        ],
    )
    conn.execute(
        "INSERT INTO edges VALUES (1, 'imports', 'src/main.js', './util.js', '')"
    )

    assert helpers.snapshot_stale_edges(conn, "src/util.js") == [
        "imports:src/main.js->src/util.js#1"
    ]


@pytest.mark.parametrize(
    ("source_suffix", "emitted_suffix"),
    [
        (".mts", ".mjs"),
        (".d.mts", ".mjs"),
        (".cts", ".cjs"),
        (".d.cts", ".cjs"),
        (".tsx", ".jsx"),
        (".d.ts", ".jsx"),
    ],
)
def test_snapshot_stale_edges_include_typescript_emitted_suffixes(
    source_suffix: str, emitted_suffix: str
) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    target = f"src/util{source_suffix}"
    import_text = f"import './util{emitted_suffix}'"
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [("src/main.mts", json.dumps([{"text": import_text}])), (target, "[]")],
    )
    conn.execute(
        "INSERT INTO edges VALUES (1, 'imports', 'src/main.mts', ?, '')",
        (f"./util{emitted_suffix}",),
    )

    assert helpers.snapshot_stale_edges(conn, target) == [
        f"imports:src/main.mts->{target}#1"
    ]


def test_cpp_same_directory_header_unit_resolves_and_certifies() -> None:
    inventory = frozenset({"src/main.cpp", "src/util.h"})
    conn = _projection_conn(
        [("src/main.cpp", [{"text": 'import "util.h";'}]), ("src/util.h", [])]
    )

    assert helpers._import_targets_from_text(
        'import "util.h";', "src/main.cpp", inventory
    ) == {"src/util.h"}
    assert helpers._quoted_include_projection_complete(conn, "src/util.h", inventory)


def test_cpp_header_unit_without_captured_search_root_does_not_resolve() -> None:
    inventory = frozenset({"src/main.cpp", "include/util.h"})

    assert (
        helpers._import_targets_from_text('import "util.h";', "src/main.cpp", inventory)
        == set()
    )


def test_cpp_ambiguous_header_unit_does_not_guess_target() -> None:
    inventory = frozenset({"src/main.cpp", "include-one/util.h", "include-two/util.h"})

    assert (
        helpers._import_targets_from_text('import "util.h";', "src/main.cpp", inventory)
        == set()
    )


def test_cpp_header_unit_without_captured_include_root_fails_closed() -> None:
    conn = _projection_conn(
        [
            ("src/main.cpp", [{"text": 'import "util.h";'}]),
            ("include/util.h", []),
        ]
    )
    inventory = frozenset({"src/main.cpp", "include/util.h"})

    assert not helpers._quoted_include_projection_complete(
        conn, "include/util.h", inventory
    )


def test_c_target_rejects_ambiguous_outgoing_quoted_include() -> None:
    conn = _projection_conn(
        [
            ("src/main.c", [{"text": '#include "util.h"'}]),
            ("a/util.h", []),
            ("b/util.h", []),
        ]
    )
    inventory = frozenset({"src/main.c", "a/util.h", "b/util.h"})

    assert not helpers._quoted_include_projection_complete(
        conn, "src/main.c", inventory
    )
