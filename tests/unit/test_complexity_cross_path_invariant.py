"""Cross-path cyclomatic-complexity invariant (RFC-0019 / #1094).

The extractor (``element.complexity_score``, used by ``--table`` and the golden
masters) and the heatmap path (``complexity_heatmap.analyze_file_complexity``,
used by the ``viz``/heatmap MCP tools and ``project_health``) must agree on the
cyclomatic complexity of the same function.

Today they do NOT: the heatmap path counts each ``switch`` arm separately while
the extractor counts the construct once. These tests pin that invariant as a
*strict xfail* — they document the known inconsistency as an executable,
falsifiable contract. When RFC-0019 routes both paths through one source of
truth, ``strict=True`` makes them fail-as-xpass, forcing the xfail marker to be
removed in the same change.
"""

import os
import tempfile

import pytest
import tree_sitter

from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity
from tree_sitter_analyzer.language_loader import loader


def _extractor_cx(lang: str, src: str, mod: str, cls: str) -> dict[str, int]:
    import importlib

    tslang = loader.load_language(lang)
    parser = tree_sitter.Parser()
    try:
        parser.set_language(tslang)
    except Exception:  # pragma: no cover - tree-sitter API drift
        parser.language = tslang
    tree = parser.parse(src.encode())
    extractor = getattr(importlib.import_module(mod), cls)()
    return {f.name: f.complexity_score for f in extractor.extract_functions(tree, src)}


def _heatmap_cx(lang: str, src: str, filename: str) -> dict[str, int]:
    d = tempfile.mkdtemp()
    fp = os.path.join(d, filename)
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write(src)
    return {f.name: f.complexity for f in analyze_file_complexity(fp, lang)}


_JAVA_SWITCH = (
    "class B { int classify(int x){ switch(x){ case 1: return 1; "
    "case 2: return 2; case 3: return 3; default: return 0; } } }"
)
_JS_SWITCH = (
    "function classify(x){ switch(x){ case 1: break; case 2: break; "
    "case 3: break; default: break; } }"
)


@pytest.mark.xfail(
    strict=True,
    reason="#1094 / RFC-0019: heatmap path counts switch per-case; extractor counts once",
)
def test_java_switch_extractor_and_heatmap_agree():
    ext = _extractor_cx(
        "java",
        _JAVA_SWITCH,
        "tree_sitter_analyzer.languages.java_plugin",
        "JavaElementExtractor",
    )
    heat = _heatmap_cx("java", _JAVA_SWITCH, "B.java")
    assert ext["classify"] == heat["classify"]


@pytest.mark.xfail(
    strict=True,
    reason="#1094 / RFC-0019: heatmap path counts switch per-case; extractor counts once",
)
def test_js_switch_extractor_and_heatmap_agree():
    ext = _extractor_cx(
        "javascript",
        _JS_SWITCH,
        "tree_sitter_analyzer.languages.javascript_plugin.extractor",
        "JavaScriptElementExtractor",
    )
    heat = _heatmap_cx("javascript", _JS_SWITCH, "classify.js")
    assert ext["classify"] == heat["classify"]
