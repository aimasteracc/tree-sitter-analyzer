#!/usr/bin/env python3
"""
Python Language Plugin

Enhanced Python-specific parsing and element extraction functionality.
Provides comprehensive support for modern Python features including async/await,
decorators, type hints, context managers, and framework-specific patterns.
Equivalent to JavaScript plugin capabilities for consistent language support.
"""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..core.analysis_engine import AnalysisRequest
from ..encoding_utils import extract_text_slice, safe_encode
from ..models import AnalysisResult, Class, CodeElement, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning
from ..utils.tree_sitter_compat import TreeSitterQueryCompat


class PythonElementExtractor(ElementExtractor):
    """Enhanced Python-specific element extractor with comprehensive feature support"""

    def __init__(self) -> None:
        """Initialize the Python element extractor."""
        self.current_module: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.imports: list[str] = []
        self.exports: list[dict[str, Any]] = []

        # Performance optimization caches
        self._node_text_cache: dict[int, str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._docstring_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

        # Python-specific tracking
        self.is_module: bool = False
        self.framework_type: str = ""  # django, flask, fastapi, etc.
        self.python_version: str = "3.8"  # default

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Python function definitions with comprehensive details"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        self._detect_file_characteristics()

        functions: list[Function] = []

        # Use optimized traversal for multiple function types
        extractors = {
            "function_definition": self._extract_function_optimized,
        }

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty functions list")
            return functions

        try:
            self._traverse_and_extract_iterative(
                tree.root_node, extractors, functions, "function"
            )
        except Exception as e:
            log_debug(f"Error during function extraction: {e}")
            # Return empty list on error to handle gracefully
            return []

        log_debug(f"Extracted {len(functions)} Python functions")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract Python class definitions with detailed information"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        # Extract class declarations
        extractors = {
            "class_definition": self._extract_class_optimized,
        }

        if tree is None or tree.root_node is None:
            log_debug("Tree or root_node is None, returning empty classes list")
            return classes

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, classes, "class"
        )

        log_debug(f"Extracted {len(classes)} Python classes")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract Python variable definitions (class attributes only)"""
        variables: list[Variable] = []

        # Only extract class-level attributes, not function-level variables
        try:
            # Find class declarations using compatible API
            class_query = """
            (class_definition
                body: (block) @class.body) @class.definition
            """

            language = tree.language if hasattr(tree, "language") else None
            if language:
                try:
                    captures = TreeSitterQueryCompat.safe_execute_query(
                        language, class_query, tree.root_node, fallback_result=[]
                    )
                    class_bodies = []
                    for node, capture_name in captures:
                        if capture_name == "class.body":
                            class_bodies.append(node)
                except Exception as e:
                    log_debug(
                        f"Could not extract Python class attributes using query: {e}"
                    )
                    class_bodies = []

                # For each class body, extract attribute assignments
                for class_body in class_bodies:
                    variables.extend(
                        self._extract_class_attributes(class_body, source_code)
                    )

        except Exception as e:
            log_warning(f"Could not extract Python class attributes: {e}")

        return variables

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._docstring_cache.clear()
        self._complexity_cache.clear()

    def _detect_file_characteristics(self) -> None:
        """Detect Python file characteristics"""
        # Check if it's a module
        self.is_module = "import " in self.source_code or "from " in self.source_code

        # Reset framework type
        self.framework_type = ""

        # Detect framework (case-sensitive)
        if "django" in self.source_code or "from django" in self.source_code:
            self.framework_type = "django"
        elif "flask" in self.source_code or "from flask" in self.source_code:
            self.framework_type = "flask"
        elif "fastapi" in self.source_code or "from fastapi" in self.source_code:
            self.framework_type = "fastapi"

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node",
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """Iterative node traversal and extraction with caching"""
        if not root_node:
            return

        target_node_types = set(extractors.keys())
        container_node_types = {
            "module",
            "class_definition",
            "function_definition",
            "if_statement",
            "for_statement",
            "while_statement",
            "with_statement",
            "try_statement",
            "block",
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
                extractor = extractors.get(node_type)
                if extractor:
                    try:
                        element = extractor(current_node)
                        self._element_cache[cache_key] = element
                        if element:
                            if isinstance(element, list):
                                results.extend(element)
                            else:
                                results.append(element)
                        self._processed_nodes.add(node_id)
                    except Exception:
                        # Skip nodes that cause extraction errors
                        self._processed_nodes.add(node_id)
                        continue

            # Add children to stack
            if current_node.children:
                try:
                    # Try to reverse children for proper traversal order
                    children = reversed(current_node.children)
                except TypeError:
                    # Fallback for Mock objects or other non-reversible types
                    try:
                        children = list(current_node.children)
                    except TypeError:
                        # If children is not iterable, skip
                        children = []

                for child in children:
                    node_stack.append((child, depth + 1))

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """Get node text with optimized caching"""
        node_id = id(node)

        if node_id in self._node_text_cache:
            return self._node_text_cache[node_id]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte

            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)

            # If byte extraction returns empty string, try fallback
            if text:
                self._node_text_cache[node_id] = text
                return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")

        # Fallback to simple text extraction
        try:
            start_point = node.start_point
            end_point = node.end_point

            # Validate points are within bounds
            if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
                return ""

            if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
                return ""

            if start_point[0] == end_point[0]:
                line = self.content_lines[start_point[0]]
                # Ensure column indices are within line bounds
                start_col = max(0, min(start_point[1], len(line)))
                end_col = max(start_col, min(end_point[1], len(line)))
                result = line[start_col:end_col]
                self._node_text_cache[node_id] = result
                return result
            else:
                lines = []
                for i in range(start_point[0], end_point[0] + 1):
                    if i < len(self.content_lines):
                        line = self.content_lines[i]
                        if i == start_point[0]:
                            start_col = max(0, min(start_point[1], len(line)))
                            lines.append(line[start_col:])
                        elif i == end_point[0]:
                            end_col = max(0, min(end_point[1], len(line)))
                            lines.append(line[:end_col])
                        else:
                            lines.append(line)
                result = "\n".join(lines)
                self._node_text_cache[node_id] = result
                return result
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            return ""

    def _extract_function_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract function information with detailed metadata"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract function details
            function_info = self._parse_function_signature_optimized(node)
            if not function_info:
                return None

            name, parameters, is_async, decorators, return_type = function_info

            # Extract docstring
            docstring = self._extract_docstring_for_line(start_line)

            # Calculate complexity
            complexity_score = self._calculate_complexity_optimized(node)

            # Extract raw text
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(self.content_lines), end_line)
            raw_text = "\n".join(self.content_lines[start_line_idx:end_line_idx])

            # Determine visibility (Python conventions)
            visibility = "public"
            if name.startswith("__") and name.endswith("__"):
                visibility = "magic"  # Magic methods
            elif name.startswith("_"):
                visibility = "private"

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="python",
                parameters=parameters,
                return_type=return_type or "Any",
                is_async=is_async,
                is_generator="yield" in raw_text,
                docstring=docstring,
                complexity_score=complexity_score,
                modifiers=decorators,
                is_static="staticmethod" in decorators,
                is_staticmethod="staticmethod" in decorators,
                is_private=visibility == "private",
                is_public=visibility == "public",
                # Python-specific properties
                framework_type=self.framework_type,
                is_property="property" in decorators,
                is_classmethod="classmethod" in decorators,
            )
        except Exception as e:
            log_error(f"Failed to extract function info: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _parse_function_signature_optimized(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, list[str], bool, list[str], str | None] | None:
        """Parse function signature for Python functions"""
        try:
            name = None
            parameters = []
            is_async = False
            decorators = []
            return_type = None

            # Check for async keyword
            node_text = self._get_node_text_optimized(node)
            is_async = node_text.strip().startswith("async def")

            # Extract decorators from preceding siblings
            if node.parent:
                for sibling in node.parent.children:
                    if sibling.type == "decorated_definition":
                        for child in sibling.children:
                            if child.type == "decorator":
                                decorator_text = self._get_node_text_optimized(child)
                                if decorator_text.startswith("@"):
                                    decorator_text = decorator_text[1:].strip()
                                decorators.append(decorator_text)

            for child in node.children:
                if child.type == "identifier":
                    name = child.text.decode("utf8") if child.text else None
                elif child.type == "parameters":
                    parameters = self._extract_parameters_from_node_optimized(child)
                elif child.type == "type":
                    return_type = self._get_node_text_optimized(child)

            return name or "", parameters, is_async, decorators, return_type
        except Exception:
            return None

    def _extract_parameters_from_node_optimized(
        self, params_node: "tree_sitter.Node"
    ) -> list[str]:
        """Extract function parameters with type hints"""
        parameters = []

        for child in params_node.children:
            if child.type == "identifier":
                param_name = self._get_node_text_optimized(child)
                parameters.append(param_name)
            elif child.type == "typed_parameter":
                # Handle typed parameters
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "default_parameter":
                # Handle default parameters
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "list_splat_pattern":
                # Handle *args
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "dictionary_splat_pattern":
                # Handle **kwargs
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)

        return parameters

    def _extract_docstring_for_line(self, target_line: int) -> str | None:
        """Extract docstring for the specified line"""
        if target_line in self._docstring_cache:
            return self._docstring_cache[target_line]

        try:
            if not self.content_lines or target_line >= len(self.content_lines):
                return None

            # Look for docstring in the next few lines after function definition
            for i in range(target_line, min(target_line + 5, len(self.content_lines))):
                line = self.content_lines[i].strip()
                if line.startswith('"""') or line.startswith("'''"):
                    # Found docstring start
                    quote_type = '"""' if line.startswith('"""') else "'''"
                    docstring_lines = []

                    # Single line docstring
                    if line.count(quote_type) >= 2:
                        docstring = line.replace(quote_type, "").strip()
                        self._docstring_cache[target_line] = docstring
                        return docstring

                    # Multi-line docstring
                    docstring_lines.append(line.replace(quote_type, ""))
                    found_closing_quote = False
                    for j in range(i + 1, len(self.content_lines)):
                        next_line = self.content_lines[j]
                        if quote_type in next_line:
                            docstring_lines.append(next_line.replace(quote_type, ""))
                            found_closing_quote = True
                            break
                        docstring_lines.append(next_line)

                    # If no closing quote found, return None (malformed docstring)
                    if not found_closing_quote:
                        self._docstring_cache[target_line] = None
                        return None

                    # Join preserving formatting and add leading newline for multi-line
                    docstring = "\n".join(docstring_lines)
                    # Add leading newline for multi-line docstrings to match expected format
                    if not docstring.startswith("\n"):
                        docstring = "\n" + docstring
                    self._docstring_cache[target_line] = docstring
                    return docstring

            self._docstring_cache[target_line] = None
            return None

        except Exception as e:
            log_debug(f"Failed to extract docstring: {e}")
            return None

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity efficiently"""
        import re

        node_id = id(node)
        if node_id in self._complexity_cache:
            return self._complexity_cache[node_id]

        complexity = 1
        try:
            node_text = self._get_node_text_optimized(node).lower()
            keywords = [
                "if",
                "elif",
                "while",
                "for",
                "except",
                "and",
                "or",
                "with",
                "match",
                "case",
            ]
            for keyword in keywords:
                # More flexible keyword matching
                pattern = rf"\b{keyword}\b"
                matches = re.findall(pattern, node_text)
                complexity += len(matches)
        except Exception as e:
            log_debug(f"Failed to calculate complexity: {e}")

        self._complexity_cache[node_id] = complexity
        return complexity

    def _extract_class_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class information with detailed metadata"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract class name
            class_name = None
            superclasses = []
            decorators = []

            # Extract decorators from preceding siblings
            if node.parent:
                for sibling in node.parent.children:
                    if sibling.type == "decorated_definition":
                        for child in sibling.children:
                            if child.type == "decorator":
                                decorator_text = self._get_node_text_optimized(child)
                                if decorator_text.startswith("@"):
                                    decorator_text = decorator_text[1:].strip()
                                decorators.append(decorator_text)

            for child in node.children:
                if child.type == "identifier":
                    class_name = child.text.decode("utf8") if child.text else None
                elif child.type == "argument_list":
                    # Extract superclasses
                    if child.children:  # Check if children exists and is not None
                        for grandchild in child.children:
                            if grandchild.type == "identifier":
                                superclass_name = (
                                    grandchild.text.decode("utf8")
                                    if grandchild.text
                                    else None
                                )
                                if superclass_name:
                                    superclasses.append(superclass_name)

            if not class_name:
                return None

            # Extract docstring
            docstring = self._extract_docstring_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            # Generate fully qualified name
            full_qualified_name = (
                f"{self.current_module}.{class_name}"
                if self.current_module
                else class_name
            )

            return Class(
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="python",
                class_type="class",
                superclass=superclasses[0] if superclasses else None,
                interfaces=superclasses[1:] if len(superclasses) > 1 else [],
                docstring=docstring,
                modifiers=decorators,
                full_qualified_name=full_qualified_name,
                package_name=self.current_module,
                # Python-specific properties
                framework_type=self.framework_type,
                is_dataclass="dataclass" in decorators,
                is_abstract="ABC" in superclasses or "abstractmethod" in raw_text,
                is_exception=any(
                    "Exception" in sc or "Error" in sc for sc in superclasses
                ),
            )
        except Exception as e:
            log_debug(f"Failed to extract class info: {e}")
            return None

    def _is_framework_class(self, node: "tree_sitter.Node", class_name: str) -> bool:
        """Check if class is a framework-specific class"""
        if self.framework_type == "django":
            # Check for Django model, view, form, etc.
            node_text = self._get_node_text_optimized(node)
            return any(
                pattern in node_text
                for pattern in ["Model", "View", "Form", "Serializer", "TestCase"]
            )
        elif self.framework_type == "flask":
            # Check for Flask patterns
            return "Flask" in self.source_code or "Blueprint" in self.source_code
        elif self.framework_type == "fastapi":
            # Check for FastAPI patterns
            return "APIRouter" in self.source_code or "BaseModel" in self.source_code
        return False

    def _extract_class_attributes(
        self, class_body_node: "tree_sitter.Node", source_code: str
    ) -> list[Variable]:
        """Extract class-level attribute assignments"""
        attributes: list[Variable] = []

        try:
            # Look for assignments directly under class body
            for child in class_body_node.children:
                if child.type == "expression_statement":
                    # Check if it's an assignment
                    for grandchild in child.children:
                        if grandchild.type == "assignment":
                            attribute = self._extract_class_attribute_info(
                                grandchild, source_code
                            )
                            if attribute:
                                attributes.append(attribute)
                elif child.type == "assignment":
                    attribute = self._extract_class_attribute_info(child, source_code)
                    if attribute:
                        attributes.append(attribute)

        except Exception as e:
            log_warning(f"Could not extract class attributes: {e}")

        return attributes

    def _extract_class_attribute_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Variable | None:
        """Extract class attribute information from assignment node"""
        try:
            # Get the full assignment text
            assignment_text = source_code[node.start_byte : node.end_byte]

            # Extract attribute name and type annotation
            if "=" in assignment_text:
                left_part = assignment_text.split("=")[0].strip()

                # Handle type annotations (e.g., "name: str = ...")
                if ":" in left_part:
                    name_part, type_part = left_part.split(":", 1)
                    attr_name = name_part.strip()
                    attr_type = type_part.strip()
                else:
                    attr_name = left_part
                    attr_type = None

                return Variable(
                    name=attr_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=assignment_text,
                    language="python",
                    variable_type=attr_type,
                )

        except Exception as e:
            log_warning(f"Could not extract class attribute info: {e}")

        return None

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Python import statements"""
        imports: list[Import] = []

        # Import statement queries
        import_queries = [
            # Regular import statements
            """
            (import_statement
                name: (dotted_name) @import.name) @import.statement
            """,
            # From import statements
            """
            (import_from_statement
                module_name: (dotted_name) @from_import.module
                name: (dotted_name) @from_import.name) @from_import.statement
            """,
            # Aliased imports
            """
            (aliased_import
                name: (dotted_name) @aliased_import.name
                alias: (identifier) @aliased_import.alias) @aliased_import.statement
            """,
        ]

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                for query_string in import_queries:
                    try:
                        captures = TreeSitterQueryCompat.safe_execute_query(
                            language, query_string, tree.root_node, fallback_result=[]
                        )

                        # Group captures by name
                        captures_dict = {}
                        for node, capture_name in captures:
                            if capture_name not in captures_dict:
                                captures_dict[capture_name] = []
                            captures_dict[capture_name].append(node)

                        # Process different types of imports
                        for key, nodes in captures_dict.items():
                            if key.endswith("statement"):
                                import_type = key.split(".")[0]
                                for node in nodes:
                                    imp = self._extract_import_info(
                                        node, source_code, import_type
                                    )
                                    if imp:
                                        imports.append(imp)
                    except Exception as query_error:
                        # Fallback to manual extraction for tree-sitter compatibility
                        log_debug(
                            f"Query execution failed, using manual extraction: {query_error}"
                        )
                        imports.extend(
                            self._extract_imports_manual(tree.root_node, source_code)
                        )
                        break

        except Exception as e:
            log_warning(f"Could not extract Python imports: {e}")
            # Final fallback
            imports.extend(self._extract_imports_manual(tree.root_node, source_code))

        return imports

    def _extract_imports_manual(
        self, root_node: "tree_sitter.Node", source_code: str
    ) -> list[Import]:
        """Manual import extraction for tree-sitter 0.25.x compatibility"""
        imports = []

        def walk_tree(node):
            if node.type in ["import_statement", "import_from_statement"]:
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = (
                        source_code[node.start_byte : node.end_byte]
                        if hasattr(node, "start_byte")
                        else ""
                    )

                    # Extract module name from the import statement
                    module_name = ""
                    imported_names = []

                    if node.type == "import_statement":
                        # Simple import: import os, sys
                        for child in node.children:
                            if child.type == "dotted_name":
                                module_name = (
                                    source_code[child.start_byte : child.end_byte]
                                    if hasattr(child, "start_byte")
                                    else ""
                                )
                                imported_names.append(module_name)
                    elif node.type == "import_from_statement":
                        # From import: from os import path
                        for child in node.children:
                            if child.type == "dotted_name" and not module_name:
                                module_name = (
                                    source_code[child.start_byte : child.end_byte]
                                    if hasattr(child, "start_byte")
                                    else ""
                                )

                    if module_name or imported_names:
                        import_obj = Import(
                            name=module_name or imported_names[0]
                            if imported_names
                            else "unknown",
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            module_name=module_name,
                            imported_names=imported_names,
                            element_type="import",
                        )
                        imports.append(import_obj)
                except Exception as e:
                    log_warning(f"Failed to extract import manually: {e}")

            # Recursively process children
            for child in node.children:
                walk_tree(child)

        walk_tree(root_node)
        return imports

    def _extract_detailed_function_info(
        self, node: "tree_sitter.Node", source_code: str, is_async: bool = False
    ) -> Function | None:
        """Extract comprehensive function information from AST node"""
        try:
            # Extract basic information
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # Extract parameters
            parameters = self._extract_parameters_from_node(node, source_code)

            # Extract decorators
            decorators = self._extract_decorators_from_node(node, source_code)

            # Extract return type hint
            return_type = self._extract_return_type_from_node(node, source_code)

            # Extract docstring
            # docstring = self._extract_docstring_from_node(node, source_code)  # Not used currently

            # Extract function body
            # body = self._extract_function_body(node, source_code)  # Not used currently

            # Calculate complexity (simplified)
            # complexity_score = self._calculate_complexity(body)  # Not used currently

            # Determine visibility (Python conventions)
            visibility = "public"
            if name.startswith("__") and name.endswith("__"):
                visibility = "magic"  # Magic methods
            elif name.startswith("_"):
                visibility = "private"

            # Safely extract raw text, avoiding index out of bounds
            start_byte = min(node.start_byte, len(source_code))
            end_byte = min(node.end_byte, len(source_code))
            raw_text = (
                source_code[start_byte:end_byte]
                if start_byte < end_byte
                else source_code
            )

            return Function(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=raw_text,
                language="python",
                parameters=parameters,
                return_type=return_type or "Any",
                modifiers=decorators,
                is_static="staticmethod" in decorators,
                is_private=visibility == "private",
                is_public=visibility == "public",
            )

        except Exception as e:
            log_warning(f"Could not extract detailed function info: {e}")
            return None

    def _extract_detailed_class_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Class | None:
        """Extract comprehensive class information from AST node"""
        try:
            # Extract basic information
            name = self._extract_name_from_node(node, source_code)
            if not name:
                return None

            # Extract superclasses
            superclasses = self._extract_superclasses_from_node(node, source_code)

            # Extract decorators
            decorators = self._extract_decorators_from_node(node, source_code)

            # Extract docstring
            # docstring = self._extract_docstring_from_node(node, source_code)  # Not used currently

            # Generate fully qualified name
            full_qualified_name = (
                f"{self.current_module}.{name}" if self.current_module else name
            )

            # Determine visibility
            # visibility = "public"
            # if name.startswith("_"):
            #     visibility = "private"  # Not used currently

            return Class(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="python",
                class_type="class",
                full_qualified_name=full_qualified_name,
                package_name=self.current_module,
                superclass=superclasses[0] if superclasses else None,
                interfaces=superclasses[1:] if len(superclasses) > 1 else [],
                modifiers=decorators,
            )

        except Exception as e:
            log_warning(f"Could not extract detailed class info: {e}")
            return None

    def _extract_variable_info(
        self, node: "tree_sitter.Node", source_code: str, assignment_type: str
    ) -> Variable | None:
        """Extract detailed variable information from AST node"""
        try:
            if not self._validate_node(node):
                return None

            # Extract variable text
            variable_text = source_code[node.start_byte : node.end_byte]

            # Extract variable name (simplified)
            if "=" in variable_text:
                name_part = variable_text.split("=")[0].strip()
                if assignment_type == "multiple_assignment" and "," in name_part:
                    name = name_part.split(",")[0].strip()
                else:
                    name = name_part
            else:
                name = "variable"

            return Variable(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=variable_text,
                language="python",
                variable_type=assignment_type,
            )

        except Exception as e:
            log_warning(f"Could not extract variable info: {e}")
            return None

    def _extract_import_info(
        self, node: "tree_sitter.Node", source_code: str, import_type: str
    ) -> Import | None:
        """Extract detailed import information from AST node"""
        try:
            if not self._validate_node(node):
                return None

            # Safely extract import text, avoiding index out of bounds
            start_byte = min(node.start_byte, len(source_code))
            end_byte = min(node.end_byte, len(source_code))
            import_text = (
                source_code[start_byte:end_byte]
                if start_byte < end_byte
                else source_code
            )

            # Extract import name and module name (simplified)
            if import_type == "from_import":
                if "from" in import_text and "import" in import_text:
                    parts = import_text.split("import")
                    module_name = parts[0].replace("from", "").strip()
                    import_name = parts[1].strip()
                else:
                    module_name = ""
                    import_name = import_text
            elif import_type == "aliased_import":
                module_name = ""
                import_name = import_text
            else:
                module_name = ""
                import_name = import_text.replace("import", "").strip()

            return Import(
                name=import_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=import_text,
                language="python",
                module_name=module_name,
            )

        except Exception as e:
            log_warning(f"Could not extract import info: {e}")
            return None

    # Helper methods
    def _validate_node(self, node: "tree_sitter.Node") -> bool:
        """Validate that a node has required attributes"""
        required_attrs = ["start_byte", "end_byte", "start_point", "end_point"]
        for attr in required_attrs:
            if not hasattr(node, attr) or getattr(node, attr) is None:
                return False
        return True

    def _extract_name_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract name from AST node"""
        for child in node.children:
            if child.type == "identifier":
                return source_code[child.start_byte : child.end_byte]
        return None

    def _extract_parameters_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> list[str]:
        """Extract parameters from function node"""
        parameters: list[str] = []
        for child in node.children:
            if child.type == "parameters":
                for param_child in child.children:
                    if param_child.type in [
                        "identifier",
                        "typed_parameter",
                        "default_parameter",
                    ]:
                        param_text = source_code[
                            param_child.start_byte : param_child.end_byte
                        ]
                        parameters.append(param_text)
        return parameters

    def _extract_decorators_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> list[str]:
        """Extract decorators from node"""
        decorators: list[str] = []

        # Decorators are before function/class definitions
        if hasattr(node, "parent") and node.parent:
            for sibling in node.parent.children:
                if (
                    sibling.type == "decorator"
                    and sibling.end_point[0] < node.start_point[0]
                ):
                    decorator_text = source_code[sibling.start_byte : sibling.end_byte]
                    # Remove @
                    if decorator_text.startswith("@"):
                        decorator_text = decorator_text[1:].strip()
                    decorators.append(decorator_text)

        return decorators

    def _extract_return_type_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract return type annotation from function node"""
        for child in node.children:
            if child.type == "type":
                return source_code[child.start_byte : child.end_byte]
        return None

    def _extract_docstring_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> str | None:
        """Extract docstring from function/class node"""
        for child in node.children:
            if child.type == "block":
                # Check if the first statement in the block is a docstring
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        for expr in stmt.children:
                            if expr.type == "string":
                                if self._validate_node(expr):
                                    docstring = source_code[
                                        expr.start_byte : expr.end_byte
                                    ]
                                    # Remove quotes
                                    if docstring.startswith(
                                        '"""'
                                    ) or docstring.startswith("'''"):
                                        return docstring[3:-3].strip()
                                    elif docstring.startswith(
                                        '"'
                                    ) or docstring.startswith("'"):
                                        return docstring[1:-1].strip()
                                    return docstring
                        break
                break
        return None

    def _extract_function_body(self, node: "tree_sitter.Node", source_code: str) -> str:
        """Extract function body"""
        for child in node.children:
            if child.type == "block":
                return source_code[child.start_byte : child.end_byte]
        return ""

    def _extract_superclasses_from_node(
        self, node: "tree_sitter.Node", source_code: str
    ) -> list[str]:
        """Extract superclasses from class node"""
        superclasses: list[str] = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        superclasses.append(source_code[arg.start_byte : arg.end_byte])
        return superclasses

    def _calculate_complexity(self, body: str) -> int:
        """Calculate cyclomatic complexity (simplified)"""
        complexity = 1  # Base complexity
        keywords = ["if", "elif", "for", "while", "try", "except", "with", "and", "or"]
        for keyword in keywords:
            complexity += body.count(f" {keyword} ") + body.count(f"\n{keyword} ")
        return complexity


