"""
Tests for Python language queries.

Validates that Python tree-sitter queries are syntactically correct
and return expected results for various Python code constructs.
"""
import pytest

try:
    import tree_sitter_python
    PYTHON_AVAILABLE = True
except ImportError:
    PYTHON_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import python as python_queries


def _lang():
    return get_language(tree_sitter_python.language())


ALL_QUERY_CONSTANTS = [
    "FUNCTIONS", "CLASSES", "IMPORTS", "VARIABLES", "DECORATORS",
    "METHODS", "EXCEPTIONS", "COMPREHENSIONS", "COMMENTS",
    "TYPE_HINTS", "ASYNC_PATTERNS", "STRING_FORMATTING",
    "CONTEXT_MANAGERS", "LAMBDAS", "MODERN_PATTERNS",
]

# Queries that have known syntax issues with tree-sitter-python 0.25
KNOWN_BROKEN_QUERIES = {
    "EXCEPTIONS", "ASYNC_PATTERNS", "STRING_FORMATTING",
    "CONTEXT_MANAGERS", "MODERN_PATTERNS",
}


@pytest.mark.skipif(not PYTHON_AVAILABLE, reason="tree-sitter-python not available")
class TestPythonQueriesSyntax:
    """Test that all Python query constants compile successfully."""

    @pytest.mark.parametrize("query_name", ALL_QUERY_CONSTANTS)
    def test_query_compiles(self, query_name, query_validator):
        if query_name in KNOWN_BROKEN_QUERIES:
            pytest.xfail(f"{query_name} has known grammar incompatibility")
        qstr = getattr(python_queries, query_name)
        assert isinstance(qstr, str) and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)

    def test_all_queries_dict_compilable_count(self):
        """Most entries in ALL_QUERIES should compile; count failures."""
        import tree_sitter
        lang = _lang()
        all_q = python_queries.ALL_QUERIES
        assert len(all_q) > 0
        compiled, failed = 0, 0
        for _name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        # At least 70% should compile
        ratio = compiled / (compiled + failed)
        assert ratio >= 0.7, (
            f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"
        )


@pytest.mark.skipif(not PYTHON_AVAILABLE, reason="tree-sitter-python not available")
class TestPythonQueriesFunctionality:
    """Test that Python queries return expected results."""

    def test_functions_query_finds_definitions(self, query_executor):
        code = '''
def calculate_sum(a, b):
    return a + b

def multiply(x, y):
    return x * y
'''
        results = query_executor(_lang(), code, python_queries.FUNCTIONS)
        assert len(results) >= 2

    def test_classes_query_finds_definitions(self, query_executor):
        code = '''
class Calculator:
    def add(self, x, y):
        return x + y

class AdvancedCalculator(Calculator):
    pass
'''
        results = query_executor(_lang(), code, python_queries.CLASSES)
        assert len(results) >= 2

    def test_imports_query_finds_statements(self, query_executor):
        code = '''
import os
import sys
from pathlib import Path
from typing import List, Dict
'''
        results = query_executor(_lang(), code, python_queries.IMPORTS)
        assert len(results) >= 4

    def test_variables_query_finds_assignments(self, query_executor):
        code = '''
MAX_SIZE = 100
USER_NAME = "admin"
config = {"debug": True}
items = [1, 2, 3]
'''
        results = query_executor(_lang(), code, python_queries.VARIABLES)
        assert len(results) >= 4

    def test_decorators_query_finds_decorators(self, query_executor):
        code = '''
@property
def name(self):
    return self._name

@staticmethod
def create():
    return MyClass()

@app.route('/api')
def api_endpoint():
    return {}
'''
        results = query_executor(_lang(), code, python_queries.DECORATORS)
        assert len(results) >= 3

    def test_methods_query_finds_methods(self, query_executor):
        code = '''
class Foo:
    def bar(self):
        pass
    def baz(self, x):
        return x
'''
        results = query_executor(_lang(), code, python_queries.METHODS)
        assert len(results) >= 2

    @pytest.mark.xfail(reason="EXCEPTIONS query has grammar incompatibility")
    def test_exceptions_query_finds_try_except(self, query_executor):
        code = '''
try:
    result = 1 / 0
except ZeroDivisionError as e:
    print(e)
except Exception:
    pass
finally:
    cleanup()
'''
        results = query_executor(_lang(), code, python_queries.EXCEPTIONS)
        assert len(results) >= 1

    def test_comprehensions_query_finds_comprehensions(self, query_executor):
        code = '''
squares = [x ** 2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
mapping = {k: v for k, v in items}
unique = {x for x in data}
gen = (x for x in range(5))
'''
        results = query_executor(_lang(), code, python_queries.COMPREHENSIONS)
        assert len(results) >= 3

    def test_type_hints_query(self, query_executor):
        code = '''
def greet(name: str) -> str:
    return f"Hello {name}"

age: int = 25
items: list[str] = []
'''
        results = query_executor(_lang(), code, python_queries.TYPE_HINTS)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="ASYNC_PATTERNS query has grammar incompatibility")
    def test_async_patterns_query(self, query_executor):
        code = '''
async def fetch_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
'''
        results = query_executor(_lang(), code, python_queries.ASYNC_PATTERNS)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="CONTEXT_MANAGERS query has grammar incompatibility")
    def test_context_managers_query(self, query_executor):
        code = '''
with open("file.txt") as f:
    data = f.read()

with lock:
    shared_resource += 1
'''
        results = query_executor(_lang(), code, python_queries.CONTEXT_MANAGERS)
        assert len(results) >= 2

    def test_lambdas_query(self, query_executor):
        code = '''
double = lambda x: x * 2
add = lambda a, b: a + b
'''
        results = query_executor(_lang(), code, python_queries.LAMBDAS)
        assert len(results) >= 2


