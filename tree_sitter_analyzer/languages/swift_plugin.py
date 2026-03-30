#!/usr/bin/env python3
"""
Swift Language Plugin

Provides Swift-specific parsing and element extraction functionality.
Supports classes, structs, protocols, enums, functions, properties,
initializers, deinitializers, subscripts, typealiases, and imports.
"""

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Expression, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


class SwiftElementExtractor(ElementExtractor):
    """Swift-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Swift element extractor."""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Swift function declarations, initializers, and deinitializers"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        extractors = {
            "function_declaration": self._extract_function,
            "init_declaration": self._extract_init,
            "deinit_declaration": self._extract_deinit,
        }

        self._traverse_and_extract(tree.root_node, extractors, functions)

        log_debug(f"Extracted {len(functions)} Swift functions/initializers")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract Swift class, struct, protocol, enum, and actor definitions"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []

        extractors = {
            "class_declaration": self._extract_class,
            "protocol_declaration": self._extract_protocol,
        }

        self._traverse_and_extract(tree.root_node, extractors, classes)

        log_debug(f"Extracted {len(classes)} Swift classes/protocols/structs")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract Swift property declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        extractors = {
            "property_declaration": self._extract_property,
            "computed_property": self._extract_computed_property,
            "typealias_declaration": self._extract_typealias,
        }

        self._traverse_and_extract(tree.root_node, extractors, variables)

        log_debug(f"Extracted {len(variables)} Swift properties/typealiases")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Swift import declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        extractors = {
            "import_declaration": self._extract_import_declaration,
        }

        self._traverse_and_extract(tree.root_node, extractors, imports)

        log_debug(f"Extracted {len(imports)} Swift imports")
        return imports

    def extract_comments(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Expression]:
        """Extract Swift comments (including multiline comments)"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        comments: list[Expression] = []

        extractors = {
            "comment": self._extract_comment,
            "multiline_comment": self._extract_comment,
        }

        self._traverse_and_extract(tree.root_node, extractors, comments)

        log_debug(f"Extracted {len(comments)} Swift comments")
        return comments

    def extract_operators(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Swift operator declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        operators: list[Function] = []

        extractors = {
            "operator_declaration": self._extract_operator_declaration,
        }

        self._traverse_and_extract(tree.root_node, extractors, operators)

        log_debug(f"Extracted {len(operators)} Swift operator declarations")
        return operators

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()

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

        for child in node.children:
            self._traverse_and_extract(child, extractors, results)

    def _extract_import_declaration(
        self, node: "tree_sitter.Node"
    ) -> Import | None:
        """Extract import declaration"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract module name from import statement
            # import Foundation, import UIKit, etc.
            match = re.search(r"import\s+(\w+)", raw_text)
            name = match.group(1) if match else "unknown"

            return Import(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                module_name=name,
                import_statement=raw_text,
            )
        except Exception as e:
            log_error(f"Error extracting Swift import: {e}")
            return None

    def _extract_comment(self, node: "tree_sitter.Node") -> Expression | None:
        """Extract comment (both single-line and multiline)"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Determine comment type
            comment_type = "multiline_comment" if node.type == "multiline_comment" else "comment"

            # Get preview (first 50 chars)
            preview = raw_text[:50] if len(raw_text) > 50 else raw_text

            return Expression(
                name=comment_type,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                expression_kind=comment_type,
                preview=preview,
            )
        except Exception as e:
            log_error(f"Error extracting Swift comment: {e}")
            return None

    def _extract_operator_declaration(
        self, node: "tree_sitter.Node"
    ) -> Function | None:
        """Extract operator declaration"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract operator name and type (infix, prefix, postfix)
            # Examples: "infix operator **: MultiplicationPrecedence"
            match = re.search(r"(infix|prefix|postfix)\s+operator\s+([^\s:]+)", raw_text)
            if match:
                op_type = match.group(1)
                op_name = match.group(2)
                name = f"{op_type} operator {op_name}"
            else:
                name = "operator"

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                parameters=[],
                return_type="",
                visibility="internal",
                docstring=None,
                is_public=False,
            )
        except Exception as e:
            log_error(f"Error extracting Swift operator declaration: {e}")
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

            # Extract modifiers (public, private, static, class, etc.)
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Parameters
            parameters = self._extract_parameters(node)

            # Return type
            return_type = self._extract_return_type(node)

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            func = Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                docstring=docstring,
                is_public=visibility == "public",
            )

            # Attach Swift-specific attributes
            if "static" in modifiers or "class" in modifiers:
                func.is_static = True
            if "async" in raw_text:
                func.is_async = True

            return func
        except Exception as e:
            log_error(f"Error extracting Swift function: {e}")
            return None

    def _extract_init(self, node: "tree_sitter.Node") -> Function | None:
        """Extract initializer declaration"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract modifiers
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Parameters
            parameters = self._extract_parameters(node)

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            # Determine init type (convenience, required, failable)
            name = "init"
            if "convenience" in modifiers:
                name = "convenience init"
            if "required" in modifiers:
                name = "required init"
            if "init?" in raw_text:
                name = "init?"
            elif "init!" in raw_text:
                name = "init!"

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                parameters=parameters,
                return_type="",
                visibility=visibility,
                docstring=docstring,
                is_public=visibility == "public",
            )
        except Exception as e:
            log_error(f"Error extracting Swift init: {e}")
            return None

    def _extract_deinit(self, node: "tree_sitter.Node") -> Function | None:
        """Extract deinitializer declaration"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            return Function(
                name="deinit",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                parameters=[],
                return_type="",
                visibility="internal",
                docstring=docstring,
                is_public=False,
            )
        except Exception as e:
            log_error(f"Error extracting Swift deinit: {e}")
            return None

    def _extract_class(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class, struct, enum, or actor declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node)
            if not name:
                return None

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract modifiers
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Determine class type
            class_type = "class"
            if "final" in modifiers:
                class_type = "final_class"

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            # Extract inheritance (protocols, superclass)
            interfaces = self._extract_inheritance(node)

            return Class(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                class_type=class_type,
                visibility=visibility,
                docstring=docstring,
                interfaces=interfaces,
            )
        except Exception as e:
            log_error(f"Error extracting Swift class: {e}")
            return None

    def _extract_protocol(self, node: "tree_sitter.Node") -> Class | None:
        """Extract protocol declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None

            name = self._get_node_text(name_node)
            if not name:
                return None

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract modifiers
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            # Extract protocol inheritance
            interfaces = self._extract_inheritance(node)

            return Class(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                class_type="protocol",
                visibility=visibility,
                docstring=docstring,
                interfaces=interfaces,
            )
        except Exception as e:
            log_error(f"Error extracting Swift protocol: {e}")
            return None

    def _extract_property(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract property declaration"""
        try:
            # Find pattern_binding to get property name
            name = None
            for child in node.children:
                if child.type == "modifiers":
                    continue
                # Look for pattern in the property_declaration
                for subchild in child.children if hasattr(child, "children") else []:
                    if subchild.type == "pattern":
                        name = self._get_node_text(subchild)
                        break
                if name:
                    break

            if not name:
                # Try to extract from raw text
                raw_text = self._get_node_text(node)
                match = re.search(r"(?:var|let)\s+(\w+)", raw_text)
                name = match.group(1) if match else "unknown"

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract modifiers
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            # Extract type annotation
            var_type = self._extract_type_annotation(node)

            raw_text = self._get_node_text(node)

            # Determine if constant (let) or variable (var)
            is_constant = raw_text.strip().startswith("let")

            var = Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                variable_type=var_type,
                visibility=visibility,
                is_constant=is_constant,
            )

            # Attach Swift-specific attributes
            if "static" in modifiers or "class" in modifiers:
                var.is_static = True

            return var
        except Exception as e:
            log_error(f"Error extracting Swift property: {e}")
            return None

    def _extract_computed_property(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract computed property"""
        try:
            # For computed properties, extract similar to regular properties
            name = None
            for child in node.children:
                if child.type == "pattern":
                    name = self._get_node_text(child)
                    break

            if not name:
                raw_text = self._get_node_text(node)
                match = re.search(r"var\s+(\w+)", raw_text)
                name = match.group(1) if match else "computed"

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract type annotation
            var_type = self._extract_type_annotation(node)

            raw_text = self._get_node_text(node)

            # Extract modifiers from parent or raw text
            modifiers: list[str] = []
            visibility = self._determine_visibility(modifiers)

            return Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                variable_type=var_type,
                visibility=visibility,
                is_constant=False,
            )
        except Exception as e:
            log_error(f"Error extracting Swift computed property: {e}")
            return None

    def _extract_typealias(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract typealias declaration"""
        try:
            name_node = node.child_by_field_name("name")
            if not name_node:
                # Try to extract from raw text
                raw_text = self._get_node_text(node)
                match = re.search(r"typealias\s+(\w+)", raw_text)
                name = match.group(1) if match else "unknown"
            else:
                name = self._get_node_text(name_node)

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract the type it aliases to
            var_type = ""
            type_node = node.child_by_field_name("type")
            if type_node:
                var_type = self._get_node_text(type_node)

            raw_text = self._get_node_text(node)

            # Extract modifiers
            modifiers = self._extract_modifiers(node)
            visibility = self._determine_visibility(modifiers)

            return Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="swift",
                variable_type=var_type,
                visibility=visibility,
                is_constant=True,
            )
        except Exception as e:
            log_error(f"Error extracting Swift typealias: {e}")
            return None

    def _extract_modifiers(self, node: "tree_sitter.Node") -> list[str]:
        """Extract modifiers from a node"""
        modifiers: list[str] = []
        for child in node.children:
            if child.type == "modifiers":
                mod_text = self._get_node_text(child)
                # Split by whitespace to get individual modifiers
                modifiers.extend(mod_text.split())
                break
        return modifiers

    def _determine_visibility(self, modifiers: list[str]) -> str:
        """Determine visibility from modifiers"""
        if "public" in modifiers or "open" in modifiers:
            return "public"
        if "private" in modifiers:
            return "private"
        if "fileprivate" in modifiers:
            return "fileprivate"
        return "internal"  # Default in Swift

    def _extract_parameters(self, node: "tree_sitter.Node") -> list[str]:
        """Extract function/method parameters"""
        parameters = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter":
                    param_text = self._get_node_text(child)
                    parameters.append(param_text)
        return parameters

    def _extract_return_type(self, node: "tree_sitter.Node") -> str:
        """Extract function/method return type"""
        # Look for return type after ->
        raw_text = self._get_node_text(node)
        match = re.search(r"->\s*([^{]+)", raw_text)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_type_annotation(self, node: "tree_sitter.Node") -> str:
        """Extract type annotation from property"""
        type_node = node.child_by_field_name("type")
        if type_node:
            return self._get_node_text(type_node)

        # Try to extract from raw text
        raw_text = self._get_node_text(node)
        match = re.search(r":\s*([^=\{]+)", raw_text)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_inheritance(self, node: "tree_sitter.Node") -> list[str]:
        """Extract inheritance/conformance list"""
        interfaces: list[str] = []
        for child in node.children:
            if child.type == "type_inheritance_clause":
                # Extract all types in the inheritance clause
                for type_child in child.children:
                    if type_child.type == "user_type" or "type" in type_child.type:
                        type_text = self._get_node_text(type_child)
                        if type_text and type_text not in [":", ","]:
                            interfaces.append(type_text)
        return interfaces

    def _extract_docstring(self, node: "tree_sitter.Node") -> str | None:
        """Extract doc comments preceding the node"""
        # In Swift, doc comments are /// or /** */ immediately before the declaration
        start_line = node.start_point[0]
        if start_line == 0:
            return None

        docs: list[str] = []
        line_idx = start_line - 1

        # Ensure line_idx is within valid range
        if line_idx >= len(self.content_lines):
            line_idx = len(self.content_lines) - 1

        in_block_comment = False
        while line_idx >= 0:
            line = self.content_lines[line_idx].strip()

            # Handle /** */ block comments
            if line.endswith("*/") and "/**" in line:
                # Single-line block comment
                comment_text = line[line.index("/**") + 3 : line.rindex("*/")].strip()
                if comment_text:
                    docs.insert(0, comment_text)
                line_idx -= 1
            elif line.endswith("*/"):
                in_block_comment = True
                comment_text = line[: line.rindex("*/")].strip()
                if comment_text:
                    docs.insert(0, comment_text)
                line_idx -= 1
            elif in_block_comment:
                if "/**" in line:
                    in_block_comment = False
                    comment_text = line[line.index("/**") + 3 :].strip()
                    if comment_text:
                        docs.insert(0, comment_text)
                    line_idx -= 1
                else:
                    # Remove leading * if present
                    comment_text = line.lstrip("*").strip()
                    if comment_text:
                        docs.insert(0, comment_text)
                    line_idx -= 1
            elif line.startswith("///"):
                docs.insert(0, line[3:].strip())
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


