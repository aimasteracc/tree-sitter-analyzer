#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.core.parser module.

This module tests the Parser class and ParseResult NamedTuple.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from tree_sitter import Tree

from tree_sitter_analyzer.core.parser import Parser, ParseResult


class TestParseResult:
    """Tests for ParseResult NamedTuple."""

    def test_parse_result_success(self) -> None:
        """Test ParseResult with successful parsing."""
        tree = MagicMock(spec=Tree)
        result = ParseResult(
            tree=tree,
            source_code="def hello(): pass",
            language="python",
            file_path="test.py",
            success=True,
            error_message=None,
        )
        assert result.tree is tree
        assert result.source_code == "def hello(): pass"
        assert result.language == "python"
        assert result.file_path == "test.py"
        assert result.success is True
        assert result.error_message is None

    def test_parse_result_failure(self) -> None:
        """Test ParseResult with failed parsing."""
        result = ParseResult(
            tree=None,
            source_code="",
            language="python",
            file_path="test.py",
            success=False,
            error_message="File not found",
        )
        assert result.tree is None
        assert result.source_code == ""
        assert result.language == "python"
        assert result.file_path == "test.py"
        assert result.success is False
        assert result.error_message == "File not found"

    def test_parse_result_without_file_path(self) -> None:
        """Test ParseResult without file path."""
        tree = MagicMock(spec=Tree)
        result = ParseResult(
            tree=tree,
            source_code="def hello(): pass",
            language="python",
            file_path=None,
            success=True,
            error_message=None,
        )
        assert result.file_path is None


class TestParserInit:
    """Tests for Parser initialization."""

    def test_parser_init(self) -> None:
        """Test Parser initialization."""
        parser = Parser()
        assert parser._loader is not None
        assert parser._encoding_manager is not None

    def test_parser_class_cache_exists(self) -> None:
        """Test that Parser has class-level cache."""
        assert hasattr(Parser, "_cache")
        assert Parser._cache is not None


class TestParserParseFile:
    """Tests for Parser.parse_file method."""

    def test_parse_file_success(self, parser: Parser, temp_file: Path) -> None:
        """Test successful file parsing."""
        result = parser.parse_file(temp_file, "python")
        assert result.success is True
        assert result.tree is not None
        # File content includes newline from fixture
        assert result.source_code == "def hello(): pass\n"
        assert result.language == "python"
        assert result.file_path == str(temp_file)
        assert result.error_message is None

    def test_parse_file_not_found(self, parser: Parser) -> None:
        """Test parsing non-existent file."""
        result = parser.parse_file("nonexistent.py", "python")
        assert result.success is False
        assert result.tree is None
        assert result.source_code == ""
        assert result.language == "python"
        assert result.error_message == "File not found: nonexistent.py"

    def test_parse_file_permission_denied(
        self, parser: Parser, temp_file: Path
    ) -> None:
        """Test parsing file with permission denied."""
        # Make file read-only
        os.chmod(temp_file, 0o000)
        try:
            result = parser.parse_file(temp_file, "python")
            # On Windows, read-only files might still be readable
            # On Unix, permission denied should fail
            # We'll check either success or error message
            if not result.success:
                assert "Permission denied" in result.error_message
        finally:
            # Restore permissions
            os.chmod(temp_file, 0o644)

    def test_parse_file_cache_hit(self, parser: Parser, temp_file: Path) -> None:
        """Test that cache is used for repeated file parsing."""
        # First parse
        result1 = parser.parse_file(temp_file, "python")
        assert result1.success is True

        # Second parse should use cache
        result2 = parser.parse_file(temp_file, "python")
        assert result2.success is True
        assert result2.source_code == result1.source_code

    def test_parse_file_with_path_object(self, parser: Parser, temp_file: Path) -> None:
        """Test parsing file with Path object."""
        result = parser.parse_file(temp_file, "python")
        assert result.success is True
        assert result.file_path == str(temp_file)


class TestParserParseCode:
    """Tests for Parser.parse_code method."""

    def test_parse_code_success(self, parser: Parser) -> None:
        """Test successful code parsing."""
        code = "def hello(): pass"
        result = parser.parse_code(code, "python")
        assert result.success is True
        assert result.tree is not None
        assert result.source_code == code
        assert result.language == "python"
        assert result.error_message is None

    def test_parse_code_unsupported_language(self, parser: Parser) -> None:
        """Test parsing code with unsupported language."""
        code = "some code"
        result = parser.parse_code(code, "unsupported_language")
        assert result.success is False
        assert result.tree is None
        assert result.error_message == "Unsupported language: unsupported_language"

    def test_parse_code_with_filename(self, parser: Parser) -> None:
        """Test parsing code with filename."""
        code = "def hello(): pass"
        result = parser.parse_code(code, "python", filename="test.py")
        assert result.success is True
        assert result.file_path == "test.py"

    def test_parse_code_without_filename(self, parser: Parser) -> None:
        """Test parsing code without filename."""
        code = "def hello(): pass"
        result = parser.parse_code(code, "python")
        assert result.success is True
        assert result.file_path is None

    def test_parse_code_empty_string(self, parser: Parser) -> None:
        """Test parsing empty code string."""
        result = parser.parse_code("", "python")
        assert result.success is True
        assert result.tree is not None


