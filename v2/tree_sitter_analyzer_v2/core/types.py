"""
Type definitions for parser and analysis operations.

This module defines all data structures and types used in parsing and analysis.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, TypedDict, runtime_checkable


# ── Shared Protocol (bridges code_map.SymbolInfo and graph node dicts) ──


@runtime_checkable
class SymbolProtocol(Protocol):
    """Minimal protocol satisfied by both code_map.SymbolInfo and graph node dicts.

    Any object exposing these read-only properties can participate in
    cross-subsystem analysis (e.g., unified dead-code detection).
    """

    @property
    def name(self) -> str: ...

    @property
    def kind(self) -> str: ...

    @property
    def file(self) -> str: ...

    @property
    def line_start(self) -> int: ...

    @property
    def line_end(self) -> int: ...


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
        return f"ASTNode(type={self.type!r}, text={self.text!r}, children={len(self.children)})"


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
    GO = ("go", [".go"])
    RUST = ("rust", [".rs"])
    C = ("c", [".c", ".h"])
    CPP = ("cpp", [".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"])

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
    def name(self) -> str:
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


# ── Domain model TypedDicts ──
# These replace raw dict[str, Any] in language parser return types.


class FunctionInfo(TypedDict, total=False):
    """Structured function/method information from language parsers."""

    name: str
    start_line: int
    end_line: int
    visibility: str
    is_static: bool
    is_constructor: bool
    is_async: bool
    return_type: str
    parameters: list[dict[str, Any]]
    decorators: list[str]
    docstring: str


class ClassInfo(TypedDict, total=False):
    """Structured class information from language parsers."""

    name: str
    start_line: int
    end_line: int
    visibility: str
    bases: list[str]
    interfaces: list[str]
    methods: list[FunctionInfo]
    fields: list[dict[str, Any]]
    decorators: list[str]
    docstring: str
    is_abstract: bool
    is_interface: bool


class ImportInfo(TypedDict, total=False):
    """Structured import information from language parsers."""

    module: str
    names: list[str]
    alias: str
    line: int
    is_from_import: bool


class ParseMetadata(TypedDict, total=False):
    """Metadata about a parse operation."""

    total_functions: int
    total_classes: int
    total_imports: int
    has_main_block: bool
    package: str
    total_lines: int


class LanguageParseResult(TypedDict, total=False):
    """Structured result from language-specific parsers (replaces dict[str, Any]).

    This is the canonical return type for PythonParser.parse(),
    JavaParser.parse(), TypeScriptParser.parse(), etc.
    """

    ast: Any  # ASTNode — kept as Any for tree-sitter compatibility
    functions: list[FunctionInfo]
    classes: list[ClassInfo]
    imports: list[ImportInfo]
    metadata: ParseMetadata
    errors: bool
    fields: list[dict[str, Any]]  # Java-specific: top-level fields


# ── Language Profile (data-driven language adapter) ──


@dataclass(frozen=True)
class LanguageProfile:
    """Data-driven language configuration for the generic parser.

    Instead of writing a full parser class (300-700 LOC) for each language,
    define a LanguageProfile with AST node type mappings and let
    GenericLanguageParser handle the extraction.

    Example:
        GO_PROFILE = LanguageProfile(
            name="go", extensions=(".go",), tree_sitter_name="go",
            function_node_types=("function_declaration",),
            class_node_types=("type_declaration",),
            import_node_types=("import_declaration",),
        )
    """

    # Identity
    name: str
    extensions: tuple[str, ...]
    tree_sitter_name: str  # tree-sitter grammar name

    # AST node type mappings — which node types represent each construct
    function_node_types: tuple[str, ...] = ()
    method_node_types: tuple[str, ...] = ()
    class_node_types: tuple[str, ...] = ()
    import_node_types: tuple[str, ...] = ()

    # Field child names in AST (how to locate name, params, body, etc.)
    name_field: str = "name"
    params_field: str = "parameters"
    body_field: str = "body"
    return_type_field: str = "return_type"

    # Visibility / modifier detection
    visibility_node_type: str = ""
    public_keywords: tuple[str, ...] = ("public",)
    default_visibility: str = "public"

    # Import extraction
    import_path_field: str = "path"

    # Comment / docstring
    comment_node_types: tuple[str, ...] = ("comment",)
    docstring_position: str = "before"  # "before" or "first_child"

    # Language-specific feature flags
    has_interfaces: bool = False
    has_packages: bool = False
    has_decorators: bool = False
    has_async: bool = False
    async_keyword: str = "async"

    # Package node type (for Go, Java, etc.)
    package_node_type: str = ""

    # Interface / trait node types
    interface_node_types: tuple[str, ...] = ()
