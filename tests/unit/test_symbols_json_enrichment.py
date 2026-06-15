"""Issue #614 — docstring/return_type/params serialized into symbols_json.

RFC-0016 prerequisite: the embedding input
``"{kind} {qualified_name}({params}) -> {return_type}\\n{docstring}"`` must be
constructible from the cache. The raw-AST walker (``_walk_for_symbols``) is
the path that feeds ``ast_index.symbols_json`` — it already carries ``params``
but dropped docstring/return_type.

The BM25-enrichment arm (docstring tokens in a low-weight FTS column) was
implemented, measured on the RFC-0016 pilot query set at weights 1.0 and
0.3, and REJECTED: no conceptual gap closed, control-query regressions at
both weights. Only the serialization half ships; pilot data on #517.
"""

from __future__ import annotations

from tree_sitter_analyzer._ast_extraction import (
    _DOCSTRING_MAX_CHARS,
)


def _symbols_for(source: str, lang: str) -> list[dict]:
    from tree_sitter_analyzer._ast_extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    result = Parser().parse_code(source, lang)
    assert result.success and result.tree is not None
    return _extract_symbols(result.tree, source, lang)["symbols"]


_PY_SRC = '''\
"""Module docstring — must NOT become a symbol docstring."""

CACHE_TTL = 60


def dispatch(request: dict, *, strict: bool = False) -> str:
    """Route an incoming request to the matching facade action."""
    return "ok"


def no_doc(x):
    return x


class Router:
    """Holds the routing table for tool dispatch."""

    def handle(self, name):
        """Resolve name and invoke the handler."""
        return name

    def _bare(self):
        pass
'''


class TestPythonDocstringSerialized:
    def _by_name(self) -> dict[str, dict]:
        return {s["name"]: s for s in _symbols_for(_PY_SRC, "python") if "name" in s}

    def test_function_docstring_serialized(self):
        syms = self._by_name()
        assert (
            syms["dispatch"]["docstring"]
            == "Route an incoming request to the matching facade action."
        )

    def test_method_docstring_serialized(self):
        syms = self._by_name()
        assert syms["handle"]["docstring"] == "Resolve name and invoke the handler."

    def test_class_docstring_serialized(self):
        syms = self._by_name()
        assert (
            syms["Router"]["docstring"] == "Holds the routing table for tool dispatch."
        )

    def test_absent_docstring_field_absent_not_empty_string(self):
        syms = self._by_name()
        assert "docstring" not in syms["no_doc"]
        assert "docstring" not in syms["_bare"]

    def test_docstring_capped_at_exactly_500_chars(self):
        assert _DOCSTRING_MAX_CHARS == 500
        long_doc = "x" * 600
        src = f'def f():\n    """{long_doc}"""\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert len(syms["f"]["docstring"]) == 500
        assert syms["f"]["docstring"] == "x" * 500

    def test_whitespace_only_docstring_field_absent(self):
        src = 'def f():\n    """   """\n    return 1\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert "docstring" not in syms["f"]

    def test_incomplete_function_without_body_is_safe(self):
        # tree-sitter error recovery: `def f():` with no body must not crash
        # the docstring helper and must not emit a docstring key.
        syms = {
            s["name"]: s for s in _symbols_for("def f():\n", "python") if "name" in s
        }
        assert "docstring" not in syms["f"]

    def test_multiline_docstring_stripped_and_preserved(self):
        src = 'def f():\n    """First line.\n\n    Body detail.\n    """\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert syms["f"]["docstring"] == "First line.\n\n    Body detail."


class TestReturnTypeAndParamsSerialized:
    def _by_name(self) -> dict[str, dict]:
        return {s["name"]: s for s in _symbols_for(_PY_SRC, "python") if "name" in s}

    def test_return_type_serialized(self):
        syms = self._by_name()
        assert syms["dispatch"]["return_type"] == "str"

    def test_absent_return_type_field_absent(self):
        syms = self._by_name()
        assert "return_type" not in syms["no_doc"]

    def test_params_already_serialized(self):
        syms = self._by_name()
        assert syms["dispatch"]["params"] == "(request: dict, *, strict: bool = False)"

    def test_rust_return_type_serialized(self):
        src = "fn add(a: i32, b: i32) -> i32 { a + b }\n"
        syms = {s["name"]: s for s in _symbols_for(src, "rust") if "name" in s}
        assert syms["add"]["return_type"] == "i32"

    def test_non_python_function_has_no_docstring(self):
        src = 'function f() { return "doc-like string"; }\n'
        syms = {s["name"]: s for s in _symbols_for(src, "javascript") if "name" in s}
        assert "docstring" not in syms["f"]


class TestExtractorVersionBump:
    def test_extractor_version_is_12_in_both_sites(self):
        # v12: #779 — walker depth cap raised 20 -> 100; bump forces re-index.
        from tree_sitter_analyzer import _ast_cache_indexer, ast_cache

        assert ast_cache._AST_CACHE_EXTRACTOR_VERSION == 12
        assert _ast_cache_indexer._AST_CACHE_EXTRACTOR_VERSION == 12


class TestCodexP2sOn621:
    def test_concatenated_string_docstring_preserved(self):
        src = 'def f():\n    "first " "second"\n    return 1\n'
        syms = {x["name"]: x for x in _symbols_for(src, "python")}
        assert syms["f"]["docstring"] == "first second"

    def test_typescript_return_annotation_stripped(self):
        src = "function f(): string { return 'x'; }\n"
        syms = {x["name"]: x for x in _symbols_for(src, "typescript")}
        assert syms["f"]["return_type"] == "string"
