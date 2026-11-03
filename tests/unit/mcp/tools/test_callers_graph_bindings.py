"""PR-3: index-unresolved JS/TS call sites the call graph already binds.

Two kinds of site no longer gate ``UNRESOLVED_INBOUND`` /
``UNRESOLVED_IN_DECLARING_FILE``:

* (b) the site is a listed caller's own certain edge into the target, counted
  again (zod ``ParseStatus.mergeObjectSync``);
* (a) ``this.m()`` in class ``C`` bound to ``C``'s own ``m``, where the target's
  class is provably not ``C`` or a subclass of ``C`` (zod ``ZodBigInt.setLimit``,
  blocked by the sibling ``ZodNumber``'s own ``this.setLimit``).

Everything else keeps its site: base-class dispatch to an override (hono
``getQueryString``), unknown or possible-only receivers, a second call of the
name on the line, a ``function`` boundary, a static method, an unresolved,
generic-through-mixin or external supertype, a class used as a value, and a
file that changed since the index.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.callers_graph_bindings import (
    BOUND_ELSEWHERE_REASON,
    LISTED_EDGE_REASON,
    MAX_SITES,
    GraphBindings,
    drop_graph_bound,
    graph_bindings,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

#: Two sibling classes with their own ``setLimit`` (zod ``ZodNumber`` / ``ZodBigInt``).
_SIBLINGS = (
    "export class Num {\n"  # 1
    "  gte(v: number) {\n"  # 2
    '    return this.setLimit("min", v)\n'  # 3
    "  }\n"  # 4
    "  protected setLimit(kind: string, v: number) {\n"  # 5
    "    return kind + v\n"  # 6
    "  }\n"  # 7
    "}\n"  # 8
    "\n"  # 9
    "export class Big {\n"  # 10
    "  gte(v: bigint) {\n"  # 11
    '    return this.setLimit("min", v)\n'  # 12
    "  }\n"  # 13
    "  protected setLimit(kind: string, v: bigint) {\n"  # 14
    "    return kind + v\n"  # 15
    "  }\n"  # 16
    "}\n"  # 17
)
#: A static helper called through its class name from a sibling static method.
_STATUS = (
    "export class Status {\n"
    "  static merge(a: number) {\n"
    "    return a\n"
    "  }\n"
    "  static mergeAsync(a: number) {\n"
    "    return Status.merge(a)\n"
    "  }\n"
    "}\n"
)
#: hono ``EventProcessor``: the base class calls an abstract method subclasses override.
_ABSTRACT_BASE = (
    "export abstract class Proc<E> {\n"
    "  protected abstract getQuery(e: E): string\n"
    "  create(e: E) {\n"
    "    return this.getQuery(e)\n"
    "  }\n"
    "}\n"
    "export class V1 extends Proc<string> {\n"
    "  protected getQuery(e: string) {\n"
    "    return e\n"
    "  }\n"
    "}\n"
)
#: The base class has its own ``getQuery``: the site binds to it certainly, but
#: dispatch may still reach the subclass override.
_CONCRETE_BASE = (
    "export class Proc {\n"
    "  getQuery(e: string) {\n"
    "    return e\n"
    "  }\n"
    "  create(e: string) {\n"
    "    return this.getQuery(e)\n"
    "  }\n"
    "}\n"
)
_SUBCLASS = (
    "import { Proc } from './proc'\n"
    "export class V1 extends Proc {\n"
    "  getQuery(e: string) {\n"
    "    return e + '1'\n"
    "  }\n"
    "}\n"
)


async def _index(root: Path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str, file_path: str | None = None) -> dict:
    args: dict[str, Any] = {"function_name": name, "include_bodies": False}
    if file_path:
        args["file_path"] = file_path
    return await CodeGraphCallersTool(root).execute(args)


def _open_lines(result: dict) -> set[int]:
    fields = ("unresolved_sites", "unresolved_inbound_sites", "name_only_sites")
    return {int(s["line"]) for f in fields for s in result.get(f) or []}


# ------------------------------------------------------------------ positives
@pytest.mark.asyncio
async def test_sibling_own_this_call_and_listed_edge_no_longer_block(
    tmp_path: Path,
) -> None:
    root = await _index(tmp_path, {"src/nums.ts": _SIBLINGS})

    result = await _callers(root, "Big.setLimit", "src/nums.ts")

    assert result["completeness"] == "complete", result["completeness_reasons"]
    assert [(c["name"], c["line"]) for c in result["callers"]] == [("gte", 11)]
    assert result["excluded_by_reason"][BOUND_ELSEWHERE_REASON] == 1
    assert result["excluded_by_reason"][LISTED_EDGE_REASON] == 1
    assert result["unresolved_inbound"] == 0
    reasons = {
        s["line"]: s["reason_code"] for s in result["unresolved_inbound_excluded"]
    }
    assert reasons == {3: BOUND_ELSEWHERE_REASON, 12: LISTED_EDGE_REASON}


@pytest.mark.asyncio
async def test_bare_union_drops_each_listed_callers_own_edge(tmp_path: Path) -> None:
    root = await _index(tmp_path, {"src/nums.ts": _SIBLINGS})

    result = await _callers(root, "setLimit", "src/nums.ts")

    assert result["completeness"] == "complete", result["completeness_reasons"]
    assert result["caller_count"] == 2
    assert result["excluded_by_reason"][LISTED_EDGE_REASON] == 2


@pytest.mark.asyncio
async def test_listed_static_call_through_class_name_is_not_counted_twice(
    tmp_path: Path,
) -> None:
    root = await _index(tmp_path, {"src/status.ts": _STATUS})

    result = await _callers(root, "Status.merge", "src/status.ts")

    assert result["completeness"] == "complete", result["completeness_reasons"]
    assert [c["name"] for c in result["callers"]] == ["mergeAsync"]


# ------------------------------------------------------------------ negatives
@pytest.mark.asyncio
async def test_abstract_base_dispatch_to_override_stays_blocked(tmp_path: Path) -> None:
    root = await _index(tmp_path, {"src/proc.ts": _ABSTRACT_BASE})

    result = await _callers(root, "V1.getQuery", "src/proc.ts")

    assert result["completeness"] != "complete"
    assert 4 in _open_lines(result)


@pytest.mark.asyncio
async def test_concrete_base_bound_to_itself_still_reaches_cross_file_override(
    tmp_path: Path,
) -> None:
    root = await _index(
        tmp_path, {"src/proc.ts": _CONCRETE_BASE, "src/v1.ts": _SUBCLASS}
    )

    result = await _callers(root, "V1.getQuery", "src/v1.ts")

    assert result["completeness"] != "complete"
    assert 6 in _open_lines(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extends",
    [
        # A mixin over the caller's class, an external package, an import that
        # resolves to no file, a namespace member: the chain cannot be read from
        # source, so the target may be a subclass of the caller's class.
        "mix(Other)",
        "Base",
        "Missing",
        "ns.Other",
    ],
)
async def test_unresolved_supertype_of_target_keeps_the_site(
    tmp_path: Path, extends: str
) -> None:
    text = (
        "import { mix } from 'mixins'\n"  # 1
        "import { Base } from 'some-package'\n"  # 2
        "import { Missing } from './missing'\n"  # 3
        "import * as ns from './nums'\n"  # 4
        "export class Other {\n"  # 5
        "  getQuery(e: string) {\n    return e\n  }\n"  # 6-8
        "  create(e: string) {\n    return this.getQuery(e)\n  }\n"  # 9-11
        "}\n"  # 12
        f"export class V1 extends {extends} {{\n"
        "  getQuery(e: string) {\n    return e + '1'\n  }\n"
        "}\n"
    )
    root = await _index(tmp_path, {"src/q.ts": text, "src/nums.ts": _SIBLINGS})

    result = await _callers(root, "V1.getQuery", "src/q.ts")

    assert result["completeness"] != "complete"
    assert 10 in _open_lines(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("old", "new"),
    [
        # Unknown receiver.
        (
            'return this.setLimit("min", v)\n  }\n  protected setLimit(kind: string, v: number)',
            'return other.setLimit("min", v)\n  }\n  protected setLimit(kind: string, v: number)',
        ),
        # A second call of the name on the same line.
        (
            'return this.setLimit("min", v)\n  }\n  protected setLimit(kind: string, v: number)',
            'return this.setLimit("min", v) + this.setLimit("max", v)\n  }\n'
            "  protected setLimit(kind: string, v: number)",
        ),
        # A ``function`` expression binds its own ``this``.
        (
            'return this.setLimit("min", v)\n  }\n  protected setLimit(kind: string, v: number)',
            'return [v].map(function () { return this.setLimit("min", v) })\n  }\n'
            "  protected setLimit(kind: string, v: number)",
        ),
        # A static method: ``this`` is the constructor.
        ("  gte(v: number) {\n", "  static gte(v: number) {\n"),
    ],
)
async def test_sibling_site_shapes_that_cannot_be_proved_stay_blocked(
    tmp_path: Path, old: str, new: str
) -> None:
    text = _SIBLINGS.replace(old, new, 1)
    assert text != _SIBLINGS
    root = await _index(tmp_path, {"src/nums.ts": text})

    result = await _callers(root, "Big.setLimit", "src/nums.ts")

    assert result["completeness"] != "complete"
    assert 3 in _open_lines(result)


@pytest.mark.asyncio
async def test_second_call_on_a_listed_callers_line_stays_counted(
    tmp_path: Path,
) -> None:
    text = _SIBLINGS.replace(
        '    return this.setLimit("min", v)\n  }\n  protected setLimit(kind: string, v: bigint)',
        '    return this.setLimit("min", v) + this.setLimit("max", v)\n  }\n'
        "  protected setLimit(kind: string, v: bigint)",
    )
    assert text != _SIBLINGS
    root = await _index(tmp_path, {"src/nums.ts": text})

    result = await _callers(root, "Big.setLimit", "src/nums.ts")

    assert result["completeness"] != "complete"
    assert 12 in _open_lines(result)


@pytest.mark.asyncio
async def test_class_used_as_a_value_keeps_the_site(tmp_path: Path) -> None:
    mixins = (
        "import { Big, Num } from './nums'\n"
        "export function applyMixins(d: any, bases: any[]) { return [d, bases] }\n"
        "applyMixins(Num, [Big])\n"
    )
    root = await _index(tmp_path, {"src/nums.ts": _SIBLINGS, "src/mix.ts": mixins})

    result = await _callers(root, "Big.setLimit", "src/nums.ts")

    assert result["completeness"] != "complete"
    assert 3 in _open_lines(result)


@pytest.mark.asyncio
async def test_file_changed_since_the_index_keeps_the_site(tmp_path: Path) -> None:
    root = await _index(tmp_path, {"src/nums.ts": _SIBLINGS})
    path = tmp_path / "src" / "nums.ts"
    path.write_text(_SIBLINGS.replace("kind + v", "kind  + v"), encoding="utf-8")

    result = await _callers(root, "Big.setLimit", "src/nums.ts")

    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_python_sites_are_untouched(tmp_path: Path) -> None:
    text = (
        "class Num:\n"
        "    def gte(self, v):\n        return self.set_limit(v)\n\n"
        "    def set_limit(self, v):\n        return v\n\n\n"
        "class Big:\n"
        "    def gte(self, v):\n        return self.set_limit(v)\n\n"
        "    def set_limit(self, v):\n        return v\n"
    )
    root = await _index(tmp_path, {"pkg/nums.py": text})

    result = await _callers(root, "Big.set_limit", "pkg/nums.py")

    assert not result.get("unresolved_inbound_excluded")
    assert BOUND_ELSEWHERE_REASON not in (result.get("excluded_by_reason") or {})


# -------------------------------------------------------------- fail closed
class _Graph:
    def __init__(self, fail: str = "") -> None:
        self.fail = fail

    def resolve_targets(self, name: str, file_path: str | None) -> list[Any]:
        if self.fail == "resolve":
            raise RuntimeError("unreadable")
        return []

    def function_refs_in_file(self, path: str) -> list[Any]:
        if self.fail == "refs":
            raise RuntimeError("unreadable")
        return []

    def call_edges(self) -> list[Any]:
        raise RuntimeError("unreadable")


def test_no_bindings_without_cache_root_or_targets() -> None:
    graph = _Graph()
    get = lambda: (graph, "cache")  # noqa: E731
    args = {"qualified": True, "declaring": None, "listed": []}
    assert graph_bindings(get, None, "/r", "A.m", None, **args) is None
    assert graph_bindings(get, object(), None, "A.m", None, **args) is None
    assert graph_bindings(get, object(), "/r", "A.m", None, **args) is None
    bare = {"qualified": False, "declaring": None, "listed": []}
    assert graph_bindings(get, object(), "/r", "m", None, **bare) is None
    bare["declaring"] = ("a.ts",)
    assert graph_bindings(get, object(), "/r", "m", None, **bare) is None


@pytest.mark.parametrize("fail", ["resolve", "refs"])
def test_unreadable_graph_builds_no_bindings(fail: str) -> None:
    graph = _Graph(fail)
    found = graph_bindings(
        lambda: (graph, "cache"),
        object(),
        "/r",
        "A.m" if fail == "resolve" else "m",
        None,
        qualified=fail == "resolve",
        declaring=("a.ts",),
        listed=[],
    )
    assert found is None


def test_drop_graph_bound_passes_unreadable_lists_through() -> None:
    sites = [{"file": "a.ts", "line": 1, "callee": "this.m"}]
    assert drop_graph_bound(None, sites, []) == (sites, [], 0)
    assert drop_graph_bound(None, None, []) == (None, [], 0)


def test_long_site_lists_and_unreadable_edges_keep_every_site(tmp_path: Path) -> None:
    target = type("Ref", (), {"name": "m", "receiver": "A", "file_path": "a.ts"})()
    bindings = GraphBindings(_Graph(), None, str(tmp_path), [target], [])
    many = [
        {"file": "a.ts", "line": n, "callee": "this.m"} for n in range(MAX_SITES + 1)
    ]
    assert bindings.partition(many) == (many, [])
    one = [{"file": "a.ts", "line": 1, "callee": "this.m"}]
    assert bindings.partition(one) == (one, [])
    assert bindings.partition(None) == (None, [])
