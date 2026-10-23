"""#1759 unit edges: every refusal branch of the external-producer / literal-table
exclusions keeps the declaring-file guard, and every unreadable fact fails closed."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools import callers_tool
from tree_sitter_analyzer.mcp.tools.callers_external_producers import (
    EXTERNAL_PRODUCER_REASON,
    LITERAL_CONTAINER_REASON,
    ExternalProducers,
    _first_target,
    drop_external_producers,
)


def _cache(files: dict[str, str], imports: list[tuple[Any, ...]] = ()) -> Any:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
    conn.execute(
        "CREATE TABLE ast_imports (file_path TEXT, local_name TEXT, module_path TEXT,"
        " is_relative INTEGER, is_star INTEGER)"
    )
    conn.executemany("INSERT INTO ast_index VALUES (?, ?)", list(files.items()))
    conn.executemany("INSERT INTO ast_imports VALUES (?, ?, ?, ?, ?)", list(imports))
    return SimpleNamespace(get_conn=lambda: conn)


def _broken() -> Any:
    def fail() -> Any:
        raise sqlite3.OperationalError("no such table")

    return SimpleNamespace(get_conn=fail)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _site(callee: str, file: str = "pkg/mod.py", line: int = 3) -> dict[str, Any]:
    return {"file": file, "line": line, "callee": callee}


@pytest.mark.parametrize(
    "site",
    [
        {"file": "", "callee": "ext(a)(b)"},
        {"file": "pkg/mod.py", "callee": ""},
        _site("ext(getattr(o, n))(b)"),
        _site("ext"),
        _site("(a or b)(c)"),
    ],
)
def test_unshaped_or_dynamic_sites_are_kept(
    tmp_path: Path, site: dict[str, Any]
) -> None:
    _write(tmp_path, "pkg/mod.py", "from ext import ext\n")
    cache = _cache({"pkg/mod.py": "python"}, [("pkg/mod.py", "ext", "ext", 0, 0)])
    assert ExternalProducers(cache, str(tmp_path)).excludes(site) is None


def test_unsupported_language_is_kept(tmp_path: Path) -> None:
    _write(tmp_path, "Mod.java", "class Mod {}\n")
    cache = _cache({"Mod.java": "java"}, [("Mod.java", "ext", "ext", 0, 0)])
    site = _site("ext(a)(b)", file="Mod.java")
    assert ExternalProducers(cache, str(tmp_path)).excludes(site) is None


def test_js_package_producer_is_excluded_and_relative_is_kept(tmp_path: Path) -> None:
    _write(tmp_path, "src/a.js", "import wrap from 'wrapper';\nwrap(app)(req);\n")
    cache = _cache(
        {"src/a.js": "javascript"},
        [("src/a.js", "wrap", "wrapper", 0, 0), ("src/a.js", "local", "/abs/x", 0, 0)],
    )
    producers = ExternalProducers(cache, str(tmp_path))
    assert producers.excludes(_site("wrap(app)(req)", file="src/a.js")) == (
        EXTERNAL_PRODUCER_REASON
    )
    assert producers.excludes(_site("local(app)(req)", file="src/a.js")) is None
    # A JS table never qualifies as a Python literal container.
    assert producers.excludes(_site("local[k](req)", file="src/a.js")) is None


def test_star_ambiguous_and_empty_module_bindings_are_kept(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/mod.py", "x = 1\n")
    cache = _cache(
        {"pkg/mod.py": "python"},
        [
            ("pkg/mod.py", "star", "ext", 0, 1),
            ("pkg/mod.py", "", "ext", 0, 0),
            ("pkg/mod.py", "twice", "ext_a", 0, 0),
            ("pkg/mod.py", "twice", "ext_b", 0, 0),
            ("pkg/mod.py", "same", "ext_a", 0, 0),
            ("pkg/mod.py", "same", "ext_a", 0, 0),
            ("pkg/mod.py", "blank", "", 0, 0),
        ],
    )
    producers = ExternalProducers(cache, str(tmp_path))
    for head in ("star", "twice", "blank"):
        assert producers.excludes(_site(f"{head}(a)(b)")) is None, head
    assert producers.excludes(_site("same(a)(b)")) == EXTERNAL_PRODUCER_REASON


def test_unreadable_source_counts_as_rebound(tmp_path: Path) -> None:
    cache = _cache({"pkg/mod.py": "python"}, [("pkg/mod.py", "ext", "ext", 0, 0)])
    assert ExternalProducers(cache, str(tmp_path)).excludes(_site("ext(a)(b)")) is None


def test_unreadable_index_keeps_every_site(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/mod.py", "from ext import ext\n")
    producers = ExternalProducers(_broken(), str(tmp_path))
    assert producers.excludes(_site("ext(a)(b)")) is None
    assert producers._bindings("pkg/mod.py") == {}
    assert producers._named_elsewhere("pkg/mod.py", "TABLE") is True
    assert producers._is_project_module("", "pkg/mod.py") is True
    assert "" in producers._project_tops()
    assert "" in producers._project_tops()  # memoised unreadable answer


_TABLE_OK = "TABLE: dict = {'a': print}\n\ndef run(k):\n    TABLE[k](1)\n"


@pytest.mark.parametrize(
    "source",
    [
        "TABLE = {'a': print}\nTABLE = {'b': print}\n",
        "TABLE = make_table()\n",
        "TABLE = []\n",
        "TABLE = {'a': getattr(mod, 'x')}\n",
        "TABLE = {'a': print}\n\ndef f():\n    global TABLE\n",
        "TABLE = {'a': print}\nTABLE['b'] = print\n",
        "TABLE = {'a': print}\nTABLE.update(b=print)\n",
        "TABLE = {'a': print}\n\ndef f():\n    for TABLE in ():\n        pass\n",
        "TABLE = {'a': print\n",
    ],
    ids=[
        "assigned_twice",
        "not_a_literal",
        "empty",
        "dynamic_value",
        "global",
        "subscript_store",
        "mutator",
        "second_store",
        "syntax_error",
    ],
)
def test_literal_table_refusals_keep_the_guard(tmp_path: Path, source: str) -> None:
    _write(tmp_path, "pkg/mod.py", source)
    cache = _cache({"pkg/mod.py": "python"})
    producers = ExternalProducers(cache, str(tmp_path))
    assert producers.excludes(_site("TABLE[k](1)")) is None


def test_annotated_literal_table_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/mod.py", _TABLE_OK)
    cache = _cache({"pkg/mod.py": "python"})
    assert ExternalProducers(cache, str(tmp_path)).excludes(_site("TABLE[k](1)")) == (
        LITERAL_CONTAINER_REASON
    )


@pytest.mark.parametrize("other", ["import pkg.mod\npkg.mod.TABLE.update({})\n", None])
def test_table_named_or_unreadable_elsewhere_keeps_the_guard(
    tmp_path: Path, other: str | None
) -> None:
    _write(tmp_path, "pkg/mod.py", _TABLE_OK)
    if other is not None:
        _write(tmp_path, "pkg/other.py", other)
    cache = _cache({"pkg/mod.py": "python", "pkg/other.py": "python"})
    assert (
        ExternalProducers(cache, str(tmp_path)).excludes(_site("TABLE[k](1)")) is None
    )


def test_unreadable_table_source_keeps_the_guard(tmp_path: Path) -> None:
    producers = ExternalProducers(_cache({"pkg/mod.py": "python"}), str(tmp_path))
    assert producers._literal_container("pkg/mod.py", "TABLE") is False


def test_first_target_reads_annotated_assignments() -> None:
    import ast

    tree = ast.parse("x = 1\nTABLE: dict = {}\n")
    target = _first_target(tree, "TABLE")
    assert target is not None
    assert target.lineno == 2
    assert _first_target(tree, "missing") is None


def test_drop_external_producers_passes_through_without_facts() -> None:
    sites = [_site("ext(a)(b)")]
    assert drop_external_producers(None, "/r", sites, []) == (sites, [])
    assert drop_external_producers(object(), "", sites, []) == (sites, [])
    assert drop_external_producers(object(), "/r", None, []) == (None, [])
    assert drop_external_producers(object(), "/r", sites, None) == (sites, None)


def test_drop_external_producers_moves_and_sorts(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/mod.py", "from ext import ext\n")
    cache = _cache({"pkg/mod.py": "python"}, [("pkg/mod.py", "ext", "ext", 0, 0)])
    kept_site = _site("self.handlers[k](1)", line=5)
    moved_site = _site("ext(a)(b)", line=9)
    prior = {"file": "pkg/mod.py", "line": 1, "classification": "excluded"}
    kept, excluded = drop_external_producers(
        cache, str(tmp_path), [kept_site, moved_site], [prior]
    )
    assert kept == [kept_site]
    assert excluded is not None
    assert [s["line"] for s in excluded] == [1, 9]
    assert excluded[1]["reason_code"] == EXTERNAL_PRODUCER_REASON
    nothing = [kept_site]
    assert drop_external_producers(cache, str(tmp_path), nothing, [prior]) == (
        nothing,
        [prior],
    )


# ------------------------------------------------------------ callers_tool helpers
def _ref(name: str, receiver: str | None, file_path: str = "pkg/mod.py") -> Any:
    return SimpleNamespace(name=name, receiver=receiver, file_path=file_path)


class _Graph:
    def __init__(self, refs: list[Any] | None) -> None:
        self._refs = refs

    def function_refs_in_file(self, file_path: str) -> list[Any]:
        if self._refs is None:
            raise RuntimeError("graph unavailable")
        return [r for r in self._refs if r.file_path == file_path]


def test_sibling_methods_edges() -> None:
    graph = _Graph([_ref("m", "B"), _ref("m", "A"), _ref("m", None), _ref("n", "A")])
    assert callers_tool._sibling_methods(graph, "m", "pkg/mod.py") == ["A.m", "B.m"]
    assert callers_tool._sibling_methods(graph, "A.m", "pkg/mod.py") == []
    assert callers_tool._sibling_methods(graph, "m", None) == []
    assert callers_tool._sibling_methods(_Graph(None), "m", "pkg/mod.py") == []


@pytest.mark.parametrize(
    ("refs", "name", "file_path", "expected"),
    [
        ([_ref("m", "A")], "m", "pkg/mod.py", "A.m"),
        ([_ref("m", "A")], "A.m", "pkg/mod.py", "A.m"),
        ([_ref("m", "A")], "m", None, "m"),
        ([_ref("m", "A")], "", "pkg/mod.py", ""),
        ([_ref("m", "A"), _ref("m", "B")], "m", "pkg/mod.py", "m"),
        ([_ref("m", None)], "m", "pkg/mod.py", "m"),
        (None, "m", "pkg/mod.py", "m"),
    ],
    ids=["one_method", "dotted", "no_file", "empty", "several", "function", "broken"],
)
def test_single_method_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    refs: list[Any] | None,
    name: str,
    file_path: str | None,
    expected: str,
) -> None:
    tool = callers_tool.CodeGraphCallersTool(str(tmp_path))
    monkeypatch.setattr(tool, "_graph_for", lambda _cache: (_Graph(refs), "cache"))
    assert tool._single_method_name(None, name, file_path) == expected


def test_single_method_name_rejects_a_mismatched_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Loose(_Graph):
        def function_refs_in_file(self, file_path: str) -> list[Any]:
            return [_ref("m", "A", file_path="elsewhere.py")]

    tool = callers_tool.CodeGraphCallersTool(str(tmp_path))
    monkeypatch.setattr(tool, "_graph_for", lambda _cache: (_Loose([]), "cache"))
    assert tool._single_method_name(None, "m", "pkg/mod.py") == "m"
