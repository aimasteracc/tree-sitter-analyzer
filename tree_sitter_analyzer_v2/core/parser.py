"""
Tree-sitter parser implementation.

This module provides a clean wrapper around tree-sitter for parsing source code.
Implements the ParserProtocol interface.
"""

import time
from typing import Any

from tree_sitter_analyzer_v2.core.exceptions import UnsupportedLanguageError
from tree_sitter_analyzer_v2.core.types import ASTNode, ParseResult, SupportedLanguage


class TreeSitterParser:
    """
    Wrapper around tree-sitter parser.

    Provides a clean, protocol-compliant interface for parsing source code
    with tree-sitter. Handles language loading, parsing, and AST conversion.
    """

    def __init__(self, language: str) -> None:
        """
        Initialize parser for a specific language.

        Args:
            language: Language identifier (e.g., 'python', 'typescript')

        Raises:
            UnsupportedLanguageError: If language is not supported
        """
        self._language_name = language

        # Validate language is supported
        lang_enum = SupportedLanguage.from_name(language)
        if lang_enum is None:
            raise UnsupportedLanguageError(language)

        self._lang_enum = lang_enum
        self._ts_parser: Any | None = None
        self._ts_language: Any | None = None

    @property
    def language(self) -> str:
        """Get the language this parser handles."""
        return self._language_name

    def parse(self, source_code: str, file_path: str | None = None) -> ParseResult:
        """
        Parse source code and return AST.

        Args:
            source_code: Source code to parse
            file_path: Optional path to the source file

        Returns:
            ParseResult containing AST and metadata
        """
        # Lazy initialization of tree-sitter
        self._ensure_initialized()

        # Time the parsing operation
        start_time = time.perf_counter()

        # Parse with tree-sitter
        source_bytes = source_code.encode("utf-8")
        ts_tree = self._ts_parser.parse(source_bytes)  # type: ignore
        has_errors = self._check_tree_has_errors(ts_tree.root_node)

        # Convert to our AST representation
        ast_root = self._convert_node(ts_tree.root_node, source_bytes)

        # Calculate parse time
        end_time = time.perf_counter()
        parse_time_ms = (end_time - start_time) * 1000

        return ParseResult(
            tree=ast_root,
            has_errors=has_errors,
            language=self._language_name,
            source_code=source_code,
            file_path=file_path,
            parse_time_ms=parse_time_ms,
        )

    def _ensure_initialized(self) -> None:
        """
        Lazy initialization of tree-sitter parser and language.

        Loads tree-sitter components only when first needed to avoid
        startup overhead.
        """
        if self._ts_parser is not None:
            return  # Already initialized

        # Import tree-sitter only when needed
        try:
            import tree_sitter
        except ImportError as e:
            raise ImportError(
                "tree-sitter library not installed. "
                "Install with: pip install tree-sitter>=0.20.0"
            ) from e

        # Load language-specific tree-sitter library
        self._ts_language = self._load_language()

        # Create parser instance
        self._ts_parser = tree_sitter.Parser(self._ts_language)

    def _load_language(self) -> Any:
        """
        Load tree-sitter language for the parser's language.

        Returns:
            Tree-sitter Language object

        Raises:
            ImportError: If language library not available
        """
        import tree_sitter

        lang_name = self._lang_enum.name

        # Map language names to tree-sitter package names
        if lang_name == "python":
            try:
                from tree_sitter_python import language

                return tree_sitter.Language(language())
            except ImportError as e:
                raise ImportError(
                    "tree-sitter-python not installed. "
                    "Install with: pip install tree-sitter-python"
                ) from e

        elif lang_name == "typescript":
            try:
                from tree_sitter_typescript import language_typescript

                return tree_sitter.Language(language_typescript())
            except ImportError as e:
                raise ImportError(
                    "tree-sitter-typescript not installed. "
                    "Install with: pip install tree-sitter-typescript"
                ) from e

        elif lang_name == "javascript":
            try:
                from tree_sitter_javascript import language

                return tree_sitter.Language(language())
            except ImportError as e:
                raise ImportError(
                    "tree-sitter-javascript not installed. "
                    "Install with: pip install tree-sitter-javascript"
                ) from e

        elif lang_name == "java":
            try:
                from tree_sitter_java import language

                return tree_sitter.Language(language())
            except ImportError as e:
                raise ImportError(
                    "tree-sitter-java not installed. " "Install with: pip install tree-sitter-java"
                ) from e

        # Should not reach here due to validation in __init__
        raise UnsupportedLanguageError(lang_name)

    def _check_tree_has_errors(self, node: Any) -> bool:
        """
        Check if tree-sitter parse tree contains errors.

        Recursively checks node and all descendants for error nodes.

        Args:
            node: Tree-sitter node to check

        Returns:
            True if tree contains errors
        """
        if node.type == "ERROR" or node.is_missing:
            return True

        # Check children recursively
        return any(self._check_tree_has_errors(child) for child in node.children)

    def _convert_node(self, ts_node: Any, source_bytes: bytes) -> ASTNode:
        """
        Convert tree-sitter node to our ASTNode representation.

        Args:
            ts_node: Tree-sitter node
            source_bytes: Source code as bytes (for text extraction)

        Returns:
            ASTNode representing the tree-sitter node
        """
        # Extract text for leaf nodes or small nodes
        text: str | None = None
        if len(ts_node.children) == 0 or ts_node.end_byte - ts_node.start_byte < 100:
            try:
                text = source_bytes[ts_node.start_byte : ts_node.end_byte].decode("utf-8")
            except UnicodeDecodeError:
                text = None  # Skip text if decoding fails

        # Convert children recursively
        children = [self._convert_node(child, source_bytes) for child in ts_node.children]

        return ASTNode(
            type=ts_node.type,
            start_byte=ts_node.start_byte,
            end_byte=ts_node.end_byte,
            start_point=(ts_node.start_point[0], ts_node.start_point[1]),
            end_point=(ts_node.end_point[0], ts_node.end_point[1]),
            text=text,
            children=children,
        )
