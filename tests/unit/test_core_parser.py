"""Tests for TreeSitterParser implementation."""

import pytest
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
from tree_sitter_analyzer_v2.core.exceptions import UnsupportedLanguageError


class TestTreeSitterParserInit:
    """Tests for TreeSitterParser initialization."""

    def test_init_python(self) -> None:
        """Test initialization with Python language."""
        parser = TreeSitterParser("python")
        assert parser.language == "python"

    def test_init_typescript(self) -> None:
        """Test initialization with TypeScript language."""
        parser = TreeSitterParser("typescript")
        assert parser.language == "typescript"

    def test_init_javascript(self) -> None:
        """Test initialization with JavaScript language."""
        parser = TreeSitterParser("javascript")
        assert parser.language == "javascript"

    def test_init_java(self) -> None:
        """Test initialization with Java language."""
        parser = TreeSitterParser("java")
        assert parser.language == "java"

    def test_init_unsupported_language(self) -> None:
        """Test initialization with unsupported language raises error."""
        with pytest.raises(UnsupportedLanguageError):
            TreeSitterParser("cobol")


class TestTreeSitterParserParse:
    """Tests for TreeSitterParser.parse method."""

    def test_parse_python_simple(self) -> None:
        """Test parsing simple Python code."""
        parser = TreeSitterParser("python")
        result = parser.parse("x = 1\n", "test.py")
        
        assert result.language == "python"
        assert result.file_path == "test.py"
        assert result.source_code == "x = 1\n"
        assert result.tree is not None
        assert result.parse_time_ms >= 0

    def test_parse_python_function(self) -> None:
        """Test parsing Python function."""
        parser = TreeSitterParser("python")
        code = '''
def hello(name):
    return f"Hello, {name}!"
'''
        result = parser.parse(code)
        
        assert result.language == "python"
        assert result.tree is not None
        assert not result.has_errors

    def test_parse_with_syntax_errors(self) -> None:
        """Test parsing code with syntax errors."""
        parser = TreeSitterParser("python")
        code = "def broken("  # Incomplete function definition
        result = parser.parse(code)
        
        assert result.has_errors is True

    def test_parse_without_file_path(self) -> None:
        """Test parsing without file path."""
        parser = TreeSitterParser("python")
        result = parser.parse("x = 1")
        
        assert result.file_path is None

    def test_parse_typescript(self) -> None:
        """Test parsing TypeScript code."""
        parser = TreeSitterParser("typescript")
        code = "const x: number = 42;\n"
        result = parser.parse(code, "test.ts")
        
        assert result.language == "typescript"
        assert result.tree is not None

    def test_parse_javascript(self) -> None:
        """Test parsing JavaScript code."""
        parser = TreeSitterParser("javascript")
        code = "const x = 42;\n"
        result = parser.parse(code, "test.js")
        
        assert result.language == "javascript"
        assert result.tree is not None

    def test_parse_java(self) -> None:
        """Test parsing Java code."""
        parser = TreeSitterParser("java")
        code = "public class Test { }\n"
        result = parser.parse(code, "Test.java")
        
        assert result.language == "java"
        assert result.tree is not None


class TestTreeSitterParserLazyInit:
    """Tests for lazy initialization."""

    def test_lazy_init_only_on_parse(self) -> None:
        """Test that parser initialization is lazy."""
        parser = TreeSitterParser("python")
        
        # Parser should not be initialized yet
        assert parser._ts_parser is None
        assert parser._ts_language is None
        
        # After parse, parser should be initialized
        parser.parse("x = 1")
        assert parser._ts_parser is not None
        assert parser._ts_language is not None

    def test_reuse_parser_instance(self) -> None:
        """Test that parser instance is reused."""
        parser = TreeSitterParser("python")
        
        # Parse once to initialize
        parser.parse("x = 1")
        ts_parser = parser._ts_parser
        
        # Parse again - should reuse parser
        parser.parse("y = 2")
        assert parser._ts_parser is ts_parser


class TestTreeSitterParserConvertNode:
    """Tests for node conversion."""

    def test_ast_node_structure(self) -> None:
        """Test AST node structure is correct."""
        parser = TreeSitterParser("python")
        result = parser.parse("x = 1")
        
        root = result.tree
        assert root.type == "module"
        assert root.start_point == (0, 0)
        assert len(root.children) > 0

    def test_ast_node_text_extraction(self) -> None:
        """Test text is extracted for nodes."""
        parser = TreeSitterParser("python")
        result = parser.parse("x = 1")
        
        # Find identifier node
        def find_identifier(node):
            if node.type == "identifier":
                return node
            for child in node.children:
                found = find_identifier(child)
                if found:
                    return found
            return None
        
        identifier = find_identifier(result.tree)
        assert identifier is not None
        assert identifier.text == "x"


class TestTreeSitterParserErrorHandling:
    """Tests for error handling."""

    def test_check_tree_has_errors_valid(self) -> None:
        """Test error checking with valid code."""
        parser = TreeSitterParser("python")
        result = parser.parse("x = 1")
        assert result.has_errors is False

    def test_check_tree_has_errors_invalid(self) -> None:
        """Test error checking with invalid code."""
        parser = TreeSitterParser("python")
        result = parser.parse("def ()")  # Invalid syntax
        assert result.has_errors is True

    def test_parse_empty_code(self) -> None:
        """Test parsing empty code."""
        parser = TreeSitterParser("python")
        result = parser.parse("")
        
        assert result.tree is not None
        assert result.tree.type == "module"


class TestTreeSitterParserLanguageLoading:
    """Tests for language loading."""

    def test_python_language_loads(self) -> None:
        """Test Python language loads successfully."""
        parser = TreeSitterParser("python")
        parser._ensure_initialized()
        assert parser._ts_language is not None

    def test_typescript_language_loads(self) -> None:
        """Test TypeScript language loads successfully."""
        parser = TreeSitterParser("typescript")
        parser._ensure_initialized()
        assert parser._ts_language is not None

    def test_javascript_language_loads(self) -> None:
        """Test JavaScript language loads successfully."""
        parser = TreeSitterParser("javascript")
        parser._ensure_initialized()
        assert parser._ts_language is not None

    def test_java_language_loads(self) -> None:
        """Test Java language loads successfully."""
        parser = TreeSitterParser("java")
        parser._ensure_initialized()
        assert parser._ts_language is not None


class TestTreeSitterParserMultiLine:
    """Tests for multi-line code parsing."""

    def test_parse_multiline_python(self) -> None:
        """Test parsing multi-line Python code."""
        parser = TreeSitterParser("python")
        code = '''class Test:
    def __init__(self):
        self.x = 1
        
    def method(self):
        return self.x
'''
        result = parser.parse(code)
        
        assert not result.has_errors
        assert result.tree is not None

    def test_line_column_info(self) -> None:
        """Test line/column information is accurate."""
        parser = TreeSitterParser("python")
        code = "x = 1\ny = 2\n"
        result = parser.parse(code)
        
        # Root node should start at (0, 0)
        assert result.tree.start_point == (0, 0)
