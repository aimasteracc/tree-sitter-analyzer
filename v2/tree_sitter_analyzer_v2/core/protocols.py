"""
Protocol definitions for the structured parser interface.

This module defines ParserProtocol — the interface for tree-sitter wrapper
parsers that return strongly-typed ParseResult objects.

NOTE: This is distinct from `parser_registry.LanguageParser`, which is the
protocol for language-specific parsers that return `dict[str, Any]`
(unstructured data used by CodeMap). The two serve different layers:

- ParserProtocol: Low-level tree-sitter wrapper → ParseResult (structured)
- LanguageParser: Language plugin → dict (flexible, schema-defined by TypedDict)

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
