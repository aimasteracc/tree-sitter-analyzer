"""
Unit tests for PathEnumerator.

Tests syntactic path discovery from code samples.
"""
from __future__ import annotations

import pytest
from tree_sitter import Language, Parser
from tree_sitter_python import language

from tree_sitter_analyzer.grammar_discovery.path_enumerator import (
    PathEnumerator,
    SyntacticPath,
)


@pytest.fixture
def python_language() -> Language:
    """Get Python tree-sitter language for testing."""
    return Language(language())


@pytest.fixture
def parser(python_language: Language) -> Parser:
    """Get Parser instance for testing."""
    parser = Parser(python_language)
    return parser


@pytest.fixture
def enumerator(python_language: Language) -> PathEnumerator:
    """Get PathEnumerator instance for testing."""
    return PathEnumerator(python_language, max_depth=3)


class TestSyntacticPath:
    """Test SyntacticPath dataclass."""

    def test_to_dict(self) -> None:
        """Test SyntacticPath serialization."""
        path = SyntacticPath(
            node_type="function_definition",
            parent_path=("module", "decorated_definition"),
            depth=2,
        )
        result = path.to_dict()
        assert result == {
            "node_type": "function_definition",
            "parent_path": "module > decorated_definition",
            "depth": 2,
        }


class TestPathEnumerator:
    """Test PathEnumerator class."""

    def test_enumerate_paths_returns_list(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that enumerate_paths returns a list."""
        code = "def foo(): pass"
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        assert isinstance(paths, list)

    def test_enumerate_paths_contains_module(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that paths include module node."""
        code = "def foo(): pass"
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        node_types = [p.node_type for p in paths]
        assert "module" in node_types

    def test_enumerate_paths_contains_function_definition(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that paths include function_definition."""
        code = "def foo(): pass"
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        node_types = [p.node_type for p in paths]
        assert "function_definition" in node_types

    def test_enumerate_paths_respects_max_depth(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that max_depth parameter limits path depth."""
        code = """
def foo():
    def bar():
        pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        for path in paths:
            assert path.depth <= 3

    def test_enumerate_paths_parent_paths_correct(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that parent paths are recorded correctly."""
        code = "def foo(): pass"
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        # Find function_definition path
        func_path = next((p for p in paths if p.node_type == "function_definition"), None)
        if func_path:
            # Parent should be module
            assert "module" in func_path.parent_path or func_path.parent_path == ("module",)

    def test_enumerate_paths_from_samples_returns_dict(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that enumerate_paths_from_samples returns a dict."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("def bar(): pass", "utf-8")).root_node,
        ]
        paths = enumerator.enumerate_paths_from_samples(code_samples)

        assert isinstance(paths, dict)

    def test_enumerate_paths_from_samples_deduplicates(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that duplicate paths are deduplicated within node type."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("def bar(): pass", "utf-8")).root_node,
        ]
        paths = enumerator.enumerate_paths_from_samples(code_samples)

        # Each node type should have unique paths
        for node_type, path_list in paths.items():
            seen_paths = set()
            for path in path_list:
                path_key = path.parent_path
                assert path_key not in seen_paths, f"Duplicate path found for {node_type}"
                seen_paths.add(path_key)

    def test_enumerate_paths_from_samples_contains_common_types(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that common node types are in results."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
        ]
        paths = enumerator.enumerate_paths_from_samples(code_samples)

        node_types = list(paths.keys())
        assert "module" in node_types
        assert "function_definition" in node_types

    def test_get_path_summary_with_list(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test get_path_summary with path list."""
        code = "def foo(): pass"
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)
        summary = enumerator.get_path_summary(paths)

        assert isinstance(summary, dict)
        assert "total_paths" in summary
        assert "unique_node_types" in summary
        assert summary["total_paths"] > 0
        assert summary["unique_node_types"] > 0

    def test_get_path_summary_with_dict(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test get_path_summary with path dict."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
        ]
        paths = enumerator.enumerate_paths_from_samples(code_samples)
        summary = enumerator.get_path_summary(paths)

        assert isinstance(summary, dict)
        assert summary["total_paths"] > 0

    def test_get_path_summary_includes_depth_distribution(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that summary includes depth distribution."""
        code = "def foo(): pass"
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)
        summary = enumerator.get_path_summary(paths)

        assert "depth_distribution" in summary
        assert isinstance(summary["depth_distribution"], dict)

    def test_find_common_patterns_filters_by_occurrences(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that find_common_patterns respects min_occurrences."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("def bar(): pass", "utf-8")).root_node,
        ]
        paths = enumerator.enumerate_paths_from_samples(code_samples)

        common = enumerator.find_common_patterns(paths, min_occurrences=1)
        common_filtered = enumerator.find_common_patterns(paths, min_occurrences=10)

        # Lower min_occurrences should return more or equal patterns
        assert len(common) >= len(common_filtered)

    def test_find_common_patterns_sorted_by_count(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that common patterns are sorted by count descending."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
            parser.parse(bytes("def bar(): pass", "utf-8")).root_node,
        ]
        paths = enumerator.enumerate_paths_from_samples(code_samples)
        common = enumerator.find_common_patterns(paths, min_occurrences=1)

        for i in range(len(common) - 1):
            assert common[i][1] >= common[i + 1][1]

    def test_find_common_patterns_returns_tuples(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that find_common_patterns returns correct tuple structure."""
        code_samples = [
            parser.parse(bytes("def foo(): pass", "utf-8")).root_node,
        ]
        paths = enumerator.enumerate_paths_from_samples(code_samples)
        common = enumerator.find_common_patterns(paths, min_occurrences=1)

        for pattern in common:
            assert isinstance(pattern, tuple)
            assert len(pattern) == 3
            assert isinstance(pattern[0], str)  # node_type
            assert isinstance(pattern[1], int)  # count
            assert isinstance(pattern[2], list)  # parent_paths

    def test_max_depth_parameter_affects_enumeration(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that max_depth parameter affects enumeration."""
        code = """
def foo():
    def bar():
        def baz():
            pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node

        enumerator_deep = PathEnumerator(enumerator._language, max_depth=5)
        enumerator_shallow = PathEnumerator(enumerator._language, max_depth=1)

        paths_deep = enumerator_deep.enumerate_paths(root_node)
        paths_shallow = enumerator_shallow.enumerate_paths(root_node)

        # Deeper max_depth should find more paths
        assert len(paths_deep) >= len(paths_shallow)

    def test_enumerate_paths_handles_empty_code(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that enumerate_paths handles empty/minimal code."""
        code = ""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        # Should at least have module node
        node_types = [p.node_type for p in paths]
        assert "module" in node_types or len(paths) >= 1

    def test_enumerate_paths_decorated_function(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test path enumeration on decorated function."""
        code = """
@decorator
def foo():
    pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        node_types = [p.node_type for p in paths]
        # Should include decorated_definition
        assert "decorated_definition" in node_types

    def test_enumerate_paths_class_with_method(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test path enumeration on class with method."""
        code = """
class MyClass:
    def method(self):
        pass
"""
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        node_types = [p.node_type for p in paths]
        assert "class_definition" in node_types
        assert "function_definition" in node_types

    def test_parent_path_chain_complete(
        self, enumerator: PathEnumerator, parser: Parser,
    ) -> None:
        """Test that parent path chain is complete."""
        code = "def foo(): pass"
        root_node = parser.parse(bytes(code, "utf-8")).root_node
        paths = enumerator.enumerate_paths(root_node)

        # Find function_definition path
        func_path = next((p for p in paths if p.node_type == "function_definition"), None)
        if func_path:
            # Path should have module as parent
            assert func_path.parent_path
            assert len(func_path.parent_path) >= 1
