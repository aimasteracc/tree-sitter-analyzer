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


# ------------------------------------------------------------ fake graph and index
_EDGE_COLUMNS = (
    "id INTEGER PRIMARY KEY, kind TEXT, caller_name TEXT, file_path TEXT, "
    "caller_line INTEGER, callee_name TEXT, callee_full TEXT, callee_line INTEGER, "
    "line INTEGER, language TEXT, callee_resolution TEXT, callee_resolved_file TEXT, "
    "metadata TEXT"
)


def _fake_cache(rows: list[tuple[Any, ...]], *, jsts: bool = True) -> Any:
    import sqlite3
    from types import SimpleNamespace

    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE edges ({_EDGE_COLUMNS})")
    if jsts:
        conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
        conn.execute("INSERT INTO ast_index VALUES ('src/nums.ts', 'typescript')")
    for caller, caller_line, callee_full, line, meta in rows:
        conn.execute(
            "INSERT INTO edges (kind, caller_name, file_path, caller_line, callee_name, "
            "callee_full, callee_line, line, language, callee_resolution, "
            "callee_resolved_file, metadata) VALUES "
            "('calls', ?, 'src/nums.ts', ?, ?, ?, ?, ?, 'typescript', ?, '', ?)",
            (
                caller,
                caller_line,
                callee_full.rpartition(".")[2],
                callee_full,
                line,
                line,
                "project" if meta else "unknown",
                meta,
            ),
        )
    return SimpleNamespace(get_conn=lambda: conn)


def _ref(name: str, line: int, end: int, receiver: str | None) -> Any:
    from tree_sitter_analyzer.call_graph import FunctionRef

    return FunctionRef("src/nums.ts", name, line, "typescript", receiver, end)


NUM_GTE = _ref("gte", 2, 4, "Num")
NUM_SET = _ref("setLimit", 5, 7, "Num")
BIG_GTE = _ref("gte", 11, 13, "Big")
BIG_SET = _ref("setLimit", 14, 16, "Big")


class _FakeGraph:
    def __init__(
        self, edges: list[tuple[Any, Any, int]], *, reach: Any = None, refs: Any = None
    ) -> None:
        self.edges = edges
        self.reach = reach
        self.refs = refs

    def function_refs_in_file(self, _path: str) -> list[Any]:
        if self.refs == "raise":
            raise RuntimeError("unreadable")
        return (
            self.refs if self.refs is not None else [NUM_GTE, NUM_SET, BIG_GTE, BIG_SET]
        )

    def call_edges(self) -> list[tuple[Any, Any, int]]:
        return self.edges

    def reachable_callee_refs_of(self, caller: Any) -> list[Any]:
        if self.reach == "raise":
            raise RuntimeError("unreadable")
        if self.reach is not None:
            return self.reach
        return [callee for c, callee, _line in self.edges if c == caller]


def _bindings(
    root: Path,
    graph: _FakeGraph,
    rows: list[tuple[Any, ...]],
    *,
    targets: list[Any] | None = None,
    listed: list[dict[str, Any]] | None = None,
    stale: bool = False,
    monkeypatch: pytest.MonkeyPatch,
) -> GraphBindings:
    from tree_sitter_analyzer.mcp.tools import callers_graph_bindings as G

    path = root / "src" / "nums.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SIBLINGS, encoding="utf-8")
    monkeypatch.setattr(
        G, "stale_reference_files", lambda *_a: ["src/nums.ts"] if stale else []
    )
    return GraphBindings(
        graph, _fake_cache(rows), str(root), targets or [BIG_SET], listed or []
    )


_ROW_NUM = ("gte", 2, "this.setLimit", 3, None)
_ROW_BIG = ("gte", 11, "this.setLimit", 12, None)
_SITE_NUM = {"file": "src/nums.ts", "line": 3, "callee": "this.setLimit"}
_SITE_BIG = {"file": "src/nums.ts", "line": 12, "callee": "this.setLimit"}
_EDGES = [(NUM_GTE, NUM_SET, 3), (BIG_GTE, BIG_SET, 12)]
_LISTED = [{"file": "src/nums.ts", "name": "Big.gte", "line": 11}]


def test_fake_graph_discharges_both_kinds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bindings = _bindings(
        tmp_path,
        _FakeGraph(_EDGES),
        [_ROW_NUM, _ROW_BIG],
        listed=_LISTED,
        monkeypatch=monkeypatch,
    )
    kept, dropped = bindings.partition([_SITE_NUM, _SITE_BIG])
    assert kept == []
    assert [s["reason_code"] for s in dropped] == [
        BOUND_ELSEWHERE_REASON,
        LISTED_EDGE_REASON,
    ]