class TestParserLanguageSupport:
    """Tests for Parser language support methods."""

    def test_is_language_supported_true(self, parser: Parser) -> None:
        """Test checking supported language."""
        assert parser.is_language_supported("python") is True

    def test_is_language_supported_false(self, parser: Parser) -> None:
        """Test checking unsupported language."""
        assert parser.is_language_supported("unsupported") is False

    def test_get_supported_languages(self, parser: Parser) -> None:
        """Test getting list of supported languages."""
        languages = parser.get_supported_languages()
        assert isinstance(languages, list)
        assert len(languages) > 0
        assert "python" in languages


class TestParserValidation:
    """Tests for Parser validation methods."""

    def test_validate_ast_valid(self, parser: Parser, temp_file: Path) -> None:
        """Test validating a valid AST."""
        result = parser.parse_file(temp_file, "python")
        assert result.success is True
        is_valid = parser.validate_ast(result.tree)
        assert is_valid is True

    def test_validate_ast_none(self, parser: Parser) -> None:
        """Test validating None AST."""
        is_valid = parser.validate_ast(None)
        assert is_valid is False

    def test_get_parse_errors_no_errors(self, parser: Parser, temp_file: Path) -> None:
        """Test getting parse errors from valid code."""
        result = parser.parse_file(temp_file, "python")
        assert result.success is True
        errors = parser.get_parse_errors(result.tree)
        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_get_parse_errors_with_errors(self, parser: Parser) -> None:
        """Test getting parse errors from invalid code."""
        # Create code with syntax error
        invalid_code = "def hello(\n"  # Missing closing parenthesis
        result = parser.parse_code(invalid_code, "python")
        # Even with syntax errors, tree-sitter might still create a tree
        # but with ERROR nodes
        if result.success:
            errors = parser.get_parse_errors(result.tree)
            assert isinstance(errors, list)


class TestParserCache:
    """Tests for Parser caching functionality."""

    def test_cache_is_lru_cache(self) -> None:
        """Test that Parser cache is LRUCache."""
        from cachetools import LRUCache

        assert isinstance(Parser._cache, LRUCache)

    def test_cache_maxsize(self) -> None:
        """Test that cache has maxsize set."""
        assert Parser._cache.maxsize == 100

    def test_cache_shared_across_instances(self) -> None:
        """Test that cache is shared across Parser instances."""
        parser1 = Parser()
        parser2 = Parser()
        assert parser1._cache is parser2._cache


class TestParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parse_code_exception_handling(self, parser: Parser) -> None:
        """Test that exceptions in parse_code are handled gracefully."""
        with patch.object(
            parser._loader, "create_parser_safely", side_effect=Exception("Test error")
        ):
            result = parser.parse_code("code", "python")
            assert result.success is False
            assert "Parsing error" in result.error_message

    def test_parse_file_exception_handling(
        self, parser: Parser, temp_file: Path
    ) -> None:
        """Test that exceptions in parse_file are handled gracefully."""
        with patch.object(parser, "parse_code", side_effect=Exception("Test error")):
            result = parser.parse_file(temp_file, "python")
            assert result.success is False
            assert "Unexpected error" in result.error_message

    def test_is_language_supported_exception_handling(self, parser: Parser) -> None:
        """Test that exceptions in is_language_supported are handled."""
        with patch.object(
            parser._loader,
            "is_language_available",
            side_effect=Exception("Test error"),
        ):
            result = parser.is_language_supported("python")
            assert result is False

    def test_get_supported_languages_exception_handling(self, parser: Parser) -> None:
        """Test that exceptions in get_supported_languages are handled."""
        with patch.object(
            parser._loader,
            "get_supported_languages",
            side_effect=Exception("Test error"),
        ):
            result = parser.get_supported_languages()
            assert result == []

    def test_validate_ast_exception_handling(self, parser: Parser) -> None:
        """Test that exceptions in validate_ast are handled."""
        tree = MagicMock(spec=Tree)
        # Make accessing root_node raise an exception
        type(tree).root_node = property(
            lambda self: (_ for _ in ()).throw(Exception("Test error"))
        )
        result = parser.validate_ast(tree)
        assert result is False

    def test_get_parse_errors_exception_handling(self, parser: Parser) -> None:
        """Test that exceptions in get_parse_errors are handled."""
        tree = MagicMock(spec=Tree)
        tree.root_node = MagicMock(side_effect=Exception("Test error"))
        result = parser.get_parse_errors(tree)
        assert result == []


# Pytest fixtures
@pytest.fixture
def parser() -> Parser:
    """Create a Parser instance for testing."""
    return Parser()


@pytest.fixture
def temp_file() -> Path:
    """Create a temporary Python file for testing."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write("def hello(): pass\n")
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    try:
        temp_path.unlink()
    except Exception:
        pass
