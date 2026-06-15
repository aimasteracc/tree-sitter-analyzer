"""Scala language wiring — graduation test for the SCAFFOLDS_WITHOUT_EXT TODO.

2026-06-10: tree-sitter-scala grammar added as a dependency, ``"scala"``
registered in ``language_loader.LANGUAGE_MODULES`` + the detector's
``SUPPORTED_LANGUAGES``, and ``.scala`` wired into ``EXT_TO_LANG`` (the
ast_cache indexer path; detector/file_handler already mapped it).

Before this, ``.scala`` was the worst case in the Theme-D audit: the
extension was detected but no grammar existed, so the parse failed — and
prior to #414 the structure tools masked that as a phantom-empty success.

These tests pin the full chain: extension → detection → grammar load →
extraction → ast_cache indexing.
"""

from __future__ import annotations

import os
import shutil
import tempfile

CORPUS = "tests/golden/corpus_scala.scala"


def test_extension_detects_scala() -> None:
    from tree_sitter_analyzer.language_detector import detect_language_from_file

    assert detect_language_from_file("Main.scala") == "scala"


def test_lang_extension_map_has_scala() -> None:
    from tree_sitter_analyzer._lang_extension_map import EXT_TO_LANG

    assert EXT_TO_LANG.get(".scala") == "scala"


def test_sc_extension_stays_unknown() -> None:
    """``.sc`` is deliberately NOT wired (ambiguous with SuperCollider) even
    though ``ScalaPlugin.get_file_extensions()`` lists it. Pin the documented
    behavior: detection returns unknown; an explicit ``language="scala"``
    override remains the supported route for Scala scripts / Ammonite."""
    from tree_sitter_analyzer._lang_extension_map import EXT_TO_LANG
    from tree_sitter_analyzer.language_detector import detect_language_from_file

    assert ".sc" not in EXT_TO_LANG
    assert detect_language_from_file("script.sc") == "unknown"


def test_loader_provides_scala_language() -> None:
    from tree_sitter_analyzer.language_loader import loader

    assert loader.is_language_available("scala"), (
        "tree-sitter-scala must be importable (declared dependency)"
    )
    assert loader.load_language("scala") is not None


def test_scala_corpus_extracts_symbols() -> None:
    """The golden scala corpus must yield real symbols, not phantom-empty."""
    import tree_sitter

    from tree_sitter_analyzer.languages.scala_plugin import ScalaPlugin

    plugin = ScalaPlugin()
    lang = plugin.get_tree_sitter_language()
    assert lang is not None
    parser = tree_sitter.Parser(lang)
    with open(CORPUS, "rb") as f:
        src = f.read()
    tree = parser.parse(src)
    assert not tree.root_node.has_error, "corpus must parse cleanly"
    elements = plugin.extract_elements(tree, src.decode())
    # Validated 2026-06-10 against tree-sitter-scala 0.26. Exact pins
    # (user rule 2026-06-10: no >=-style approximate assertions) — a
    # grammar-version bump that changes these counts MUST fail the test
    # and force a conscious re-pin, not pass silently.
    assert len(elements["functions"]) == 66
    assert (
        len(elements["classes"]) == 38
    )  # +5 from enum/given/type extraction (#762 #764)
    assert len(elements["imports"]) == 3


def test_ast_cache_indexes_scala_file() -> None:
    """The project indexer must index .scala files without errors."""
    from tree_sitter_analyzer.ast_cache import ASTCache

    d = tempfile.mkdtemp()
    try:
        shutil.copy(CORPUS, os.path.join(d, "Main.scala"))
        cache = ASTCache(d)
        cache.index_project()
        conn = cache.get_conn()
        count = conn.execute("SELECT COUNT(*) FROM ast_symbol_rows").fetchone()[0]
        # Repinned 2026-06-15: Scala object/trait/enum/given/type symbols are
        # now indexed in the AST cache instead of only the plugin extractor.
        assert count == 107, f"expected exactly 107 scala symbols indexed, got {count}"
        cache.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
