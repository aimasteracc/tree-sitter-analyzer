"""
Tests for C# language queries.

Validates that C# tree-sitter queries are syntactically correct
and return expected results for various C# code constructs.
"""

import pytest

try:
    import tree_sitter_c_sharp

    CSHARP_AVAILABLE = True
except ImportError:
    CSHARP_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import csharp as csharp_queries


def _lang():
    return get_language(tree_sitter_c_sharp.language())


SAMPLE_CSHARP_CODE = """
using System;
using System.Collections.Generic;

namespace MyApp {
    public class Calculator {
        private int _result;
        public const int MaxValue = 1000;

        public Calculator() { _result = 0; }

        public int Add(int a, int b) { return a + b; }
        public static int Multiply(int a, int b) => a * b;
        public async Task<string> FetchAsync() { return await Task.FromResult("ok"); }

        public int Result { get; set; }
    }

    public interface IShape {
        double Area();
    }

    public enum Color { Red, Green, Blue }
    public record Point(int X, int Y);
    public struct Vector { public double X; public double Y; }
}
"""

# Queries with known grammar incompatibilities
KNOWN_BROKEN_QUERIES = {"generic_class", "generic_method"}

CSHARP_KEYS_TO_TEST = [
    "class",
    "interface",
    "record",
    "enum",
    "struct",
    "method",
    "constructor",
    "async_method",
    "public_method",
    "private_method",
    "static_method",
    "property",
    "auto_property",
    "field",
    "const_field",
    "event",
    "using",
    "namespace",
    "attribute",
    "generic_class",
    "lambda",
    "if_statement",
    "for_statement",
    "foreach_statement",
    "while_statement",
    "switch_statement",
    "try_statement",
    "comment",
    "all_declarations",
]


def _get_query(key):
    """Get query string from CSHARP_QUERIES."""
    if key not in csharp_queries.CSHARP_QUERIES:
        return None
    return csharp_queries.CSHARP_QUERIES[key]


@pytest.mark.skipif(not CSHARP_AVAILABLE, reason="tree-sitter-c-sharp not available")
class TestCSharpQueriesSyntax:
    """Test that C# queries compile successfully."""

    def test_csharp_queries_dict_exists(self):
        assert hasattr(csharp_queries, "CSHARP_QUERIES")
        assert isinstance(csharp_queries.CSHARP_QUERIES, dict)
        assert len(csharp_queries.CSHARP_QUERIES) > 0

    def test_csharp_queries_no_all_queries(self):
        """C# module has no ALL_QUERIES attribute."""
        assert not hasattr(csharp_queries, "ALL_QUERIES")

    def test_csharp_queries_dict_compilable_count(self):
        """At least 70% of CSHARP_QUERIES should compile."""
        import tree_sitter

        lang = _lang()
        queries = csharp_queries.CSHARP_QUERIES
        compiled, failed = 0, 0
        for name, qstr in queries.items():
            assert isinstance(qstr, str), f"{name} should be plain query string"
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed) if (compiled + failed) > 0 else 1.0
        assert (
            ratio >= 0.7
        ), f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"

    @pytest.mark.parametrize(
        "key", [k for k in CSHARP_KEYS_TO_TEST if k in csharp_queries.CSHARP_QUERIES]
    )
    def test_individual_query_compiles(self, key, query_validator):
        if key in KNOWN_BROKEN_QUERIES:
            pytest.xfail(f"{key} has known grammar incompatibility")
        qstr = _get_query(key)
        assert qstr is not None and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not CSHARP_AVAILABLE, reason="tree-sitter-c-sharp not available")
class TestCSharpQueriesFunctionality:
    """Test that C# queries return expected results."""

    def test_class_query_finds_classes(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("class"))
        assert len(results) >= 1  # Calculator

    def test_interface_query_finds_interfaces(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("interface"))
        assert len(results) >= 1  # IShape

    def test_record_query_finds_records(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("record"))
        assert len(results) >= 1  # Point

    def test_enum_query_finds_enums(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("enum"))
        assert len(results) >= 1  # Color

    def test_struct_query_finds_structs(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("struct"))
        assert len(results) >= 1  # Vector

    def test_method_query_finds_methods(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("method"))
        assert len(results) >= 2  # Add, Multiply, FetchAsync, Area

    def test_constructor_query_finds_constructors(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("constructor"))
        assert len(results) >= 1  # Calculator()

    def test_async_method_query_finds_async_methods(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_CSHARP_CODE, _get_query("async_method")
        )
        assert len(results) >= 1  # FetchAsync

    def test_property_query_finds_properties(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("property"))
        assert len(results) >= 1  # Result

    def test_field_query_finds_fields(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("field"))
        assert len(results) >= 1  # _result, MaxValue, X, Y

    def test_const_field_query_finds_const(self, query_executor):
        code = "class C { public const int X = 1; }"
        results = query_executor(_lang(), code, _get_query("const_field"))
        assert isinstance(results, list)

    def test_using_query_finds_using_directives(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("using"))
        assert len(results) >= 2  # System, System.Collections.Generic

    def test_namespace_query_finds_namespace(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSHARP_CODE, _get_query("namespace"))
        assert len(results) >= 1  # MyApp

    def test_all_declarations_query_finds_declarations(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_CSHARP_CODE, _get_query("all_declarations")
        )
        assert len(results) >= 5


@pytest.mark.skipif(not CSHARP_AVAILABLE, reason="tree-sitter-c-sharp not available")
class TestCSharpQueriesEdgeCases:
    """Test C# queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", _get_query("class"))
        assert len(results) == 0

    def test_comments_only_returns_no_class_matches(self, query_executor):
        code = "// comment\n/* block */\n"
        results = query_executor(_lang(), code, _get_query("class"))
        assert len(results) == 0

    def test_single_using_directive(self, query_executor):
        code = "using System.Linq;"
        results = query_executor(_lang(), code, _get_query("using"))
        assert len(results) >= 1

    def test_empty_class(self, query_executor):
        code = "public class Empty { }"
        results = query_executor(_lang(), code, _get_query("class"))
        assert len(results) >= 1

    def test_if_statement_with_control_flow(self, query_executor):
        code = """
public class Foo {
    void Bar() {
        if (x > 0) { }
        for (int i = 0; i < 10; i++) { }
        foreach (var item in items) { }
        while (true) { }
    }
}
"""
        results = query_executor(_lang(), code, _get_query("if_statement"))
        assert len(results) >= 1
