#!/usr/bin/env python3
"""
PHP Language Plugin

Provides PHP-specific parsing and element extraction functionality.
Supports extraction of classes, interfaces, traits, enums, methods, functions, properties, and use statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error
from ..utils.tree_sitter_compat import get_node_text_safe
from .php_helpers import (
    determine_visibility as _determine_vis_standalone,
)
from .php_helpers import (
    extract_attributes as _extract_attrs_standalone,
)
from .php_helpers import (
    extract_modifiers as _extract_mods_standalone,
)
from .php_helpers import (
    extract_php_class_element as _extract_class_standalone,
)
from .php_helpers import (
    extract_php_constant_elements as _extract_const_standalone,
)
from .php_helpers import (
    extract_php_function_element as _extract_func_standalone,
)
from .php_helpers import (
    extract_php_method_element as _extract_method_standalone,
)
from .php_helpers import (
    extract_php_property_elements as _extract_prop_standalone,
)
from .php_helpers import (
    extract_use_statement as _extract_use_standalone,
)


class PHPElementExtractor(ElementExtractor):
    """
    PHP-specific element extractor.

    This extractor parses PHP AST and extracts code elements, mapping them
    to the unified element model:
    - Classes, Interfaces, Traits, Enums → Class elements
    - Methods, Functions → Function elements
    - Properties, Constants → Variable elements
    - Use statements → Import elements

    The extractor handles modern PHP syntax including:
    - PHP 8+ attributes
    - PHP 8.1+ enums
    - PHP 7.4+ typed properties
    - Magic methods
    - Namespaces
    """

    def __init__(self) -> None:
        """
        Initialize the PHP element extractor.

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

    def _get_node_text_optimized(self, node: tree_sitter.Node) -> str:
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

    def _extract_namespace(self, node: tree_sitter.Node) -> None:
        """
        Extract namespace from the AST and set current_namespace.

        Args:
            node: Root node of the AST
        """
        if node.type == "namespace_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                self.current_namespace = self._get_node_text_optimized(name_node)
                return

        # Recursively search for namespace
        for child in node.children:
            if child.type == "namespace_definition":
                name_node = child.child_by_field_name("name")
                if name_node:
                    self.current_namespace = self._get_node_text_optimized(name_node)
                    return
            elif child.child_count > 0:
                self._extract_namespace(child)

    def _extract_modifiers(self, node: tree_sitter.Node) -> list[str]:
        """Extract modifiers from a declaration node."""
        return _extract_mods_standalone(node, self._get_node_text_optimized)

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """Determine visibility from modifiers."""
        return _determine_vis_standalone(modifiers)

    def _extract_attributes(self, node: tree_sitter.Node) -> list[dict[str, Any]]:
        """Extract PHP 8+ attributes from a node."""
        return _extract_attrs_standalone(
            node, self._get_node_text_optimized, self._attribute_cache
        )

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """
        Extract PHP classes, interfaces, traits, and enums.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Class elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()
        self._reset_caches()
        self._extract_namespace(tree.root_node)

        classes: list[Class] = []

        # Iterative traversal to avoid stack overflow
        stack: list[tree_sitter.Node] = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type in (
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
                "enum_declaration",
            ):
                class_elem = self._extract_class_element(node)
                if class_elem:
                    classes.append(class_elem)

            # Add children to stack for traversal
            for child in reversed(node.children):
                stack.append(child)

        return classes

    def _extract_class_element(self, node: tree_sitter.Node) -> Class | None:
        """Extract a single class, interface, trait, or enum element."""
        return _extract_class_standalone(
            node,
            self.current_namespace,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
        )

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """
        Extract PHP methods and functions.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Function elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        functions: list[Function] = []

        # Iterative traversal
        stack: list[tuple[tree_sitter.Node, str]] = [(tree.root_node, "")]

        while stack:
            node, parent_class = stack.pop()

            if node.type == "method_declaration":
                func_elem = self._extract_method_element(node, parent_class)
                if func_elem:
                    functions.append(func_elem)
            elif node.type == "function_definition":
                func_elem = self._extract_function_element(node)
                if func_elem:
                    functions.append(func_elem)

            # Track parent class for methods
            new_parent = parent_class
            if node.type in (
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
            ):
                name_node = node.child_by_field_name("name")
                if name_node:
                    new_parent = self._get_node_text_optimized(name_node)

            # Add children to stack
            for child in reversed(node.children):
                stack.append((child, new_parent))

        return functions

    def _extract_method_element(
        self, node: tree_sitter.Node, parent_class: str
    ) -> Function | None:
        """Extract a method element."""
        return _extract_method_standalone(
            node,
            parent_class,
            self._get_node_text_optimized,
            self._extract_modifiers,
            self._extract_attributes,
        )

    def _extract_function_element(self, node: tree_sitter.Node) -> Function | None:
        """Extract a function element."""
        return _extract_func_standalone(
            node,
            self.current_namespace,
            self._get_node_text_optimized,
        )

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """
        Extract PHP properties and constants.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Variable elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        variables: list[Variable] = []

        # Iterative traversal
        stack: list[tuple[tree_sitter.Node, str]] = [(tree.root_node, "")]

        while stack:
            node, parent_class = stack.pop()

            if node.type == "property_declaration":
                var_elems = self._extract_property_elements(node, parent_class)
                variables.extend(var_elems)
            elif node.type == "const_declaration":
                var_elems = self._extract_constant_elements(node, parent_class)
                variables.extend(var_elems)

            # Track parent class — enums may declare consts too (Codex P2
            # on #625): without enum_declaration here, an enum const emits
            # with receiver_type=None and masquerades as a global.
            new_parent = parent_class
            if node.type in (
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
                "enum_declaration",
            ):
                name_node = node.child_by_field_name("name")
                if name_node:
                    new_parent = self._get_node_text_optimized(name_node)

            # Add children to stack
            for child in reversed(node.children):
                stack.append((child, new_parent))

        return variables

    def _extract_property_elements(
        self, node: tree_sitter.Node, parent_class: str
    ) -> list[Variable]:
        """Extract property elements from a property declaration."""
        return _extract_prop_standalone(
            node,
            parent_class,
            self._get_node_text_optimized,
            self._extract_modifiers,
        )

    def _extract_constant_elements(
        self, node: tree_sitter.Node, parent_class: str
    ) -> list[Variable]:
        """Extract constant elements from a const declaration."""
        return _extract_const_standalone(
            node,
            parent_class,
            self._get_node_text_optimized,
            self._extract_modifiers,
        )

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """
        Extract PHP use statements.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Source code string

        Returns:
            List of Import elements
        """
        self.source_code = source_code
        self.content_lines = source_code.splitlines()

        imports: list[Import] = []

        # Iterative traversal
        stack: list[tree_sitter.Node] = [tree.root_node]

        while stack:
            node = stack.pop()

            if node.type == "namespace_use_declaration":
                import_elems = self._extract_use_statement(node)
                imports.extend(import_elems)

            # Add children to stack
            for child in reversed(node.children):
                stack.append(child)

        return imports

    def _extract_use_statement(self, node: tree_sitter.Node) -> list[Import]:
        """Extract use statement elements."""
        return _extract_use_standalone(node, self._get_node_text_optimized)


class PHPPlugin(LanguagePlugin):
    """
    PHP language plugin.

    Provides PHP-specific parsing and element extraction using tree-sitter-php.
    Supports modern PHP features including PHP 8+ attributes, enums, and typed properties.
    """

    _language_instance: tree_sitter.Language | None = None

    def get_language_name(self) -> str:
        """
        Get the name of the language.

        Returns:
            Language name string
        """
        return "php"

    def get_file_extensions(self) -> list[str]:
        """
        Get supported file extensions.

        Returns:
            List of file extensions
        """
        return [".php"]

    def get_tree_sitter_language(self) -> tree_sitter.Language:
        """
        Get the tree-sitter language instance for PHP.

        Returns:
            tree-sitter Language instance

        Raises:
            ImportError: If tree-sitter-php is not installed
        """
        if not TREE_SITTER_AVAILABLE:
            raise ImportError(
                "tree-sitter is not installed. Install it with: pip install tree-sitter"
            )

        if PHPPlugin._language_instance is None:
            try:
                import tree_sitter_php

                PHPPlugin._language_instance = tree_sitter.Language(
                    tree_sitter_php.language_php()
                )
            except ImportError as e:
                raise ImportError(
                    "tree-sitter-php is not installed. Install it with: pip install tree-sitter-php"
                ) from e

        return PHPPlugin._language_instance

    def create_extractor(self) -> ElementExtractor:
        """
        Create a PHP element extractor.

        Returns:
            PHPElementExtractor instance
        """
        return PHPElementExtractor()

    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> dict[str, list]:
        """Unified extraction entry point — delegates to the extractor."""
        return self.create_extractor().extract_elements(tree, source_code)

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """
        Analyze a PHP file.

        Args:
            file_path: Path to the PHP file
            request: Analysis request configuration

        Returns:
            AnalysisResult containing extracted elements
        """
        from ..models import AnalysisResult

        try:
            # Load file content
            content = await self._load_file_safe(file_path)

            # Parse with tree-sitter
            language = self.get_tree_sitter_language()
            parser = tree_sitter.Parser(language)
            tree = parser.parse(content.encode("utf-8"))

            # Extract elements
            extractor = self.create_extractor()
            classes = extractor.extract_classes(tree, content)
            functions = extractor.extract_functions(tree, content)
            variables = extractor.extract_variables(tree, content)
            imports = extractor.extract_imports(tree, content)

            # Combine all elements
            all_elements = classes + functions + variables + imports

            return AnalysisResult(
                language=self.get_language_name(),
                file_path=file_path,
                success=True,
                elements=all_elements,
                node_count=self._count_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing PHP file {file_path}: {e}")
            return AnalysisResult(
                language=self.get_language_name(),
                file_path=file_path,
                success=False,
                error_message=str(e),
                elements=[],
                node_count=0,
            )

    def _count_nodes(self, node: tree_sitter.Node) -> int:
        """
        Count total nodes in the AST.

        Args:
            node: Root node to count from

        Returns:
            Total node count
        """
        count = 1
        if node.children:
            for child in node.children:
                count += self._count_nodes(child)
        return count

    async def _load_file_safe(self, file_path: str) -> str:
        """
        Load file content with encoding detection.

        Args:
            file_path: Path to the file

        Returns:
            File content as string

        Raises:
            IOError: If file cannot be read
        """
        import chardet

        try:
            # Read file in binary mode
            with open(file_path, "rb") as f:
                raw_content = f.read()

            # Detect encoding
            detected = chardet.detect(raw_content)
            encoding = detected.get("encoding", "utf-8")

            # Decode with detected encoding
            return raw_content.decode(encoding or "utf-8")
        except Exception as e:
            log_error(f"Error loading file {file_path}: {e}")
            raise OSError(f"Failed to load file {file_path}: {e}") from e
