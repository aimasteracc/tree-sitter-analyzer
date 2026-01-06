#!/usr/bin/env python3
"""
PHP Language Plugin

Provides PHP-specific parsing and element extraction functionality.
Supports extraction of classes, interfaces, traits, enums, methods, functions, properties, and use statements.
"""

from typing import TYPE_CHECKING, Any, Optional

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
        self._file_encoding: str | None = None
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

        # Extract text directly from source code string
        text = self.source_code[node.start_byte : node.end_byte]
        self._node_text_cache[cache_key] = text
        return text

    def _extract_namespace(self, node: "tree_sitter.Node") -> None:
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

    def _extract_modifiers(self, node: "tree_sitter.Node") -> list[str]:
        """
        Extract modifiers from a declaration node.

        Args:
            node: Declaration node (class, method, property, etc.)

        Returns:
            List of modifier strings (e.g., ["public", "static", "final"])
        """
        modifiers: list[str] = []
        for child in node.children:
            if child.type in (
                "visibility_modifier",
                "static_modifier",
                "final_modifier",
                "abstract_modifier",
                "readonly_modifier",
            ):
                modifier_text = self._get_node_text_optimized(child)
                modifiers.append(modifier_text)
        return modifiers

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """
        Determine visibility from modifiers.

        Args:
            modifiers: List of modifier strings

        Returns:
            Visibility string ("public", "private", "protected")
        """
        if "public" in modifiers:
            return "public"
        elif "private" in modifiers:
            return "private"
        elif "protected" in modifiers:
            return "protected"
        else:
            return "public"  # PHP default visibility

    def _extract_attributes(self, node: "tree_sitter.Node") -> list[dict[str, Any]]:
        """
        Extract PHP 8+ attributes from a node.

        Args:
            node: Node to extract attributes from

        Returns:
            List of attribute dictionaries with name and arguments
        """
        # Check cache first - use position-based key for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._attribute_cache:
            return self._attribute_cache[cache_key]

        attributes: list[dict[str, Any]] = []

        # Look for attribute_list nodes before the declaration
        for child in node.children:
            if child.type == "attribute_list":
                for attr_group in child.children:
                    if attr_group.type == "attribute_group":
                        for attr in attr_group.children:
                            if attr.type == "attribute":
                                name_node = attr.child_by_field_name("name")
                                if name_node:
                                    attr_name = self._get_node_text_optimized(name_node)
                                    attributes.append(
                                        {"name": attr_name, "arguments": []}
                                    )

        self._attribute_cache[cache_key] = attributes
        return attributes

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
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

    def _extract_class_element(self, node: "tree_sitter.Node") -> Class | None:
        """
        Extract a single class, interface, trait, or enum element.

        Args:
            node: Class/interface/trait/enum declaration node

        Returns:
            Class element or None if extraction fails
        """
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text_optimized(name_node)
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)
            attributes = self._extract_attributes(node)

            # Determine type
            is_interface = node.type == "interface_declaration"
            is_trait = node.type == "trait_declaration"
            is_enum = node.type == "enum_declaration"

            # Extract base class and interfaces
            base_classes: list[str] = []
            interfaces: list[str] = []

            for child in node.children:
                if child.type == "base_clause":
                    base_node = child.child_by_field_name("type")
                    if base_node:
                        base_classes.append(self._get_node_text_optimized(base_node))
                elif child.type == "class_interface_clause":
                    for interface_node in child.children:
                        if interface_node.type == "name":
                            interfaces.append(
                                self._get_node_text_optimized(interface_node)
                            )

            # Build fully qualified name
            full_name = (
                f"{self.current_namespace}\\{name}" if self.current_namespace else name
            )

            # Determine class type
            class_type = "class"
            if is_interface:
                class_type = "interface"
            elif is_trait:
                class_type = "trait"
            elif is_enum:
                class_type = "enum"

            return Class(
                name=full_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                visibility=visibility,
                is_abstract="abstract" in modifiers,
                full_qualified_name=full_name,
                superclass=base_classes[0] if base_classes else None,
                interfaces=interfaces,
                modifiers=modifiers,
                annotations=[{"name": attr["name"]} for attr in attributes],
                class_type=class_type,
            )
        except Exception as e:
            log_error(f"Error extracting class element: {e}")
            return None

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
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
        self, node: "tree_sitter.Node", parent_class: str
    ) -> Function | None:
        """
        Extract a method element.

        Args:
            node: Method declaration node
            parent_class: Name of the parent class

        Returns:
            Function element or None if extraction fails
        """
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text_optimized(name_node)
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)
            attributes = self._extract_attributes(node)

            # Extract parameters
            parameters: list[str] = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for param in params_node.children:
                    if (
                        param.type == "simple_parameter"
                        or param.type == "property_promotion_parameter"
                    ):
                        param_text = self._get_node_text_optimized(param)
                        parameters.append(param_text)

            # Extract return type
            return_type = "void"
            return_type_node = node.child_by_field_name("return_type")
            if return_type_node:
                return_type = self._get_node_text_optimized(return_type_node)

            # Check if magic method
            # is_magic = name.startswith("__")  # Reserved for future use

            return Function(
                name=f"{parent_class}::{name}" if parent_class else name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                visibility=visibility,
                is_static="static" in modifiers,
                is_async=False,  # PHP doesn't have async/await like C#
                is_abstract="abstract" in modifiers,
                parameters=parameters,
                return_type=return_type,
                modifiers=modifiers,
                annotations=[{"name": attr["name"]} for attr in attributes],
            )
        except Exception as e:
            log_error(f"Error extracting method element: {e}")
            return None

    def _extract_function_element(self, node: "tree_sitter.Node") -> Function | None:
        """
        Extract a function element.

        Args:
            node: Function definition node

        Returns:
            Function element or None if extraction fails
        """
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text_optimized(name_node)

            # Extract parameters
            parameters: list[str] = []
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for param in params_node.children:
                    if param.type == "simple_parameter":
                        param_text = self._get_node_text_optimized(param)
                        parameters.append(param_text)

            # Extract return type
            return_type = "void"
            return_type_node = node.child_by_field_name("return_type")
            if return_type_node:
                return_type = self._get_node_text_optimized(return_type_node)

            # Build fully qualified name
            full_name = (
                f"{self.current_namespace}\\{name}" if self.current_namespace else name
            )

            return Function(
                name=full_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                visibility="public",
                is_static=False,
                is_async=False,
                is_abstract=False,
                parameters=parameters,
                return_type=return_type,
                modifiers=[],
                annotations=[],
            )
        except Exception as e:
            log_error(f"Error extracting function element: {e}")
            return None

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
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

            # Track parent class
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

        return variables

    def _extract_property_elements(
        self, node: "tree_sitter.Node", parent_class: str
    ) -> list[Variable]:
        """
        Extract property elements from a property declaration.

        Args:
            node: Property declaration node
            parent_class: Name of the parent class

        Returns:
            List of Variable elements
        """
        variables: list[Variable] = []

        try:
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Extract type
            var_type = "mixed"
            type_node = node.child_by_field_name("type")
            if type_node:
                var_type = self._get_node_text_optimized(type_node)

            # Extract property names
            for child in node.children:
                if child.type == "property_element":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = self._get_node_text_optimized(name_node).lstrip("$")
                        full_name = f"{parent_class}::{name}" if parent_class else name

                        variables.append(
                            Variable(
                                name=full_name,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                visibility=visibility,
                                is_static="static" in modifiers,
                                is_constant=False,
                                is_final=False,
                                is_readonly="readonly" in modifiers,
                                variable_type=var_type,
                                modifiers=modifiers,
                            )
                        )
        except Exception as e:
            log_error(f"Error extracting property elements: {e}")

        return variables

    def _extract_constant_elements(
        self, node: "tree_sitter.Node", parent_class: str
    ) -> list[Variable]:
        """
        Extract constant elements from a const declaration.

        Args:
            node: Const declaration node
            parent_class: Name of the parent class

        Returns:
            List of Variable elements
        """
        variables: list[Variable] = []

        try:
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Extract constant names
            for child in node.children:
                if child.type == "const_element":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = self._get_node_text_optimized(name_node)
                        full_name = f"{parent_class}::{name}" if parent_class else name

                        variables.append(
                            Variable(
                                name=full_name,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                visibility=visibility,
                                is_static=True,
                                is_constant=True,
                                is_final=True,
                                variable_type="const",
                                modifiers=modifiers,
                            )
                        )
        except Exception as e:
            log_error(f"Error extracting constant elements: {e}")

        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
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

    def _extract_use_statement(self, node: "tree_sitter.Node") -> list[Import]:
        """
        Extract use statement elements.

        Args:
            node: Namespace use declaration node

        Returns:
            List of Import elements
        """
        imports: list[Import] = []

        try:
            # Check for use type (function, const, or class)
            # use_type = "class"  # Reserved for future use
            for child in node.children:
                if child.type == "use":
                    use_text = self._get_node_text_optimized(child)
                    if "function" in use_text:
                        pass  # use_type = "function"  # Reserved for future use
                    elif "const" in use_text:
                        pass  # use_type = "const"  # Reserved for future use

            # Extract use clauses
            for child in node.children:
                if child.type == "namespace_use_clause":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")

                    if name_node:
                        import_name = self._get_node_text_optimized(name_node)
                        alias = None
                        if alias_node:
                            alias = self._get_node_text_optimized(alias_node)

                        imports.append(
                            Import(
                                name=import_name,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                alias=alias,
                                is_wildcard=False,
                            )
                        )
        except Exception as e:
            log_error(f"Error extracting use statement: {e}")

        return imports


class PHPPlugin(LanguagePlugin):
    """
    PHP language plugin.

    Provides PHP-specific parsing and element extraction using tree-sitter-php.
    Supports modern PHP features including PHP 8+ attributes, enums, and typed properties.
    """

    _language_instance: Optional["tree_sitter.Language"] = None

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

    def get_tree_sitter_language(self) -> "tree_sitter.Language":
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

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
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

    def _count_nodes(self, node: "tree_sitter.Node") -> int:
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
