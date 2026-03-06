#!/usr/bin/env python3
"""
Kotlin Language Plugin

Provides Kotlin-specific parsing and element extraction functionality.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


class KotlinElementExtractor(ElementExtractor):
    """Kotlin-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Kotlin element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Kotlin function declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        self._traverse_and_extract(
            tree.root_node,
            {"function_declaration": self._extract_function},
            functions,
        )

        log_debug(f"Extracted {len(functions)} Kotlin functions")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract Kotlin class declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        # Extract package
        self._extract_package(tree.root_node)

        classes: list[Class] = []

        extractors = {
            "class_declaration": self._extract_class,
            "object_declaration": self._extract_object,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            classes,
        )

        log_debug(f"Extracted {len(classes)} Kotlin classes")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract Kotlin properties"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        extractors = {
            "property_declaration": self._extract_property,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            variables,
        )

        log_debug(f"Extracted {len(variables)} Kotlin properties")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Kotlin imports"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        extractors = {
            "import_header": self._extract_import,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            imports,
        )

        log_debug(f"Extracted {len(imports)} Kotlin imports")
        return imports

    def extract_packages(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Package]:
        """Extract Kotlin package"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        packages: list[Package] = []
        self._extract_package(tree.root_node)
        if self.current_package:
            # Find package node if needed for lines, or just create from string
            # We'll try to find the package_header node
            for child in tree.root_node.children:
                if child.type == "package_header":
                    pkg = Package(
                        name=self.current_package,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        raw_text=self._get_node_text(child),
                        language="kotlin",
                    )
                    packages.append(pkg)
                    break

        return packages

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        # Keep current_package if already extracted?
        # Usually safe to re-extract or clear.
        if not self.source_code:
            self.current_package = ""

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
                results.append(element)

        for child in node.children:
            self._traverse_and_extract(child, extractors, results)

    def _extract_package(self, node: "tree_sitter.Node") -> None:
        """Extract package declaration"""
        # Find package_header at top level usually
        for child in node.children:
            if child.type == "package_header":
                # Check children for identifier
                # package_header -> (package) (identifier)
                for grandchild in child.children:
                    if (
                        grandchild.type == "identifier"
                        or grandchild.type == "simple_identifier"
                    ):
                        self.current_package = self._get_node_text(grandchild)
                        return
                    # Or maybe deeper if qualified name
                    if "identifier" in grandchild.type:
                        self.current_package = self._get_node_text(grandchild)
                        return

    def _extract_function(self, node: "tree_sitter.Node") -> Function | None:
        """Extract function information"""
        try:
            # name: simple_identifier
            name = "anonymous"
            # Try getting by field name first
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node)
            else:
                # Fallback to simple_identifier search
                for child in node.children:
                    if child.type == "simple_identifier":
                        name = self._get_node_text(child)
                        break

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Parameters
            parameters = []
            params_node = node.child_by_field_name(
                "parameters"
            )  # function_value_parameters
            if params_node:
                for child in params_node.children:
                    if child.type == "parameter":
                        # parameter -> simple_identifier: type
                        param_name = ""
                        param_type = ""
                        for grandchild in child.children:
                            if grandchild.type == "simple_identifier":
                                param_name = self._get_node_text(grandchild)
                            elif (
                                "type" in grandchild.type
                                or grandchild.type == "user_type"
                            ):
                                param_type = self._get_node_text(grandchild)

                        if param_name:
                            parameters.append(f"{param_name}: {param_type or 'Any'}")

            # Return type
            return_type = "Unit"
            # search for return type, usually after :
            # function_declaration -> ... (type)? ...
            # Hard to find specific field without query, iterating children
            # If we find a colon, next child might be type?
            # Tree-sitter-kotlin structure: function_declaration can have children: modifiers, fun, simple_identifier, function_value_parameters, type (return type), function_body

            for i, child in enumerate(node.children):
                if child.type == ":":
                    # Next sibling should be return type
                    if i + 1 < len(node.children):
                        return_type = self._get_node_text(node.children[i + 1])
                    break

            # Visibility and modifiers
            visibility = "public"
            is_suspend = False
            modifiers_node = node.child_by_field_name("modifiers")
            if modifiers_node:
                mods = self._get_node_text(modifiers_node)
                if "private" in mods:
                    visibility = "private"
                elif "protected" in mods:
                    visibility = "protected"
                elif "internal" in mods:
                    visibility = "internal"

                if "suspend" in mods:
                    is_suspend = True

            # Docstring
            docstring = self._extract_docstring(node)

            raw_text = self._get_node_text(node)

            func = Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="kotlin",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                docstring=docstring,
            )
            func.is_suspend = is_suspend
            return func

        except Exception as e:
            log_error(f"Error extracting Kotlin function: {e}")
            return None

    def _extract_class(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class declaration"""
        return self._extract_class_or_object(node, "class")

    def _extract_object(self, node: "tree_sitter.Node") -> Class | None:
        """Extract object declaration"""
        return self._extract_class_or_object(node, "object")

    def _extract_class_or_object(
        self, node: "tree_sitter.Node", kind: str
    ) -> Class | None:
        """Generic extraction for class/object/interface"""
        try:
            name = "anonymous"
            # Try getting by field name first
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node)
            else:
                for child in node.children:
                    if child.type == "simple_identifier":
                        name = self._get_node_text(child)
                        break

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            visibility = "public"
            modifiers_node = node.child_by_field_name("modifiers")
            if modifiers_node:
                mods = self._get_node_text(modifiers_node)
                if "private" in mods:
                    visibility = "private"
                elif "protected" in mods:
                    visibility = "protected"
                elif "internal" in mods:
                    visibility = "internal"

            # Detect interface by checking for 'interface' keyword child node
            # tree-sitter-kotlin parses both class and interface as class_declaration
            # but includes 'interface' or 'class' keyword as a child node
            if kind == "class":
                for child in node.children:
                    if child.type == "interface":
                        kind = "interface"
                        break
                    elif child.type == "class":
                        # Explicitly a class, not interface
                        break

            raw_text = self._get_node_text(node)

            return Class(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="kotlin",
                class_type=kind,
                visibility=visibility,
                package_name=self.current_package,
            )

        except Exception as e:
            log_error(f"Error extracting Kotlin class: {e}")
            return None

    def _extract_property(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract property declaration"""
        try:
            # var declaration or val declaration
            is_val = False
            is_var = False
            text = self._get_node_text(node)
            if text.startswith("val "):
                is_val = True
            elif text.startswith("var "):
                is_var = True

            # variable_declaration -> (modifiers)? (val/var) ...
            # Need to find name
            name = "unknown"

            # Try getting by field name 'name' directly on property_declaration (might work in newer grammars)
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node)
            else:
                # Fallback: Iterate children
                for child in node.children:
                    if child.type == "variable_declaration":
                        for grandchild in child.children:
                            if grandchild.type == "simple_identifier":
                                name = self._get_node_text(grandchild)
                                break
                    elif child.type == "simple_identifier":
                        name = self._get_node_text(child)
                        break

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Type?
            prop_type = "Inferred"
            # Look for : type

            visibility = "public"
            modifiers_node = node.child_by_field_name("modifiers")
            if modifiers_node:
                mods = self._get_node_text(modifiers_node)
                if "private" in mods:
                    visibility = "private"

            docstring = self._extract_docstring(node)
            raw_text = self._get_node_text(node)

            var = Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="kotlin",
                variable_type=prop_type,
                visibility=visibility,
                docstring=docstring,
            )
            var.is_val = is_val
            var.is_var = is_var

            return var

        except Exception as e:
            log_error(f"Error extracting Kotlin property: {e}")
            return None

    def _extract_import(self, node: "tree_sitter.Node") -> Import | None:
        """Extract import header"""
        try:
            # import_header -> 'import' identifier .*
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Parse name
            parts = raw_text.split()
            if len(parts) > 1:
                name = parts[1]
            else:
                name = "unknown"

            return Import(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="kotlin",
                import_statement=raw_text,
            )
        except Exception as e:
            log_error(f"Error extracting Kotlin import: {e}")
            return None

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

    def _extract_docstring(self, node: "tree_sitter.Node") -> str | None:
        """Extract KDoc"""
        # Similar to Rust/Java logic
        return None


class KotlinPlugin(LanguagePlugin):
    """Kotlin language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Kotlin language plugin."""
        super().__init__()
        self.extractor = KotlinElementExtractor()
        self.language = "kotlin"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "kotlin"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".kt", ".kts"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return KotlinElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze Kotlin code and return structured results."""

        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="kotlin",
                    line_count=len(file_content.split("\n")),
                    elements=[],
                    source_code=file_content,
                )

            import tree_sitter

            parser = tree_sitter.Parser()

            # Set language
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
            all_elements.extend(elements_dict.get("functions", []))
            all_elements.extend(elements_dict.get("classes", []))
            all_elements.extend(elements_dict.get("variables", []))
            all_elements.extend(elements_dict.get("imports", []))
            all_elements.extend(elements_dict.get("packages", []))

            node_count = (
                self._count_tree_nodes(tree.root_node) if tree and tree.root_node else 0
            )

            # Get package
            package = (
                elements_dict.get("packages", [])[0]
                if elements_dict.get("packages")
                else None
            )

            return AnalysisResult(
                file_path=file_path,
                language="kotlin",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
                package=package,
            )

        except Exception as e:
            log_error(f"Error analyzing Kotlin file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="kotlin",
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
        """Get the tree-sitter language for Kotlin."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_kotlin

            caps_or_lang = tree_sitter_kotlin.language()

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
            log_error(f"tree-sitter-kotlin not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Kotlin: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements."""
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

    def supports_file(self, file_path: str) -> bool:
        """Check if this plugin supports the given file."""
        return any(
            file_path.lower().endswith(ext) for ext in self.get_file_extensions()
        )
