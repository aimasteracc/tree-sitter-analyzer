"""
Protocol definitions for parser interface.

This module defines the abstract interfaces that parsers must implement.
Using protocols (PEP 544) for structural subtyping.
"""

from typing import Protocol, runtime_checkable

from tree_sitter_analyzer_v2.core.types import ParseResult


@runtime_checkable
class ParserProtocol(Protocol):
    """
    Protocol defining the interface that all parsers must implement.

    This uses structural subtyping (PEP 544) so any class that implements
    these methods will be considered a valid parser.
    """

    @property
    def language(self) -> str:
        """
        Get the language this parser handles.

        Returns:
            Language identifier (e.g., 'python')
        """
        ...

    def parse(self, source_code: str, file_path: str | None = None) -> ParseResult:
        """
        Parse source code and return AST.

        Args:
            source_code: Source code to parse
            file_path: Optional path to the source file

        Returns:
            ParseResult containing AST and metadata

        Raises:
            ParseError: If parsing fails critically
        """
        ...
