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
)

_CORPUS = {
    "kotlin": "tests/golden/corpus_kotlin.kt",
    "ruby": "tests/golden/corpus_ruby.rb",
    "php": "tests/golden/corpus_php.php",
}


@pytest.mark.parametrize("lang", ["csharp", "kotlin", "ruby", "php"])
def test_language_wired_into_extraction(lang: str) -> None:
    assert _CALL_NODE_TYPES.get(lang), f"{lang} missing from _CALL_NODE_TYPES"
    assert _FUNC_DEF_TYPES.get(lang), f"{lang} missing from _FUNC_DEF_TYPES"


@pytest.mark.parametrize(
    "lang,ext", [("kotlin", ".kt"), ("ruby", ".rb"), ("php", ".php")]
)
def test_extraction_produces_edges_and_moat_holds(lang: str, ext: str) -> None:
    """A real index of a corpus file + a Python shadow: the language's call edges
    are extracted, and NONE binds to the Python file (the cross-language moat)."""
    d = tempfile.mkdtemp()
    try:
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
