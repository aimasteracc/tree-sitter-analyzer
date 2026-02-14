"""Tests for Go language queries."""

import pytest

try:
    import tree_sitter_go

    GO_AVAILABLE = True
except ImportError:
    GO_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import go as go_queries


def _lang():
    return get_language(tree_sitter_go.language())


SAMPLE_GO_CODE = """
package main

import (
    "fmt"
    "strings"
)

type Animal struct {
    Name string
    Age  int
}

type Speaker interface {
    Speak() string
}

func (a Animal) Speak() string {
    return fmt.Sprintf("I am %s", a.Name)
}

func add(a, b int) int {
    return a + b
}

func main() {
    animal := Animal{Name: "Dog", Age: 5}
    fmt.Println(animal.Speak())

    numbers := []int{1, 2, 3, 4, 5}
    for _, n := range numbers {
        fmt.Println(n)
    }
}

const MaxSize = 100
var globalCount int
"""

# Keys to test individually
GO_KEYS_TO_TEST = [
    "package",
    "import",
    "function",
    "method",
    "struct",
    "interface",
    "const",
    "var",
    "for",
    "defer",
]


def _get_query(module, key):
    """Get query string from ALL_QUERIES."""
    all_q = module.ALL_QUERIES
    if key not in all_q:
        return None
    entry = all_q[key]
    return entry["query"] if isinstance(entry, dict) else entry


@pytest.mark.skipif(not GO_AVAILABLE, reason="tree-sitter-go not available")
class TestGoQueriesSyntax:
    """Test that Go queries compile successfully."""

    def test_all_queries_dict_compilable_count(self):
        import tree_sitter

        lang = _lang()
        all_q = go_queries.ALL_QUERIES
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
        assert (
            ratio >= 0.7
        ), f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"

    @pytest.mark.parametrize("key", GO_KEYS_TO_TEST)
    def test_individual_query_compiles(self, key, query_validator):
        qstr = _get_query(go_queries, key)
        if qstr is None:
            pytest.skip(f"Key {key} not in ALL_QUERIES")
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not GO_AVAILABLE, reason="tree-sitter-go not available")
class TestGoQueriesFunctionality:
    """Test that Go queries return expected results."""

    def test_package_query_finds_package(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "package")
        )
        assert len(results) >= 1

    def test_import_query_finds_imports(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "import")
        )
        assert len(results) >= 1

    def test_function_query_finds_functions(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "function")
        )
        assert len(results) >= 2  # add, main (Speak is a method)

    def test_method_query_finds_methods(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "method")
        )
        assert len(results) >= 1  # Speak

    def test_struct_query_finds_structs(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "struct")
        )
        assert len(results) >= 1

    def test_interface_query_finds_interfaces(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "interface")
        )
        assert len(results) >= 1

    def test_const_query_finds_constants(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "const")
        )
        assert len(results) >= 1

    def test_var_query_finds_variables(self, query_executor):
        results = query_executor(_lang(), SAMPLE_GO_CODE, _get_query(go_queries, "var"))
        assert len(results) >= 1

    def test_for_query_finds_loops(self, query_executor):
        results = query_executor(_lang(), SAMPLE_GO_CODE, _get_query(go_queries, "for"))
        assert len(results) >= 1

    def test_function_name_query(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "function_name")
        )
        assert len(results) >= 2  # add, main (Speak is a method)

    def test_struct_name_query(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "struct_name")
        )
        assert len(results) >= 1

    def test_interface_name_query(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_GO_CODE, _get_query(go_queries, "interface_name")
        )
        assert len(results) >= 1


@pytest.mark.skipif(not GO_AVAILABLE, reason="tree-sitter-go not available")
class TestGoQueriesEdgeCases:
    """Test Go queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", _get_query(go_queries, "function"))
        assert len(results) == 0

    def test_comments_only_returns_no_function_matches(self, query_executor):
        code = "// comment only\n"
        results = query_executor(_lang(), code, _get_query(go_queries, "function"))
        assert len(results) == 0

    def test_single_package(self, query_executor):
        code = "package main"
        results = query_executor(_lang(), code, _get_query(go_queries, "package"))
        assert len(results) >= 1

    def test_empty_struct(self, query_executor):
        code = "package p\n\ntype Empty struct {}"
        results = query_executor(_lang(), code, _get_query(go_queries, "struct"))
        assert len(results) >= 1

    def test_empty_interface(self, query_executor):
        code = "package p\n\ntype Empty interface {}"
        results = query_executor(_lang(), code, _get_query(go_queries, "interface"))
        assert len(results) >= 1

    def test_multiple_imports(self, query_executor):
        code = 'package p\n\nimport (\n    "fmt"\n    "os"\n)'
        results = query_executor(_lang(), code, _get_query(go_queries, "import"))
        assert len(results) >= 1


@pytest.mark.skipif(not GO_AVAILABLE, reason="tree-sitter-go not available")
class TestGoQueriesHelpers:
    """Test helper functions in the go queries module."""

    def test_get_query_valid(self):
        all_q = go_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = go_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            go_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = go_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = go_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_go_query_valid(self):
        available = go_queries.get_available_go_queries()
        if available:
            result = go_queries.get_go_query(available[0])
            assert isinstance(result, str | dict)

    def test_get_go_query_invalid_raises(self):
        with pytest.raises(ValueError):
            go_queries.get_go_query("__nonexistent__")

    def test_get_go_query_description(self):
        available = go_queries.get_available_go_queries()
        if available:
            desc = go_queries.get_go_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_go_query_description_unknown(self):
        desc = go_queries.get_go_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_go_queries(self):
        result = go_queries.get_available_go_queries()
        assert isinstance(result, list)
        assert len(result) > 0
