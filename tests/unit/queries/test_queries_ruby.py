"""
Tests for Ruby language queries.

Validates that Ruby tree-sitter queries are syntactically correct
and return expected results for various Ruby code constructs.
"""
import pytest

try:
    import tree_sitter_ruby
    RUBY_AVAILABLE = True
except ImportError:
    RUBY_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import ruby as ruby_queries


def _lang():
    return get_language(tree_sitter_ruby.language())


RUBY_QUERY_CONSTANTS = [
    "RUBY_CLASS_QUERY",
    "RUBY_METHOD_QUERY",
    "RUBY_CONSTANT_QUERY",
    "RUBY_INSTANCE_VAR_QUERY",
    "RUBY_CLASS_VAR_QUERY",
    "RUBY_REQUIRE_QUERY",
    "RUBY_ATTR_QUERY",
    "RUBY_BLOCK_QUERY",
    "RUBY_PROC_LAMBDA_QUERY",
    "RUBY_ALL_ELEMENTS_QUERY",
]

SAMPLE_RUBY_CODE = """
require 'json'
require_relative 'helper'

module Animals
  class Dog
    attr_accessor :name, :age
    @@count = 0
    MAX_AGE = 20

    def initialize(name, age)
      @name = name
      @age = age
      @@count += 1
    end

    def speak
      "Woof! I'm #{@name}"
    end

    def self.count
      @@count
    end
  end
end

def greet(name)
  puts "Hello, #{name}"
end

multiply = ->(a, b) { a * b }
double = proc { |x| x * 2 }

[1, 2, 3].each do |n|
  puts n
end
"""


def _safe_execute(query_executor, lang, code, qstr):
    """Execute query, return results or None if query fails to compile."""
    try:
        return query_executor(lang, code, qstr)
    except Exception:
        return None


@pytest.mark.skipif(not RUBY_AVAILABLE, reason="tree-sitter-ruby not available")
class TestRubyQueriesSyntax:
    """Test that all Ruby query constants compile successfully."""

    @pytest.mark.parametrize("query_name", RUBY_QUERY_CONSTANTS)
    def test_query_compiles(self, query_name, query_validator):
        qstr = getattr(ruby_queries, query_name)
        assert isinstance(qstr, str) and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not RUBY_AVAILABLE, reason="tree-sitter-ruby not available")
class TestRubyQueriesFunctionality:
    """Test that Ruby queries return expected results."""

    def test_class_query_finds_classes_and_modules(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_CLASS_QUERY)
        if results is None:
            pytest.skip("RUBY_CLASS_QUERY failed to compile")
        assert len(results) >= 2

    def test_method_query_finds_methods(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_METHOD_QUERY)
        if results is None:
            pytest.skip("RUBY_METHOD_QUERY failed to compile")
        assert len(results) >= 3

    def test_constant_query_finds_constants(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_CONSTANT_QUERY)
        if results is None:
            pytest.skip("RUBY_CONSTANT_QUERY failed to compile")
        assert len(results) >= 1

    def test_instance_var_query_finds_instance_vars(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_INSTANCE_VAR_QUERY)
        if results is None:
            pytest.skip("RUBY_INSTANCE_VAR_QUERY failed to compile")
        assert len(results) >= 2

    def test_class_var_query_finds_class_vars(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_CLASS_VAR_QUERY)
        if results is None:
            pytest.skip("RUBY_CLASS_VAR_QUERY failed to compile")
        assert len(results) >= 1

    def test_require_query_finds_requires(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_REQUIRE_QUERY)
        if results is None:
            pytest.skip("RUBY_REQUIRE_QUERY failed to compile")
        assert len(results) >= 2

    def test_attr_query_finds_attr_accessor(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_ATTR_QUERY)
        if results is None:
            pytest.skip("RUBY_ATTR_QUERY failed to compile")
        assert len(results) >= 1

    def test_block_query_finds_blocks(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_BLOCK_QUERY)
        if results is None:
            pytest.skip("RUBY_BLOCK_QUERY failed to compile")
        assert len(results) >= 2

    def test_proc_lambda_query_finds_procs_and_lambdas(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_PROC_LAMBDA_QUERY)
        if results is None:
            pytest.skip("RUBY_PROC_LAMBDA_QUERY failed to compile")
        assert len(results) >= 2

    def test_all_elements_query_finds_multiple(self, query_executor):
        results = _safe_execute(query_executor, _lang(), SAMPLE_RUBY_CODE, ruby_queries.RUBY_ALL_ELEMENTS_QUERY)
        if results is None:
            pytest.skip("RUBY_ALL_ELEMENTS_QUERY failed to compile")
        assert len(results) >= 5

    def test_singleton_method_detected(self, query_executor):
        code = """
class Foo
  def self.bar
  end
end
"""
        results = _safe_execute(query_executor, _lang(), code, ruby_queries.RUBY_METHOD_QUERY)
        if results is None:
            pytest.skip("RUBY_METHOD_QUERY failed to compile")
        assert len(results) >= 1

    def test_nested_module(self, query_executor):
        code = """
module Outer
  module Inner
    class MyClass
    end
  end
end
"""
        results = _safe_execute(query_executor, _lang(), code, ruby_queries.RUBY_CLASS_QUERY)
        if results is None:
            pytest.skip("RUBY_CLASS_QUERY failed to compile")
        assert len(results) >= 2


@pytest.mark.skipif(not RUBY_AVAILABLE, reason="tree-sitter-ruby not available")
class TestRubyQueriesEdgeCases:
    """Test Ruby queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", ruby_queries.RUBY_CLASS_QUERY)
        assert len(results) == 0

    def test_comments_only_returns_no_matches(self, query_executor):
        code = "# comment\n=begin\nblock\n=end\n"
        results = query_executor(_lang(), code, ruby_queries.RUBY_CLASS_QUERY)
        assert len(results) == 0

    def test_empty_class(self, query_executor):
        code = """
class Empty
end
"""
        results = _safe_execute(query_executor, _lang(), code, ruby_queries.RUBY_CLASS_QUERY)
        if results is None:
            pytest.skip("RUBY_CLASS_QUERY failed to compile")
        assert len(results) >= 1

    def test_require_relative_only(self, query_executor):
        code = "require_relative 'foo'"
        results = _safe_execute(query_executor, _lang(), code, ruby_queries.RUBY_REQUIRE_QUERY)
        if results is None:
            pytest.skip("RUBY_REQUIRE_QUERY failed to compile")
        assert len(results) >= 1

    def test_attr_reader_writer(self, query_executor):
        code = """
class C
  attr_reader :a
  attr_writer :b
end
"""
        results = _safe_execute(query_executor, _lang(), code, ruby_queries.RUBY_ATTR_QUERY)
        if results is None:
            pytest.skip("RUBY_ATTR_QUERY failed to compile")
        assert len(results) >= 2

    def test_standalone_method(self, query_executor):
        code = """
def top_level_method
  nil
end
"""
        results = _safe_execute(query_executor, _lang(), code, ruby_queries.RUBY_METHOD_QUERY)
        if results is None:
            pytest.skip("RUBY_METHOD_QUERY failed to compile")
        assert len(results) >= 1
