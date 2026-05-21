#!/usr/bin/env python3
"""
C# Language Plugin

Provides C#-specific parsing and element extraction functionality.
Supports extraction of classes, interfaces, records, methods, properties, fields, and using directives.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

    from ..core.request import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from ..utils.tree_sitter_compat import get_node_text_safe
from .csharp_helpers import (
    calculate_complexity as _calc_complexity_standalone,
)
from .csharp_helpers import (
    determine_visibility as _determine_vis_standalone,
)
from .csharp_helpers import (
    extract_attributes as _extract_attrs_standalone,
)
from .csharp_helpers import (
    extract_class_declaration as _extract_class_standalone,
)
from .csharp_helpers import (
    extract_constructor_declaration as _extract_ctor_standalone,
)
from .csharp_helpers import (
    extract_event_declaration as _extract_event_standalone,
)
from .csharp_helpers import (
    extract_field_declaration as _extract_field_standalone,
)
from .csharp_helpers import (
    extract_method_declaration as _extract_method_standalone,
)
from .csharp_helpers import (
    extract_modifiers as _extract_mods_standalone,
)
from .csharp_helpers import (
    extract_parameters as _extract_params_standalone,
)
from .csharp_helpers import (
    extract_property_declaration as _extract_prop_standalone,
)
from .csharp_helpers import (
    extract_type_name as _extract_type_standalone,
)
from .csharp_helpers import (
    extract_using_directive as _extract_using_standalone,
)


def _traverse_nodes(root_node: "tree_sitter.Node") -> Iterator["tree_sitter.Node"]:
    stack = [root_node]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(list(node.children)))


class CSharpElementExtractor(ElementExtractor):
    """
    C#-specific element extractor.

    This extractor parses C# AST and extracts code elements, mapping them
    to the unified element model:
    - Classes, Interfaces, Records, Enums, Structs → Class elements
    - Methods, Constructors, Properties → Function elements
    - Fields, Constants, Events → Variable elements
    - Using directives → Import elements

    The extractor handles modern C# syntax including:
    - C# 8+ nullable reference types
    - C# 9+ records
    - Async/await patterns
    - Attributes (annotations)
    - Generic types
    """

    def __init__(self) -> None:
        """
        Initialize the C# element extractor.

        Sets up internal state for source code processing and performance
        optimization caches for node text extraction.
        """
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.current_namespace: str = ""

        # Performance optimization caches - use position-based keys for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[tuple[int, int]] = set()
        self._element_cache: dict[tuple[tuple[int, int], str], Any] = {}
        self._attribute_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}

    def _reset_caches(self) -> None:
        """Reset all internal caches for a new file analysis."""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._attribute_cache.clear()
        self.current_namespace = ""

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """
        Get text content of a node with caching for performance.

        Args:
            node: Tree-sitter node to extract text from

        Returns:
            Text content of the node as string
        """
        # Use node position as cache key instead of object id for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        # Extract text via UTF-8 bytes to handle multibyte chars correctly.
        # ``node.start_byte``/``end_byte`` are byte offsets — slicing ``str``
        # directly mis-aligns on any non-ASCII source.
        text = get_node_text_safe(node, self.source_code)
        self._node_text_cache[cache_key] = text
        return text

    def _extract_namespace(self, node: "tree_sitter.Node") -> None:
        """
        Extract namespace from the AST and set current_namespace.

        Args:
            node: Root node of the AST
        """
        if node.type == "namespace_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                self.current_namespace = self._get_node_text_optimized(name_node)
                return

        # Recursively search for namespace
        for child in node.children:
            if child.type == "namespace_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    self.current_namespace = self._get_node_text_optimized(name_node)
                    return
            elif child.child_count > 0:
                self._extract_namespace(child)

    def _extract_modifiers(self, node: "tree_sitter.Node") -> list[str]:
        """Extract modifiers from a declaration node."""
        return _extract_mods_standalone(node, self._get_node_text_optimized)

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """Determine visibility from modifiers."""
        return _determine_vis_standalone(modifiers)

    def _extract_attributes(self, node: "tree_sitter.Node") -> list[dict[str, Any]]:
        """Extract attributes (annotations) from a node."""
        return _extract_attrs_standalone(
            node, self._get_node_text_optimized, self._attribute_cache
        )

    def _extract_type_name(self, type_node: Optional["tree_sitter.Node"]) -> str:
        """Extract type name from a type node."""
        return _extract_type_standalone(type_node, self._get_node_text_optimized)

    def _extract_parameters(
        self, params_node: Optional["tree_sitter.Node"]
    ) -> list[str]:
        """Extract method parameters."""
        return _extract_params_standalone(params_node, self._get_node_text_optimized)

    def _traverse_iterative(
        self, root_node: "tree_sitter.Node"
    ) -> Iterator["tree_sitter.Node"]:
        yield from _traverse_nodes(root_node)

    def extract_classes(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[Class]:
        """
        Extract classes, interfaces, records, enums, and structs.

        Args:
            tree: Tree-sitter AST tree parsed from C# source
            source_code: Original C# source code as string

        Returns:
            List of Class objects representing all class-like declarations
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        if tree is None or tree.root_node is None:
            return classes

        # Extract namespace first
        self._extract_namespace(tree.root_node)

        # Extract all class-like declarations
        for node in self._traverse_iterative(tree.root_node):
            if node.type in [
                "class_declaration",
                "interface_declaration",
                "record_declaration",
                "enum_declaration",
                "struct_declaration",
            ]:
                class_obj = self._extract_class_declaration(node)
                if class_obj:
                    classes.append(class_obj)

        # Sort by start line for deterministic output
        classes.sort(key=lambda c: c.start_line)

        return classes

    def _extract_class_declaration(self, node: "tree_sitter.Node") -> Class | None:
        """Extract a single class declaration."""
        return _extract_class_standalone(
            node,
            self.current_namespace,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
        )

    def extract_functions(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[Function]:
        """
        Extract methods, constructors, and properties.

        Args:
            tree: Tree-sitter AST tree parsed from C# source
            source_code: Original C# source code as string

        Returns:
            List of Function objects representing methods, constructors, and properties
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        if tree is None or tree.root_node is None:
            return functions

        # Extract namespace first
        self._extract_namespace(tree.root_node)

        # Extract methods, constructors, and properties
        for node in self._traverse_iterative(tree.root_node):
            if node.type == "method_declaration":
                func = self._extract_method(node)
                if func:
                    functions.append(func)
            elif node.type == "constructor_declaration":
                func = self._extract_constructor(node)
                if func:
                    functions.append(func)
            elif node.type == "property_declaration":
                func = self._extract_property(node)
                if func:
                    functions.append(func)

        # Sort by start line for deterministic output
        functions.sort(key=lambda f: f.start_line)

        return functions

    def _extract_method(self, node: "tree_sitter.Node") -> Function | None:
        """Extract a method declaration."""
        return _extract_method_standalone(
            node,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
            self._extract_type_name,
            self._extract_parameters,
            self._calculate_complexity,
        )

    def _extract_constructor(self, node: "tree_sitter.Node") -> Function | None:
        """Extract a constructor declaration."""
        return _extract_ctor_standalone(
            node,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
            self._extract_parameters,
        )

    def _extract_property(self, node: "tree_sitter.Node") -> Function | None:
        """Extract a property declaration."""
        return _extract_prop_standalone(
            node,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
            self._extract_type_name,
        )

    def _calculate_complexity(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity of a method."""
        return _calc_complexity_standalone(node, self._traverse_iterative)

    def extract_variables(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[Variable]:
        """
        Extract fields, constants, and events.

        Args:
            tree: Tree-sitter AST tree parsed from C# source
            source_code: Original C# source code as string

        Returns:
            List of Variable objects representing fields
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        if tree is None or tree.root_node is None:
            return variables

        # Extract fields
        for node in self._traverse_iterative(tree.root_node):
            if node.type == "field_declaration":
                vars_list = self._extract_field(node)
                variables.extend(vars_list)
            elif node.type == "event_field_declaration":
                vars_list = self._extract_event(node)
                variables.extend(vars_list)

        # Sort by start line for deterministic output
        variables.sort(key=lambda v: v.start_line)

        return variables

    def _extract_field(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract field declarations."""
        return _extract_field_standalone(
            node,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
            self._extract_type_name,
        )

    def _extract_event(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract event field declarations."""
        return _extract_event_standalone(
            node,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
            self._extract_type_name,
        )

    def extract_imports(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[Import]:
        """
        Extract using directives.

        Args:
            tree: Tree-sitter AST tree parsed from C# source
            source_code: Original C# source code as string

        Returns:
            List of Import objects representing using directives
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")

        imports: list[Import] = []

        if tree is None or tree.root_node is None:
            return imports

        # Extract using directives
        for node in self._traverse_iterative(tree.root_node):
            if node.type == "using_directive":
                import_obj = self._extract_using_directive(node)
                if import_obj:
                    imports.append(import_obj)

        # Sort by start line for deterministic output
        imports.sort(key=lambda i: i.start_line)

        return imports

    def _extract_using_directive(self, node: "tree_sitter.Node") -> Import | None:
        """Extract a using directive."""
        return _extract_using_standalone(node, self._get_node_text_optimized)


class CSharpPlugin(LanguagePlugin):
    """
    C# language plugin implementation.

    This plugin provides C# language support for tree-sitter-analyzer,
    enabling analysis of C# source files including modern C# features
    like records, nullable reference types, and async/await patterns.
    """

    def __init__(self) -> None:
        """Initialize the C# plugin."""
        super().__init__()
        self.extractor = CSharpElementExtractor()
        self.language = "csharp"
        self.supported_extensions = [".cs"]
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """
        Get the language name.

        Returns:
            Language name as string: "csharp"
        """
        return "csharp"

    def get_file_extensions(self) -> list[str]:
        """
        Get supported file extensions.

        Returns:
            List of file extensions: [".cs"]
        """
        return [".cs"]

    def create_extractor(self) -> ElementExtractor:
        """
        Create a new C# element extractor instance.

        Returns:
            CSharpElementExtractor instance
        """
        return CSharpElementExtractor()

    def get_queries(self) -> dict[str, str]:
        """
        Return C#-specific tree-sitter queries.

        Returns:
            Dictionary of query names to query strings
        """
        from ..queries.csharp import CSHARP_QUERIES

        return CSHARP_QUERIES

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """
        Execute query strategy for C#.

        Args:
            query_key: Query key to execute
            language: Language name

        Returns:
            Query string or None if not applicable
        """
        if language != "csharp":
            return None

        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_element_categories(self) -> dict[str, list[str]]:
        """
        Return C# element categories for query execution.

        Returns:
            Dictionary of category names to element types
        """
        return {
            "classes": ["class", "interface", "record", "enum", "struct"],
            "methods": ["method", "constructor"],
            "properties": ["property", "auto_property", "computed_property"],
            "fields": ["field", "const_field", "readonly_field", "event"],
            "imports": ["using", "static_using"],
            "attributes": ["attribute", "http_attribute", "authorize_attribute"],
            "async": ["async_method"],
            "linq": ["linq_query", "from_clause", "where_clause", "select_clause"],
            "control_flow": [
                "if_statement",
                "for_statement",
                "foreach_statement",
                "while_statement",
                "switch_statement",
                "try_statement",
            ],
        }

    def get_tree_sitter_language(self) -> Any | None:
        """
        Load tree-sitter-c-sharp language.

        Returns:
            Tree-sitter Language object or None if loading fails
        """
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter_c_sharp

            lang = tree_sitter_c_sharp.language()

            # Handle both old and new tree-sitter API
            if hasattr(lang, "__class__") and "Language" in str(type(lang)):
                self._cached_language = lang
            else:
                self._cached_language = tree_sitter.Language(lang)

            log_debug("Successfully loaded tree-sitter-c-sharp language")
            return self._cached_language

        except ImportError as e:
            log_error(f"tree-sitter-c-sharp not available: {e}")
            log_error("Install with: pip install tree-sitter-c-sharp")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for C#: {e}")
            return None

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """
        Analyze a C# file and extract all elements.

        Args:
            file_path: Path to the C# file to analyze
            request: Analysis request containing file options

        Returns:
            AnalysisResult with extracted elements
        """
        from ..encoding_utils import read_file_safe
        from ..models import AnalysisResult

        try:
            source_code, encoding = read_file_safe(file_path)

            language = self.get_tree_sitter_language()
            if not language:
                log_error("Failed to load C# language")
                return AnalysisResult(
                    file_path=file_path,
                    language="csharp",
                    elements=[],
                    success=False,
                    error_message="Failed to load C# language",
                )

            parser = tree_sitter.Parser()
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            elif hasattr(parser, "language"):
                parser.language = language
            else:
                parser = tree_sitter.Parser(language)

            tree = parser.parse(source_code.encode("utf-8"))

            extractor = self.create_extractor()
            elements: list[Any] = []
            elements.extend(extractor.extract_classes(tree, source_code))
            elements.extend(extractor.extract_functions(tree, source_code))
            elements.extend(extractor.extract_variables(tree, source_code))
            elements.extend(extractor.extract_imports(tree, source_code))

            node_count = sum(1 for _ in _traverse_nodes(tree.root_node))
            line_count = len(source_code.split("\n"))

            return AnalysisResult(
                file_path=file_path,
                language="csharp",
                elements=elements,
                node_count=node_count,
                line_count=line_count,
                source_code=source_code,
            )

        except Exception as e:
            log_error(f"Error analyzing C# file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="csharp",
                elements=[],
                success=False,
                error_message=str(e),
            )