class PythonPlugin(LanguagePlugin):
    """Python language plugin for the new architecture"""

    def __init__(self) -> None:
        """Initialize the Python plugin"""
        super().__init__()
        self._language_cache: tree_sitter.Language | None = None
        self._extractor: PythonElementExtractor | None = None

        # Legacy compatibility attributes for tests
        self.language = "python"
        self.extractor = self.get_extractor()

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "python"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".py", ".pyw", ".pyi"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return PythonElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        """Get the cached extractor instance, creating it if necessary"""
        if self._extractor is None:
            self._extractor = PythonElementExtractor()
        return self._extractor

    def get_language(self) -> str:
        """Get the language name for Python (legacy compatibility)"""
        return "python"

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract functions from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_functions(tree, source_code)

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract classes from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_classes(tree, source_code)

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract variables from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_variables(tree, source_code)

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract imports from the tree (legacy compatibility)"""
        extractor = self.get_extractor()
        return extractor.extract_imports(tree, source_code)

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Get the Tree-sitter language object for Python"""
        if self._language_cache is None:
            try:
                import tree_sitter
                import tree_sitter_python as tspython

                # PyCapsuleオブジェクトをLanguageオブジェクトに変換
                language_capsule = tspython.language()
                self._language_cache = tree_sitter.Language(language_capsule)
            except ImportError:
                log_error("tree-sitter-python not available")
                return None
            except Exception as e:
                log_error(f"Failed to load Python language: {e}")
                return None
        return self._language_cache

    def get_supported_queries(self) -> list[str]:
        """Get list of supported query names for this language"""
        return [
            "function",
            "class",
            "variable",
            "import",
            "async_function",
            "method",
            "decorator",
            "exception",
            "comprehension",
            "lambda",
            "context_manager",
            "type_hint",
            "docstring",
            "django_model",
            "flask_route",
            "fastapi_endpoint",
        ]

    def is_applicable(self, file_path: str) -> bool:
        """Check if this plugin is applicable for the given file"""
        return any(
            file_path.lower().endswith(ext.lower())
            for ext in self.get_file_extensions()
        )

    def get_plugin_info(self) -> dict:
        """Get information about this plugin"""
        return {
            "name": "Python Plugin",
            "language": self.get_language_name(),
            "extensions": self.get_file_extensions(),
            "version": "2.0.0",
            "supported_queries": self.get_supported_queries(),
            "features": [
                "Async/await functions",
                "Type hints support",
                "Decorators",
                "Context managers",
                "Comprehensions",
                "Lambda expressions",
                "Exception handling",
                "Docstring extraction",
                "Django framework support",
                "Flask framework support",
                "FastAPI framework support",
                "Dataclass support",
                "Abstract class detection",
                "Complexity analysis",
            ],
        }

    def execute_query_strategy(
        self, tree: "tree_sitter.Tree", source_code: str, query_key: str
    ) -> list[dict]:
        """
        Execute query strategy for Python language

        Args:
            tree: Tree-sitter tree object
            source_code: Source code string
            query_key: Query key to execute

        Returns:
            List of query results
        """
        # Use the extractor to get elements based on query_key
        extractor = self.get_extractor()

        # Map query keys to extraction methods
        if query_key in ["function", "functions", "method", "methods"]:
            elements = extractor.extract_functions(tree, source_code)
        elif query_key in ["class", "classes"]:
            elements = extractor.extract_classes(tree, source_code)
        elif query_key in ["variable", "variables"]:
            elements = extractor.extract_variables(tree, source_code)
        elif query_key in ["import", "imports", "from_import", "from_imports"]:
            elements = extractor.extract_imports(tree, source_code)
        else:
            # For unknown query keys, return empty list
            return []

        # Convert elements to query result format
        results = []
        for element in elements:
            result = {
                "capture_name": query_key,
                "node_type": self._get_node_type_for_element(element),
                "start_line": element.start_line,
                "end_line": element.end_line,
                "text": element.raw_text,
                "name": element.name,
            }
            results.append(result)

        return results

    def _get_node_type_for_element(self, element) -> str:
        """Get appropriate node type for element"""
        from ..models import Class, Function, Import, Variable

        if isinstance(element, Function):
            return "function_definition"
        elif isinstance(element, Class):
            return "class_definition"
        elif isinstance(element, Variable):
            return "assignment"
        elif isinstance(element, Import):
            return "import_statement"
        else:
            return "unknown"

    def get_element_categories(self) -> dict[str, list[str]]:
        """
        Get element categories mapping query keys to node types

        Returns:
            Dictionary mapping query keys to lists of node types
        """
        return {
            # Function-related queries
            "function": ["function_definition"],
            "functions": ["function_definition"],
            "async_function": ["function_definition"],
            "async_functions": ["function_definition"],
            "method": ["function_definition"],
            "methods": ["function_definition"],
            "lambda": ["lambda"],
            "lambdas": ["lambda"],
            # Class-related queries
            "class": ["class_definition"],
            "classes": ["class_definition"],
            # Import-related queries
            "import": ["import_statement", "import_from_statement"],
            "imports": ["import_statement", "import_from_statement"],
            "from_import": ["import_from_statement"],
            "from_imports": ["import_from_statement"],
            # Variable-related queries
            "variable": ["assignment"],
            "variables": ["assignment"],
            # Decorator-related queries
            "decorator": ["decorator"],
            "decorators": ["decorator"],
            # Exception-related queries
            "exception": ["raise_statement", "except_clause"],
            "exceptions": ["raise_statement", "except_clause"],
            # Comprehension-related queries
            "comprehension": [
                "list_comprehension",
                "set_comprehension",
                "dictionary_comprehension",
                "generator_expression",
            ],
            "comprehensions": [
                "list_comprehension",
                "set_comprehension",
                "dictionary_comprehension",
                "generator_expression",
            ],
            # Context manager queries
            "context_manager": ["with_statement"],
            "context_managers": ["with_statement"],
            # Type hint queries
            "type_hint": ["type"],
            "type_hints": ["type"],
            # Docstring queries
            "docstring": ["string"],
            "docstrings": ["string"],
            # Framework-specific queries
            "django_model": ["class_definition"],
            "django_models": ["class_definition"],
            "flask_route": ["decorator"],
            "flask_routes": ["decorator"],
            "fastapi_endpoint": ["function_definition"],
            "fastapi_endpoints": ["function_definition"],
            # Generic queries
            "all_elements": [
                "function_definition",
                "class_definition",
                "import_statement",
                "import_from_statement",
                "assignment",
                "decorator",
                "raise_statement",
                "except_clause",
                "list_comprehension",
                "set_comprehension",
                "dictionary_comprehension",
                "generator_expression",
                "with_statement",
                "type",
                "string",
                "lambda",
            ],
        }

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze a Python file and return the analysis results."""
        if not TREE_SITTER_AVAILABLE:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Tree-sitter library not available.",
            )

        language = self.get_tree_sitter_language()
        if not language:
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message="Could not load Python language for parsing.",
            )

        try:
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            parser = tree_sitter.Parser()
            parser.language = language
            tree = parser.parse(bytes(source_code, "utf8"))

            extractor = self.create_extractor()
            extractor.current_file = file_path  # Set current file for context

            elements: list[CodeElement] = []

            # Extract all element types
            functions = extractor.extract_functions(tree, source_code)
            classes = extractor.extract_classes(tree, source_code)
            variables = extractor.extract_variables(tree, source_code)
            imports = extractor.extract_imports(tree, source_code)

            elements.extend(functions)
            elements.extend(classes)
            elements.extend(variables)
            elements.extend(imports)

            def count_nodes(node: "tree_sitter.Node") -> int:
                count = 1
                for child in node.children:
                    count += count_nodes(child)
                return count

            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=True,
                elements=elements,
                line_count=len(source_code.splitlines()),
                node_count=count_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing Python file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.get_language_name(),
                success=False,
                error_message=str(e),
            )

    def execute_query(self, tree: "tree_sitter.Tree", query_name: str) -> dict:
        """Execute a specific query on the tree"""
        try:
            language = self.get_tree_sitter_language()
            if not language:
                return {"error": "Language not available"}

            # Simple query execution for testing
            if query_name == "function":
                query_string = "(function_definition) @function"
            elif query_name == "class":
                query_string = "(class_definition) @class"
            else:
                return {"error": f"Unknown query: {query_name}"}

            captures = TreeSitterQueryCompat.safe_execute_query(
                language, query_string, tree.root_node, fallback_result=[]
            )
            return {"captures": captures, "query": query_string}

        except Exception as e:
            log_error(f"Query execution failed: {e}")
            return {"error": str(e)}

    def extract_elements(self, tree: "tree_sitter.Tree", source_code: str) -> list:
        """Extract elements from source code using tree-sitter AST"""
        extractor = self.get_extractor()
        elements = []

        try:
            elements.extend(extractor.extract_functions(tree, source_code))
            elements.extend(extractor.extract_classes(tree, source_code))
            elements.extend(extractor.extract_variables(tree, source_code))
            elements.extend(extractor.extract_imports(tree, source_code))
        except Exception as e:
            log_error(f"Failed to extract elements: {e}")

        return elements
