#!/usr/bin/env python3
"""
C++ Language Plugin

Provides C++ specific parsing and element extraction functionality.
Supports modern C++ features including classes, templates, namespaces,
and advanced constructs.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning
from .cpp_helpers import (
    calculate_complexity as _calc_complexity_standalone,
)
from .cpp_helpers import (
    determine_visibility as _determine_vis_standalone,
)
from .cpp_helpers import (
    extract_base_classes as _extract_base_standalone,
)
from .cpp_helpers import (
    extract_comment_for_line as _extract_comment_standalone,
)
from .cpp_helpers import (
    extract_cpp_field_declaration as _extract_cpp_field_standalone,
)
from .cpp_helpers import (
    extract_cpp_imports as _extract_imports_standalone,
)
from .cpp_helpers import (
    extract_cpp_namespaces as _extract_namespaces_standalone,
)
from .cpp_helpers import (
    extract_cpp_variable_declaration as _extract_cpp_var_standalone,
)
from .cpp_helpers import (
    extract_function_declaration as _extract_func_decl_standalone,
)
from .cpp_helpers import (
    extract_function_from_field_declaration as _extract_func_field_standalone,
)
from .cpp_helpers import (
    extract_parameters as _extract_params_standalone,
)
from .cpp_helpers import (
    get_access_specifier as _get_access_standalone,
)
from .cpp_helpers import (
    is_global_scope as _is_global_standalone,
)
from .cpp_helpers import (
    parse_function_signature as _parse_sig_standalone,
)


class CppElementExtractor(ElementExtractor):
    """C++ specific element extractor with advanced analysis support"""

    def __init__(self) -> None:
        """Initialize the C++ element extractor."""
        self.current_namespace: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.includes: list[str] = []

        # Performance optimization caches - use position-based keys for deterministic caching
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._comment_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract C++ function definitions with comprehensive details"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        # Use optimized traversal for function types
        extractors = {
            "function_definition": self._extract_function_optimized,
            "function_declarator": self._extract_function_declaration,
            "template_declaration": self._extract_template_function,
            "field_declaration": self._extract_function_from_field_declaration,  # Pure virtual, etc
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "function"
        )

        log_debug(f"Extracted {len(functions)} C++ functions")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract C++ class/struct definitions with detailed information"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        # Extract class, struct, and union declarations
        extractors = {
            "class_specifier": self._extract_class_optimized,
            "struct_specifier": self._extract_struct_optimized,
            "union_specifier": self._extract_union_optimized,
            "template_declaration": self._extract_template_class,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} C++ classes/structs")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract C++ variable/field declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        # Extract field and variable declarations
        extractors = {
            "field_declaration": self._extract_field_optimized,
            "declaration": self._extract_variable_declaration,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, variables, "variable"
        )

        log_debug(f"Extracted {len(variables)} C++ variables/fields")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract C++ include directives"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        return _extract_imports_standalone(
            tree, source_code, self._get_node_text_optimized
        )

    def extract_packages(self, tree: "tree_sitter.Tree", source_code: str) -> list[Any]:
        """Extract C++ namespace declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        return _extract_namespaces_standalone(tree, self._get_node_text_optimized)

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._comment_cache.clear()
        self._complexity_cache.clear()
        self.current_namespace = ""

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node | None",
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction with caching"""
        if root_node is None:
            return

        target_node_types = set(extractors.keys())
        container_node_types = {
            "translation_unit",
            "namespace_definition",
            "class_specifier",
            "struct_specifier",
            "union_specifier",
            "declaration_list",
            "field_declaration_list",
            "compound_statement",
            "template_declaration",
            "declaration",
        }

        node_stack = [(root_node, 0)]
        processed_nodes = 0
        max_depth = 50

        while node_stack:
            current_node, depth = node_stack.pop()

            if depth > max_depth:
                log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
                continue

            processed_nodes += 1
            node_type = current_node.type

            # Early termination for irrelevant nodes
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue

            # Process target nodes
            if node_type in target_node_types:
                node_id = id(current_node)

                if node_id in self._processed_nodes:
                    continue

                cache_key = (node_id, element_type)
                if cache_key in self._element_cache:
                    element = self._element_cache[cache_key]
                    if element:
                        if isinstance(element, list):
                            results.extend(element)
                        else:
                            results.append(element)
                    self._processed_nodes.add(node_id)
                    continue

                # Extract and cache
                extractor = extractors[node_type]
                element = extractor(current_node)
                self._element_cache[cache_key] = element
                if element:
                    if isinstance(element, list):
                        results.extend(element)
                    else:
                        results.append(element)
                self._processed_nodes.add(node_id)

            # Add children to stack (reversed for correct DFS traversal)
            if current_node.children:
                for child in reversed(current_node.children):
                    node_stack.append((child, depth + 1))

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching using position-based keys"""
        # Use position-based cache key for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)

        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte

            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            self._node_text_cache[cache_key] = text
            return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")
            # Fallback to simple text extraction
            try:
                start_point = node.start_point
                end_point = node.end_point

                if start_point[0] == end_point[0]:
                    line = self.content_lines[start_point[0]]
                    result: str = line[start_point[1] : end_point[1]]
                    return result
                else:
                    lines = []
                    for i in range(start_point[0], end_point[0] + 1):
                        if i < len(self.content_lines):
                            line = self.content_lines[i]
                            if i == start_point[0]:
                                lines.append(line[start_point[1] :])
                            elif i == end_point[0]:
                                lines.append(line[: end_point[1]])
                            else:
                                lines.append(line)
                    return "\n".join(lines)
            except Exception as fallback_error:
                log_error(f"Fallback text extraction also failed: {fallback_error}")
                return ""

    def _extract_function_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract function information optimized"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function details
            function_info = self._parse_function_signature(node)
            if not function_info:
                return None

            name, return_type, parameters, modifiers = function_info

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Determine visibility (check if function is global or class member)
            is_global = self._is_global_scope(node)
            visibility = self._determine_visibility(
                modifiers, is_global=is_global, node=node
            )

            # Extract comments/documentation
            docstring = self._extract_comment_for_line(start_line)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="cpp",
                parameters=parameters,
                return_type=return_type or "void",
                modifiers=modifiers,
                is_static="static" in modifiers,
                is_private="private" in modifiers,
                is_public="public" in modifiers,
                visibility=visibility,
                docstring=docstring,
                complexity_score=complexity_score,
            )
        except (AttributeError, ValueError, TypeError) as e:
            log_debug(f"Failed to extract function info: {e}")
            return None
        except Exception as e:
            log_error(f"Unexpected error in function extraction: {e}")
            return None

    def _extract_function_from_field_declaration(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract function from field_declaration (pure virtual, deleted, etc)."""
        return _extract_func_field_standalone(
            node,
            self._get_node_text_optimized,
            self._extract_parameters,
            self._is_global_scope,
            self._determine_visibility,
            self._extract_comment_for_line,
        )

    def _extract_function_declaration(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract function declaration (prototype)"""
        return _extract_func_decl_standalone(
            node,
            self._get_node_text_optimized,
            self._extract_parameters,
        )

    def _extract_template_function(self, node: "tree_sitter.Node") -> Function | None:
        """Extract template function definition"""
        try:
            # Find the actual function definition inside the template
            for child in node.children:
                if child.type == "function_definition":
                    # Mark child as processed to prevent double extraction
                    child_id = id(child)
                    self._processed_nodes.add(child_id)

                    func = self._extract_function_optimized(child)
                    if func:
                        func.modifiers = func.modifiers or []
                        if "template" not in func.modifiers:
                            func.modifiers.append("template")
                        return func
            return None
        except Exception as e:
            log_debug(f"Failed to extract template function: {e}")
            return None

    def _parse_function_signature(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, str, list[str], list[str]] | None:
        """Parse C++ function signature"""
        return _parse_sig_standalone(
            node, self._get_node_text_optimized, self._extract_parameters
        )

    def _extract_parameters(self, params_node: "tree_sitter.Node") -> list[str]:
        """Extract function parameters"""
        return _extract_params_standalone(params_node, self._get_node_text_optimized)

    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information optimized"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            class_name = None
            superclasses: list[str] = []
            modifiers: list[str] = []

            for child in node.children:
                if child.type == "type_identifier":
                    class_name = self._get_node_text_optimized(child)
                elif child.type == "base_class_clause":
                    superclasses = self._extract_base_classes(child)

            if not class_name:
                return None

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            # Extract comments/documentation
            docstring = self._extract_comment_for_line(start_line)

            # Build fully qualified name with namespace
            full_qualified_name = (
                f"{self.current_namespace}::{class_name}"
                if self.current_namespace
                else class_name
            )

            return Class(
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="cpp",
                class_type="class",
                full_qualified_name=full_qualified_name,
                package_name=self.current_namespace,
                superclass=superclasses[0] if superclasses else None,
                interfaces=superclasses[1:] if len(superclasses) > 1 else [],
                modifiers=modifiers,
                docstring=docstring,
            )
        except Exception as e:
            log_debug(f"Failed to extract class info: {e}")
            return None

    def _extract_struct_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract struct information optimized"""
        try:
            result = self._extract_class_optimized(node)
            if result:
                result.class_type = "struct"
            return result
        except Exception as e:
            log_debug(f"Failed to extract struct info: {e}")
            return None

    def _extract_union_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract union information optimized"""
        try:
            result = self._extract_class_optimized(node)
            if result:
                result.class_type = "union"
            return result
        except Exception as e:
            log_debug(f"Failed to extract union info: {e}")
            return None

    def _extract_template_class(self, node: "tree_sitter.Node") -> Class | None:
        """Extract template class definition"""
        try:
            for child in node.children:
                if child.type == "class_specifier":
                    # Mark child as processed to prevent double extraction
                    child_id = id(child)
                    self._processed_nodes.add(child_id)

                    cls = self._extract_class_optimized(child)
                    if cls:
                        cls.modifiers = cls.modifiers or []
                        if "template" not in cls.modifiers:
                            cls.modifiers.append("template")
                        return cls
                elif child.type == "struct_specifier":
                    # Mark child as processed to prevent double extraction
                    child_id = id(child)
                    self._processed_nodes.add(child_id)

                    cls = self._extract_struct_optimized(child)
                    if cls:
                        cls.modifiers = cls.modifiers or []
                        if "template" not in cls.modifiers:
                            cls.modifiers.append("template")
                        return cls
            return None
        except Exception as e:
            log_debug(f"Failed to extract template class: {e}")
            return None

    def _extract_base_classes(self, node: "tree_sitter.Node") -> list[str]:
        """Extract base class names from base_class_clause"""
        return _extract_base_standalone(node, self._get_node_text_optimized)

    def _extract_field_optimized(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract field declaration"""
        return _extract_cpp_field_standalone(
            node,
            self._get_node_text_optimized,
            self._is_global_scope,
            self._determine_visibility,
        )

    def _extract_variable_declaration(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract variable declarations (not class members)"""
        return _extract_cpp_var_standalone(
            node,
            self._get_node_text_optimized,
            self._is_global_scope,
            self._determine_visibility,
        )

    def _extract_include_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        from .cpp_helpers import _extract_include_info as _impl

        return _impl(node, source_code, self._get_node_text_optimized)

    def _extract_includes_fallback(self, source_code: str) -> list[Import]:
        from .cpp_helpers import _extract_includes_fallback

        return _extract_includes_fallback(source_code)

    def _extract_namespace_info(self, node: "tree_sitter.Node") -> Any:
        from .cpp_helpers import _extract_namespace_info as _impl

        result = _impl(node, self._get_node_text_optimized)
        if result:
            self.current_namespace = result.name
        return result

    def _is_global_scope(self, node: "tree_sitter.Node") -> bool:
        return _is_global_standalone(node)

    def _get_access_specifier(self, node: "tree_sitter.Node") -> str | None:
        return _get_access_standalone(node, self._get_node_text_optimized)

    def _determine_visibility(
        self,
        modifiers: list[str],
        is_global: bool = False,
        node: "tree_sitter.Node | None" = None,
    ) -> str:
        return _determine_vis_standalone(
            modifiers, is_global, node, self._get_node_text_optimized
        )

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        return _calc_complexity_standalone(node)

    def _extract_comment_for_line(self, line: int) -> str | None:
        return _extract_comment_standalone(line, self.content_lines)


class CppPlugin(LanguagePlugin):
    """C++ language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the C++ language plugin."""
        super().__init__()
        self.extractor = CppElementExtractor()
        self.language = "cpp"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "cpp"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".h++", ".c++"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return CppElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze C++ code and return structured results."""
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="cpp",
                    line_count=len(file_content.split("\n")),
                    elements=[],
                    source_code=file_content,
                )

            import tree_sitter

            parser = tree_sitter.Parser()

            if hasattr(parser, "set_language"):
                parser.set_language(language)
            elif hasattr(parser, "language"):
                parser.language = language
            else:
                try:
                    parser = tree_sitter.Parser(language)
                except Exception as e:
                    log_error(f"Failed to create parser with language: {e}")
                    return AnalysisResult(
                        file_path=file_path,
                        language="cpp",
                        line_count=len(file_content.split("\n")),
                        elements=[],
                        source_code=file_content,
                        error_message=f"Parser creation failed: {e}",
                        success=False,
                    )

            tree = parser.parse(file_content.encode("utf-8"))

            elements_dict = self.extract_elements(tree, file_content)

            all_elements = []
            all_elements.extend(elements_dict.get("functions", []))
            all_elements.extend(elements_dict.get("classes", []))
            all_elements.extend(elements_dict.get("variables", []))
            all_elements.extend(elements_dict.get("imports", []))
            all_elements.extend(elements_dict.get("packages", []))

            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            return AnalysisResult(
                file_path=file_path,
                language="cpp",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )

        except Exception as e:
            log_error(f"Error analyzing C++ file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="cpp",
                line_count=0,
                elements=[],
                source_code="",
                error_message=str(e),
                success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """Recursively count nodes in the AST tree."""
        if node is None:
            return 0

        count = 1
        if hasattr(node, "children"):
            for child in node.children:
                count += self._count_tree_nodes(child)
        return count

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for C++."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_cpp

            caps_or_lang = tree_sitter_cpp.language()

            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                self._cached_language = caps_or_lang
            else:
                try:
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language object from PyCapsule: {e}")
                    return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-cpp not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for C++: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements from C++ code."""
        if tree is None:
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "packages": [],
            }

        try:
            extractor = self.create_extractor()
            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "packages": extractor.extract_packages(tree, source_code),
            }
        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "packages": [],
            }