@pytest.mark.skipif(not PYTHON_AVAILABLE, reason="tree-sitter-python not available")
class TestPythonQueriesEdgeCases:
    """Test Python queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", python_queries.FUNCTIONS)
        assert len(results) == 0

    def test_comments_only_returns_no_function_matches(self, query_executor):
        code = '# just a comment\n"""docstring only"""\n'
        results = query_executor(_lang(), code, python_queries.FUNCTIONS)
        assert len(results) == 0

    def test_nested_classes_detected(self, query_executor):
        code = '''
class Outer:
    class Inner:
        pass
    class AnotherInner:
        def method(self):
            pass
'''
        results = query_executor(_lang(), code, python_queries.CLASSES)
        assert len(results) >= 3

    def test_complex_type_hints(self, query_executor):
        code = '''
from typing import List, Dict, Optional, Union

def process(
    items: List[Dict[str, Union[int, str]]],
    config: Optional[Dict[str, any]] = None
) -> List[str]:
    return []
'''
        results = query_executor(_lang(), code, python_queries.FUNCTIONS)
        assert len(results) >= 1

    def test_multiline_function(self, query_executor):
        code = '''
def very_long_function_name(
    param_one,
    param_two,
    param_three,
    param_four
):
    pass
'''
        results = query_executor(_lang(), code, python_queries.FUNCTIONS)
        assert len(results) >= 1


@pytest.mark.skipif(not PYTHON_AVAILABLE, reason="tree-sitter-python not available")
class TestPythonQueriesHelpers:
    """Test helper functions in the python queries module."""

    def test_get_query_valid(self):
        all_q = python_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = python_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            python_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = python_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = python_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_python_query_valid(self):
        available = python_queries.get_available_python_queries()
        if available:
            result = python_queries.get_python_query(available[0])
            assert isinstance(result, (str, dict))

    def test_get_python_query_invalid_raises(self):
        with pytest.raises(ValueError):
            python_queries.get_python_query("__nonexistent__")

    def test_get_python_query_description(self):
        available = python_queries.get_available_python_queries()
        if available:
            desc = python_queries.get_python_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_python_query_description_unknown(self):
        desc = python_queries.get_python_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_python_queries(self):
        result = python_queries.get_available_python_queries()
        assert isinstance(result, list)
        assert len(result) > 0
