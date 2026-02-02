"""
Test parser interface and protocols.

Following TDD: Write interface tests FIRST to define the contract.
This is T1.1: Parser Interface Design
"""


class TestParserProtocol:
    """Test that parser protocol is properly defined."""

    def test_parser_protocol_exists(self):
        """Test that ParserProtocol is defined."""
        from tree_sitter_analyzer_v2.core.protocols import ParserProtocol

        assert ParserProtocol is not None

    def test_parser_protocol_has_parse_method(self):
        """Test that protocol defines parse method."""
        from tree_sitter_analyzer_v2.core.protocols import ParserProtocol

        # Protocol should require parse method
        assert hasattr(ParserProtocol, "parse")

    def test_parser_protocol_has_language_property(self):
        """Test that protocol defines language property."""
        from tree_sitter_analyzer_v2.core.protocols import ParserProtocol

        assert hasattr(ParserProtocol, "language")


class TestParseResult:
    """Test ParseResult data structure."""

    def test_parse_result_exists(self):
        """Test that ParseResult type exists."""
        from tree_sitter_analyzer_v2.core.types import ParseResult

        assert ParseResult is not None

    def test_parse_result_has_required_fields(self):
        """Test ParseResult has all required fields."""
        from tree_sitter_analyzer_v2.core.types import ParseResult

        # Create a parse result
        result = ParseResult(
            tree=None,
            has_errors=False,
            language="python",
            source_code="print('hello')",
        )

        assert hasattr(result, "tree")
        assert hasattr(result, "has_errors")
        assert hasattr(result, "language")
        assert hasattr(result, "source_code")
        assert result.has_errors is False
        assert result.language == "python"

    def test_parse_result_with_errors(self):
        """Test ParseResult can represent errors."""
        from tree_sitter_analyzer_v2.core.types import ParseResult

        result = ParseResult(
            tree=None,
            has_errors=True,
            language="python",
            source_code="def broken(",
            error_message="Syntax error at position 11",
        )

        assert result.has_errors is True
        assert result.error_message is not None
        assert "Syntax error" in result.error_message

    def test_parse_result_optional_metadata(self):
        """Test ParseResult can include optional metadata."""
        from tree_sitter_analyzer_v2.core.types import ParseResult

        result = ParseResult(
            tree=None,
            has_errors=False,
            language="python",
            source_code="x = 1",
            file_path="/path/to/file.py",
            parse_time_ms=15.5,
        )

        assert result.file_path == "/path/to/file.py"
        assert result.parse_time_ms == 15.5


class TestParserExceptions:
    """Test parser exception types."""

    def test_unsupported_language_error_exists(self):
        """Test UnsupportedLanguageError exception."""
        from tree_sitter_analyzer_v2.core.exceptions import UnsupportedLanguageError

        error = UnsupportedLanguageError("unknown_lang")
        assert "unknown_lang" in str(error)

    def test_parse_error_exists(self):
        """Test ParseError exception."""
        from tree_sitter_analyzer_v2.core.exceptions import ParseError

        error = ParseError("Failed to parse", file_path="/test.py")
        assert "Failed to parse" in str(error)
        assert hasattr(error, "file_path")

    def test_file_too_large_error_exists(self):
        """Test FileTooLargeError exception."""
        from tree_sitter_analyzer_v2.core.exceptions import FileTooLargeError

        error = FileTooLargeError("/huge.py", size=10_000_000, max_size=1_000_000)
        assert "/huge.py" in str(error)
        assert hasattr(error, "size")
        assert hasattr(error, "max_size")


class TestASTNodeTypes:
    """Test AST node type definitions."""

    def test_ast_node_exists(self):
        """Test that ASTNode type is defined."""
        from tree_sitter_analyzer_v2.core.types import ASTNode

        # Should be able to create an AST node representation
        node = ASTNode(
            type="function_definition",
            start_byte=0,
            end_byte=50,
            start_point=(0, 0),
            end_point=(5, 0),
        )

        assert node.type == "function_definition"
        assert node.start_byte == 0
        assert node.end_byte == 50

    def test_ast_node_with_children(self):
        """Test ASTNode can have children."""
        from tree_sitter_analyzer_v2.core.types import ASTNode

        child = ASTNode(
            type="identifier", start_byte=4, end_byte=8, start_point=(0, 4), end_point=(0, 8)
        )

        parent = ASTNode(
            type="function_definition",
            start_byte=0,
            end_byte=50,
            start_point=(0, 0),
            end_point=(5, 0),
            children=[child],
        )

        assert len(parent.children) == 1
        assert parent.children[0].type == "identifier"

    def test_ast_node_text_content(self):
        """Test ASTNode can store text content."""
        from tree_sitter_analyzer_v2.core.types import ASTNode

        node = ASTNode(
            type="identifier",
            start_byte=4,
            end_byte=8,
            start_point=(0, 4),
            end_point=(0, 8),
            text="test",
        )

        assert node.text == "test"


class TestLanguageEnum:
    """Test language enumeration."""

    def test_supported_languages_defined(self):
        """Test that supported languages are enumerated."""
        from tree_sitter_analyzer_v2.core.types import SupportedLanguage

        # Should have at least the 3 initial languages
        assert hasattr(SupportedLanguage, "PYTHON")
        assert hasattr(SupportedLanguage, "TYPESCRIPT")
        assert hasattr(SupportedLanguage, "JAVA")

    def test_language_has_extensions(self):
        """Test that each language knows its file extensions."""
        from tree_sitter_analyzer_v2.core.types import SupportedLanguage

        python = SupportedLanguage.PYTHON
        assert ".py" in python.extensions
        assert ".pyw" in python.extensions

    def test_language_has_name(self):
        """Test that each language has a name."""
        from tree_sitter_analyzer_v2.core.types import SupportedLanguage

        assert SupportedLanguage.PYTHON.name == "python"
        assert SupportedLanguage.TYPESCRIPT.name == "typescript"
        assert SupportedLanguage.JAVA.name == "java"
