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
    from tree_sitter_analyzer.languages.lang_extension_map import EXT_TO_LANG

    assert EXT_TO_LANG.get(".scala") == "scala"


def test_sc_extension_stays_unknown() -> None:
    """``.sc`` is deliberately NOT wired (ambiguous with SuperCollider) even
    though ``ScalaPlugin.get_file_extensions()`` lists it. Pin the documented
    behavior: detection returns unknown; an explicit ``language="scala"``
    override remains the supported route for Scala scripts / Ammonite."""
    from tree_sitter_analyzer.language_detector import detect_language_from_file
    from tree_sitter_analyzer.languages.lang_extension_map import EXT_TO_LANG

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


def test_ast_cache_path_excludes_method_local_given_and_type() -> None:
    """#961: the shared ast_cache walk (``_extract_symbols``) must NOT emit a
    ``given``/``type`` declared inside a method body as a top-level symbol —
    matching the plugin path (``test_local_given_and_type_inside_method_are_
    not_members``). Top-level constructs in the same file still ARE emitted.
    """
    import tree_sitter

    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.languages.scala_plugin import ScalaPlugin

    code = """object Ops:
  def configure(): Unit =
    given localOrdering: Ordering[Int] = Ordering.Int
    type LocalAlias = String

  given topGiven: Int = 1
  type TopAlias = String
"""
    lang = ScalaPlugin().get_tree_sitter_language()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(code.encode("utf-8"))
    names = [s["name"] for s in _extract_symbols(tree, code, "scala")["symbols"]]

    # Method-local declarations must NOT leak as top-level symbols.
    assert "localOrdering" not in names
    assert "LocalAlias" not in names
    # Top-level constructs in the same file are still emitted.
    assert "Ops" in names
    assert "topGiven" in names
    assert "TopAlias" in names


# ---------------------------------------------------------------------------
# #972: ast_cache symbol-extraction helpers (_scala_symbol_from_node /
# _scala_symbol_name / _scala_given_type_text). These mirror the plugin
# helpers but live on the shared ast_cache walk; the branches differ, so
# they are covered independently here.
# ---------------------------------------------------------------------------


def _scala_node(code: str, node_type: str):
    """Return the first ``node_type`` node in a parsed Scala snippet."""
    import tree_sitter

    from tree_sitter_analyzer.languages.scala_plugin import ScalaPlugin

    lang = ScalaPlugin().get_tree_sitter_language()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(code.encode("utf-8"))

    def find(node):
        if node.type == node_type:
            return node
        for child in node.children:
            hit = find(child)
            if hit is not None:
                return hit
        return None

    return find(tree.root_node)


def test_ast_cache_symbol_from_node_object_is_class() -> None:
    from tree_sitter_analyzer.cache.extraction import _scala_symbol_from_node

    code = "object Box:\n  val x = 1\n"
    node = _scala_node(code, "object_definition")
    sym = _scala_symbol_from_node(node, code)
    assert sym is not None
    assert sym["kind"] == "class"
    assert sym["name"] == "Box"


def test_ast_cache_symbol_from_node_enum_is_enum() -> None:
    from tree_sitter_analyzer.cache.extraction import _scala_symbol_from_node

    code = "enum Color:\n  case Red\n"
    node = _scala_node(code, "enum_definition")
    sym = _scala_symbol_from_node(node, code)
    assert sym is not None
    assert sym["kind"] == "enum"
    assert sym["name"] == "Color"


def test_ast_cache_symbol_from_node_rejects_non_class_like() -> None:
    """A node outside ``_SCALA_CLASS_LIKE`` (e.g. the bare ``enum`` keyword)
    returns None (line 877-878 guard)."""
    from tree_sitter_analyzer.cache.extraction import _scala_symbol_from_node

    code = "enum Color:\n  case Red\n"
    keyword = _scala_node(code, "enum")
    assert _scala_symbol_from_node(keyword, code) is None


def test_ast_cache_symbol_name_uses_identifier_child_for_object() -> None:
    """``object_definition`` exposes no ``name`` field, so the identifier-child
    fallback path (line 895-897) resolves the name."""
    from tree_sitter_analyzer.cache.extraction import _scala_symbol_name

    code = "object Box:\n  val x = 1\n"
    node = _scala_node(code, "object_definition")
    assert _scala_symbol_name(node, code) == "Box"


def test_ast_cache_symbol_name_named_given_via_type() -> None:
    from tree_sitter_analyzer.cache.extraction import _scala_symbol_name

    code = "object O:\n  given Ordering[Int] = ???\n"
    node = _scala_node(code, "given_definition")
    assert _scala_symbol_name(node, code) == "given Ordering[Int]"


def test_ast_cache_symbol_name_degenerate_given_is_empty() -> None:
    """``given = 1`` parses with an empty ``type_identifier`` child, so the
    identifier-child branch (line 895-897) returns ``""`` — distinct from the
    plugin path which line-numbers it. The empty name then trips the
    ``if not name`` guard in ``_scala_symbol_from_node`` (line 880-881)."""
    from tree_sitter_analyzer.cache.extraction import (
        _scala_symbol_from_node,
        _scala_symbol_name,
    )

    code = "object O:\n  given = 1\n"
    node = _scala_node(code, "given_definition")
    assert _scala_symbol_name(node, code) == ""
    # Empty name => the class-like guard rejects the node.
    assert _scala_symbol_from_node(node, code) is None


def test_ast_cache_given_type_text_resolves_tuple_type() -> None:
    from tree_sitter_analyzer.cache.extraction import _scala_given_type_text

    code = "object O:\n  given (Int, String) = ???\n"
    node = _scala_node(code, "given_definition")
    assert _scala_given_type_text(node, code) == "(Int, String)"


def test_ast_cache_given_type_text_resolves_generic_type() -> None:
    from tree_sitter_analyzer.cache.extraction import _scala_given_type_text

    code = "object O:\n  given Ordering[Int] = ???\n"
    node = _scala_node(code, "given_definition")
    assert _scala_given_type_text(node, code) == "Ordering[Int]"
