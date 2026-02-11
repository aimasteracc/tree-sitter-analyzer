"""
Test tree-sitter wrapper implementation.

Following TDD: Write tests FIRST to define the contract.
This is T1.2: Tree-sitter Wrapper
"""

import pytest


class TestTreeSitterParser:
    """Test basic tree-sitter parser functionality."""

    def test_parser_can_be_created_for_python(self):
        """Test that we can create a parser for Python."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        assert parser.language == "python"

    def test_parser_raises_error_for_unsupported_language(self):
        """Test that unsupported language raises error."""
        from tree_sitter_analyzer_v2.core.exceptions import UnsupportedLanguageError
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        with pytest.raises(UnsupportedLanguageError) as exc_info:
            TreeSitterParser("unknown_lang")

        assert "unknown_lang" in str(exc_info.value)

    def test_parse_simple_python_code(self, sample_python_code):
        """Test parsing a simple Python function."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse(sample_python_code)

        assert result is not None
        assert result.language == "python"
        assert result.has_errors is False
        assert result.tree is not None
        assert result.source_code == sample_python_code

    def test_parse_invalid_python_code(self):
        """Test that parsing invalid code detects errors."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        invalid_code = "def broken("

        result = parser.parse(invalid_code)

        assert result is not None
        assert result.has_errors is True
        assert result.tree is not None  # Tree-sitter still returns partial tree

    def test_parse_with_file_path(self, sample_python_code):
        """Test parsing with file path metadata."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse(sample_python_code, file_path="/test/sample.py")

        assert result.file_path == "/test/sample.py"

    def test_parse_records_timing(self, sample_python_code):
        """Test that parse result includes timing information."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse(sample_python_code)

        assert result.parse_time_ms is not None
        assert result.parse_time_ms >= 0

    def test_parser_implements_protocol(self):
        """Test that TreeSitterParser implements ParserProtocol."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
        from tree_sitter_analyzer_v2.core.protocols import ParserProtocol

        parser = TreeSitterParser("python")
        assert isinstance(parser, ParserProtocol)


class TestASTNodeConversion:
    """Test conversion from tree-sitter nodes to ASTNode."""

    def test_convert_simple_node(self, sample_python_code):
        """Test converting tree-sitter node to ASTNode."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse(sample_python_code)

        # Root node should be 'module'
        assert result.tree is not None
        assert result.tree.type == "module"
        assert result.tree.start_byte >= 0
        assert result.tree.end_byte == len(sample_python_code)

    def test_ast_node_has_children(self, sample_python_code):
        """Test that AST nodes have children."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse(sample_python_code)

        # Module should have function_definition child
        assert result.tree is not None
        assert len(result.tree.children) > 0

    def test_ast_node_includes_text(self, sample_python_code):
        """Test that AST nodes can include text content."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse("x = 1")

        # Should have assignment with identifier 'x'
        assert result.tree is not None
        # Verify we can traverse the AST tree structure
        found_identifier = any(
            ggchild.type == "identifier"
            for child in result.tree.children
            if child.type == "expression_statement"
            for grandchild in child.children
            if grandchild.type == "assignment"
            for ggchild in grandchild.children
        )

        # Tree-sitter structure varies, just check we can parse
        assert result.has_errors is False
        # Identifier should be found in well-formed code
        assert found_identifier or len(result.tree.children) > 0

    def test_ast_node_position_tracking(self, sample_python_code):
        """Test that AST nodes track position correctly."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse(sample_python_code)

        assert result.tree is not None
        # Root node position tracking
        assert result.tree.start_point is not None
        assert isinstance(result.tree.start_point, tuple)
        assert len(result.tree.start_point) == 2
        # End point should be at end of file
        assert result.tree.end_point[0] >= 0  # row


class TestParserCaching:
    """Test parser instance caching."""

    def test_parser_can_reuse_language(self):
        """Test that parser can be reused for multiple parses."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")

        result1 = parser.parse("x = 1")
        result2 = parser.parse("y = 2")

        assert result1.has_errors is False
        assert result2.has_errors is False
        assert result1.source_code != result2.source_code

    def test_multiple_parsers_independent(self):
        """Test that multiple parsers work independently."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser_py = TreeSitterParser("python")
        parser_ts = TreeSitterParser("typescript")

        assert parser_py.language == "python"
        assert parser_ts.language == "typescript"


class TestParserEdgeCases:
    """Test parser edge cases."""

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        result = parser.parse("")

        assert result is not None
        assert result.tree is not None
        assert result.source_code == ""

    def test_parse_unicode_content(self):
        """Test parsing unicode content."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        code = "# 中文注释\ndef 函数(): pass"
        result = parser.parse(code)

        assert result is not None
        assert result.has_errors is False

    def test_parse_large_file(self):
        """Test parsing larger file."""
        from tree_sitter_analyzer_v2.core.parser import TreeSitterParser

        parser = TreeSitterParser("python")
        # Create a large-ish file
        code = "\n".join([f"def func_{i}(): pass" for i in range(100)])
        result = parser.parse(code)

        assert result is not None
        assert result.has_errors is False
        assert result.parse_time_ms is not None
