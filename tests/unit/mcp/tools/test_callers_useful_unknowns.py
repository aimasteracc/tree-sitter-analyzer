"""PR-4: make ``unknown`` callers answers useful, without new trust errors.

1. A registering decorator on the target's own definition is a known use: it
   is listed as a ``registration`` entry and the answer becomes ``incomplete``
   (never ``complete``).
2. ``open_sites`` bounds an ``unknown`` answer: ``enumerated: true`` only when
   every blocking site is listed, untruncated, and the review gates the edge
   layer skipped were run too.

Negative controls: a same-named decorated definition elsewhere, a decorated
nested definition, a truncated site list, an accessor, a stacked decorator with
a non-registering wrapper, a decorator behind an edge-level blocker.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_compact import compact_callers
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_APP = "class App:\n    def get(self, path):\n        return lambda fn: fn\n\n\napp = App()\n"


async def _index(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    # One unrelated call edge, so an answer never rests on an empty call graph.
    files = {
        "main.py": "def helper():\n    return 1\n\n\ndef main():\n    return helper()\n",
        **files,
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


async def _callers(root: str, name: str, file_path: str | None = None) -> dict:
    args: dict = {"function_name": name, "include_bodies": False}
    if file_path:
        args["file_path"] = file_path
    return await CodeGraphCallersTool(root).execute(args)


def _registrations(result: dict) -> list[dict]:
    return [c for c in result["callers"] if c.get("resolution_kind") == "registration"]


# ---------------------------------------------------------------------------
# 1. registration -> incomplete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registered_route_is_incomplete_with_a_registration_entry(
    tmp_path,
) -> None:
    routes = 'from app import app\n\n\n@app.get("/items")\ndef read_items():\n    return []\n'
    root = await _index(tmp_path, {"app.py": _APP, "routes.py": routes})

    result = await _callers(root, "read_items", "routes.py")

    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["DECORATOR_MAY_REGISTER"]
    assert result["caller_count"] == 1
    (entry,) = _registrations(result)
    assert entry["via"] == '@app.get("/items")'
    assert (entry["file"], entry["line"], entry["name"]) == ("routes.py", 4, "<module>")
    assert entry["confidence_tier"] == "registration"
    assert "framework-side callers cannot be listed" in result["next_step"]
    assert "open_sites" not in result  # only unknown answers carry the bound
    compact = compact_callers(result)
    assert '@app.get("/items")  routes.py:4  registration' in compact["answer"]
    assert compact["completeness"] == "incomplete"


@pytest.mark.asyncio
async def test_bare_and_qualified_registration_agree(tmp_path) -> None:
    views = (
        "from app import app\n\n\n"
        "class Views:\n"
        '    @app.get("/v")\n'
        "    def show(self):\n"
        "        return 1\n"
    )
    root = await _index(tmp_path, {"app.py": _APP, "views.py": views})

    bare = await _callers(root, "show", "views.py")
    qualified = await _callers(root, "Views.show", "views.py")

    for result in (bare, qualified):
        assert result["completeness"] == "incomplete"
        assert [e["line"] for e in _registrations(result)] == [5]


@pytest.mark.asyncio
async def test_stacked_decorator_lists_only_the_registering_one(tmp_path) -> None:
    routes = (
        "import functools\n\nfrom app import app\n\n\n"
        '@app.get("/x")\n'
        "@functools.lru_cache\n"
        "def cached():\n"
        "    return 1\n"
    )
    root = await _index(tmp_path, {"app.py": _APP, "routes.py": routes})

    result = await _callers(root, "cached", "routes.py")

    assert result["completeness"] == "incomplete"
    assert [e["via"] for e in _registrations(result)] == ['@app.get("/x")']


@pytest.mark.asyncio
async def test_only_wrapper_decorators_stay_complete(tmp_path) -> None:
    # Control: a known wrapper registers nothing; no entry, no new verdict.
    mod = "import functools\n\n\n@functools.lru_cache\ndef cached():\n    return 1\n"
    root = await _index(tmp_path, {"mod.py": mod})

    result = await _callers(root, "cached", "mod.py")

    assert result["completeness"] == "complete"
    assert result["callers"] == []


@pytest.mark.asyncio
async def test_same_named_decorated_definition_elsewhere_is_not_a_registration(
    tmp_path,
) -> None:
    # Two `handler` definitions: the decorated one is not the queried one when
    # the query is unscoped, so the gate still blocks but nothing is listed.
    routes = 'from app import app\n\n\n@app.get("/h")\ndef handler():\n    return 1\n'
    plain = "def handler():\n    return 2\n"
    root = await _index(
        tmp_path, {"app.py": _APP, "routes.py": routes, "plain.py": plain}
    )

    unscoped = await _callers(root, "handler")
    scoped_plain = await _callers(root, "handler", "plain.py")

    assert unscoped["completeness_reasons"] == ["DECORATOR_MAY_REGISTER"]
    assert _registrations(unscoped) == []
    assert scoped_plain["completeness"] in ("complete", "unknown")
    assert _registrations(scoped_plain) == []


@pytest.mark.asyncio
async def test_same_named_decorated_method_in_another_class_is_not_a_registration(
    tmp_path,
) -> None:
    views = (
        "from app import app\n\n\n"
        "class A:\n"
        '    @app.get("/a")\n'
        "    def m(self):\n"
        "        return 1\n\n\n"
        "class B:\n"
        "    def m(self):\n"
        "        return 2\n"
    )
    root = await _index(tmp_path, {"app.py": _APP, "views.py": views})

    result = await _callers(root, "B.m", "views.py")

    assert result["completeness_reasons"] == ["DECORATOR_MAY_REGISTER"]
    assert _registrations(result) == []


@pytest.mark.asyncio
async def test_decorated_nested_definition_is_not_a_registration(tmp_path) -> None:
    # The inner `def` runs only when `factory()` runs: not a certain use.
    mod = (
        "from app import app\n\n\n"
        "def factory():\n"
        '    @app.get("/n")\n'
        "    def inner():\n"
        "        return 1\n"
    )
    root = await _index(tmp_path, {"app.py": _APP, "mod.py": mod})

    result = await _callers(root, "inner", "mod.py")

    assert result["completeness_reasons"] == ["DECORATOR_MAY_REGISTER"]
    assert _registrations(result) == []


# ---------------------------------------------------------------------------
# 2. open_sites on unknown answers
# ---------------------------------------------------------------------------

_BOX = "class Box:\n    def fetch(self):\n        return 1\n"


@pytest.mark.asyncio
async def test_enumerated_bound_names_every_blocking_site(tmp_path) -> None:
    user = "def use(thing):\n    return thing.fetch()\n"
    root = await _index(tmp_path, {"box.py": _BOX, "user.py": user})

    result = await _callers(root, "Box.fetch", "box.py")

    assert result["completeness"] == "unknown"
    bound = result["open_sites"]
    assert bound["enumerated"] is True
    assert bound["total"] == 1
    refs = {
        (site["file"], site["line"])
        for field in bound["fields"]
        for site in result[field]
    }
    assert refs == {("user.py", 2)}
    assert result["next_step"].startswith("The bound is exhaustive (`open_sites`)")
    compact = compact_callers(result)
    assert "open: 1 sites (exhaustive)  user.py:2" in compact["answer"]
    assert compact["open_sites"] == {"total": 1, "enumerated": True}


@pytest.mark.asyncio
async def test_truncated_site_list_is_not_enumerated(tmp_path) -> None:
    calls = "".join(f"    thing.fetch()  # {i}\n" for i in range(25))
    user = "def use(thing):\n" + calls
    root = await _index(tmp_path, {"box.py": _BOX, "user.py": user})

    result = await _callers(root, "Box.fetch", "box.py")

    assert result["completeness"] == "unknown"
    assert result["open_sites"] == {"enumerated": False, "reason": "SITES_TRUNCATED"}
    assert "open_sites" not in compact_callers(result)
    assert "open:" not in compact_callers(result)["answer"]


@pytest.mark.asyncio
async def test_accessor_is_not_enumerated(tmp_path) -> None:
    mod = "class Box:\n    @property\n    def size(self):\n        return 1\n"
    root = await _index(tmp_path, {"box.py": mod})

    result = await _callers(root, "Box.size", "box.py")

    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == ["ACCESSOR_NOT_CALL_EDGES"]
    assert result["open_sites"] == {"enumerated": False, "reason": "NO_SITE_LIST"}


@pytest.mark.asyncio
async def test_edge_blocked_bound_runs_the_skipped_review_gates(tmp_path) -> None:
    # The name-only site is listed, but the decorator gate (skipped by the edge
    # layer) would still block: the bound is not exhaustive.
    box = (
        "from app import app\n\n\n"
        "class Box:\n"
        '    @app.get("/f")\n'
        "    def fetch(self):\n"
        "        return 1\n"
    )
    user = "def use(thing):\n    return thing.fetch()\n"
    root = await _index(tmp_path, {"app.py": _APP, "box.py": box, "user.py": user})

    result = await _callers(root, "Box.fetch", "box.py")

    assert result["completeness"] == "unknown"
    assert _registrations(result) == []  # the decorator gate did not decide
    assert result["open_sites"] == {"enumerated": False, "reason": "NO_SITE_LIST"}


@pytest.mark.asyncio
async def test_non_call_reference_joins_the_bound(tmp_path) -> None:
    user = "def use(thing):\n    return thing.fetch()\n\n\ndef keep(box):\n    return box.fetch\n"
    root = await _index(tmp_path, {"box.py": _BOX, "user.py": user})

    result = await _callers(root, "Box.fetch", "box.py")

    assert result["completeness"] == "unknown"
    bound = result["open_sites"]
    assert bound["enumerated"] is True
    assert "non_call_reference_sites" in bound["fields"]
    refs = {
        (site["file"], site["line"])
        for field in bound["fields"]
        for site in result[field]
    }
    assert ("user.py", 6) in refs
    assert bound["total"] == len(refs)


@pytest.mark.asyncio
async def test_complete_and_incomplete_answers_carry_no_bound(tmp_path) -> None:
    user = "from box import Box\n\n\ndef use():\n    return Box().fetch()\n"
    root = await _index(tmp_path, {"box.py": _BOX, "user.py": user})

    result = await _callers(root, "Box.fetch", "box.py")

    assert result["completeness"] in ("complete", "incomplete")
    assert "open_sites" not in result
