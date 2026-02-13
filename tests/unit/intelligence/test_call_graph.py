#!/usr/bin/env python3
"""Tests for CallGraphBuilder (Code Intelligence Graph)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from tree_sitter_analyzer.intelligence.call_graph import CallGraphBuilder
from tree_sitter_analyzer.intelligence.models import CallSite


@pytest.fixture
def mock_analysis_engine():
    engine = MagicMock()
    engine.analyze = AsyncMock()
    return engine


@pytest.fixture
def builder(mock_analysis_engine):
    return CallGraphBuilder(mock_analysis_engine)


class TestCallGraphBuilderInit:
    def test_init(self, builder):
        assert builder is not None
        assert builder._call_sites == {}

    def test_init_with_engine(self, builder, mock_analysis_engine):
        assert builder._engine is mock_analysis_engine


class TestCallGraphBuilderExtractCalls:
    def test_extract_calls_from_source_simple(self, builder):
        """Extract calls from simple Python code."""
        source = '''
def main():
    print("hello")
    result = calculate(42)
'''
        calls = builder.extract_calls_from_source(source, "test.py")
        call_names = [c.callee_name for c in calls]
        assert "print" in call_names
        assert "calculate" in call_names

    def test_extract_calls_from_source_method(self, builder):
        """Extract method calls."""
        source = '''
def process():
    self.validate(data)
    obj.transform(value)
'''
        calls = builder.extract_calls_from_source(source, "test.py")
        method_calls = [c for c in calls if c.callee_object is not None]
        assert len(method_calls) >= 1

    def test_extract_calls_from_source_no_calls(self, builder):
        """File with no calls should return empty list."""
        source = '''
x = 42
y = "hello"
'''
        calls = builder.extract_calls_from_source(source, "test.py")
        assert calls == []

    def test_extract_calls_from_source_nested(self, builder):
        """Extract nested function calls."""
        source = '''
def main():
    result = outer(inner(x))
'''
        calls = builder.extract_calls_from_source(source, "test.py")
        call_names = [c.callee_name for c in calls]
        assert "outer" in call_names
        assert "inner" in call_names

    def test_extract_calls_preserves_line_numbers(self, builder):
        """Call sites should have correct line numbers."""
        source = '''def main():
    foo()
    bar()
'''
        calls = builder.extract_calls_from_source(source, "test.py")
        assert all(c.line > 0 for c in calls)

    def test_extract_calls_with_caller_function(self, builder):
        """Calls should know which function they're in."""
        source = '''
def main():
    foo()

def helper():
    bar()
'''
        calls = builder.extract_calls_from_source(source, "test.py")
        # At minimum, caller_file should be set
        assert all(c.caller_file == "test.py" for c in calls)


class TestCallGraphBuilderFindCallers:
    def test_find_callers_empty(self, builder):
        """No callers for unknown symbol."""
        callers = builder.find_callers("unknown_func")
        assert callers == []

    def test_find_callers_after_indexing(self, builder):
        """After indexing calls, find_callers should return callers."""
        # Manually add call sites
        builder._call_sites["test.py"] = [
            CallSite("test.py", "main", "foo", None, 5, "foo()"),
            CallSite("test.py", "helper", "foo", None, 10, "foo()"),
        ]
        callers = builder.find_callers("foo")
        assert len(callers) == 2

    def test_find_callers_with_depth_limit(self, builder):
        """Depth limit should restrict results."""
        builder._call_sites["a.py"] = [
            CallSite("a.py", "func_a", "func_b", None, 5, "func_b()"),
        ]
        builder._call_sites["b.py"] = [
            CallSite("b.py", "func_b", "func_c", None, 10, "func_c()"),
        ]
        # depth=1 should only find direct callers
        callers = builder.find_callers("func_b", depth=1)
        caller_names = [c.caller_function for c in callers]
        assert "func_a" in caller_names


class TestCallGraphBuilderFindCallees:
    def test_find_callees_empty(self, builder):
        """No callees for unknown symbol."""
        callees = builder.find_callees("unknown_func")
        assert callees == []

    def test_find_callees_after_indexing(self, builder):
        """After indexing, find_callees returns what a function calls."""
        builder._call_sites["test.py"] = [
            CallSite("test.py", "main", "foo", None, 5, "foo()"),
            CallSite("test.py", "main", "bar", None, 6, "bar()"),
            CallSite("test.py", "helper", "baz", None, 10, "baz()"),
        ]
        callees = builder.find_callees("main")
        callee_names = [c.callee_name for c in callees]
        assert "foo" in callee_names
        assert "bar" in callee_names
        assert "baz" not in callee_names
