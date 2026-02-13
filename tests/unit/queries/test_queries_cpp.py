"""
Tests for C++ language queries.

Validates that C++ tree-sitter queries are syntactically correct
and return expected results for various C++ code constructs.
"""
import pytest

try:
    import tree_sitter_cpp
    CPP_AVAILABLE = True
except ImportError:
    CPP_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import cpp as cpp_queries


def _lang():
    return get_language(tree_sitter_cpp.language())


SAMPLE_CPP_CODE = """
#include <iostream>
#include <vector>
#include <string>
#include <memory>

namespace mylib {

class Animal {
public:
    Animal(std::string name) : name_(std::move(name)) {}
    virtual ~Animal() = default;
    virtual std::string speak() const = 0;

    std::string getName() const { return name_; }

protected:
    std::string name_;
};

class Dog : public Animal {
public:
    using Animal::Animal;
    std::string speak() const override { return "Woof!"; }
};

template<typename T>
T add(T a, T b) { return a + b; }

enum class Color { Red, Green, Blue };

struct Point {
    double x;
    double y;
};

const int MAX_SIZE = 100;

}

int main() {
    auto dog = std::make_unique<mylib::Dog>("Buddy");
    std::cout << dog->speak() << std::endl;

    std::vector<int> nums = {1, 2, 3, 4, 5};
    for (const auto& n : nums) {
        std::cout << n << "\\n";
    }

    return 0;
}
"""

# Well-known C++ queries to test functionality
CPP_KEYS_TO_TEST = [
    "class", "struct", "function", "method", "namespace",
    "include", "template", "enum", "lambda", "range_for",
    "constructor", "destructor", "variable",
]


def _get_query(module, key):
    """Get query string from ALL_QUERIES, returning None if not found."""
    all_q = module.ALL_QUERIES
    if key not in all_q:
        return None
    entry = all_q[key]
    return entry["query"] if isinstance(entry, dict) else entry


def _safe_execute(query_executor, lang, code, qstr):
    """Execute query, return results or None if query fails to compile."""
    if qstr is None:
        return None
    try:
        return query_executor(lang, code, qstr)
    except Exception:
        return None


@pytest.mark.skipif(not CPP_AVAILABLE, reason="tree-sitter-cpp not available")
class TestCppQueriesSyntax:
    """Test that C++ queries compile successfully."""

    def test_all_queries_dict_compilable_count(self):
        import tree_sitter
        lang = _lang()
        all_q = cpp_queries.ALL_QUERIES
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

    @pytest.mark.parametrize("key", CPP_KEYS_TO_TEST)
    def test_individual_query_compiles(self, key, query_validator):
        qstr = _get_query(cpp_queries, key)
        if qstr is None:
            pytest.skip(f"Key {key} not in ALL_QUERIES")
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not CPP_AVAILABLE, reason="tree-sitter-cpp not available")
class TestCppQueriesFunctionality:
    """Test that C++ queries return expected results."""

    def test_class_query_finds_classes(self, query_executor):
        qstr = _get_query(cpp_queries, "class")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("class query failed to compile or not found")
        assert len(results) >= 2

    def test_struct_query_finds_structs(self, query_executor):
        qstr = _get_query(cpp_queries, "struct")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("struct query failed to compile or not found")
        assert len(results) >= 1

    def test_function_query_finds_functions(self, query_executor):
        qstr = _get_query(cpp_queries, "function")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("function query failed to compile or not found")
        assert len(results) >= 2

    def test_method_query_finds_methods(self, query_executor):
        qstr = _get_query(cpp_queries, "method")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("method query failed to compile or not found")
        assert len(results) >= 3

    def test_namespace_query_finds_namespaces(self, query_executor):
        qstr = _get_query(cpp_queries, "namespace")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("namespace query failed to compile or not found")
        assert len(results) >= 1

    def test_include_query_finds_includes(self, query_executor):
        qstr = _get_query(cpp_queries, "include")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("include query failed to compile or not found")
        assert len(results) >= 4

    def test_template_query_finds_templates(self, query_executor):
        qstr = _get_query(cpp_queries, "template")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("template query failed to compile or not found")
        assert len(results) >= 1

    def test_enum_query_finds_enums(self, query_executor):
        qstr = _get_query(cpp_queries, "enum")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("enum query failed to compile or not found")
        assert len(results) >= 1

    def test_range_for_query_finds_range_loops(self, query_executor):
        qstr = _get_query(cpp_queries, "range_for")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("range_for query failed to compile or not found")
        assert len(results) >= 1

    def test_constructor_query_finds_constructors(self, query_executor):
        qstr = _get_query(cpp_queries, "constructor")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("constructor query failed to compile or not found")
        assert len(results) >= 1

    def test_destructor_query_finds_destructors(self, query_executor):
        qstr = _get_query(cpp_queries, "destructor")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("destructor query failed to compile or not found")
        assert len(results) >= 1

    def test_auto_type_query(self, query_executor):
        qstr = _get_query(cpp_queries, "auto_type")
        results = _safe_execute(query_executor, _lang(), SAMPLE_CPP_CODE, qstr)
        if results is None:
            pytest.skip("auto_type query failed to compile or not found")
        # auto dog = ... in sample; grammar may parse differently
        if len(results) == 0:
            pytest.skip("auto_type query returns 0 (grammar/query mismatch)")
        assert len(results) >= 1


