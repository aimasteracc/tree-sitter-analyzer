"""#1376：test_safe_to_edit_tool_jsts_projection 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _projection_conn
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


@pytest.mark.parametrize("test_path", ["checks/check_api.js", "checks/check_api.ts"])
def test_certified_exercising_tests_reject_custom_jsts_filename_pattern(
    test_path: str,
) -> None:
    inventory = frozenset({"src/util.js", test_path})

    assert not helpers._pytest_exercising_projection_complete(
        "src/util.js",
        [test_path],
        inventory,
        reverse_dependencies={},
    )


def test_jsts_projection_complete_for_relative_imports_only() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _jsts_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/main.ts", json.dumps([{"text": "import './util'"}])),
            ("src/util.ts", "[]"),
            ("tools/build.py", json.dumps([{"text": "import os"}])),
        ],
    )
    inventory = frozenset({"src/main.ts", "src/util.ts", "tools/build.py"})

    assert _jsts_import_projection_complete(conn, inventory) is True


def test_jsts_projection_rejects_unparseable_module_load() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _jsts_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute(
        "INSERT INTO ast_index VALUES ('src/main.ts', ?)",
        (json.dumps([{"text": "import(`./${name}`)"}]),),
    )

    assert _jsts_import_projection_complete(conn, frozenset({"src/main.ts"})) is False


def test_jsts_projection_rejects_commonjs_directory_entry_without_metadata() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _jsts_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/main.js", json.dumps([{"text": "require('./lib')"}])),
            ("src/lib/index.js", "[]"),
            ("src/lib/entry.js", "[]"),
        ],
    )
    inventory = frozenset({"src/main.js", "src/lib/index.js", "src/lib/entry.js"})

    assert _jsts_import_projection_complete(conn, inventory) is False


def test_jsts_projection_fails_closed_without_snapshot_table() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _jsts_import_projection_complete,
    )

    assert (
        _jsts_import_projection_complete(sqlite3.connect(":memory:"), frozenset())
        is False
    )


def test_certified_jsts_facts_use_language_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helpers, "_symbol_walk_projections_complete", lambda *_: True)
    monkeypatch.setattr(helpers, "_jsts_import_projection_complete", lambda *_: False)

    assert (
        helpers._certified_import_facts_available(
            "src/main.ts", conn=object(), inventory=frozenset({"src/main.ts"})
        )
        is False
    )


def test_query_only_jsts_specifier_is_not_resolved() -> None:
    assert (
        helpers._resolve_import_spec_from_inventory(
            "?worker", "src/main.ts", frozenset({"src/main.ts"})
        )
        is None
    )


def test_commonjs_projection_rejects_missing_extensionless_target() -> None:
    conn = _projection_conn([("src/main.js", [{"text": "require('./missing')"}])])

    assert (
        helpers._jsts_import_projection_complete(conn, frozenset({"src/main.js"}))
        is False
    )


def test_commonjs_projection_accepts_extensionless_file_target() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "require('./util')"}]),
            ("src/util.js", []),
        ]
    )
    inventory = frozenset({"src/main.js", "src/util.js"})

    assert helpers._jsts_import_projection_complete(conn, inventory) is True


def test_commonjs_projection_rejects_escaped_module_specifier() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": r'require("./uti\x6c.js")'}]),
            ("src/util.js", []),
        ]
    )

    assert not helpers._jsts_import_projection_complete(
        conn, frozenset({"src/main.js", "src/util.js"})
    )


def test_computed_commonjs_projection_accepts_literal_target() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "module['require']('./util.js')"}]),
            ("src/util.js", []),
        ]
    )
    inventory = frozenset({"src/main.js", "src/util.js"})

    assert helpers._jsts_import_projection_complete(conn, inventory) is True
    assert helpers._import_targets_from_text(
        "module['require']('./util.js')", "src/main.js", inventory
    ) == {"src/util.js"}


@pytest.mark.parametrize(
    "import_text",
    [
        "module?.require('./util.js')",
        "require?.('./util.js')",
        "module?.require?.('./util.js')",
    ],
)
def test_optional_commonjs_projection_accepts_literal_target(
    import_text: str,
) -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": import_text}]),
            ("src/util.js", []),
        ]
    )
    inventory = frozenset({"src/main.js", "src/util.js"})

    assert helpers._jsts_import_projection_complete(conn, inventory) is True
    assert helpers._import_targets_from_text(import_text, "src/main.js", inventory) == {
        "src/util.js"
    }


@pytest.mark.parametrize(
    ("import_extension", "source_extension"),
    [("mjs", "mts"), ("cjs", "cts")],
)
def test_typescript_projection_accepts_node_module_source_extension(
    import_extension: str, source_extension: str
) -> None:
    import_text = f"import './util.{import_extension}'"
    target = f"src/util.{source_extension}"
    conn = _projection_conn(
        [
            ("src/main.ts", [{"text": import_text}]),
            (target, []),
        ]
    )
    inventory = frozenset({"src/main.ts", target})

    assert helpers._jsts_import_projection_complete(conn, inventory) is True
    assert helpers._import_targets_from_text(import_text, "src/main.ts", inventory) == {
        target
    }


def test_jsts_projection_rejects_casefold_only_target() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "import './Util.js'"}]),
            ("src/util.js", []),
        ]
    )
    inventory = frozenset({"src/main.js", "src/util.js"})

    assert helpers._jsts_import_projection_complete(conn, inventory) is False


def test_jsts_projection_rejects_casefold_collision() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "import './util.js'"}]),
            ("src/util.js", []),
            ("src/Util.js", []),
        ]
    )
    inventory = frozenset({"src/main.js", "src/util.js", "src/Util.js"})

    assert helpers._jsts_import_projection_complete(conn, inventory) is False


def test_commonjs_loader_alias_projection_is_consumed() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "load('./util')"}]),
            ("src/util.js", []),
        ]
    )

    inventory = frozenset({"src/main.js", "src/util.js"})

    assert helpers._jsts_import_projection_complete(conn, inventory) is True
    assert helpers._import_targets_from_text(
        "load('./util')", "src/main.js", inventory
    ) == {"src/util.js"}


def test_commonjs_loader_alias_projection_rejects_directory_entry_ambiguity() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "load('./util')"}]),
            ("src/util/index.js", []),
        ]
    )

    assert (
        helpers._jsts_import_projection_complete(
            conn, frozenset({"src/main.js", "src/util/index.js"})
        )
        is False
    )
