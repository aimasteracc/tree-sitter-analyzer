"""
Type definitions for parser and analysis operations.

This module defines all data structures and types used in parsing and analysis.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


@dataclass
class ASTNode:
    """
    Representation of a tree-sitter AST node.

    This is a simplified, serializable representation of tree-sitter nodes
    that can be easily used across the codebase.

    Attributes:
        type: Node type (e.g., 'function_definition', 'identifier')
        start_byte: Start position in bytes
        end_byte: End position in bytes
        start_point: Start position as (row, column)
        end_point: End position as (row, column)
        text: Optional text content of the node
        children: Child nodes
    """

    type: str
    start_byte: int
    end_byte: int
    start_point: tuple[int, int]
    end_point: tuple[int, int]
    text: str | None = None
    children: list["ASTNode"] = field(default_factory=list)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"ASTNode(type={self.type!r}, "
            f"text={self.text!r}, "
            f"children={len(self.children)})"
        )


@dataclass
class ParseResult:
    """
    Result of a parsing operation.

    Contains the parsed AST tree and metadata about the parsing operation.

    Attributes:
        tree: The root AST node (None if parsing failed)
        has_errors: Whether the parse contained syntax errors
        language: Language that was parsed
        source_code: The source code that was parsed
        error_message: Error message if parsing failed
        file_path: Optional path to the file that was parsed
        parse_time_ms: Time taken to parse in milliseconds
    """

    tree: ASTNode | None
    has_errors: bool
    language: str
    source_code: str
    error_message: str | None = None
    file_path: str | None = None
    parse_time_ms: float | None = None

    def is_valid(self) -> bool:
        """
        Check if parse result is valid (no errors).

        Returns:
            True if parsing succeeded without errors
        """
        return not self.has_errors and self.tree is not None


class SupportedLanguage(Enum):
    """
    Enumeration of supported programming languages.

    Each language has:
    - name: Language identifier (lowercase)
    - extensions: File extensions for this language
    """

    PYTHON = ("python", [".py", ".pyw", ".pyi"])
    TYPESCRIPT = ("typescript", [".ts", ".tsx"])
    JAVASCRIPT = ("javascript", [".js", ".jsx", ".mjs", ".cjs"])
    JAVA = ("java", [".java"])

    def __init__(self, language_name: str, file_extensions: list[str]) -> None:
        """
        Initialize language enum value.

        Args:
            language_name: Language identifier
            file_extensions: List of file extensions
        """
        self._language_name = language_name
        self._file_extensions = file_extensions

    @property
    def name(self) -> str:  # type: ignore[override]
        """Get language name."""
        return self._language_name

    @property
    def extensions(self) -> list[str]:
        """Get file extensions for this language."""
        return self._file_extensions

    @classmethod
    def from_extension(cls, extension: str) -> Optional["SupportedLanguage"]:
        """
        Get language from file extension.

        Args:
            extension: File extension (e.g., '.py')

        Returns:
            SupportedLanguage if found, None otherwise
        """
        for lang in cls:
            if extension.lower() in lang.extensions:
                return lang
        return None

    @classmethod
    def from_name(cls, name: str) -> Optional["SupportedLanguage"]:
        """
        Get language from name.

        Args:
            name: Language name (e.g., 'python')

        Returns:
            SupportedLanguage if found, None otherwise
        """
        name_lower = name.lower()
        for lang in cls:
            if lang.name == name_lower:
                return lang
        return None
