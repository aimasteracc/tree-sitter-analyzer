"""#1675: persisted call-edge resolutions reproduce the freshly built graph exactly."""

from __future__ import annotations

import marshal
from pathlib import Path

import pytest

from tree_sitter_analyzer import call_graph_memo, call_graph_store
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.call_graph import CachedCallGraph

_SOURCES = {
    "pkg/__init__.py": "from .core import helper\n",
    "pkg/core.py": (
        "def helper(x):\n    return x + 1\n\n"
        "class Engine:\n"
        "    def run(self):\n        return self.step() + helper(1)\n\n"
        "    def step(self):\n        return 2\n\n"
        "helper(0)\n"
    ),
    "app.py": (
        "from pkg.core import Engine, helper\n\n"
        "def main():\n    e = Engine()\n    e.run()\n    return helper(3)\n\n"
        "def unrelated(obj):\n    return obj.run()\n\n"
        "main()\n"
    ),
}


def _key(ref):
    return (
        ref.file_path,
        ref.name,
        ref.start_line,
        ref.end_line,
        ref.language,
        ref.receiver,
    )


def _snapshot(graph: CachedCallGraph) -> dict:
    def adj(mapping):
        return {_key(k): [_key(v) for v in vs] for k, vs in mapping.items()}

    return {
        "functions": [_key(r) for r in graph._functions],
        "by_name": {n: [_key(r) for r in rs] for n, rs in graph._func_by_name.items()},
        "by_file": {n: [_key(r) for r in rs] for n, rs in graph._func_by_file.items()},
        "by_qualified": {n: _key(r) for n, r in graph._func_by_qualified.items()},
        "callees": adj(graph._callees),
        "callers": adj(graph._callers),
        "possible_callees": adj(graph._possible_callees),
        "possible_callers": adj(graph._possible_callers),
        "call_edges": [(_key(a), _key(b), line) for a, b, line in graph._call_edges],
        "edge_bindings": dict(graph._edge_bindings),
        "plain_edges": set(graph._plain_edges),
    }


@pytest.fixture
async def indexed_project(tmp_path):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in _SOURCES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    result = await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": "full"})
    assert result["published"] is True
    call_graph_memo.clear()
    yield str(tmp_path)
    call_graph_memo.clear()


def _build(root: str, *, persist: bool) -> CachedCallGraph:
    call_graph_memo.clear()
    cache = ASTCache(root)
    graph = CachedCallGraph(root, cache=cache, persist=persist)
    try:
        graph.build()
    finally:
        cache.close()
    assert graph.is_built
    return graph


def _stored_files(root: str) -> list[Path]:
    directory = Path(root) / ".ast-cache" / call_graph_store.DIR_NAME
    return sorted(directory.glob("*.bin")) if directory.is_dir() else []


@pytest.mark.asyncio
async def test_replayed_graph_equals_the_fresh_build(indexed_project, monkeypatch):
    fresh = _build(indexed_project, persist=True)
    assert len(_stored_files(indexed_project)) == 1
    assert fresh._call_edges, "fixture must produce call edges"

    calls = []
    original = call_graph_store.decode
    monkeypatch.setattr(
        call_graph_store,
        "decode",
        lambda *args: calls.append(1) or original(*args),
    )
    replayed = _build(indexed_project, persist=False)

    assert calls == [1]
    assert _snapshot(replayed) == _snapshot(fresh)
    for name in ("helper", "run", "step", "main"):
        assert replayed.callers_of(name) == fresh.callers_of(name)
        assert replayed.callees_of(name) == fresh.callees_of(name)


@pytest.mark.asyncio
async def test_nothing_is_written_without_persist(indexed_project):
    _build(indexed_project, persist=False)
    assert not (
        Path(indexed_project) / ".ast-cache" / call_graph_store.DIR_NAME
    ).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["garbage", "bad_index", "short"])
