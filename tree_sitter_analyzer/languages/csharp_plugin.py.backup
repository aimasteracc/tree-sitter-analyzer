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

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


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
        """
        Extract modifiers from a declaration node.

        Args:
            node: Declaration node (class, method, field, etc.)

        Returns:
            List of modifier strings (e.g., ["public", "static", "async"])
        """
        modifiers: list[str] = []
        for child in node.children:
            if child.type == "modifier":
                modifier_text = self._get_node_text_optimized(child)
                modifiers.append(modifier_text)
        return modifiers

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """
        Determine visibility from modifiers.

        Args:
            modifiers: List of modifier strings

        Returns:
            Visibility string ("public", "private", "protected", "internal")
        """
        if "public" in modifiers:
            return "public"
        elif "private" in modifiers:
            return "private"
        elif "protected" in modifiers:
            return "protected"
        elif "internal" in modifiers:
            return "internal"
        else:
            return "private"  # Default to private in C#

    def _extract_attributes(self, node: "tree_sitter.Node") -> list[dict[str, Any]]:
        """
        Extract attributes (annotations) from a node.

        Args:
            node: Node that may have attributes

        Returns:
            List of attribute dictionaries with name, line, and text
        """
        # Use position-based cache key for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._attribute_cache:
            return self._attribute_cache[cache_key]

        attributes: list[dict[str, Any]] = []

        # Look for attribute_list nodes before the declaration
        prev_sibling = node.prev_sibling
        while prev_sibling:
            if prev_sibling.type == "attribute_list":
                attr_text = self._get_node_text_optimized(prev_sibling)
                attributes.append(
                    {
                        "name": attr_text.strip("[]"),
                        "line": prev_sibling.start_point[0] + 1,
                        "text": attr_text,
                    }
                )
            elif prev_sibling.type not in ["comment", "line_comment", "block_comment"]:
                break
            prev_sibling = prev_sibling.prev_sibling

        attributes.reverse()  # Restore original order
        self._attribute_cache[cache_key] = attributes
        return attributes

    def _extract_type_name(self, type_node: Optional["tree_sitter.Node"]) -> str:
        """
        Extract type name from a type node, handling generic types and nullable types.

        Args:
            type_node: Type node from the AST

        Returns:
            Type name as string (e.g., "int", "List<string>", "string?")
        """
        if not type_node:
            return "void"

        return self._get_node_text_optimized(type_node)

    def _extract_parameters(
        self, params_node: Optional["tree_sitter.Node"]
    ) -> list[str]:
        """
        Extract method parameters.

        Args:
            params_node: Parameter list node

        Returns:
            List of parameter strings (e.g., ["int id", "string name"])
        """
        if not params_node:
            return []

        parameters: list[str] = []
        for child in params_node.children:
            if child.type == "parameter":
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)

        return parameters

    def _traverse_iterative(
        self, root_node: "tree_sitter.Node"
    ) -> Iterator["tree_sitter.Node"]:
        """
        Iteratively traverse AST nodes to avoid stack overflow on large files.

        Args:
            root_node: Root node to start traversal from

        Yields:
            Tree-sitter nodes in depth-first order
        """
        stack = [root_node]
        while stack:
            node = stack.pop()
            yield node
            # Add children in reverse order to maintain left-to-right traversal
            stack.extend(reversed(list(node.children)))

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
        """
        Extract a single class declaration.

        Args:
            node: Class declaration node

        Returns:
            Class object or None if extraction fails
        """
        try:
            # Get class name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            class_name = self._get_node_text_optimized(name_node)

            # Get modifiers and visibility
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Get attributes
            attributes = self._extract_attributes(node)

            # Get base class and interfaces
            base_list_node = node.child_by_field_name("bases")
            superclass = None
            interfaces: list[str] = []

            if base_list_node:
                base_items = [
                    self._get_node_text_optimized(child)
                    for child in base_list_node.children
                    if child.type
                    in ["type_identifier", "generic_name", "qualified_name"]
                ]
                if base_items:
                    if node.type == "interface_declaration":
                        interfaces = base_items
                    else:
                        superclass = base_items[0]
                        interfaces = base_items[1:] if len(base_items) > 1 else []

            # Get full qualified name
            full_name = (
                f"{self.current_namespace}.{class_name}"
                if self.current_namespace
                else class_name
            )

            # Get raw text
            raw_text = self._get_node_text_optimized(node)

            # Determine class type
            class_type_map = {
                "class_declaration": "class",
                "interface_declaration": "interface",
                "record_declaration": "record",
                "enum_declaration": "enum",
                "struct_declaration": "struct",
            }
            class_type = class_type_map.get(node.type, "class")

            return Class(
                name=class_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                full_qualified_name=full_name,
                superclass=superclass,
                interfaces=interfaces,
                modifiers=modifiers,
                visibility=visibility,
                annotations=attributes,
                class_type=class_type,
            )

        except Exception as e:
            log_error(f"Error extracting class declaration: {e}")
            return None

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
        """
        Extract a method declaration.

        Args:
            node: Method declaration node

        Returns:
            Function object or None if extraction fails
        """
        try:
            # Get method name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            method_name = self._get_node_text_optimized(name_node)

            # Get modifiers and visibility
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Check if async
            is_async = "async" in modifiers

            # Get attributes
            attributes = self._extract_attributes(node)

            # Get return type
            type_node = node.child_by_field_name("type")
            return_type = self._extract_type_name(type_node)

            # Get parameters
            params_node = node.child_by_field_name("parameters")
            parameters = self._extract_parameters(params_node)

            # Get raw text
            raw_text = self._get_node_text_optimized(node)

            # Calculate complexity (simplified)
            complexity_score = self._calculate_complexity(node)

            return Function(
                name=method_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                parameters=parameters,
                return_type=return_type,
                modifiers=modifiers,
                visibility=visibility,
                is_async=is_async,
                annotations=attributes,
                complexity_score=complexity_score,
            )

        except Exception as e:
            log_error(f"Error extracting method: {e}")
            return None

    def _extract_constructor(self, node: "tree_sitter.Node") -> Function | None:
        """
        Extract a constructor declaration.

        Args:
            node: Constructor declaration node

        Returns:
            Function object or None if extraction fails
        """
        try:
            # Get constructor name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            constructor_name = self._get_node_text_optimized(name_node)

            # Get modifiers and visibility
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Get attributes
            attributes = self._extract_attributes(node)

            # Get parameters
            params_node = node.child_by_field_name("parameters")
            parameters = self._extract_parameters(params_node)

            # Get raw text
            raw_text = self._get_node_text_optimized(node)

            return Function(
                name=constructor_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                parameters=parameters,
                return_type="void",
                modifiers=modifiers,
                visibility=visibility,
                is_constructor=True,
                annotations=attributes,
            )

        except Exception as e:
            log_error(f"Error extracting constructor: {e}")
            return None

    def _extract_property(self, node: "tree_sitter.Node") -> Function | None:
        """
        Extract a property declaration.

        Args:
            node: Property declaration node

        Returns:
            Function object with is_property=True or None if extraction fails
        """
        try:
            # Get property name
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            property_name = self._get_node_text_optimized(name_node)

            # Get modifiers and visibility
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Get attributes
            attributes = self._extract_attributes(node)

            # Get property type
            type_node = node.child_by_field_name("type")
            property_type = self._extract_type_name(type_node)

            # Get raw text
            raw_text = self._get_node_text_optimized(node)

            # Check for getter/setter (for future use)
            # has_getter = False
            # has_setter = False
            # for child in node.children:
            #     if child.type == "accessor_list":
            #         for accessor in child.children:
            #             if accessor.type == "get_accessor_declaration":
            #                 has_getter = True
            #             elif accessor.type == "set_accessor_declaration":
            #                 has_setter = True
            #             elif accessor.type == "init_accessor_declaration":
            #                 has_setter = True  # init is a special setter

            return Function(
                name=property_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                parameters=[],
                return_type=property_type,
                modifiers=modifiers,
                visibility=visibility,
                is_property=True,
                annotations=attributes,
            )

        except Exception as e:
            log_error(f"Error extracting property: {e}")
            return None

    def _calculate_complexity(self, node: "tree_sitter.Node") -> int:
        """
        Calculate cyclomatic complexity of a method.

        Args:
            node: Method node

        Returns:
            Complexity score (1 + number of decision points)
        """
        complexity = 1
        decision_keywords = {
            "if_statement",
            "switch_statement",
            "for_statement",
            "foreach_statement",
            "while_statement",
            "do_statement",
            "catch_clause",
            "conditional_expression",  # ternary operator
        }

        for child in self._traverse_iterative(node):
            if child.type in decision_keywords:
                complexity += 1

        return complexity

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
        """
        Extract field declarations.

        Args:
            node: Field declaration node

        Returns:
            List of Variable objects (can be multiple if multiple variables declared)
        """
        variables: list[Variable] = []

        try:
            # Get modifiers
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Check if constant or readonly
            is_constant = "const" in modifiers
            # is_readonly = "readonly" in modifiers  # For future use

            # Get attributes
            attributes = self._extract_attributes(node)

            # Get field type
            type_node = None
            for child in node.children:
                if child.type == "variable_declaration":
                    type_node = child.child_by_field_name("type")
                    break

            field_type = self._extract_type_name(type_node)

            # Get variable declarators
            for child in node.children:
                if child.type == "variable_declaration":
                    for declarator in child.children:
                        if declarator.type == "variable_declarator":
                            name_node = declarator.child_by_field_name("name")
                            if name_node:
                                field_name = self._get_node_text_optimized(name_node)
                                raw_text = self._get_node_text_optimized(node)

                                variables.append(
                                    Variable(
                                        name=field_name,
                                        start_line=node.start_point[0] + 1,
                                        end_line=node.end_point[0] + 1,
                                        raw_text=raw_text,
                                        variable_type=field_type,
                                        modifiers=modifiers,
                                        visibility=visibility,
                                        is_constant=is_constant,
                                        annotations=attributes,
                                    )
                                )

        except Exception as e:
            log_error(f"Error extracting field: {e}")

        return variables

    def _extract_event(self, node: "tree_sitter.Node") -> list[Variable]:
        """
        Extract event field declarations.

        Args:
            node: Event field declaration node

        Returns:
            List of Variable objects representing events
        """
        variables: list[Variable] = []

        try:
            # Get modifiers
            modifiers = self._extract_modifiers(node)
            modifiers.append("event")  # Mark as event
            visibility = self._determine_visibility(modifiers)

            # Get attributes
            attributes = self._extract_attributes(node)

            # Get event type
            type_node = None
            for child in node.children:
                if child.type == "variable_declaration":
                    type_node = child.child_by_field_name("type")
                    break

            event_type = self._extract_type_name(type_node)

            # Get variable declarators
            for child in node.children:
                if child.type == "variable_declaration":
                    for declarator in child.children:
                        if declarator.type == "variable_declarator":
                            name_node = declarator.child_by_field_name("name")
                            if name_node:
                                event_name = self._get_node_text_optimized(name_node)
                                raw_text = self._get_node_text_optimized(node)

                                variables.append(
                                    Variable(
                                        name=event_name,
                                        start_line=node.start_point[0] + 1,
                                        end_line=node.end_point[0] + 1,
                                        raw_text=raw_text,
                                        variable_type=event_type,
                                        modifiers=modifiers,
                                        visibility=visibility,
                                        annotations=attributes,
                                    )
                                )

        except Exception as e:
            log_error(f"Error extracting event: {e}")

        return variables

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
        """
        Extract a using directive.

        Args:
            node: Using directive node

        Returns:
            Import object or None if extraction fails
        """
        try:
            # Get the namespace or type being imported
            name_node = node.child_by_field_name("name")
            if not name_node:
                # Try to find qualified_name or identifier
                for child in node.children:
                    if child.type in ["qualified_name", "identifier", "name_equals"]:
                        name_node = child
                        break

            if not name_node:
                return None

            import_name = self._get_node_text_optimized(name_node)

            # Check if it's a static using
            is_static = False
            for child in node.children:
                if (
                    child.type == "static"
                    or self._get_node_text_optimized(child) == "static"
                ):
                    is_static = True
                    break

            # Get raw text
            raw_text = self._get_node_text_optimized(node)

            return Import(
                name=import_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                module_name=import_name,
                is_static=is_static,
            )

        except Exception as e:
            log_error(f"Error extracting using directive: {e}")
            return None


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
            # Read file content
            source_code, encoding = read_file_safe(file_path)
            self.extractor._file_encoding = encoding

            # Get tree-sitter language
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

            # Parse the source code
            parser = tree_sitter.Parser()

            # Set language using the appropriate method
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            elif hasattr(parser, "language"):
                parser.language = language
            else:
                parser = tree_sitter.Parser(language)

            tree = parser.parse(source_code.encode("utf-8"))

            # Extract all elements
            classes = self.extractor.extract_classes(tree, source_code)
            functions = self.extractor.extract_functions(tree, source_code)
            variables = self.extractor.extract_variables(tree, source_code)
            imports = self.extractor.extract_imports(tree, source_code)

            # Combine all elements into a single list
            elements: list[Any] = []
            elements.extend(classes)
            elements.extend(functions)
            elements.extend(variables)
            elements.extend(imports)

            # Count AST nodes
            node_count = sum(
                1 for _ in self.extractor._traverse_iterative(tree.root_node)
            )

            # Count lines
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
