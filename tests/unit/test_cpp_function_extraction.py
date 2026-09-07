"""Regression tests: C++ function_definition nodes must be indexed.

BUG: extraction.py gated _c_function_def_name() to language=="c" only.
C++ shares the identical grammar shape (function_definition carries the
identifier inside function_declarator, not in a "name" field), so all
C++ free functions and class methods were absent from ast_symbol_rows.
"""

from __future__ import annotations

import sqlite3

import tree_sitter_cpp
from tree_sitter import Language, Parser

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.extraction import _extract_symbols

_CPP_PARSER = Parser(Language(tree_sitter_cpp.language()))


def _symbols(source: str) -> list[dict]:
    tree = _CPP_PARSER.parse(source.encode("utf-8"))
    return _extract_symbols(tree, source, "cpp")["symbols"]


CPP_SRC = """\
#include <iostream>

int add(int a, int b) {
    return a + b;
}

double multiply(double x, double y) {
    return x * y;
}

class Calculator {
public:
    Calculator() {}
    int compute(int n) { return n * 2; }
    static int zero() { return 0; }
};

void free_func() {}
"""


def test_cpp_free_functions_are_indexed() -> None:
    """Free C++ functions must produce function symbols."""
    symbols = _symbols(CPP_SRC)
    names = {s["name"] for s in symbols if s.get("kind") == "function"}
    assert "add" in names, f"add missing from cpp symbols: {names}"
    assert "multiply" in names, f"multiply missing: {names}"
    assert "free_func" in names, f"free_func missing: {names}"


def test_cpp_class_methods_are_indexed() -> None:
    """C++ class methods must be indexed with kind=method."""
    symbols = _symbols(CPP_SRC)
    methods = {s["name"] for s in symbols if s.get("kind") == "method"}
    assert "compute" in methods, f"compute missing from cpp methods: {methods}"
    assert "zero" in methods, f"zero missing: {methods}"


def test_cpp_function_line_numbers_correct() -> None:
    """Line numbers of C++ functions must match source."""
    symbols = _symbols(CPP_SRC)
    by_name = {s["name"]: s for s in symbols}
    assert by_name["add"]["line"] == 3, f"add line={by_name['add']['line']}"
    assert by_name["multiply"]["line"] == 7


def test_cpp_symbols_reach_sqlite(tmp_path) -> None:
    """C++ functions and methods must persist into ast_symbol_rows."""
    (tmp_path / "calc.cpp").write_text(CPP_SRC, encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project()

    con = sqlite3.connect(str(tmp_path / ".ast-cache" / "index.db"))
    try:
        rows = con.execute(
            "SELECT kind, name FROM ast_symbol_rows WHERE language='cpp' ORDER BY kind, name"
        ).fetchall()
        names_by_kind = {}
        for kind, name in rows:
            names_by_kind.setdefault(kind, set()).add(name)

        assert "function" in names_by_kind, f"no functions in cpp index: {rows}"
        assert "add" in names_by_kind["function"]
        assert "multiply" in names_by_kind["function"]
        assert "method" in names_by_kind, f"no methods in cpp index: {rows}"
        assert "compute" in names_by_kind["method"]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Kotlin companion object attribution (found during multi-language MECE check)
# ---------------------------------------------------------------------------


def test_kotlin_companion_object_members_attributed_to_outer_class() -> None:
    """Methods inside a companion object must be attributed to the enclosing class."""
    import tree_sitter_kotlin as _kt
    from tree_sitter import Language as _Lang
    from tree_sitter import Parser as _Parser

    from tree_sitter_analyzer.cache.extraction import _extract_symbols as _ex

    src = """\
class Person(val name: String) {
    companion object {
        fun createDefault(): Person = Person("Default")
    }
    fun greet() = name
}
"""
    tree = _Parser(_Lang(_kt.language())).parse(src.encode())
    symbols = _ex(tree, src, "kotlin")["symbols"]
    by_name = {s["name"]: s for s in symbols}

    create = by_name["createDefault"]
    assert create["kind"] == "method", f"expected method, got {create['kind']}"
    assert create["class"] == "Person", (
        f"expected class=Person, got {create.get('class')}"
    )

    greet = by_name["greet"]
    assert greet["kind"] == "method"
    assert greet["class"] == "Person"


# ---------------------------------------------------------------------------
# Java record_declaration (found during multi-language MECE check)
# ---------------------------------------------------------------------------


def test_java_record_methods_attributed_to_record() -> None:
    """Java 16+ record methods must be classified kind=method, not function."""
    import tree_sitter_java as _java
    from tree_sitter import Language as _Lang
    from tree_sitter import Parser as _Parser

    from tree_sitter_analyzer.cache.extraction import _extract_symbols as _ex

    src = """\
public record Point(int x, int y) {
    public double distance() {
        return Math.sqrt(x * x + y * y);
    }
    public static Point origin() {
        return new Point(0, 0);
    }
}
"""
    tree = _Parser(_Lang(_java.language())).parse(src.encode())
    symbols = _ex(tree, src, "java")["symbols"]
    by_name = {s["name"]: s for s in symbols}

    assert by_name["Point"]["kind"] == "class"
    assert by_name["distance"]["kind"] == "method"
    assert by_name["distance"]["class"] == "Point"
    assert by_name["origin"]["kind"] == "method"
    assert by_name["origin"]["class"] == "Point"