async def test_damaged_store_falls_back_to_a_fresh_build(indexed_project, damage):
    fresh = _build(indexed_project, persist=True)
    (stored,) = _stored_files(indexed_project)
    if damage == "garbage":
        stored.write_bytes(b"\x00not marshal")
    else:
        fmt, digest, functions, edges, records = marshal.loads(stored.read_bytes())
        if damage == "bad_index":
            index = next(i for i, record in enumerate(records) if record is not None)
            caller, certain, possible, binding, line = records[index]
            records[index] = (10**6, certain, possible, binding, line)
        else:
            records = records[:-1]
        stored.write_bytes(marshal.dumps((fmt, digest, functions, edges, records)))

    rebuilt = _build(indexed_project, persist=False)
    assert _snapshot(rebuilt) == _snapshot(fresh)


@pytest.mark.asyncio
async def test_other_code_or_inputs_never_read_the_store(indexed_project, monkeypatch):
    _build(indexed_project, persist=True)
    loads = []
    original = call_graph_store.load
    monkeypatch.setattr(
        call_graph_store,
        "load",
        lambda *args, **kwargs: loads.append(original(*args, **kwargs)) or loads[-1],
    )
    monkeypatch.setattr(call_graph_store, "source_fingerprint", lambda: "other-code")
    _build(indexed_project, persist=False)
    assert loads == [None]


@pytest.mark.asyncio
async def test_changed_inputs_miss_and_store_a_new_entry(indexed_project):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    _build(indexed_project, persist=True)
    (Path(indexed_project) / "extra.py").write_text(
        "from pkg.core import helper\n\ndef extra():\n    return helper(9)\n",
        encoding="utf-8",
    )
    result = await CodeGraphFullIndexTool(indexed_project).execute({"mode": "full"})
    assert result["published"] is True
    fresh = _build(indexed_project, persist=True)
    assert len(_stored_files(indexed_project)) == 2
    assert any(
        ref.name == "extra"
        for ref in fresh.caller_refs_of(
            next(r for r in fresh.function_refs() if r.name == "helper")
        )
    )
    replayed = _build(indexed_project, persist=False)
    assert _snapshot(replayed) == _snapshot(fresh)


_CROSS_PROCESS = """
import sys
from tree_sitter_analyzer import call_graph_store
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.call_graph import CachedCallGraph

used = []
original = call_graph_store.decode
call_graph_store.decode = lambda *a: used.append(1) or original(*a)
cache = ASTCache(sys.argv[1])
graph = CachedCallGraph(sys.argv[1], cache=cache, persist=True)
graph.build()
cache.close()
print("replayed" if used else "built", len(graph._call_edges))
"""


@pytest.mark.asyncio
@pytest.mark.timeout(900)
async def test_a_new_process_with_another_hash_seed_reuses_the_store(
    indexed_project,
):
    """String hashing differs per process; the store key must not (#1675)."""
    import os
    import subprocess
    import sys

    outputs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        completed = subprocess.run(
            [sys.executable, "-c", _CROSS_PROCESS, indexed_project],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
        outputs.append(completed.stdout.split())
    (first, first_edges), (second, second_edges) = outputs
    assert (first, second) == ("built", "replayed")
    assert first_edges == second_edges
    assert len(_stored_files(indexed_project)) == 1


def test_stable_form_orders_sets_and_unfolds_dataclasses():
    from dataclasses import dataclass

    @dataclass
    class Box:
        items: set[str]

    a = call_graph_memo.stable_form({"k": Box({"b", "a", "c"})})
    b = call_graph_memo.stable_form({"k": Box({"c", "a", "b"})})
    assert a == b
    ((key, (type_name, fields)),) = a[1]
    assert (key, type_name.rsplit(".", 1)[-1]) == ("k", "Box")
    assert fields == [("items", ("set", ["a", "b", "c"]))]
    assert call_graph_memo.input_digest(a) == call_graph_memo.input_digest(b)


def test_store_needs_an_existing_real_ast_cache_dir(tmp_path):
    call_graph_store.save(str(tmp_path), "digest", [], [None])
    assert not (tmp_path / ".ast-cache").exists()
    assert call_graph_store.load(str(tmp_path), "digest", functions=0, edges=1) is None