@pytest.mark.parametrize(
    ("site", "rows", "graph", "opts"),
    [
        # Not JS/TS, no line, computed or other name.
        (
            {"file": "a.py", "line": 3, "callee": "self.setLimit"},
            [_ROW_NUM],
            _FakeGraph(_EDGES),
            {},
        ),
        ({**_SITE_NUM, "line": 0}, [_ROW_NUM], _FakeGraph(_EDGES), {}),
        ({**_SITE_NUM, "callee": "HANDLERS[k]"}, [_ROW_NUM], _FakeGraph(_EDGES), {}),
        ({**_SITE_NUM, "callee": "this.other"}, [_ROW_NUM], _FakeGraph(_EDGES), {}),
        # No row, two rows, another row that may name the target.
        (_SITE_NUM, [], _FakeGraph(_EDGES), {}),
        (
            _SITE_NUM,
            [_ROW_NUM, ("gte", 2, "this.setLimit", 3, "x")],
            _FakeGraph(_EDGES),
            {},
        ),
        (
            _SITE_NUM,
            [_ROW_NUM, ("gte", 2, "other.setLimit", 3, None)],
            _FakeGraph(_EDGES),
            {},
        ),
        (
            _SITE_NUM,
            [
                _ROW_NUM,
                ("gte", 2, "alias", 3, '{"import_alias": {"name": "setLimit"}}'),
            ],
            _FakeGraph(_EDGES),
            {},
        ),
        (_SITE_NUM, [_ROW_NUM, ("gte", 2, "f(", 3, None)], _FakeGraph(_EDGES), {}),
        # A stale file, a line past the end, no caller name, an unknown caller.
        (_SITE_NUM, [_ROW_NUM], _FakeGraph(_EDGES), {"stale": True}),
        (
            {**_SITE_NUM, "line": 99},
            [("gte", 2, "this.setLimit", 99, None)],
            _FakeGraph(_EDGES),
            {},
        ),
        (_SITE_NUM, [("", 0, "this.setLimit", 3, None)], _FakeGraph(_EDGES), {}),
        (_SITE_NUM, [_ROW_NUM], _FakeGraph(_EDGES, refs="raise"), {}),
        (_SITE_NUM, [_ROW_NUM], _FakeGraph(_EDGES, refs=[]), {}),
        # No certain edge, or certain only to another name.
        (_SITE_NUM, [_ROW_NUM], _FakeGraph([]), {}),
        # The target is reachable from the caller, or reachability cannot be read.
        (_SITE_NUM, [_ROW_NUM], _FakeGraph(_EDGES, reach=[BIG_SET]), {}),
        (_SITE_NUM, [_ROW_NUM], _FakeGraph(_EDGES, reach="raise"), {}),
        # Bound to a method of another class.
        (
            _SITE_NUM,
            [_ROW_NUM],
            _FakeGraph([(NUM_GTE, _ref("setLimit", 30, 31, "Zed"), 3)]),
            {},
        ),
        # A module-level function target has no class to prove.
        (
            _SITE_NUM,
            [_ROW_NUM],
            _FakeGraph(_EDGES),
            {"targets": [_ref("setLimit", 40, 41, None)]},
        ),
        # A listed caller's line whose caller is not in the list.
        (_SITE_BIG, [_ROW_BIG], _FakeGraph(_EDGES), {}),
    ],
)
def test_fake_graph_keeps_every_unproved_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    site: dict[str, Any],
    rows: list[tuple[Any, ...]],
    graph: _FakeGraph,
    opts: dict[str, Any],
) -> None:
    bindings = _bindings(tmp_path, graph, rows, monkeypatch=monkeypatch, **opts)
    assert bindings.partition([site]) == ([site], [])


def test_static_call_bound_elsewhere_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = _SIBLINGS.replace(
        'this.setLimit("min", v)\n  }\n  protected setLimit(kind: string, v: number)',
        'Num.setLimit("min", v)\n  }\n  protected setLimit(kind: string, v: number)',
        1,
    )
    bindings = _bindings(
        tmp_path,
        _FakeGraph(_EDGES),
        [("gte", 2, "Num.setLimit", 3, None)],
        monkeypatch=monkeypatch,
    )
    (tmp_path / "src" / "nums.ts").write_text(text, encoding="utf-8")
    site = {**_SITE_NUM, "callee": "Num.setLimit"}
    assert bindings.partition([site]) == ([site], [])


def test_unreadable_index_listing_keeps_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.mcp.tools import callers_graph_bindings as G

    bindings = _bindings(
        tmp_path, _FakeGraph(_EDGES), [_ROW_NUM], monkeypatch=monkeypatch
    )
    monkeypatch.setattr(bindings, "_cache", _fake_cache([_ROW_NUM], jsts=False))
    assert bindings.partition([_SITE_NUM]) == ([_SITE_NUM], [])
    assert G.drop_graph_bound(bindings, [_SITE_NUM], []) == ([_SITE_NUM], [], 0)
