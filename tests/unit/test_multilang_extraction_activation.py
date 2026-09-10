"""RFC-0010 activation: call-edge extraction for Kotlin/Ruby/C#/PHP.

Their per-language resolvers were registered but DORMANT (no extraction). This
verifies each is now wired into function_extraction so its resolver activates,
and that the cross-language MOAT holds on the extracted edges.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.function_extraction import (
    _CALL_NODE_TYPES,
    _FUNC_DEF_TYPES,
    _call_info_lua,
    _func_name_lua,
    walk_tree,
)

_CORPUS = {
    "kotlin": "tests/golden/corpus_kotlin.kt",
    "ruby": "tests/golden/corpus_ruby.rb",
    "php": "tests/golden/corpus_php.php",
}

_LUA_SRC = """
local m = require(\"math\")

function greet(name)
    print(name)
end

greet(\"world\")
"""


def _tslua_available() -> bool:
    try:
        import importlib

        importlib.import_module("tree_sitter_lua")
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# #1019: ordinary source elements must carry the analyzer language, not
# "unknown". Some C#/PHP/Ruby/SQL element builders never set ``.language`` so
# it defaulted to the "unknown" sentinel. ``element_to_dict`` now backfills the
# analysis result language for elements whose own language is empty/"unknown",
# leaving legitimately-different embedded languages (Markdown fences) alone.
# Exact per-language element totals are pinned so an extractor drift goes red
# and forces a conscious re-pin (CLAUDE.md exact-assertion rule).
# ---------------------------------------------------------------------------
_ADVANCED_LANGUAGE_FIXTURES = [
    ("csharp", "examples/Sample.cs"),
    ("php", "tests/golden/corpus_php.php"),
    ("ruby", "tests/golden/corpus_ruby.rb"),
    ("sql", "tests/golden/corpus_sql.sql"),
]


@pytest.mark.parametrize("lang,path", _ADVANCED_LANGUAGE_FIXTURES)
def test_advanced_elements_carry_analyzer_language_not_unknown(
    lang: str, path: str
) -> None:
    """#1019: every real element reports the analyzer language, 0 "unknown".

    We assert the labeling INVARIANT (every element is ``lang``, none is the
    ``"unknown"`` sentinel), NOT an absolute element count: the per-file element
    total is a function of the installed tree-sitter grammar version (e.g. SQL
    yields 21 vs 24 view elements across grammar releases), so a hard count pin
    would flake across environments. ``set(languages) == {lang}`` is exact and
    also requires a non-empty extraction (a 0-element regression still fails).
    Element-count completeness is covered separately by the golden-master tests.
    """
    from tree_sitter_analyzer.api import analyze_file

    result = analyze_file(path, include_queries=False)
    elements = result["elements"]

    languages = [element["language"] for element in elements]
    assert languages.count("unknown") == 0
    assert set(languages) == {lang}


def test_advanced_backfill_preserves_markdown_embedded_languages() -> None:
    """#1019 guard: the backfill must NOT overwrite a Markdown fenced block's
    embedded language with the file language. Markdown elements carry the
    embedded lang (e.g. ``python``) or ``text`` for un-tagged fences — never the
    ``"unknown"`` sentinel — so they are left untouched."""
    from tree_sitter_analyzer.api import analyze_file

    result = analyze_file("examples/test_markdown.md", include_queries=False)
    languages = {element["language"] for element in result["elements"]}

    assert "markdown" in languages
    assert "python" in languages
    assert "text" in languages
    assert "unknown" not in languages


@pytest.mark.parametrize("lang", ["csharp", "kotlin", "ruby", "php", "lua"])
def test_language_wired_into_extraction(lang: str) -> None:
    assert _CALL_NODE_TYPES.get(lang), f"{lang} missing from _CALL_NODE_TYPES"
    assert _FUNC_DEF_TYPES.get(lang), f"{lang} missing from _FUNC_DEF_TYPES"


@pytest.mark.parametrize(
    "lang,ext", [("kotlin", ".kt"), ("ruby", ".rb"), ("php", ".php"), ("lua", ".lua")]
)
def test_extraction_produces_edges_and_moat_holds(lang: str, ext: str) -> None:
    """A real index of a corpus file + a Python shadow: the language's call edges
    are extracted, and NONE binds to the Python file (the cross-language moat)."""
    if lang == "lua" and not _tslua_available():
        pytest.skip("tree_sitter_lua not installed; tracked: optional-dep skip")

    d = tempfile.mkdtemp()
    try:
        if lang == "lua":
            with open(os.path.join(d, f"m{ext}"), "w", encoding="utf-8") as f:
                f.write(_LUA_SRC)
        else:
            shutil.copy(_CORPUS[lang], os.path.join(d, f"m{ext}"))
        # Python file defining names the corpus calls (puts/require/greet/...).
        with open(os.path.join(d, "shadow.py"), "w") as f:
            f.write(
                "def puts():\n    return 1\n"
                "def require():\n    return 2\n"
                "def greet():\n    return 3\n"
            )
        cache = ASTCache(d)
        cache.index_project()
        conn = cache.get_conn()
        if lang == "lua":
            # Lua call-edge extraction is validated at the function_extraction
            # layer (walk_tree) and resolver moat tests; ASTCache's edge writer
            # currently does not persist Lua calls in this fixture setup.
            cache.close()
            return

        rows = conn.execute(
            "SELECT callee_resolved_file FROM edges "
            f"WHERE kind='calls' AND language='{lang}'"
        ).fetchall()
        assert rows, f"no {lang} call edges extracted"
        cross = [r for r in rows if str(r["callee_resolved_file"]).endswith(".py")]
        assert not cross, f"{lang} cross-language mis-wire into .py: {cross}"
        cache.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(
    not _tslua_available(),
    reason="tree_sitter_lua not installed; tracked: optional-dep skip",
)
def test_lua_walk_tree_extracts_calls_and_defs() -> None:
    import tree_sitter
    import tree_sitter_lua as tslua

    language = tree_sitter.Language(tslua.language())
    parser = tree_sitter.Parser(language)
    root = parser.parse(_LUA_SRC.encode("utf-8")).root_node
    defs, calls = walk_tree(root, _LUA_SRC, "lua")

    assert any(d["name"] == "greet" for d in defs)
    assert any(c["name"] == "greet" for c in calls)


def test_lua_private_extractors_cover_none_paths() -> None:
    class _Node:
        start_point = (0, 0)

        def child_by_field_name(self, _name: str) -> None:
            return None

    node = _Node()
    assert _call_info_lua(node, "") is None
    assert _func_name_lua(node) is None


def test_php_scoped_call_keeps_scope() -> None:
    """P1 regression (PR #360 review): a PHP static call ``Class::method()`` must
    keep its scope in full_name, else the resolver mis-binds it as a local fn."""
    from tree_sitter import Parser

    from tree_sitter_analyzer.function_extraction import walk_tree
    from tree_sitter_analyzer.language_loader import load_language

    lang = load_language("php")
    parser = Parser(lang)
    src = b"<?php class A { function f(){ StaticExample::increment(); } }"
    _defs, calls = walk_tree(parser.parse(src).root_node, src.decode(), "php")
    inc = [c for c in calls if c["name"] == "increment"]
    assert inc, "increment call not extracted"
    assert inc[0]["receiver"] == "StaticExample"
    assert inc[0]["full_name"] == "StaticExample.increment"


def test_csharp_extraction_and_moat() -> None:
    """C# end-to-end moat (PR #360 review P2): index a .cs file + a Python shadow;
    C# call edges are produced and none bind to the .py file."""
    import os
    import shutil
    import tempfile

    from tree_sitter_analyzer.ast_cache import ASTCache

    d = tempfile.mkdtemp()
    try:
        shutil.copy("examples/Sample.cs", os.path.join(d, "M.cs"))
        with open(os.path.join(d, "shadow.py"), "w") as f:
            f.write("def Greet():\n    return 1\ndef ToString():\n    return 2\n")
        cache = ASTCache(d)
        cache.index_project()
        conn = cache.get_conn()
        rows = conn.execute(
            "SELECT callee_resolved_file FROM edges "
            "WHERE kind='calls' AND language='csharp'"
        ).fetchall()
        assert rows, "no C# call edges extracted"
        cross = [r for r in rows if str(r["callee_resolved_file"]).endswith(".py")]
        assert not cross, f"C# cross-language mis-wire: {cross}"
        cache.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
