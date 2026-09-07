"""#1376：test_safe_to_edit_tool_python_projection 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _projection_conn
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_python_relative_import_cannot_escape_top_package() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _resolve_import_spec_from_inventory,
    )

    inventory = frozenset({"app.py", "pkg/routes.py"})

    assert (
        _resolve_import_spec_from_inventory("..app", "pkg/routes.py", inventory) is None
    )


def test_snapshot_stale_edges_excludes_python_basename_collision() -> None:
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
        "INSERT INTO ast_index VALUES (?, '[]')",
        [("pkg/app.py",), ("other/app.py",), ("routes.py",)],
    )
    conn.execute("INSERT INTO edges VALUES (1, 'imports', 'routes.py', 'app', '')")

    assert snapshot_stale_edges(conn, "pkg/app.py") == []


def test_python_projection_complete_ignores_static_and_non_python_imports() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _python_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "app.py",
                json.dumps(
                    [
                        {"text": "import os"},
                        {"text": "importlib.import_module('pkg.util')"},
                    ]
                ),
            ),
            ("src/main.ts", json.dumps([{"text": "import '@app/util'"}])),
        ],
    )

    assert _python_import_projection_complete(
        conn, frozenset({"app.py", "src/main.ts"})
    )


def test_python_projection_rejects_relative_dynamic_import() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _python_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute(
        "INSERT INTO ast_index VALUES ('pkg/app.py', ?)",
        (json.dumps([{"text": "importlib.import_module('.util', __package__)"}]),),
    )

    assert not _python_import_projection_complete(conn, frozenset({"pkg/app.py"}))


def test_python_projection_rejects_ambiguous_absolute_import() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _python_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("routes.py", json.dumps([{"text": "import pkg.app"}])),
            ("src/pkg/app.py", "[]"),
            ("vendor/pkg/app.py", "[]"),
        ],
    )

    assert not _python_import_projection_complete(
        conn,
        frozenset({"routes.py", "src/pkg/app.py", "vendor/pkg/app.py"}),
    )


def test_python_projection_accepts_aliased_literal_dynamic_import() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _python_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "app.py",
                json.dumps(
                    [
                        {"text": "from importlib import import_module as load"},
                        {"text": "load('pkg.util')"},
                    ]
                ),
            ),
            ("pkg/util.py", "[]"),
        ],
    )

    assert _python_import_projection_complete(
        conn, frozenset({"app.py", "pkg/util.py"})
    )


def test_python_projection_accepts_assignment_aliased_dynamic_import() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _python_import_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "app.py",
                json.dumps(
                    [
                        {"text": "import importlib"},
                        {"text": "loader = importlib.import_module"},
                        {"text": "loader('pkg.util')"},
                    ]
                ),
            ),
            ("pkg/util.py", "[]"),
        ],
    )

    assert _python_import_projection_complete(
        conn, frozenset({"app.py", "pkg/util.py"})
    )


def test_python_relative_root_helper_and_dynamic_relative_loader_fail_closed() -> None:
    inventory = frozenset({"src/__init__.py", "src/pkg/__init__.py", "src/pkg/app.py"})
    assert not helpers._python_relative_package_root_ambiguous(
        "pkg.util", "src/pkg/app.py", inventory
    )
    assert helpers._python_relative_package_root_ambiguous(
        ".util", "src/pkg/app.py", inventory
    )

    conn = _projection_conn(
        [
            ("src/pkg/app.py", [{"text": "importlib.import_module('.util')"}]),
            ("src/pkg/util.py", []),
        ]
    )
    assert not helpers._python_import_projection_complete(
        conn, frozenset({"src/pkg/app.py", "src/pkg/util.py"})
    )


def test_python_projection_rejects_relative_import_across_package_boundaries() -> None:
    conn = _projection_conn(
        [
            ("src/pkg/app.py", [{"text": "from .missing import value"}]),
            ("src/pkg/__init__.py", []),
            ("src/__init__.py", []),
        ]
    )
    inventory = frozenset({"src/pkg/app.py", "src/pkg/__init__.py", "src/__init__.py"})

    assert not helpers._python_import_projection_complete(conn, inventory)


def test_python_from_import_rejects_attribute_submodule_ambiguity() -> None:
    conn = _projection_conn(
        [
            ("consumer.py", [{"text": "from pkg import value"}]),
            ("pkg/__init__.py", []),
            ("pkg/value.py", []),
        ]
    )
    inventory = frozenset({"consumer.py", "pkg/__init__.py", "pkg/value.py"})

    assert helpers._python_import_projection_complete(conn, inventory) is False


def test_python_projection_rejects_invalid_loader_statement() -> None:
    conn = _projection_conn([("app.py", [{"text": "if ("}])])

    assert (
        helpers._python_import_projection_complete(conn, frozenset({"app.py"})) is False
    )


def test_python_projection_rejects_missing_snapshot_table() -> None:
    assert (
        helpers._python_import_projection_complete(
            sqlite3.connect(":memory:"), frozenset()
        )
        is False
    )


def test_python_future_import_never_resolves_to_project_file() -> None:
    inventory = frozenset({"app.py", "__future__.py"})

    assert (
        helpers._import_targets_from_text(
            "from __future__ import annotations", "app.py", inventory
        )
        == set()
    )


def test_python_future_import_has_no_causal_module_name() -> None:
    assert helpers._import_module_name("from __future__ import annotations") is None


def test_python_future_import_has_no_static_dependency_spec() -> None:
    assert (
        helpers._python_static_import_specs("from __future__ import annotations") == ()
    )


def test_python_builtins_import_never_resolves_to_project_file() -> None:
    inventory = frozenset({"app.py", "builtins.py"})

    assert (
        helpers._import_targets_from_text("import builtins", "app.py", inventory)
        == set()
    )


def test_python_builtins_loader_resolves_literal_target() -> None:
    inventory = frozenset({"app.py", "pkg/util.py"})

    assert helpers._import_targets_from_text(
        "builtins.__import__('pkg.util')", "app.py", inventory
    ) == {"pkg/util.py"}


def test_python_projection_rejects_invalid_static_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _projection_conn([("app.py", [{"text": "if ("}])])
    monkeypatch.setattr(
        helpers,
        "_python_dynamic_loader_names_from_projection",
        lambda _: frozenset({"__import__"}),
    )

    assert (
        helpers._python_import_projection_complete(conn, frozenset({"app.py"})) is False
    )


def test_python_projection_rejects_ambiguous_dynamic_import() -> None:
    conn = _projection_conn(
        [
            ("app.py", [{"text": "__import__('pkg.util')"}]),
            ("src/pkg/util.py", []),
            ("vendor/pkg/util.py", []),
        ]
    )
    inventory = frozenset({"app.py", "src/pkg/util.py", "vendor/pkg/util.py"})

    assert helpers._python_import_projection_complete(conn, inventory) is False


@pytest.mark.parametrize(
    "call",
    [
        "__import__('pkg', fromlist=['util'])",
        "__import__('pkg.util', globals(), locals(), (), 1)",
    ],
)
def test_python_projection_rejects_extended_loader_call_semantics(call: str) -> None:
    conn = _projection_conn(
        [
            ("app.py", [{"text": call}]),
            ("pkg/__init__.py", []),
            ("pkg/util.py", []),
        ]
    )
    inventory = frozenset({"app.py", "pkg/__init__.py", "pkg/util.py"})

    assert helpers._python_import_projection_complete(conn, inventory) is False


def test_python_projection_rejects_ambiguous_relative_package_root() -> None:
    conn = _projection_conn(
        [
            ("src/pkg/main.py", [{"text": "from . import util"}]),
            ("src/pkg/util.py", []),
            ("src/pkg/__init__.py", []),
            ("src/__init__.py", []),
        ]
    )
    inventory = frozenset(
        {
            "src/pkg/main.py",
            "src/pkg/util.py",
            "src/pkg/__init__.py",
            "src/__init__.py",
        }
    )

    assert helpers._python_import_projection_complete(conn, inventory) is False


@pytest.mark.parametrize(
    "inventory",
    [
        frozenset({"consumer.py", "pkg/util.py"}),
        frozenset({"consumer.py", "Pkg/util.py", "pkg/util.py"}),
    ],
)
def test_python_projection_rejects_casefold_only_or_colliding_target(
    inventory: frozenset[str],
) -> None:
    conn = _projection_conn(
        [
            ("consumer.py", [{"text": "import Pkg.util"}]),
            *((path, []) for path in inventory if path != "consumer.py"),
        ]
    )

    assert helpers._python_import_projection_complete(conn, inventory) is False


def test_python_dynamic_projection_rejects_casefold_only_target() -> None:
    conn = _projection_conn(
        [
            ("consumer.py", [{"text": "__import__('Pkg.util')"}]),
            ("pkg/util.py", []),
        ]
    )
    inventory = frozenset({"consumer.py", "pkg/util.py"})

    assert helpers._python_import_projection_complete(conn, inventory) is False


def test_python_projection_rejects_root_and_source_root_ambiguity() -> None:
    conn = _projection_conn(
        [
            ("app.py", [{"text": "import pkg.util"}]),
            ("pkg/util.py", []),
            ("src/pkg/util.py", []),
        ]
    )
    inventory = frozenset({"app.py", "pkg/util.py", "src/pkg/util.py"})

    assert helpers._python_import_projection_complete(conn, inventory) is False


def test_python_projection_rejects_suffix_only_source_root_guess() -> None:
    conn = _projection_conn(
        [("app.py", [{"text": "import acme"}]), ("vendor/acme.py", [])]
    )

    assert not helpers._python_import_projection_complete(
        conn, frozenset({"app.py", "vendor/acme.py"})
    )


def test_python_projection_rejects_dynamic_suffix_only_source_root_guess() -> None:
    conn = _projection_conn(
        [
            ("app.py", [{"text": "importlib.import_module('acme')"}]),
            ("vendor/acme.py", []),
        ]
    )

    assert not helpers._python_import_projection_complete(
        conn, frozenset({"app.py", "vendor/acme.py"})
    )
