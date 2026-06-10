"""Bash language wiring — graduation test for the SCAFFOLDS_WITHOUT_EXT TODO.

2026-06-10: tree-sitter-bash grammar added as a dependency and ``.sh`` /
``.bash`` / ``.zsh`` wired across the three extension maps
(``language_detector`` / ``_lang_extension_map`` / ``file_handler``) plus the
``language_loader`` module map. Before this, every shell file was either
undetectable (CLI: "Could not detect language") or — worse — would have been
masked as an empty-success by the structure tools (Theme D, fixed in #414).

These tests pin the full chain: extension → detection → grammar load →
extraction → ast_cache indexing.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

CORPUS = "tests/golden/corpus_bash.sh"


@pytest.mark.parametrize("ext", [".sh", ".bash", ".zsh"])
def test_extension_detects_bash(ext: str) -> None:
    from tree_sitter_analyzer.language_detector import detect_language_from_file

    assert detect_language_from_file(f"script{ext}") == "bash"


def test_lang_extension_map_has_bash() -> None:
    from tree_sitter_analyzer._lang_extension_map import EXT_TO_LANG

    assert EXT_TO_LANG.get(".sh") == "bash"
    assert EXT_TO_LANG.get(".bash") == "bash"
    assert EXT_TO_LANG.get(".zsh") == "bash"


def test_loader_provides_bash_language() -> None:
    from tree_sitter_analyzer.language_loader import loader

    assert loader.is_language_available("bash"), (
        "tree-sitter-bash must be importable (declared dependency)"
    )
    assert loader.load_language("bash") is not None


def test_bash_corpus_extracts_functions() -> None:
    """The golden bash corpus must yield its function definitions."""
    import tree_sitter

    from tree_sitter_analyzer.languages.bash_plugin import BashPlugin

    plugin = BashPlugin()
    lang = plugin.get_tree_sitter_language()
    assert lang is not None
    parser = tree_sitter.Parser(lang)
    with open(CORPUS, "rb") as f:
        src = f.read()
    tree = parser.parse(src)
    elements = plugin.extract_elements(tree, src.decode())
    # corpus_bash_expected.json records 11 function_definition nodes.
    # Exact pin (user rule 2026-06-10: no >=-style approximate assertions) —
    # a grammar-version bump that changes this count MUST fail the test and
    # force a conscious re-pin, not pass silently.
    assert len(elements["functions"]) == 11


def test_ast_cache_indexes_sh_file() -> None:
    """The project indexer must index .sh files without errors."""
    from tree_sitter_analyzer.ast_cache import ASTCache

    d = tempfile.mkdtemp()
    try:
        shutil.copy(CORPUS, os.path.join(d, "deploy.sh"))
        cache = ASTCache(d)
        cache.index_project()
        conn = cache.get_conn()
        count = conn.execute("SELECT COUNT(*) FROM ast_symbol_rows").fetchone()[0]
        assert count == 11, f"expected exactly 11 bash symbols indexed, got {count}"
        cache.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
