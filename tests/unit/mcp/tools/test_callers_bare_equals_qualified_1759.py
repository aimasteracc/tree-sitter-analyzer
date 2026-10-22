"""#1759：裸名与限定名对同一个方法给出同样的答案；声明文件守卫对两者都生效。

dogfood 第 11 轮：限定名 ``Class.method`` 按限定名查声明文件，查不到，于是完全跳过
RFC-0028 §1.2 守卫；裸名则受守卫约束。两者不一致（fastapi 37 vs 10 / 80 complete），
而限定名一侧会出错：``self.handlers[e](data)`` 经 ``getattr(self, "handle_" + e)`` 构造
的字典到达 ``Handler.handle_open``，不点名它，限定名却答 ``complete, 0``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_dispatch import could_name_target
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_HANDLER = (
    "EVENTS = ('open', 'close')\n"
    "\n"
    "\n"
    "class Handler:\n"
    "    def __init__(self):\n"
    "        self.handlers = {e: getattr(self, 'handle_' + e) for e in EVENTS}\n"
    "\n"
    "    def dispatch(self, event, data):\n"
    "        return self.handlers[event](data)\n"
    "\n"
    "    def handle_open(self, data):\n"
    "        return data\n"
    "\n"
    "    def plain(self):\n"
    "        return 1\n"
)
_COPYABLE = (
    "class Copyable:\n"
    "    def copy(self):\n"
    "        return type(self)()\n"
    "\n"
    "    def size(self):\n"
    "        return 2\n"
    "\n"
    "\n"
    "class Other:\n"
    "    def size(self):\n"
    "        return 3\n"
)
_USER = (
    "from .handler import Handler\n"
    "from .copyable import Copyable\n"
    "\n"
    "\n"
    "def run():\n"
    "    return Handler().plain() + Copyable().size()\n"
)


async def _index(root: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    files = {
        "pkg/__init__.py": "",
        "pkg/handler.py": _HANDLER,
        "pkg/copyable.py": _COPYABLE,
        "pkg/user.py": _USER,
    }
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _ask(root: str, name: str, file_path: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


def _shape(result: dict) -> tuple:
    return (
        result["completeness"],
        tuple(result.get("completeness_reasons") or ()),
        tuple(sorted((c["file"], c["name"]) for c in result.get("callers") or [])),
        tuple(
            sorted((s["file"], s["line"]) for s in result.get("unresolved_sites") or [])
        ),
    )


@pytest.mark.asyncio
async def test_qualified_method_is_gated_by_computed_dispatch_in_its_file(
    tmp_path,
) -> None:
    root = await _index(tmp_path)

    result = await _ask(root, "Handler.handle_open", "pkg/handler.py")

    # Reached through `self.handlers[event](data)`, never by name.
    assert result["completeness"] != "complete"
    assert "UNRESOLVED_IN_DECLARING_FILE" in result["completeness_reasons"]
    assert [(s["line"], s["callee"]) for s in result["unresolved_sites"]] == [
        (9, "self.handlers[event]")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("qualified", "file_path"),
    [
        ("Handler.handle_open", "pkg/handler.py"),
        ("Handler.plain", "pkg/handler.py"),
        ("Handler.dispatch", "pkg/handler.py"),
        ("Copyable.copy", "pkg/copyable.py"),
    ],
)
async def test_bare_and_qualified_get_the_same_answer_for_one_method(
    tmp_path, qualified: str, file_path: str
) -> None:
    root = await _index(tmp_path)

    asked_qualified = await _ask(root, qualified, file_path)
    asked_bare = await _ask(root, qualified.rsplit(".", 1)[1], file_path)

    assert _shape(asked_bare) == _shape(asked_qualified)


@pytest.mark.asyncio
async def test_type_construction_does_not_guard_other_methods(tmp_path) -> None:
    root = await _index(tmp_path)

    # copyable.py's only unresolved call is `type(self)()`: it cannot reach `copy`.
    result = await _ask(root, "Copyable.copy", "pkg/copyable.py")

    assert result["completeness"] == "complete"
    assert all(
        s["callee"] != "type(self)" for s in result.get("unresolved_sites") or []
    )


@pytest.mark.asyncio
async def test_a_bare_name_with_several_definitions_keeps_the_union(tmp_path) -> None:
    root = await _index(tmp_path)

    # `size` is defined by two classes in copyable.py: not one method, so it is not
    # rewritten to either; the answer covers both and is no more confident than either.
    bare = await _ask(root, "size", "pkg/copyable.py")
    one = await _ask(root, "Copyable.size", "pkg/copyable.py")

    assert bare["function"] == "size"
    assert {c["name"] for c in bare.get("callers") or []} >= {
        c["name"] for c in one.get("callers") or []
    }
    if one["completeness"] != "complete":
        assert bare["completeness"] != "complete"


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("copy", False),
        ("size", False),
        ("__init__", True),
        ("__new__", True),
        ("__call__", True),
    ],
)
def test_type_construction_reaches_only_constructor_methods(
    target: str, expected: bool
) -> None:
    assert could_name_target("type(self)", target) is expected
    assert could_name_target("type(obj.inner)", target) is expected


_ROUTES = (
    "from extlib.wrappers import wrap_app\n"
    "import anyio\n"
    "from .local import make\n"
    "\n"
    "\n"
    "class Route:\n"
    "    async def handle(self, app, scope):\n"
    "        await wrap_app(app, scope)(scope)\n"
    "        anyio.stream[bytes](0)\n"
    "        return self.target()\n"
    "\n"
    "    def target(self):\n"
    "        return 1\n"
)
_ROUTES_PROJECT_PRODUCER = _ROUTES.replace(
    "        anyio.stream[bytes](0)\n", "        make(self)(scope)\n"
)
_ROUTES_DYNAMIC = _ROUTES.replace(
    "wrap_app(app, scope)(scope)", "wrap_app(getattr(self, scope))(scope)"
)
_ROUTES_REBOUND = _ROUTES + "\n\nwrap_app = None\n"


async def _index_routes(root: Path, routes: str) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    files = {
        "app/__init__.py": "",
        "app/local.py": "def make(obj):\n    return obj.target\n",
        "app/routes.py": routes,
        "app/user.py": "from .routes import Route\n\n\ndef go():\n    return Route().target()\n",
    }
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


@pytest.mark.asyncio
async def test_callables_produced_by_external_functions_do_not_guard(tmp_path) -> None:
    root = await _index_routes(tmp_path, _ROUTES)

    for name in ("Route.target", "target"):
        result = await _ask(root, name, "app/routes.py")
        excluded = {
            (s["line"], s.get("reason_code"))
            for s in result.get("excluded_sites") or []
        }
        assert (8, "produced_by_external_call") in excluded
        assert (9, "produced_by_external_call") in excluded
        assert "UNRESOLVED_IN_DECLARING_FILE" not in (
            result.get("completeness_reasons") or []
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("routes", "line"),
    [(_ROUTES_PROJECT_PRODUCER, 9), (_ROUTES_DYNAMIC, 8), (_ROUTES_REBOUND, 8)],
    ids=["project_producer", "dynamic_name_in_arguments", "rebound_import"],
)
async def test_producers_that_may_hand_back_a_project_method_keep_the_guard(
    tmp_path, routes: str, line: int
) -> None:
    root = await _index_routes(tmp_path, routes)

    for name in ("Route.target", "target"):
        result = await _ask(root, name, "app/routes.py")
        assert line in {s["line"] for s in result.get("unresolved_sites") or []}
        assert result["completeness"] != "complete"


_TABLE = (
    "_MATCH = {\n"
    "    ('a', 1): lambda f, s: (f, s),\n"
    "    ('b', 2): lambda f, s: s,\n"
    "}\n"
    "\n"
    "\n"
    "def apply(kind, f, s):\n"
    "    return _MATCH[kind](f, s)\n"
    "\n"
    "\n"
    "class Builder:\n"
    "    def build(self):\n"
    "        return 1\n"
)
_TABLE_MUTATED = _TABLE + "\n\n_MATCH[('c', 3)] = Builder.build\n"
_TABLE_COMPUTED = _TABLE.replace(
    "_MATCH = {\n    ('a', 1): lambda f, s: (f, s),\n    ('b', 2): lambda f, s: s,\n}\n",
    "_MATCH = {k: getattr(Builder, k) for k in ('build',)}\n",
)


async def _index_table(root: Path, text: str) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, body in {
        "lib/__init__.py": "",
        "lib/table.py": text,
        "lib/use.py": "from .table import Builder\n\n\ndef go():\n    return Builder().build()\n",
    }.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


@pytest.mark.asyncio
async def test_dispatch_through_a_module_level_literal_table_does_not_guard(
    tmp_path,
) -> None:
    root = await _index_table(tmp_path, _TABLE)

    for name in ("Builder.build", "build"):
        result = await _ask(root, name, "lib/table.py")
        excluded = {
            (s["line"], s.get("reason_code"))
            for s in result.get("excluded_sites") or []
        }
        assert (8, "literal_container_dispatch") in excluded
        assert "UNRESOLVED_IN_DECLARING_FILE" not in (
            result.get("completeness_reasons") or []
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", [_TABLE_MUTATED, _TABLE_COMPUTED], ids=["mutated", "computed"]
)
async def test_tables_that_can_hold_the_target_keep_the_guard(
    tmp_path, text: str
) -> None:
    root = await _index_table(tmp_path, text)

    for name in ("Builder.build", "build"):
        result = await _ask(root, name, "lib/table.py")
        assert result["completeness"] != "complete"


_APP = (
    "class App:\n"
    "    def openapi(self):\n"
    "        return {}\n"
    "\n"
    "    def setup(self):\n"
    "        def openapi(req):\n"
    "            return self.openapi()\n"
    "\n"
    "        return openapi\n"
)
_APP_USER = "from .app import App\n\n\ndef schema():\n    app = App()\n    return app.openapi()\n"


@pytest.mark.asyncio
async def test_bare_name_covers_a_method_beside_a_same_named_function(tmp_path) -> None:
    # fastapi/applications.py: the method `FastAPI.openapi` and a nested `openapi`
    # closure share a name; the bare query used to resolve to the closure only.
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in {
        "web/__init__.py": "",
        "web/app.py": _APP,
        "web/user.py": _APP_USER,
    }.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True

    qualified = await _ask(str(tmp_path), "App.openapi", "web/app.py")
    bare = await _ask(str(tmp_path), "openapi", "web/app.py")

    qualified_callers = {(c["file"], c["name"]) for c in qualified.get("callers") or []}
    bare_callers = {(c["file"], c["name"]) for c in bare.get("callers") or []}
    assert ("web/user.py", "schema") in qualified_callers
    assert qualified_callers <= bare_callers
