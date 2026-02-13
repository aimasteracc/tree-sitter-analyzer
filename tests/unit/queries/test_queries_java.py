"""Tests for Java language queries."""
import pytest

try:
    import tree_sitter_java
    JAVA_AVAILABLE = True
except ImportError:
    JAVA_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import java as java_queries


def _lang():
    return get_language(tree_sitter_java.language())


SAMPLE_JAVA_CODE = """
import java.util.List;
import java.util.ArrayList;

public class Calculator {
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        Calculator calc = new Calculator();
        System.out.println(calc.add(1, 2));
    }
}

interface Shape {
    double area();
    double perimeter();
}

enum Color {
    RED, GREEN, BLUE
}

abstract class Animal {
    abstract void speak();
}
"""

# Keys to test individually (from ALL_QUERIES)
JAVA_KEYS_TO_TEST = [
    "class", "interface", "method", "import", "constructor",
    "field", "enum", "package", "annotation", "lambda",
]


def _get_query(module, key):
    """Get query string from ALL_QUERIES, returning None if not found."""
    all_q = module.ALL_QUERIES
    if key not in all_q:
        return None
    entry = all_q[key]
    return entry["query"] if isinstance(entry, dict) else entry


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="tree-sitter-java not available")
class TestJavaQueriesSyntax:
    """Test that Java queries compile successfully."""

    def test_all_queries_dict_compilable_count(self):
        import tree_sitter
        lang = _lang()
        all_q = java_queries.ALL_QUERIES
        assert len(all_q) > 0
        compiled, failed = 0, 0
        for _name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed)
        assert ratio >= 0.7, (
            f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"
        )

    @pytest.mark.parametrize("key", JAVA_KEYS_TO_TEST)
    def test_individual_query_compiles(self, key, query_validator):
        qstr = _get_query(java_queries, key)
        if qstr is None:
            pytest.skip(f"Key {key} not in ALL_QUERIES")
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="tree-sitter-java not available")
class TestJavaQueriesFunctionality:
    """Test that Java queries return expected results."""

    def test_class_query_finds_classes(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "class"))
        assert results is not None
        assert len(results) >= 2  # Calculator, Animal (Shape is interface, Color is enum)

    def test_interface_query_finds_interfaces(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "interface"))
        assert results is not None
        assert len(results) >= 1  # Shape

    def test_method_query_finds_methods(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "method"))
        assert results is not None
        assert len(results) >= 4  # add, main, area, perimeter, speak

    def test_import_query_finds_imports(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "import"))
        assert results is not None
        assert len(results) >= 2

    def test_constructor_query_finds_constructors(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "constructor"))
        assert results is not None
        assert len(results) >= 1

    def test_field_query_finds_fields(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "field"))
        assert results is not None
        assert len(results) >= 1

    def test_enum_query_finds_enums(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "enum"))
        assert results is not None
        assert len(results) >= 1

    def test_class_name_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "class_name"))
        assert results is not None
        assert len(results) >= 1

    def test_method_name_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_JAVA_CODE, _get_query(java_queries, "method_name"))
        assert results is not None
        assert len(results) >= 3


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="tree-sitter-java not available")
class TestJavaQueriesEdgeCases:
    """Test Java queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        qstr = _get_query(java_queries, "class")
        results = query_executor(_lang(), "", qstr)
        assert len(results) == 0

    def test_comments_only_returns_no_class_matches(self, query_executor):
        code = "// single line\n/* block comment */\n"
        results = query_executor(_lang(), code, _get_query(java_queries, "class"))
        assert len(results) == 0

    def test_single_import(self, query_executor):
        code = "import java.util.List;"
        results = query_executor(_lang(), code, _get_query(java_queries, "import"))
        assert len(results) >= 1

    def test_empty_class(self, query_executor):
        code = "public class Empty { }"
        results = query_executor(_lang(), code, _get_query(java_queries, "class"))
        assert len(results) >= 1

    def test_nested_class(self, query_executor):
        code = """
public class Outer {
    static class Inner {
        void method() {}
    }
}
"""
        results = query_executor(_lang(), code, _get_query(java_queries, "class"))
        assert len(results) >= 2


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="tree-sitter-java not available")
class TestJavaQueriesHelpers:
    """Test helper functions in the java queries module."""

    def test_get_query_valid(self):
        all_q = java_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = java_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            java_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = java_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = java_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_java_query_valid(self):
        available = java_queries.get_available_java_queries()
        if available:
            result = java_queries.get_java_query(available[0])
            assert isinstance(result, (str, dict))

    def test_get_java_query_invalid_raises(self):
        with pytest.raises(ValueError):
            java_queries.get_java_query("__nonexistent__")

    def test_get_java_query_description(self):
        available = java_queries.get_available_java_queries()
        if available:
            desc = java_queries.get_java_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_java_query_description_unknown(self):
        desc = java_queries.get_java_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_java_queries(self):
        result = java_queries.get_available_java_queries()
        assert isinstance(result, list)
        assert len(result) > 0
