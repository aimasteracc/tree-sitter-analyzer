"""
Tests for features/semantic_search.py module.

TDD: Testing semantic code search functionality.
"""

import ast
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.features.semantic_search import (
    SearchResult,
    ASTPattern,
    FunctionCallPattern,
    VariableAssignmentPattern,
    SemanticSearchEngine,
    semantic_search,
)


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_creation(self) -> None:
        """Should create SearchResult."""
        result = SearchResult(
            file="test.py",
            line_number=10,
            code_snippet="x = 1",
            context="context",
            match_type="assignment"
        )
        
        assert result.file == "test.py"
        assert result.line_number == 10


class TestFunctionCallPattern:
    """Test FunctionCallPattern."""

    def test_matches_function_call(self) -> None:
        """Should match function calls."""
        pattern = FunctionCallPattern(function_name="print")
        
        code = "print('hello')"
        tree = ast.parse(code)
        call_node = tree.body[0].value
        
        assert pattern.matches(call_node) is True

    def test_not_matches_wrong_function(self) -> None:
        """Should not match different function."""
        pattern = FunctionCallPattern(function_name="print")
        
        code = "len([1, 2, 3])"
        tree = ast.parse(code)
        call_node = tree.body[0].value
        
        assert pattern.matches(call_node) is False

    def test_matches_method_call(self) -> None:
        """Should match method calls."""
        pattern = FunctionCallPattern(function_name="append")
        
        code = "items.append(1)"
        tree = ast.parse(code)
        call_node = tree.body[0].value
        
        assert pattern.matches(call_node) is True

    def test_matches_any_call(self) -> None:
        """Should match any call when no name specified."""
        pattern = FunctionCallPattern()
        
        code = "foo()"
        tree = ast.parse(code)
        call_node = tree.body[0].value
        
        assert pattern.matches(call_node) is True

    def test_not_matches_non_call(self) -> None:
        """Should not match non-call nodes."""
        pattern = FunctionCallPattern()
        
        code = "x = 1"
        tree = ast.parse(code)
        assign_node = tree.body[0]
        
        assert pattern.matches(assign_node) is False


class TestVariableAssignmentPattern:
    """Test VariableAssignmentPattern."""

    def test_matches_assignment(self) -> None:
        """Should match variable assignment."""
        pattern = VariableAssignmentPattern(variable_name="x")
        
        code = "x = 1"
        tree = ast.parse(code)
        assign_node = tree.body[0]
        
        assert pattern.matches(assign_node) is True

    def test_matches_specific_variable(self) -> None:
        """Should find specific variable in targets."""
        pattern = VariableAssignmentPattern(variable_name="x")
        
        code = "x = 1"
        tree = ast.parse(code)
        assign_node = tree.body[0]
        
        # Returns True when variable matches
        assert pattern.matches(assign_node) is True

    def test_matches_any_assignment(self) -> None:
        """Should match any assignment when no name specified."""
        pattern = VariableAssignmentPattern()
        
        code = "z = 1"
        tree = ast.parse(code)
        assign_node = tree.body[0]
        
        assert pattern.matches(assign_node) is True


class TestSemanticSearchEngine:
    """Test SemanticSearchEngine."""

    def test_search_pattern_in_file(self) -> None:
        """Should find pattern in file."""
        engine = SemanticSearchEngine()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\nprint(x)\ny = 2\n")
            f.flush()
            path = Path(f.name)
        
        try:
            pattern = FunctionCallPattern(function_name="print")
            results = engine.search_pattern(path, pattern)
            
            assert len(results) >= 1
            assert "print" in results[0].code_snippet
        finally:
            path.unlink()

    def test_search_pattern_no_matches(self) -> None:
        """Should return empty for no matches."""
        engine = SemanticSearchEngine()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = Path(f.name)
        
        try:
            pattern = FunctionCallPattern(function_name="nonexistent")
            results = engine.search_pattern(path, pattern)
            
            assert len(results) == 0
        finally:
            path.unlink()

    def test_search_pattern_syntax_error(self) -> None:
        """Should handle syntax errors."""
        engine = SemanticSearchEngine()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("{{{ invalid")
            f.flush()
            path = Path(f.name)
        
        try:
            pattern = FunctionCallPattern()
            results = engine.search_pattern(path, pattern)
            
            assert results == []
        finally:
            path.unlink()

    def test_search_directory(self) -> None:
        """Should search entire directory."""
        engine = SemanticSearchEngine()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text("print('a')\n")
            (Path(tmpdir) / "b.py").write_text("print('b')\n")
            
            pattern = FunctionCallPattern(function_name="print")
            results = engine.search_directory(Path(tmpdir), pattern)
            
            assert len(results) >= 2

    def test_search_function_calls(self) -> None:
        """Should find function calls."""
        engine = SemanticSearchEngine()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("helper()\nhelper()\n")
            
            results = engine.search_function_calls(Path(tmpdir), "helper")
            
            assert len(results) >= 2

    def test_search_variable_assignments(self) -> None:
        """Should find variable assignments."""
        engine = SemanticSearchEngine()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("data = []\ndata = {}\n")
            
            results = engine.search_variable_assignments(Path(tmpdir), "data")
            
            assert len(results) >= 2

    def test_search_semantic_function_calls(self) -> None:
        """Should perform semantic search for function calls."""
        engine = SemanticSearchEngine()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("process(data)\n")
            
            result = engine.search_semantic(
                Path(tmpdir),
                "function_calls",
                function_name="process"
            )
            
            assert result["query_type"] == "function_calls"
            assert result["total_results"] >= 1

    def test_search_semantic_assignments(self) -> None:
        """Should perform semantic search for assignments."""
        engine = SemanticSearchEngine()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("config = {}\n")
            
            result = engine.search_semantic(
                Path(tmpdir),
                "assignments",
                variable_name="config"
            )
            
            assert result["query_type"] == "assignments"
            assert result["total_results"] >= 1

    def test_search_semantic_unknown_type(self) -> None:
        """Should handle unknown query type."""
        engine = SemanticSearchEngine()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = engine.search_semantic(Path(tmpdir), "unknown")
            
            assert result["total_results"] == 0


class TestSemanticSearch:
    """Test semantic_search convenience function."""

    def test_semantic_search(self) -> None:
        """Should perform semantic search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("foo()\n")
            
            result = semantic_search(
                Path(tmpdir),
                "function_calls",
                function_name="foo"
            )
            
            assert result["total_results"] >= 1
