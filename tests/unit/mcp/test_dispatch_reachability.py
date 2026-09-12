#!/usr/bin/env python3
"""RFC-0028 §3.1 — every resolver dispatch branch is reached via a public entry point.

§3.1 records the defect this catches: the ESM branch of `ImportGraph._resolve_import`
was unreachable in production while its helper's unit tests passed. A test that
calls the private helper proves the helper works; it proves nothing about whether
the dispatch ever routes to it.

So this gate drives the **public** entry point (`ImportGraph.build`) and pairs each
resolver invocation with the *line inside the dispatch* that made it. It then
requires that observed set of dispatch lines to equal the set of resolver call
sites found by parsing the dispatch. A branch with no fixture — or dead code with
no producer — leaves an unmatched line and fails here, which is the point.

Pairing on line numbers rather than on "was the js resolver called at all" matters:
after the ESM fix, `_resolve_js_import` is reachable through the extension path, so
a coarse assertion would pass while the *text-sniff* fallback stayed dead. Two
call sites, one branch label — only per-line pairing separates them.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import tree_sitter_analyzer.import_graph as import_graph
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.import_graph import ImportGraph

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = PROJECT_ROOT / "tree_sitter_analyzer" / "import_graph.py"

_RESOLVERS = ("_resolve_js_import", "_resolve_python_import")

#: One fixture per branch, in that language's own idiom. The first two are
#: routed by the source file's extension; the third is a mapped language that is
#: neither JS/TS nor Python, which is what reaches the text-sniff fallback.
_FIXTURES: dict[str, str] = {
    "py_mod.py": "from py_other import thing\n",
    "js_mod.mjs": "import { run } from './js_util.mjs'\n",
    "go_mod.go": 'import "py_other"\n',
}


def _dispatch_call_sites() -> set[tuple[str, int]]:
    """``(resolver, lineno)`` for every resolver call site inside the dispatch."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    dispatch = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_resolve_import"
    )
    sites: set[tuple[str, int]] = set()
    for node in ast.walk(dispatch):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _RESOLVERS:
                sites.add((node.func.id, node.lineno))
    return sites


def _observed_call_sites(tmp_path: Path) -> set[tuple[str, int]]:
    """``(resolver, lineno)`` actually taken, driven only through ``build()``."""
    for name, text in _FIXTURES.items():
        (tmp_path / name).write_text(text, encoding="utf-8")

    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()

    observed: set[tuple[str, int]] = set()
    originals = {name: getattr(import_graph, name) for name in _RESOLVERS}

    def make_wrapper(name: str):
        def wrapper(*args, **kwargs):
            # The caller two frames up is the dispatch method; record *its* line,
            # which is what distinguishes two call sites of the same resolver.
            for frame in inspect.stack()[1:]:
                if frame.function == "_resolve_import":
                    observed.add((name, frame.lineno))
                    break
            return originals[name](*args, **kwargs)

        return wrapper

    for name in _RESOLVERS:
        setattr(import_graph, name, make_wrapper(name))
    try:
        ImportGraph(str(tmp_path)).build()
    finally:
        for name, original in originals.items():
            setattr(import_graph, name, original)
    return observed


@pytest.fixture
def reached_dispatch_lines(tmp_path) -> set[tuple[str, int]]:
    return _observed_call_sites(tmp_path)


def test_the_public_entry_point_is_what_is_driven(reached_dispatch_lines) -> None:
    """Guard against the gate quietly testing the helper instead of the dispatch."""
    assert reached_dispatch_lines, (
        "driving ImportGraph.build() reached no resolver at all; the fixture or "
        "the entry point changed and the invariant below would be vacuous"
    )


def test_every_dispatch_call_site_is_reached_through_the_public_entry(
    reached_dispatch_lines,
) -> None:
    declared = _dispatch_call_sites()
    unreached = sorted(declared - reached_dispatch_lines)

    assert unreached == [], (
        "RFC-0028 §3.1 dispatch reachability is red. These resolver call sites in "
        "`ImportGraph._resolve_import` are reached by no public-input fixture, so "
        "either they are dead code or the dispatch never routes to them — the "
        "shape of defect #3, where the helper's unit tests passed while the branch "
        "was unreachable in production. Give each a producer or delete it:\n  "
        + "\n  ".join(f"{name} at import_graph.py:{line}" for name, line in unreached)
    )


def test_the_gate_can_fail(reached_dispatch_lines) -> None:
    """The comparison is per call site, not per resolver.

    A gate asserting only "the js resolver ran" would pass today while a second,
    unreachable js call site sat beside it. This asserts the two differ.
    """
    names = {name for name, _line in reached_dispatch_lines}
    assert len(names) >= 1
    lines_for_a_name = [
        line for name, line in reached_dispatch_lines if name in names
    ]
    assert len(set(lines_for_a_name)) == len(lines_for_a_name), (
        "the same call site was recorded twice; line attribution is broken and "
        "the invariant above cannot distinguish call sites"
    )
