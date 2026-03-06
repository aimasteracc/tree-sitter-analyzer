#!/usr/bin/env python3
"""
Go Language Plugin

Provides Go-specific parsing and element extraction functionality.
Supports packages, functions, methods, structs, interfaces, type aliases,
const/var declarations, goroutines, and channels.
"""

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


class GoElementExtractor(ElementExtractor):
    """Go-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Go element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}
        # Go-specific metadata
        self.goroutines: list[dict[str, Any]] = []
        self.channels: list[dict[str, Any]] = []
        self.defers: list[dict[str, Any]] = []

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Go function and method declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        extractors = {
            "function_declaration": self._extract_function,
            "method_declaration": self._extract_method,
        }

        self._traverse_and_extract(tree.root_node, extractors, functions)

        log_debug(f"Extracted {len(functions)} Go functions/methods")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract Go struct and interface definitions"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        # Extract type declarations (struct, interface, type alias)
        self._traverse_for_types(tree.root_node, classes)

        log_debug(f"Extracted {len(classes)} Go structs/interfaces")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract Go const and var declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        extractors = {
            "const_declaration": self._extract_const_declaration,
            "var_declaration": self._extract_var_declaration,
        }

        self._traverse_and_extract(tree.root_node, extractors, variables)

        log_debug(f"Extracted {len(variables)} Go const/var declarations")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Go import declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        extractors = {
            "import_declaration": self._extract_import_declaration,
        }

        self._traverse_and_extract(tree.root_node, extractors, imports)

        log_debug(f"Extracted {len(imports)} Go imports")
        return imports

    def extract_packages(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Package]:
        """Extract Go package declaration"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        packages: list[Package] = []

        for child in tree.root_node.children:
            if child.type == "package_clause":
                pkg = self._extract_package(child)
                if pkg:
                    packages.append(pkg)
                    self.current_package = pkg.name
                break

        log_debug(f"Extracted {len(packages)} Go packages")
        return packages

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self.goroutines.clear()
        self.channels.clear()
        self.defers.clear()

    def _traverse_and_extract(
        self,
        node: "tree_sitter.Node",
        extractors: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Recursive traversal to find and extract elements"""
        if node.type in extractors:
            element = extractors[node.type](node)
            if element:
                if isinstance(element, list):
                    results.extend(element)
                else:
                    results.append(element)

        # Also detect goroutines, channels, defers
        if node.type == "go_statement":
            self._extract_goroutine(node)
        elif node.type == "send_statement":
            self._extract_channel_operation(node, "send")
        elif node.type == "defer_statement":
            self._extract_defer(node)

        for child in node.children:
            self._traverse_and_extract(child, extractors, results)

    def _traverse_for_types(
        self, node: "tree_sitter.Node", results: list[Class]
    ) -> None:
        """Traverse to find type declarations"""
        if node.type == "type_declaration":
            classes = self._extract_type_declaration(node)
            if classes:
                results.extend(classes)

        for child in node.children:
            self._traverse_for_types(child, results)

    def _extract_package(self, node: "tree_sitter.Node") -> Package | None:
        """Extract package declaration"""
        try:
            for child in node.children:
                if child.type == "package_identifier":
                    name = self._get_node_text(child)
                    return Package(
                        name=name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        raw_text=self._get_node_text(node),
                        language="go",
                    )
            return None
        except Exception as e:
            log_error(f"Error extracting Go package: {e}")
            return None

    def _extract_import_declaration(
        self, node: "tree_sitter.Node"
    ) -> list[Import] | None:
        """Extract import declaration (may contain multiple imports)"""
        imports: list[Import] = []
        try:
            # Find import_spec_list or single import_spec
            for child in node.children:
                if child.type == "import_spec_list":
                    for spec in child.children:
                        if spec.type == "import_spec":
                            imp = self._extract_import_spec(spec)
                            if imp:
                                imports.append(imp)
                elif child.type == "import_spec":
                    imp = self._extract_import_spec(child)
                    if imp:
                        imports.append(imp)

            return imports if imports else None
        except Exception as e:
            log_error(f"Error extracting Go import: {e}")
            return None

    def _extract_import_spec(self, node: "tree_sitter.Node") -> Import | None:
        """Extract single import spec"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract path and optional alias
            alias = None
            path = None

            for child in node.children:
                if child.type == "package_identifier":
                    alias = self._get_node_text(child)
                elif child.type == "blank_identifier":
                    alias = "_"
                elif child.type == "dot":
                    alias = "."
                elif child.type == "interpreted_string_literal":
                    path = self._get_node_text(child).strip('"')

            if path:
                # Extract package name from path
                name = path.split("/")[-1] if "/" in path else path
                return Import(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="go",
                    module_name=path,
                    import_statement=raw_text,
                    alias=alias,
                )
            return None
        except Exception as e:
            log_error(f"Error extracting Go import spec: {e}")
            return None

    def _extract_function(self, node: "tree_sitter.Node") -> Function | None:
        """Extract function declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node)
            if not name:
                return None

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Parameters
            parameters = self._extract_parameters(node)

            # Return type
            return_type = self._extract_return_type(node)

            # Visibility (exported if starts with uppercase)
            visibility = "public" if name[0].isupper() else "private"

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="go",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                docstring=docstring,
                is_public=visibility == "public",
            )
        except Exception as e:
            log_error(f"Error extracting Go function: {e}")
            return None

    def _extract_method(self, node: "tree_sitter.Node") -> Function | None:
        """Extract method declaration (function with receiver)"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node)
            if not name:
                return None

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Receiver
            receiver = None
            receiver_type = None
            receiver_node = node.child_by_field_name("receiver")
            if receiver_node:
                receiver_text = self._get_node_text(receiver_node)
                # Parse receiver: (r *ReceiverType) or (r ReceiverType)
                match = re.search(r"\(\s*(\w+)\s+(\*?\w+)\s*\)", receiver_text)
                if match:
                    receiver = match.group(1)
                    receiver_type = match.group(2)

            # Parameters
            parameters = self._extract_parameters(node)

            # Return type
            return_type = self._extract_return_type(node)

            # Visibility
            visibility = "public" if name[0].isupper() else "private"

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            func = Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="go",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                docstring=docstring,
                is_public=visibility == "public",
            )
            # Attach Go-specific method attributes
            func.receiver = receiver
            func.receiver_type = receiver_type
            func.is_method = True

            return func
        except Exception as e:
            log_error(f"Error extracting Go method: {e}")
            return None

    def _extract_parameters(self, node: "tree_sitter.Node") -> list[str]:
        """Extract function/method parameters"""
        parameters = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter_declaration":
                    param_text = self._get_node_text(child)
                    parameters.append(param_text)
        return parameters

    def _extract_return_type(self, node: "tree_sitter.Node") -> str:
        """Extract function/method return type"""
        result_node = node.child_by_field_name("result")
        if result_node:
            return self._get_node_text(result_node)
        return ""

    def _extract_type_declaration(self, node: "tree_sitter.Node") -> list[Class]:
        """Extract type declaration (struct, interface, type alias)"""
        classes: list[Class] = []
        try:
            for child in node.children:
                if child.type == "type_spec":
                    cls = self._extract_type_spec(child)
                    if cls:
                        classes.append(cls)
        except Exception as e:
            log_error(f"Error extracting Go type declaration: {e}")
        return classes

    def _extract_type_spec(self, node: "tree_sitter.Node") -> Class | None:
        """Extract single type spec"""
        try:
            name_node = node.child_by_field_name("name")
            type_node = node.child_by_field_name("type")

            if not name_node:
                return None

            name = self._get_node_text(name_node)
            if not name:
                return None

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Determine type kind
            class_type = "type"
            if type_node:
                if type_node.type == "struct_type":
                    class_type = "struct"
                elif type_node.type == "interface_type":
                    class_type = "interface"
                else:
                    class_type = "type_alias"

            # Visibility
            visibility = "public" if name[0].isupper() else "private"

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            # For struct, extract embedded types (interfaces)
            interfaces: list[str] = []
            if type_node and type_node.type == "struct_type":
                interfaces = self._extract_embedded_types(type_node)

            return Class(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="go",
                class_type=class_type,
                visibility=visibility,
                docstring=docstring,
                interfaces=interfaces,
            )
        except Exception as e:
            log_error(f"Error extracting Go type spec: {e}")
            return None

    def _extract_embedded_types(self, struct_node: "tree_sitter.Node") -> list[str]:
        """Extract embedded types from struct"""
        embedded: list[str] = []
        for child in struct_node.children:
            if child.type == "field_declaration_list":
                for field in child.children:
                    if field.type == "field_declaration":
                        # Check if it's an embedded field (no name, just type)
                        has_name = False
                        type_text = None
                        for fc in field.children:
                            if fc.type == "field_identifier":
                                has_name = True
                            elif fc.type in ["type_identifier", "qualified_type"]:
                                type_text = self._get_node_text(fc)
                        if not has_name and type_text:
                            embedded.append(type_text)
        return embedded

    def _extract_const_declaration(
        self, node: "tree_sitter.Node"
    ) -> list[Variable] | None:
        """Extract const declaration"""
        return self._extract_var_or_const(node, is_const=True)

    def _extract_var_declaration(
        self, node: "tree_sitter.Node"
    ) -> list[Variable] | None:
        """Extract var declaration"""
        return self._extract_var_or_const(node, is_const=False)

    def _extract_var_or_const(
        self, node: "tree_sitter.Node", is_const: bool
    ) -> list[Variable] | None:
        """Extract var or const declaration"""
        variables: list[Variable] = []
        try:
            for child in node.children:
                if child.type in ["const_spec", "var_spec"]:
                    vars_from_spec = self._extract_var_spec(child, is_const)
                    if vars_from_spec:
                        variables.extend(vars_from_spec)
        except Exception as e:
            log_error(f"Error extracting Go {'const' if is_const else 'var'}: {e}")
        return variables if variables else None

    def _extract_var_spec(
        self, node: "tree_sitter.Node", is_const: bool
    ) -> list[Variable]:
        """Extract single var/const spec"""
        variables: list[Variable] = []
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            # Extract names and type
            names: list[str] = []
            var_type = ""

            for child in node.children:
                if child.type == "identifier":
                    names.append(self._get_node_text(child))
                elif child.type in [
                    "type_identifier",
                    "pointer_type",
                    "array_type",
                    "slice_type",
                    "map_type",
                    "channel_type",
                    "qualified_type",
                ]:
                    var_type = self._get_node_text(child)

            for name in names:
                visibility = "public" if name[0].isupper() else "private"
                variables.append(
                    Variable(
                        name=name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        language="go",
                        variable_type=var_type,
                        visibility=visibility,
                        is_constant=is_const,
                    )
                )
        except Exception as e:
            log_error(f"Error extracting Go var spec: {e}")
        return variables

    def _extract_goroutine(self, node: "tree_sitter.Node") -> None:
        """Extract goroutine invocation"""
        try:
            self.goroutines.append(
                {
                    "line": node.start_point[0] + 1,
                    "text": self._get_node_text(node),
                }
            )
        except Exception as e:
            log_error(f"Error extracting goroutine: {e}")

    def _extract_channel_operation(
        self, node: "tree_sitter.Node", op_type: str
    ) -> None:
        """Extract channel operation"""
        try:
            self.channels.append(
                {
                    "type": op_type,
                    "line": node.start_point[0] + 1,
                    "text": self._get_node_text(node),
                }
            )
        except Exception as e:
            log_error(f"Error extracting channel operation: {e}")

    def _extract_defer(self, node: "tree_sitter.Node") -> None:
        """Extract defer statement"""
        try:
            self.defers.append(
                {
                    "line": node.start_point[0] + 1,
                    "text": self._get_node_text(node),
                }
            )
        except Exception as e:
            log_error(f"Error extracting defer: {e}")

    def _extract_docstring(self, node: "tree_sitter.Node") -> str | None:
        """Extract doc comments preceding the node"""
        # In Go, doc comments are // comments immediately before the declaration
        start_line = node.start_point[0]
        if start_line == 0:
            return None

        docs: list[str] = []
        line_idx = start_line - 1

        # Ensure line_idx is within valid range
        if line_idx >= len(self.content_lines):
            line_idx = len(self.content_lines) - 1

        while line_idx >= 0:
            line = self.content_lines[line_idx].strip()
            if line.startswith("//"):
                docs.insert(0, line[2:].strip())
                line_idx -= 1
            elif line == "":
                line_idx -= 1
            else:
                break

        return "\n".join(docs) if docs else None

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        """Get node text with caching using position-based keys"""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)
            self._node_text_cache[cache_key] = text
            return text
        except Exception:
            return ""


