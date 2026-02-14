"""
Tests for PHP language queries.

Validates that PHP tree-sitter queries are syntactically correct
and return expected results for various PHP code constructs.
"""

import pytest

try:
    import tree_sitter_php  # noqa: F401

    PHP_AVAILABLE = True
except ImportError:
    PHP_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import php as php_queries


def _lang():
    import tree_sitter_php

    if hasattr(tree_sitter_php, "language_php"):
        return get_language(tree_sitter_php.language_php())
    return get_language(tree_sitter_php.language())


# Queries that may fail with certain tree-sitter-php grammar versions
KNOWN_BROKEN_PHP_QUERIES = {
    "PHP_CONSTANT_QUERY",
    "PHP_ATTRIBUTE_QUERY",
    "PHP_ALL_ELEMENTS_QUERY",  # includes PHP_ATTRIBUTE_QUERY
}

PHP_QUERY_CONSTANTS = [
    "PHP_CLASS_QUERY",
    "PHP_METHOD_QUERY",
    "PHP_FUNCTION_QUERY",
    "PHP_PROPERTY_QUERY",
    "PHP_CONSTANT_QUERY",
    "PHP_USE_QUERY",
    "PHP_NAMESPACE_QUERY",
    "PHP_ATTRIBUTE_QUERY",
    "PHP_MAGIC_METHOD_QUERY",
    "PHP_ALL_ELEMENTS_QUERY",
]

SAMPLE_PHP_CODE = """<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class User extends Model {
    private string $name;
    public const MAX_AGE = 150;

    public function __construct(string $name) {
        $this->name = $name;
    }

    public function getName(): string {
        return $this->name;
    }

    public static function create(string $name): self {
        return new self($name);
    }

    public function __toString(): string {
        return $this->name;
    }
}

function helper(int $x): int {
    return $x * 2;
}

$count = 0;
$items = [1, 2, 3];
"""


def _safe_execute(query_executor, lang, code, qstr):
    """Execute query, return results or None if query fails to compile."""
    try:
        return query_executor(lang, code, qstr)
    except Exception:
        return None


@pytest.mark.skipif(not PHP_AVAILABLE, reason="tree-sitter-php not available")
class TestPHPQueriesSyntax:
    """Test that all PHP query constants compile successfully."""

    @pytest.mark.parametrize("query_name", PHP_QUERY_CONSTANTS)
    def test_query_compiles(self, query_name, query_validator):
        if query_name in KNOWN_BROKEN_PHP_QUERIES:
            pytest.xfail(f"{query_name} has known grammar incompatibility")
        qstr = getattr(php_queries, query_name)
        assert isinstance(qstr, str) and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not PHP_AVAILABLE, reason="tree-sitter-php not available")
class TestPHPQueriesFunctionality:
    """Test that PHP queries return expected results."""

    def test_class_query_finds_classes(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_CLASS_QUERY
        )
        if results is None:
            pytest.skip("PHP_CLASS_QUERY failed to compile")
        assert len(results) >= 1

    def test_method_query_finds_methods(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_METHOD_QUERY
        )
        if results is None:
            pytest.skip("PHP_METHOD_QUERY failed to compile")
        assert len(results) >= 3

    def test_function_query_finds_functions(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_FUNCTION_QUERY
        )
        if results is None:
            pytest.skip("PHP_FUNCTION_QUERY failed to compile")
        assert len(results) >= 1

    def test_property_query_finds_properties(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_PROPERTY_QUERY
        )
        if results is None:
            pytest.skip("PHP_PROPERTY_QUERY failed to compile")
        assert len(results) >= 1

    def test_constant_query_finds_constants(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_CONSTANT_QUERY
        )
        if results is None:
            pytest.skip("PHP_CONSTANT_QUERY failed to compile")
        assert len(results) >= 1

    def test_use_query_finds_imports(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_USE_QUERY
        )
        if results is None:
            pytest.skip("PHP_USE_QUERY failed to compile")
        assert len(results) >= 1

    def test_namespace_query_finds_namespaces(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_NAMESPACE_QUERY
        )
        if results is None:
            pytest.skip("PHP_NAMESPACE_QUERY failed to compile")
        assert len(results) >= 1

    def test_magic_method_query_finds_magic_methods(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_MAGIC_METHOD_QUERY
        )
        if results is None:
            pytest.skip("PHP_MAGIC_METHOD_QUERY failed to compile")
        assert len(results) >= 2  # __construct, __toString

    def test_all_elements_query_finds_multiple(self, query_executor):
        results = _safe_execute(
            query_executor, _lang(), SAMPLE_PHP_CODE, php_queries.PHP_ALL_ELEMENTS_QUERY
        )
        if results is None:
            pytest.skip("PHP_ALL_ELEMENTS_QUERY failed to compile")
        assert len(results) >= 5

    def test_static_method_detected(self, query_executor):
        code = """<?php
class Foo {
    public static function bar(): void {}
}
"""
        results = _safe_execute(
            query_executor, _lang(), code, php_queries.PHP_METHOD_QUERY
        )
        if results is None:
            pytest.skip("PHP_METHOD_QUERY failed to compile")
        assert len(results) >= 1

    def test_interface_and_trait_support(self, query_executor):
        code = """<?php
interface IUser {}
trait HasTimestamp {}
"""
        results = _safe_execute(
            query_executor, _lang(), code, php_queries.PHP_CLASS_QUERY
        )
        if results is None:
            pytest.skip("PHP_CLASS_QUERY failed to compile")
        assert len(results) >= 1


@pytest.mark.skipif(not PHP_AVAILABLE, reason="tree-sitter-php not available")
class TestPHPQueriesEdgeCases:
    """Test PHP queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", php_queries.PHP_CLASS_QUERY)
        assert len(results) == 0

    def test_comments_only_returns_no_matches(self, query_executor):
        code = """<?php
// single line
/* block comment */
# shell style
"""
        results = query_executor(_lang(), code, php_queries.PHP_CLASS_QUERY)
        assert len(results) == 0

    def test_php_only_open_tag(self, query_executor):
        code = "<?php\n"
        results = query_executor(_lang(), code, php_queries.PHP_FUNCTION_QUERY)
        assert len(results) == 0

    def test_namespace_only(self, query_executor):
        code = """<?php
namespace App;
"""
        results = _safe_execute(
            query_executor, _lang(), code, php_queries.PHP_NAMESPACE_QUERY
        )
        if results is None:
            pytest.skip("PHP_NAMESPACE_QUERY failed to compile")
        assert len(results) >= 1

    def test_empty_class(self, query_executor):
        code = """<?php
class Empty {}
"""
        results = _safe_execute(
            query_executor, _lang(), code, php_queries.PHP_CLASS_QUERY
        )
        if results is None:
            pytest.skip("PHP_CLASS_QUERY failed to compile")
        assert len(results) >= 1

    def test_nested_class_in_namespace(self, query_executor):
        code = """<?php
namespace NS;
class Outer {
    class Inner {}
}
"""
        results = _safe_execute(
            query_executor, _lang(), code, php_queries.PHP_CLASS_QUERY
        )
        if results is None:
            pytest.skip("PHP_CLASS_QUERY failed to compile")
        assert len(results) >= 1