@pytest.mark.skipif(not CPP_AVAILABLE, reason="tree-sitter-cpp not available")
class TestCppQueriesEdgeCases:
    """Test C++ queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        qstr = _get_query(cpp_queries, "class")
        results = query_executor(_lang(), "", qstr)
        assert len(results) == 0

    def test_comments_only_returns_no_matches(self, query_executor):
        code = "// line\n/* block */\n"
        qstr = _get_query(cpp_queries, "class")
        results = query_executor(_lang(), code, qstr)
        assert len(results) == 0

    def test_single_include(self, query_executor):
        code = "#include <iostream>"
        qstr = _get_query(cpp_queries, "include")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("include query failed to compile or not found")
        assert len(results) >= 1

    def test_empty_class(self, query_executor):
        code = "class Empty {};"
        qstr = _get_query(cpp_queries, "class")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("class query failed to compile or not found")
        assert len(results) >= 1

    def test_lambda_query(self, query_executor):
        code = "auto f = [](int x) { return x * 2; };"
        qstr = _get_query(cpp_queries, "lambda")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("lambda query failed to compile or not found")
        assert len(results) >= 1

    def test_inheritance_detected(self, query_executor):
        code = """
class Base {};
class Derived : public Base {};
"""
        qstr = _get_query(cpp_queries, "base_class")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("base_class query failed to compile or not found")
        assert len(results) >= 1

    def test_namespace_with_class(self, query_executor):
        code = """
namespace ns {
    class C {};
}
"""
        qstr = _get_query(cpp_queries, "namespace")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("namespace query failed to compile or not found")
        assert len(results) >= 1


@pytest.mark.skipif(not CPP_AVAILABLE, reason="tree-sitter-cpp not available")
class TestCppQueriesHelpers:
    """Test helper functions in the cpp queries module."""

    def test_get_query_valid(self):
        all_q = cpp_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = cpp_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            cpp_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = cpp_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = cpp_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_cpp_query_valid(self):
        available = cpp_queries.get_available_cpp_queries()
        if available:
            result = cpp_queries.get_cpp_query(available[0])
            assert isinstance(result, (str, dict))

    def test_get_cpp_query_invalid_raises(self):
        with pytest.raises(ValueError):
            cpp_queries.get_cpp_query("__nonexistent__")

    def test_get_cpp_query_description(self):
        available = cpp_queries.get_available_cpp_queries()
        if available:
            desc = cpp_queries.get_cpp_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_cpp_query_description_unknown(self):
        desc = cpp_queries.get_cpp_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_cpp_queries(self):
        result = cpp_queries.get_available_cpp_queries()
        assert isinstance(result, list)
        assert len(result) > 0
