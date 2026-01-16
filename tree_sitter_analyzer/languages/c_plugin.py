#!/usr/bin/env python3
"""
C Language Plugin

Provides C specific parsing and element extraction functionality.
Supports standard C constructs including functions, structs, unions,
enums, and preprocessor directives.
"""

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..plugins.programming_language_extractor import ProgrammingLanguageExtractor
from ..utils import log_debug, log_error


class CElementExtractor(ProgrammingLanguageExtractor):
    """C specific element extractor with advanced analysis support"""

    def __init__(self) -> None:
        """Initialize the C element extractor."""
        super().__init__()
        self.current_file: str = ""
        self.includes: list[str] = []

        # C-specific caches (in addition to inherited base caches)
        self._comment_cache: dict[int, str] = {}
        self._complexity_cache: dict[int, int] = {}

    def _get_function_handlers(self) -> dict[str, Any]:
        """Get function node type handlers for C."""
        return {
            "function_definition": self._extract_function_optimized,
            "preproc_function_def": self._extract_macro_function,
        }

    def _get_class_handlers(self) -> dict[str, Any]:
        """Get class node type handlers for C (struct/union/enum)."""
        return {
            "struct_specifier": self._extract_struct_optimized,
            "union_specifier": self._extract_union_optimized,
            "enum_specifier": self._extract_enum_optimized,
        }

    # extract_functions() and extract_classes() are inherited from base class
    # Base class implementation uses _get_function_handlers() and _get_class_handlers()

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract C variable/field declarations"""
        self._initialize_source(source_code)

        variables: list[Variable] = []

        # Extract field and variable declarations
        extractors = {
            "field_declaration": self._extract_field_optimized,
            "declaration": self._extract_variable_declaration,
            "preproc_def": self._extract_macro_definition,
        }

        self._traverse_and_extract_iterative(
            tree.root_node, extractors, variables, "variable"
        )

        log_debug(f"Extracted {len(variables)} C variables/fields")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract C include directives"""
        self._initialize_source(source_code)

        imports: list[Import] = []

        # Extract preprocessor includes
        for child in tree.root_node.children:
            if child.type == "preproc_include":
                import_info = self._extract_include_info(child, source_code)
                if import_info:
                    imports.append(import_info)

        # Fallback: use regex if tree-sitter doesn't catch all includes
        if not imports and "#include" in source_code:
            log_debug("No includes found via tree-sitter, trying regex fallback")
            fallback_imports = self._extract_includes_fallback(source_code)
            imports.extend(fallback_imports)

        log_debug(f"Extracted {len(imports)} C includes")
        return imports

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        super()._reset_caches()
        self._comment_cache.clear()
        self._complexity_cache.clear()

    def _get_container_node_types(self) -> set[str]:
        """Get C-specific container node types for traversal."""
        return super()._get_container_node_types() | {
            "translation_unit",
            "compound_statement",
            "struct_specifier",
            "union_specifier",
            "field_declaration_list",
            "declaration_list",
            "type_definition",  # For typedef structs
        }

    def _extract_function_optimized(self, node: "tree_sitter.Node") -> Function | None:
        """Extract function information optimized"""
        try:
            # Use base class method to extract common metadata
            metadata = self._extract_common_metadata(node)

            # Extract function details
            function_info = self._parse_function_signature(node)
            if not function_info:
                return None

            name, return_type, parameters, modifiers = function_info

            return Function(
                name=name,
                start_line=metadata["start_line"],
                end_line=metadata["end_line"],
                raw_text=metadata["raw_text"],
                language="c",
                parameters=parameters,
                return_type=return_type or "int",
                modifiers=modifiers,
                is_static="static" in modifiers,
                visibility="public",  # C functions are effectively public
                docstring=metadata["docstring"],
                complexity_score=metadata["complexity"],
            )
        except (AttributeError, ValueError, TypeError) as e:
            log_debug(f"Failed to extract function info: {e}")
            return None
        except Exception as e:
            log_error(f"Unexpected error in function extraction: {e}")
            return None

    def _parse_function_signature(
        self, node: "tree_sitter.Node"
    ) -> tuple[str, str, list[str], list[str]] | None:
        """Parse C function signature"""
        try:
            name = None
            return_type = "int"
            parameters: list[str] = []
            modifiers: list[str] = []

            def find_function_declarator(n: "tree_sitter.Node") -> None:
                """Recursively find function_declarator in pointer_declarator"""
                nonlocal name, parameters
                for child in n.children:
                    if child.type == "function_declarator":
                        for grandchild in child.children:
                            if grandchild.type == "identifier":
                                name = self._get_node_text_optimized(grandchild)
                            elif grandchild.type == "parameter_list":
                                parameters = self._extract_parameters(grandchild)
                    elif child.type == "pointer_declarator":
                        find_function_declarator(child)

            for child in node.children:
                if child.type == "function_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            name = self._get_node_text_optimized(grandchild)
                        elif grandchild.type == "parameter_list":
                            parameters = self._extract_parameters(grandchild)
                elif child.type == "pointer_declarator":
                    # Handle pointer return types (e.g., int* func())
                    find_function_declarator(child)
                    # Mark return type as pointer
                    if return_type and "*" not in return_type:
                        return_type = return_type + "*"
                elif child.type in [
                    "primitive_type",
                    "type_identifier",
                    "sized_type_specifier",
                ]:
                    return_type = self._get_node_text_optimized(child)
                elif child.type == "storage_class_specifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "type_qualifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)

            if not name:
                return None

            return name, return_type, parameters, modifiers
        except Exception:
            return None

    def _extract_parameters(self, params_node: "tree_sitter.Node") -> list[str]:
        """Extract function parameters"""
        parameters: list[str] = []

        for child in params_node.children:
            if child.type == "parameter_declaration":
                param_text = self._get_node_text_optimized(child)
                parameters.append(param_text)
            elif child.type == "variadic_parameter":
                parameters.append("...")

        return parameters

    def _extract_struct_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract struct information optimized"""
        try:
            # Determine the actual node to use for metadata extraction
            actual_node = node
            if node.parent and node.parent.type == "type_definition":
                # Use typedef node for position if it's a typedef struct
                actual_node = node.parent

            # Use base class method to extract common metadata
            metadata = self._extract_common_metadata(actual_node)

            struct_name = None

            # Look for name in struct_specifier children first (named struct)
            for child in node.children:
                if child.type == "type_identifier":
                    struct_name = self._get_node_text_optimized(child)

            # If anonymous, check if parent is type_definition for typedef name
            if (
                not struct_name
                and node.parent
                and node.parent.type == "type_definition"
            ):
                for sibling in node.parent.children:
                    if sibling.type == "type_identifier":
                        struct_name = self._get_node_text_optimized(sibling)
                        break

            if not struct_name:
                # Truly anonymous struct
                struct_name = f"anonymous_struct_{metadata['start_line']}"

            return Class(
                name=struct_name,
                start_line=metadata["start_line"],
                end_line=metadata["end_line"],
                raw_text=metadata["raw_text"],
                language="c",
                class_type="struct",
                full_qualified_name=struct_name,
                docstring=metadata["docstring"],
            )
        except Exception as e:
            log_debug(f"Failed to extract struct info: {e}")
            return None

    def _extract_union_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract union information optimized"""
        try:
            result = self._extract_struct_optimized(node)
            if result:
                result.class_type = "union"
                if result.name.startswith("anonymous_struct_"):
                    result.name = result.name.replace(
                        "anonymous_struct_", "anonymous_union_"
                    )
                    result.full_qualified_name = result.name
            return result
        except Exception as e:
            log_debug(f"Failed to extract union info: {e}")
            return None

    def _extract_enum_optimized(self, node: "tree_sitter.Node") -> Class | None:
        """Extract enum information optimized"""
        try:
            # Determine the actual node to use for metadata extraction
            actual_node = node
            if node.parent and node.parent.type == "type_definition":
                # Use typedef node for position if it's a typedef enum
                actual_node = node.parent

            # Use base class method to extract common metadata
            metadata = self._extract_common_metadata(actual_node)

            enum_name = None

            # Look for name in enum_specifier children first (named enum)
            for child in node.children:
                if child.type == "type_identifier":
                    enum_name = self._get_node_text_optimized(child)

            # If anonymous, check if parent is type_definition for typedef name
            if not enum_name and node.parent and node.parent.type == "type_definition":
                for sibling in node.parent.children:
                    if sibling.type == "type_identifier":
                        enum_name = self._get_node_text_optimized(sibling)
                        break

            if not enum_name:
                # Truly anonymous enum
                enum_name = f"anonymous_enum_{metadata['start_line']}"

            return Class(
                name=enum_name,
                start_line=metadata["start_line"],
                end_line=metadata["end_line"],
                raw_text=metadata["raw_text"],
                language="c",
                class_type="enum",
                full_qualified_name=enum_name,
                docstring=metadata["docstring"],
            )
        except Exception as e:
            log_debug(f"Failed to extract enum info: {e}")
            return None

    def _extract_field_optimized(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract field declaration"""
        fields: list[Variable] = []

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            field_type = None
            field_names: list[str] = []
            modifiers: list[str] = []

            for child in node.children:
                if child.type in [
                    "primitive_type",
                    "type_identifier",
                    "sized_type_specifier",
                    "struct_specifier",
                    "union_specifier",
                    "enum_specifier",
                ]:
                    field_type = self._get_node_text_optimized(child)
                elif child.type == "type_qualifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "field_identifier":
                    field_names.append(self._get_node_text_optimized(child))
                elif child.type == "array_declarator":
                    # Handle array fields (e.g. char name[50])
                    for grandchild in child.children:
                        if grandchild.type == "field_identifier":
                            field_names.append(
                                self._get_node_text_optimized(grandchild)
                            )
                    # Append [] to type to indicate array
                    field_type = field_type + "[]" if field_type else "[]"
                elif child.type == "field_declaration_list":
                    # Nested struct/union, skip
                    pass
                elif child.type == "init_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "field_identifier":
                            field_names.append(
                                self._get_node_text_optimized(grandchild)
                            )
                        elif grandchild.type == "identifier":
                            field_names.append(
                                self._get_node_text_optimized(grandchild)
                            )
                elif child.type == "pointer_declarator":
                    # Handle pointer fields
                    for grandchild in child.children:
                        if grandchild.type == "field_identifier":
                            field_names.append(
                                self._get_node_text_optimized(grandchild)
                            )
                            field_type = field_type + "*" if field_type else "*"

            if not field_type or not field_names:
                return fields

            raw_text = self._get_node_text_optimized(node)

            # In C, struct/union fields are always public (no access control)
            visibility = "public"

            for field_name in field_names:
                field = Variable(
                    name=field_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="c",
                    variable_type=field_type,
                    modifiers=modifiers,
                    is_constant="const" in modifiers,
                    visibility=visibility,
                )
                fields.append(field)

        except Exception as e:
            log_debug(f"Failed to extract field info: {e}")

        return fields

    def _extract_variable_declaration(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract variable declarations (not struct members)"""
        # Skip if parent is a struct/union body
        if node.parent and node.parent.type == "field_declaration_list":
            return []

        variables: list[Variable] = []

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            var_type = None
            var_names: list[str] = []
            modifiers: list[str] = []

            for child in node.children:
                if child.type in [
                    "primitive_type",
                    "type_identifier",
                    "sized_type_specifier",
                    "struct_specifier",
                    "union_specifier",
                    "enum_specifier",
                ]:
                    var_type = self._get_node_text_optimized(child)
                elif child.type == "storage_class_specifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "type_qualifier":
                    mod = self._get_node_text_optimized(child)
                    if mod:
                        modifiers.append(mod)
                elif child.type == "identifier":
                    var_names.append(self._get_node_text_optimized(child))
                elif child.type == "init_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            var_names.append(self._get_node_text_optimized(grandchild))
                elif child.type == "pointer_declarator":
                    # Handle pointer declarations
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            var_names.append(self._get_node_text_optimized(grandchild))
                            var_type = var_type + "*" if var_type else "*"

            if not var_type or not var_names:
                return variables

            raw_text = self._get_node_text_optimized(node)

            # C global variables visibility:
            # - static = private (internal linkage)
            # - non-static = public (external linkage)
            visibility = "private" if "static" in modifiers else "public"

            for var_name in var_names:
                variable = Variable(
                    name=var_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="c",
                    variable_type=var_type,
                    modifiers=modifiers,
                    is_static="static" in modifiers,
                    is_constant="const" in modifiers,
                    visibility=visibility,
                )
                variables.append(variable)

        except Exception as e:
            log_debug(f"Failed to extract variable declaration: {e}")

        return variables

    def _extract_include_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        """Extract include directive information"""
        try:
            include_text = self._get_node_text_optimized(node)
            line_num = node.start_point[0] + 1

            # Determine if it's a system include (<...>) or local include ("...")
            is_system = "<" in include_text

            # Extract the included file path
            if is_system:
                match = re.search(r"<([^>]+)>", include_text)
            else:
                match = re.search(r'"([^"]+)"', include_text)

            if match:
                include_path = match.group(1)

                return Import(
                    name=include_path,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=include_text,
                    language="c",
                    module_name=include_path,
                    import_statement=include_text,
                )

        except Exception as e:
            log_debug(f"Failed to extract include info: {e}")

        return None

    def _extract_includes_fallback(self, source_code: str) -> list[Import]:
        """Fallback include extraction using regex"""
        imports: list[Import] = []
        lines = source_code.split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if line.startswith("#include"):
                # System include
                system_match = re.search(r"#include\s*<([^>]+)>", line)
                if system_match:
                    include_path = system_match.group(1)
                    imports.append(
                        Import(
                            name=include_path,
                            start_line=line_num,
                            end_line=line_num,
                            raw_text=line,
                            language="c",
                            module_name=include_path,
                            import_statement=line,
                        )
                    )
                else:
                    # Local include
                    local_match = re.search(r'#include\s*"([^"]+)"', line)
                    if local_match:
                        include_path = local_match.group(1)
                        imports.append(
                            Import(
                                name=include_path,
                                start_line=line_num,
                                end_line=line_num,
                                raw_text=line,
                                language="c",
                                module_name=include_path,
                                import_statement=line,
                            )
                        )

        return imports

    def _extract_macro_definition(self, node: "tree_sitter.Node") -> list[Variable]:
        """Extract macro definitions as constants"""
        variables: list[Variable] = []
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            name = None

            for child in node.children:
                if child.type == "identifier":
                    name = self._get_node_text_optimized(child)
                    break

            if name:
                raw_text = self._get_node_text_optimized(node)
                var = Variable(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="c",
                    variable_type="macro",
                    modifiers=["const", "macro"],
                    is_constant=True,
                    visibility="public",
                )
                variables.append(var)
        except Exception as e:
            log_debug(f"Failed to extract macro: {e}")

        return variables

    def _extract_macro_function(self, node: "tree_sitter.Node") -> Function | None:
        """Extract macro function definition"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            name = None
            params: list[str] = []

            for child in node.children:
                if child.type == "identifier":
                    name = self._get_node_text_optimized(child)
                elif child.type == "preproc_params":
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            params.append(self._get_node_text_optimized(grandchild))
                        elif grandchild.type == "variadic_parameter":  # Handle ...
                            params.append("...")

            if name:
                return Function(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=self._get_node_text_optimized(node),
                    language="c",
                    parameters=params,
                    return_type="macro",
                    modifiers=["macro"],
                    visibility="public",
                    complexity_score=1,
                )
        except Exception as e:
            log_debug(f"Failed to extract macro function: {e}")
            return None
        return None

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1  # Base complexity

        decision_nodes = [
            "if_statement",
            "while_statement",
            "for_statement",
            "switch_statement",
            "case_statement",
            "conditional_expression",
            "do_statement",
        ]

        def count_decisions(n: "tree_sitter.Node") -> int:
            count = 0
            if hasattr(n, "type") and n.type in decision_nodes:
                count += 1
            if hasattr(n, "children"):
                try:
                    for child in n.children:
                        count += count_decisions(child)
                except (TypeError, AttributeError):
                    pass
            return count

        complexity += count_decisions(node)
        return complexity

    def _extract_docstring_for_node(self, node: "tree_sitter.Node") -> str | None:
        """Extract docstring/comment for a C node (override base class)."""
        start_line = node.start_point[0] + 1
        return self._extract_comment_for_line(start_line)

    def _extract_comment_for_line(self, line: int) -> str | None:
        """Extract comment (documentation) for a specific line"""
        try:
            # Look for comment immediately before the line
            for i in range(max(0, line - 5), line):
                if i < len(self.content_lines):
                    line_content = self.content_lines[i].strip()
                    # Check for Doxygen-style comments
                    if line_content.startswith("/**"):
                        comment_lines = []
                        for j in range(i, min(len(self.content_lines), line)):
                            doc_line = self.content_lines[j].strip()
                            comment_lines.append(doc_line)
                            if doc_line.endswith("*/"):
                                break
                        return "\n".join(comment_lines)
                    # Check for /* ... */ style comments
                    elif line_content.startswith("/*"):
                        comment_lines = []
                        for j in range(i, min(len(self.content_lines), line)):
                            doc_line = self.content_lines[j].strip()
                            comment_lines.append(doc_line)
                            if doc_line.endswith("*/"):
                                break
                        return "\n".join(comment_lines)

        except Exception as e:
            log_debug(f"Failed to extract comment: {e}")

        return None


class CPlugin(LanguagePlugin):
    """C language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the C language plugin."""
        super().__init__()
        self.extractor = CElementExtractor()
        self.language = "c"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "c"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".c", ".h"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return CElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze C code and return structured results."""
        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="c",
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
                        language="c",
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

            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            return AnalysisResult(
                file_path=file_path,
                language="c",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
            )

        except Exception as e:
            log_error(f"Error analyzing C file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="c",
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
        """Get the tree-sitter language for C."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_c

            caps_or_lang = tree_sitter_c.language()

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
            log_error(f"tree-sitter-c not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for C: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements from C code."""
        if tree is None:
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
            }

        try:
            extractor = self.create_extractor()
            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
            }
        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
            }