class GoPlugin(LanguagePlugin):
    """Go language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Go language plugin."""
        super().__init__()
        self.extractor = GoElementExtractor()
        self.language = "go"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "go"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".go"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return GoElementExtractor()

    def get_supported_element_types(self) -> list[str]:
        """Get supported element types for Go."""
        return [
            "package",
            "import",
            "function",
            "method",
            "struct",
            "interface",
            "type_alias",
            "const",
            "var",
            "goroutine",
            "channel",
        ]

    def get_queries(self) -> dict[str, str]:
        """Get Go-specific tree-sitter queries."""
        from ..queries.go import GO_QUERIES

        return GO_QUERIES

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze Go code and return structured results."""
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="go",
                    line_count=len(file_content.split("\n")),
                    elements=[],
                    source_code=file_content,
                )

            import tree_sitter

            parser = tree_sitter.Parser()

            # Set language (handle different tree-sitter versions)
            if hasattr(parser, "set_language"):
                parser.set_language(language)
            elif hasattr(parser, "language"):
                parser.language = language
            else:
                parser = tree_sitter.Parser(language)

            tree = parser.parse(file_content.encode("utf-8"))

            # Extract elements
            elements_dict = self.extract_elements(tree, file_content)

            all_elements = []
            all_elements.extend(elements_dict.get("packages", []))
            all_elements.extend(elements_dict.get("imports", []))
            all_elements.extend(elements_dict.get("functions", []))
            all_elements.extend(elements_dict.get("classes", []))
            all_elements.extend(elements_dict.get("variables", []))

            # Count nodes
            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            result = AnalysisResult(
                file_path=file_path,
                language="go",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )

            # Attach Go-specific metadata
            result.goroutines = self.extractor.goroutines
            result.channels = self.extractor.channels
            result.defers = self.extractor.defers

            return result

        except Exception as e:
            log_error(f"Error analyzing Go file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="go",
                line_count=0,
                elements=[],
                source_code="",
                error_message=str(e),
                success=False,
            )

    def _count_tree_nodes(self, node: Any) -> int:
        """Recursively count nodes."""
        if node is None:
            return 0
        count = 1
        if hasattr(node, "children"):
            for child in node.children:
                count += self._count_tree_nodes(child)
        return count

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Go."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_go

            caps_or_lang = tree_sitter_go.language()

            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                self._cached_language = caps_or_lang
            else:
                try:
                    self._cached_language = tree_sitter.Language(caps_or_lang)
                except Exception as e:
                    log_error(f"Failed to create Language object: {e}")
                    return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-go not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Go: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements from Go source code."""
        if tree is None:
            return {
                "packages": [],
                "imports": [],
                "functions": [],
                "classes": [],
                "variables": [],
            }

        try:
            extractor = self.create_extractor()

            result = {
                "packages": extractor.extract_packages(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
            }

            # Capture Go-specific metadata
            if isinstance(extractor, GoElementExtractor):
                self.extractor.goroutines = extractor.goroutines
                self.extractor.channels = extractor.channels
                self.extractor.defers = extractor.defers

            return result

        except Exception as e:
            log_error(f"Error extracting Go elements: {e}")
            return {
                "packages": [],
                "imports": [],
                "functions": [],
                "classes": [],
                "variables": [],
            }

    def supports_file(self, file_path: str) -> bool:
        """Check if this plugin supports the given file."""
        return any(
            file_path.lower().endswith(ext) for ext in self.get_file_extensions()
        )
