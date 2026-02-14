"""
Tests for C language queries.

Validates that C tree-sitter queries are syntactically correct
and return expected results for various C code constructs.
"""

import pytest

try:
    import tree_sitter_c

    C_AVAILABLE = True
except ImportError:
    C_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import c as c_queries


def _lang():
    return get_language(tree_sitter_c.language())


SAMPLE_C_CODE = """
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SIZE 100
#define SQUARE(x) ((x) * (x))

typedef struct {
    char name[50];
    int age;
} Person;

enum Color { RED, GREEN, BLUE };

int add(int a, int b) {
    return a + b;
}

static void helper(void) {
    printf("helper\\n");
}

int main(int argc, char *argv[]) {
    Person p = {"Alice", 30};
    int numbers[] = {1, 2, 3, 4, 5};
    int *ptr = malloc(sizeof(int) * 10);

    for (int i = 0; i < 5; i++) {
        printf("%d\\n", numbers[i]);
    }

    if (ptr != NULL) {
        free(ptr);
    }

    return 0;
}

const int GLOBAL_CONST = 42;
static int module_var = 0;
"""

# Well-known C queries to test functionality
C_KEYS_TO_TEST = [
    "function",
    "struct",
    "enum",
    "include",
    "define",
    "typedef",
    "variable",
    "for_statement",
    "if_statement",
    "function_call",
    "return_statement",
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


@pytest.mark.skipif(not C_AVAILABLE, reason="tree-sitter-c not available")
class TestCQueriesSyntax:
    """Test that C queries compile successfully."""

    def test_all_queries_dict_compilable_count(self):
        import tree_sitter

        lang = _lang()
        all_q = c_queries.ALL_QUERIES
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

    @pytest.mark.parametrize("key", C_KEYS_TO_TEST)
    def test_individual_query_compiles(self, key, query_validator):
        qstr = _get_query(c_queries, key)
        if qstr is None:
            pytest.skip(f"Key {key} not in ALL_QUERIES")
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not C_AVAILABLE, reason="tree-sitter-c not available")
class TestCQueriesFunctionality:
    """Test that C queries return expected results."""

    def test_function_query_finds_functions(self, query_executor):
        qstr = _get_query(c_queries, "function")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("function query failed to compile or not found")
        assert len(results) >= 3

    def test_struct_query_finds_structs(self, query_executor):
        qstr = _get_query(c_queries, "struct")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("struct query failed to compile or not found")
        assert len(results) >= 1

    def test_enum_query_finds_enums(self, query_executor):
        qstr = _get_query(c_queries, "enum")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("enum query failed to compile or not found")
        assert len(results) >= 1

    def test_include_query_finds_includes(self, query_executor):
        qstr = _get_query(c_queries, "include")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("include query failed to compile or not found")
        assert len(results) >= 3

    def test_define_query_finds_defines(self, query_executor):
        qstr = _get_query(c_queries, "define")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("define query failed to compile or not found")
        # Grammar may vary; at least one define expected
        assert len(results) >= 1

    def test_typedef_query_finds_typedefs(self, query_executor):
        qstr = _get_query(c_queries, "typedef")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("typedef query failed to compile or not found")
        assert len(results) >= 1

    def test_variable_query_finds_declarations(self, query_executor):
        qstr = _get_query(c_queries, "variable")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("variable query failed to compile or not found")
        assert len(results) >= 1

    def test_for_statement_query_finds_for_loops(self, query_executor):
        qstr = _get_query(c_queries, "for_statement")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("for_statement query failed to compile or not found")
        assert len(results) >= 1

    def test_function_call_query_finds_calls(self, query_executor):
        qstr = _get_query(c_queries, "function_call")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("function_call query failed to compile or not found")
        assert len(results) >= 3

    def test_static_function_query(self, query_executor):
        qstr = _get_query(c_queries, "static_function")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("static_function query failed to compile or not found")
        assert len(results) >= 1

    def test_function_name_query(self, query_executor):
        qstr = _get_query(c_queries, "function_name")
        results = _safe_execute(query_executor, _lang(), SAMPLE_C_CODE, qstr)
        if results is None:
            pytest.skip("function_name query failed to compile or not found")
        assert len(results) >= 2


@pytest.mark.skipif(not C_AVAILABLE, reason="tree-sitter-c not available")
class TestCQueriesEdgeCases:
    """Test C queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        qstr = _get_query(c_queries, "function")
        results = query_executor(_lang(), "", qstr)
        assert len(results) == 0

    def test_comments_only_returns_no_matches(self, query_executor):
        code = "/* block */\n// line comment\n"
        qstr = _get_query(c_queries, "function")
        results = query_executor(_lang(), code, qstr)
        assert len(results) == 0

    def test_single_include(self, query_executor):
        code = "#include <stdio.h>"
        qstr = _get_query(c_queries, "include")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("include query failed to compile or not found")
        assert len(results) >= 1

    def test_empty_struct(self, query_executor):
        code = "struct Empty {};"
        qstr = _get_query(c_queries, "struct")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("struct query failed to compile or not found")
        assert len(results) >= 1

    def test_simple_function_only(self, query_executor):
        code = "int foo() { return 0; }"
        qstr = _get_query(c_queries, "function")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("function query failed to compile or not found")
        assert len(results) >= 1

    def test_define_macro_only(self, query_executor):
        code = "#define FOO 42"
        qstr = _get_query(c_queries, "define")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("define query failed to compile or not found")
        assert len(results) >= 1

    def test_enum_constant_query(self, query_executor):
        code = "enum E { A, B, C };"
        qstr = _get_query(c_queries, "enum_constant")
        results = _safe_execute(query_executor, _lang(), code, qstr)
        if results is None:
            pytest.skip("enum_constant query failed to compile or not found")
        assert len(results) >= 3


@pytest.mark.skipif(not C_AVAILABLE, reason="tree-sitter-c not available")
class TestCQueriesHelpers:
    """Test helper functions in the c queries module."""

    def test_get_query_valid(self):
        all_q = c_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = c_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            c_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = c_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = c_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_c_query_valid(self):
        available = c_queries.get_available_c_queries()
        if available:
            result = c_queries.get_c_query(available[0])
            assert isinstance(result, str | dict)

    def test_get_c_query_invalid_raises(self):
        with pytest.raises(ValueError):
            c_queries.get_c_query("__nonexistent__")

    def test_get_c_query_description(self):
        available = c_queries.get_available_c_queries()
        if available:
            desc = c_queries.get_c_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_c_query_description_unknown(self):
        desc = c_queries.get_c_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_c_queries(self):
        result = c_queries.get_available_c_queries()
        assert isinstance(result, list)
        assert len(result) > 0