class SwiftPlugin(LanguagePlugin):
    """Swift language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Swift language plugin."""
        super().__init__()
        self.extractor = SwiftElementExtractor()
        self.language = "swift"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "swift"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".swift"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return SwiftElementExtractor()

    def get_supported_element_types(self) -> list[str]:
        """Get supported element types for Swift."""
        return [
            "import",
            "function",
            "class",
            "struct",
            "protocol",
            "enum",
            "actor",
            "property",
            "computed_property",
            "init",
            "deinit",
            "subscript",
            "typealias",
        ]

    def get_queries(self) -> dict[str, str]:
        """Get Swift-specific tree-sitter queries."""
        # Swift queries would be defined in queries/swift.py
        # For now, return empty dict
        return {}

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze Swift code and return structured results."""
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="swift",
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
            all_elements.extend(elements_dict.get("imports", []))
            all_elements.extend(elements_dict.get("functions", []))
            all_elements.extend(elements_dict.get("classes", []))
            all_elements.extend(elements_dict.get("variables", []))
            all_elements.extend(elements_dict.get("comments", []))
            all_elements.extend(elements_dict.get("operators", []))

            # Count nodes
            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            result = AnalysisResult(
                file_path=file_path,
                language="swift",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )

            return result

        except Exception as e:
            log_error(f"Error analyzing Swift file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="swift",
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
        """Get the tree-sitter language for Swift."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_swift

            caps_or_lang = tree_sitter_swift.language()

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
            log_error(f"tree-sitter-swift not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Swift: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements from Swift source code."""
        if tree is None:
            return {
                "imports": [],
                "functions": [],
                "classes": [],
                "variables": [],
                "comments": [],
                "operators": [],
            }

        try:
            extractor = self.create_extractor()

            result = {
                "imports": extractor.extract_imports(tree, source_code),
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "comments": extractor.extract_comments(tree, source_code),  # type: ignore[attr-defined]
                "operators": extractor.extract_operators(tree, source_code),  # type: ignore[attr-defined]
            }

            return result

        except Exception as e:
            log_error(f"Error extracting Swift elements: {e}")
            return {
                "imports": [],
                "functions": [],
                "classes": [],
                "variables": [],
                "comments": [],
                "operators": [],
            }

    def supports_file(self, file_path: str) -> bool:
        """Check if this plugin supports the given file."""
        return any(
            file_path.lower().endswith(ext) for ext in self.get_file_extensions()
        )
