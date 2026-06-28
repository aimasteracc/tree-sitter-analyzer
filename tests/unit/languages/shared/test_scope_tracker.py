"""Tests for tree_sitter_analyzer.languages.shared.scope_tracker."""

from __future__ import annotations

from tree_sitter_analyzer.languages.shared.scope_tracker import ScopeStack


class TestScopeStack:
    def test_empty_stack_returns_empty_string(self):
        stack = ScopeStack()
        assert stack.current_qualified_name() == ""

    def test_single_push_returns_name(self):
        stack = ScopeStack()
        stack.push("MyClass", "class")
        assert stack.current_qualified_name() == "MyClass"

    def test_nested_push_returns_dot_joined(self):
        stack = ScopeStack()
        stack.push("MyClass", "class")
        stack.push("my_method", "method")
        assert stack.current_qualified_name() == "MyClass.my_method"

    def test_three_level_nesting(self):
        stack = ScopeStack()
        stack.push("Outer", "class")
        stack.push("Inner", "class")
        stack.push("method", "method")
        assert stack.current_qualified_name() == "Outer.Inner.method"

    def test_pop_removes_innermost_frame(self):
        stack = ScopeStack()
        stack.push("MyClass", "class")
        stack.push("my_method", "method")
        popped = stack.pop()
        assert popped is not None
        assert popped.name == "my_method"
        assert popped.kind == "method"
        assert stack.current_qualified_name() == "MyClass"

    def test_pop_on_empty_returns_none(self):
        stack = ScopeStack()
        assert stack.pop() is None

    def test_depth_tracks_push_pop(self):
        stack = ScopeStack()
        assert stack.depth() == 0
        stack.push("A", "class")
        assert stack.depth() == 1
        stack.push("B", "method")
        assert stack.depth() == 2
        stack.pop()
        assert stack.depth() == 1

    def test_is_empty(self):
        stack = ScopeStack()
        assert stack.is_empty() is True
        stack.push("A", "class")
        assert stack.is_empty() is False

    def test_current_kind_returns_innermost_kind(self):
        stack = ScopeStack()
        assert stack.current_kind() is None
        stack.push("Cls", "class")
        assert stack.current_kind() == "class"
        stack.push("meth", "method")
        assert stack.current_kind() == "method"
        stack.pop()
        assert stack.current_kind() == "class"

    def test_push_empty_name_still_works(self):
        """Pushing empty string is allowed; qualified name shows empty segment."""
        stack = ScopeStack()
        stack.push("", "namespace")
        # dot-joined with empty string stays empty
        assert stack.current_qualified_name() == ""
        stack.push("MyClass", "class")
        assert stack.current_qualified_name() == ".MyClass"

    def test_spec_acceptance_criteria(self):
        """REQ-2-002 acceptance criterion:
        push("MyClass", "class") → push("my_method", "method")
        → current_qualified_name() returns exactly "MyClass.my_method".
        """
        stack = ScopeStack()
        stack.push("MyClass", "class")
        stack.push("my_method", "method")
        assert stack.current_qualified_name() == "MyClass.my_method"
