"""Codex P2 — abstract_method_signature reaches FUNCTIONS/SIGNATURES query path.

Issue #459 surfaced that ``abstract_method_signature`` was registered only in
``extract_functions()`` (the plugin extractor path) but NOT in:

  * ``FUNCTIONS`` query string (used by ``--query functions`` / ``search action=symbol``)
  * ``SIGNATURES`` query string (used by ``--query signatures``)
  * ``TypeScriptPlugin.get_element_categories()`` (walked by plugin_category_captures)

This file pins those three invariants with RED-first assertions.
All three assertions must stay exact (== N), per CLAUDE.md locked rule.
"""

from __future__ import annotations

import tree_sitter
from tree_sitter_typescript import language_typescript

from tree_sitter_analyzer.languages.typescript_plugin.plugin import TypeScriptPlugin
from tree_sitter_analyzer.queries import typescript as ts_queries
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ABSTRACT_SRC = """\
abstract class Base {
    abstract validate(): boolean;
    public abstract doThing(x: string): void;
    protected abstract transform(n: number): string;
}
"""


def _lang() -> tree_sitter.Language:
    return tree_sitter.Language(language_typescript())


def _parse(src: str) -> tree_sitter.Tree:
    lang = _lang()
    parser = tree_sitter.Parser(lang)
    return parser.parse(src.encode())


def _run_query(query_string: str, src: str) -> list[tuple[object, str]]:
    """Execute a tree-sitter query string against *src* and return captures."""
    tree = _parse(src)
    return TreeSitterQueryCompat.safe_execute_query(
        _lang(), query_string, tree.root_node, fallback_result=[]
    )


# ---------------------------------------------------------------------------
# I-1  FUNCTIONS query must capture abstract_method_signature nodes
# ---------------------------------------------------------------------------


def test_functions_query_contains_abstract_method_signature_pattern() -> None:
    """FUNCTIONS string must reference abstract_method_signature so the query
    path can capture abstract method declarations without a body."""
    assert "abstract_method_signature" in ts_queries.FUNCTIONS, (
        "FUNCTIONS query is missing abstract_method_signature — "
        "--query functions returns no captures for abstract-only members"
    )


def test_functions_query_captures_abstract_methods_exact_count() -> None:
    """Running FUNCTIONS against a 3-abstract-method snippet must yield exactly 3
    captures whose capture-name is 'abstract.method' (or similar function group)."""
    captures = _run_query(ts_queries.FUNCTIONS, _ABSTRACT_SRC)
    # Filter to captures that correspond to abstract_method_signature nodes
    abstract_captures = [
        (node, cap)
        for node, cap in captures
        if node.type == "abstract_method_signature"
    ]
    assert len(abstract_captures) == 3, (
        f"Expected 3 abstract_method_signature captures from FUNCTIONS query, "
        f"got {len(abstract_captures)}: {[(n.text[:40], c) for n, c in abstract_captures]}"
    )


# ---------------------------------------------------------------------------
# I-2  SIGNATURES query must capture abstract_method_signature nodes
# ---------------------------------------------------------------------------


def test_signatures_query_contains_abstract_method_signature_pattern() -> None:
    """SIGNATURES string must reference abstract_method_signature."""
    assert "abstract_method_signature" in ts_queries.SIGNATURES, (
        "SIGNATURES query is missing abstract_method_signature"
    )


def test_signatures_query_captures_abstract_methods_exact_count() -> None:
    """Running SIGNATURES against the 3-abstract-method snippet must yield
    exactly 3 captures for abstract_method_signature nodes."""
    captures = _run_query(ts_queries.SIGNATURES, _ABSTRACT_SRC)
    abstract_captures = [
        (node, cap)
        for node, cap in captures
        if node.type == "abstract_method_signature"
    ]
    assert len(abstract_captures) == 3, (
        f"Expected 3 abstract_method_signature captures from SIGNATURES query, "
        f"got {len(abstract_captures)}"
    )


# ---------------------------------------------------------------------------
# I-3  get_element_categories() must list abstract_method_signature
# ---------------------------------------------------------------------------


def test_get_element_categories_method_includes_abstract_method_signature() -> None:
    """TypeScriptPlugin.get_element_categories()['method'] must include
    'abstract_method_signature' so plugin_category_captures finds them."""
    plugin = TypeScriptPlugin()
    cats = plugin.get_element_categories()
    method_types = cats.get("method", [])
    assert "abstract_method_signature" in method_types, (
        f"'abstract_method_signature' missing from get_element_categories()['method']; "
        f"got {method_types}"
    )


def test_get_element_categories_signature_includes_abstract_method_signature() -> None:
    """TypeScriptPlugin.get_element_categories()['signature'] must include
    'abstract_method_signature' so signature-category queries find them."""
    plugin = TypeScriptPlugin()
    cats = plugin.get_element_categories()
    sig_types = cats.get("signature", [])
    assert "abstract_method_signature" in sig_types, (
        f"'abstract_method_signature' missing from get_element_categories()['signature']; "
        f"got {sig_types}"
    )
