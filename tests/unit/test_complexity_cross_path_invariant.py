"""Cross-path cyclomatic-complexity invariant (RFC-0019 / #1094).

Every consumer must agree on a function's cyclomatic complexity:

- the **extractor** (``element.complexity_score``, used by ``--table`` and the
  golden masters — the single source of truth),
- the **live heatmap** (``complexity_heatmap.analyze_file_complexity``, used by
  the ``viz``/heatmap MCP tools and ``project_health``),
- the **cache-backed heatmap** (``analyze_file_complexity_from_cache``).

This was the #1094 inconsistency: the heatmap counted each ``switch`` arm
separately while the extractor counts the construct once (Java/JS: 2 vs 5).
RFC-0019 routes the heatmap count — live and cache — through the extractor's
``complexity_score``, so all three now agree by construction. These are enforced
invariants (they originally landed as strict-xfail documenting the gap).
"""

import importlib
import os
import tempfile

import pytest
import tree_sitter

from tree_sitter_analyzer._ast_extraction import _extract_symbols
from tree_sitter_analyzer.complexity_heatmap import (
    analyze_file_complexity,
    analyze_file_complexity_from_cache,
)
from tree_sitter_analyzer.language_loader import loader


def _parse(lang: str, src: str):
    tslang = loader.load_language(lang)
    parser = tree_sitter.Parser()
    try:
        parser.set_language(tslang)
    except Exception:  # pragma: no cover - tree-sitter API drift
        parser.language = tslang
    return parser.parse(src.encode())


def _extractor_cx(lang: str, src: str, mod: str, cls: str) -> dict[str, int]:
    tree = _parse(lang, src)
    extractor = getattr(importlib.import_module(mod), cls)()
    return {f.name: f.complexity_score for f in extractor.extract_functions(tree, src)}


def _live_cx(lang: str, src: str, filename: str) -> dict[str, int]:
    d = tempfile.mkdtemp()
    fp = os.path.join(d, filename)
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write(src)
    return {f.name: f.complexity for f in analyze_file_complexity(fp, lang)}


def _cache_cx(lang: str, src: str, filename: str) -> dict[str, int]:
    tree = _parse(lang, src)
    syms = _extract_symbols(tree, src, lang)

    class _FakeCache:
        def lookup(self, _fp):
            return {"symbols": syms, "language": lang}

    return {
        f.name: f.complexity
        for f in analyze_file_complexity_from_cache(_FakeCache(), filename)
    }


# (lang, filename, extractor module, extractor class, fn name, source).
# Each fixture has a multi-arm switch/match — the construct the heatmap used to
# over-count per arm.
_CASES = [
    (
        "java",
        "B.java",
        "tree_sitter_analyzer.languages.java_plugin",
        "JavaElementExtractor",
        "classify",
        "class B { int classify(int x){ switch(x){ case 1: return 1; "
        "case 2: return 2; case 3: return 3; default: return 0; } } }",
    ),
    (
        "javascript",
        "f.js",
        "tree_sitter_analyzer.languages.javascript_plugin.extractor",
        "JavaScriptElementExtractor",
        "classify",
        "function classify(x){ switch(x){ case 1: break; case 2: break; "
        "case 3: break; default: break; } }",
    ),
    (
        "typescript",
        "f.ts",
        "tree_sitter_analyzer.languages.typescript_plugin.extractor",
        "TypeScriptElementExtractor",
        "classify",
        "function classify(x: number){ switch(x){ case 1: break; case 2: break; "
        "case 3: break; default: break; } }",
    ),
    (
        "go",
        "f.go",
        "tree_sitter_analyzer.languages.go_plugin",
        "GoElementExtractor",
        "classify",
        "package m\nfunc classify(x int) int { switch x { case 1: case 2: "
        "case 3: }; return x }",
    ),
    (
        "rust",
        "f.rs",
        "tree_sitter_analyzer.languages.rust_plugin",
        "RustPlugin",
        "classify",
        "fn classify(x: i32) -> i32 { match x { 1 => 1, 2 => 2, _ => 0 } }",
    ),
]


@pytest.mark.parametrize("lang,fname,mod,cls,fn,src", _CASES)
def test_extractor_live_and_cache_all_agree(lang, fname, mod, cls, fn, src):
    if cls == "RustPlugin":
        tree = _parse(lang, src)
        ext_obj = getattr(importlib.import_module(mod), cls)().create_extractor()
        ext = {f.name: f.complexity_score for f in ext_obj.extract_functions(tree, src)}
    else:
        ext = _extractor_cx(lang, src, mod, cls)
    live = _live_cx(lang, src, fname)
    cache = _cache_cx(lang, src, fname)
    assert ext[fn] == live[fn], (
        f"{lang}: extractor {ext[fn]} != live heatmap {live[fn]}"
    )
    assert ext[fn] == cache[fn], (
        f"{lang}: extractor {ext[fn]} != cache heatmap {cache[fn]}"
    )
