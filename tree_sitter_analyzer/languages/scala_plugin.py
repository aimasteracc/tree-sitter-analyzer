#!/usr/bin/env python3
"""
Scala Language Plugin

Provides Scala-specific parsing and element extraction functionality.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.request import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Expression, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error


class ScalaElementExtractor(ElementExtractor):
    """Scala-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Scala element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract Scala function definitions and declarations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        functions: list[Function] = []

        extractors = {
            "function_definition": self._extract_function,
            "function_declaration": self._extract_function_declaration,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            functions,
        )

        log_debug(f"Extracted {len(functions)} Scala functions")
        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract Scala class, object, and trait definitions"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        # Extract package first
        self._extract_package(tree.root_node)

        classes: list[Class] = []

        extractors = {
            "class_definition": self._extract_class,
            "object_definition": self._extract_object,
            "trait_definition": self._extract_trait,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            classes,
        )

        log_debug(f"Extracted {len(classes)} Scala classes/objects/traits")
        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract Scala val and var definitions"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []

        extractors = {
            "val_definition": self._extract_val,
            "var_definition": self._extract_var,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            variables,
        )

        log_debug(f"Extracted {len(variables)} Scala val/var definitions")
        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract Scala imports"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        imports: list[Import] = []

        extractors = {
            "import_declaration": self._extract_import,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            imports,
        )

        log_debug(f"Extracted {len(imports)} Scala imports")
        return imports

    def extract_packages(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Package]:
        """Extract Scala package"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        packages: list[Package] = []
        self._extract_package(tree.root_node)
        if self.current_package:
            # Find package_clause node for line information
            for child in tree.root_node.children:
                if child.type == "package_clause":
                    pkg = Package(
                        name=self.current_package,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        raw_text=self._get_node_text(child),
                        language="scala",
                    )
                    packages.append(pkg)
                    break

        return packages

    def extract_comments(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Expression]:
        """Extract Scala block comments"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        comments: list[Expression] = []

        extractors = {
            "block_comment": self._extract_comment,
        }

        self._traverse_and_extract(tree.root_node, extractors, comments)

        log_debug(f"Extracted {len(comments)} Scala comments")
        return comments

    def extract_annotations(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Expression]:
        """Extract Scala annotations"""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        annotations: list[Expression] = []

        extractors = {
            "annotation": self._extract_annotation,
        }

        self._traverse_and_extract(tree.root_node, extractors, annotations)

        log_debug(f"Extracted {len(annotations)} Scala annotations")
        return annotations

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        if not self.source_code:
            self.current_package = ""

    def _traverse_and_extract(
        self,
        node: "tree_sitter.Node",
        extractors: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Iterative traversal to find and extract elements (stack-safe)."""
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in extractors:
                element = extractors[current.type](current)
                if element:
                    results.append(element)
            stack.extend(reversed(current.children))

    def _extract_package(self, node: "tree_sitter.Node") -> None:
        """Extract package declaration from package_clause"""
        for child in node.children:
            if child.type == "package_clause":
                # package_clause -> 'package' qualified_identifier
                for grandchild in child.children:
                    if (
                        grandchild.type == "package_identifier"
                        or grandchild.type == "identifier"
                        or "identifier" in grandchild.type
                    ):
                        self.current_package = self._get_node_text(grandchild)
                        return

    def _extract_function(self, node: "tree_sitter.Node") -> Function | None:
        """Extract function definition (with body)"""
        return self._extract_function_common(node)

    def _extract_function_declaration(self, node: "tree_sitter.Node") -> Function | None:
        """Extract function declaration (abstract, without body)"""
        return self._extract_function_common(node)

    def _extract_function_common(self, node: "tree_sitter.Node") -> Function | None:
        """Common extraction logic for Scala functions"""
        try:
            # Find function name (identifier node)
            name = "anonymous"
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node)
            else:
                # Fallback: search for identifier
                for child in node.children:
                    if child.type == "identifier":
                        name = self._get_node_text(child)
                        break

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract parameters
            parameters = []
            # Look for parameter_clause or parameters
            for child in node.children:
                if "parameter" in child.type:
                    params = self._extract_parameters(child)
                    parameters.extend(params)

            # Extract return type
            return_type = "Unit"
            # Look for type annotation after ':'
            for i, child in enumerate(node.children):
                if child.type == ":":
                    if i + 1 < len(node.children):
                        return_type = self._get_node_text(node.children[i + 1])
                    break

            # Extract visibility and modifiers
            visibility = "public"
            modifiers_text = ""
            for child in node.children:
                if child.type == "modifiers":
                    modifiers_text = self._get_node_text(child)
                    if "private" in modifiers_text:
                        visibility = "private"
                    elif "protected" in modifiers_text:
                        visibility = "protected"
                    break

            # Extract docstring
            docstring = self._extract_docstring(node)
            raw_text = self._get_node_text(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                docstring=docstring,
            )

        except Exception as e:
            log_error(f"Error extracting Scala function: {e}")
            return None

    def _extract_parameters(self, param_node: "tree_sitter.Node") -> list[str]:
        """Extract parameters from a parameter clause"""
        parameters = []
        for child in param_node.children:
            if child.type == "parameter" or child.type == "class_parameter":
                # parameter -> identifier : type
                param_name = ""
                param_type = ""
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        param_name = self._get_node_text(grandchild)
                    elif "type" in grandchild.type or grandchild.type == "type_identifier":
                        param_type = self._get_node_text(grandchild)

                if param_name:
                    parameters.append(f"{param_name}: {param_type or 'Any'}")
            elif child.type == "parameters" or "parameter" in child.type:
                # Recursively extract nested parameters
                parameters.extend(self._extract_parameters(child))

        return parameters

    def _extract_class(self, node: "tree_sitter.Node") -> Class | None:
        """Extract class definition"""
        return self._extract_class_like(node, "class")

    def _extract_object(self, node: "tree_sitter.Node") -> Class | None:
        """Extract object definition (Scala singleton)"""
        return self._extract_class_like(node, "object")

    def _extract_trait(self, node: "tree_sitter.Node") -> Class | None:
        """Extract trait definition (Scala interface/mixin)"""
        return self._extract_class_like(node, "trait")

    def _extract_class_like(
        self, node: "tree_sitter.Node", kind: str
    ) -> Class | None:
        """Generic extraction for class/object/trait"""
        try:
            # Extract name
            name = "anonymous"
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node)
            else:
                for child in node.children:
                    if child.type == "identifier" or child.type == "type_identifier":
                        name = self._get_node_text(child)
                        break

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract visibility
            visibility = "public"
            for child in node.children:
                if child.type == "modifiers":
                    mods = self._get_node_text(child)
                    if "private" in mods:
                        visibility = "private"
                    elif "protected" in mods:
                        visibility = "protected"
                    break

            raw_text = self._get_node_text(node)

            # Extract docstring
            docstring = self._extract_docstring(node)

            return Class(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                class_type=kind,
                visibility=visibility,
                package_name=self.current_package,
                docstring=docstring,
            )

        except Exception as e:
            log_error(f"Error extracting Scala {kind}: {e}")
            return None

    def _extract_val(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract val definition (immutable)"""
        return self._extract_variable(node, is_val=True)

    def _extract_var(self, node: "tree_sitter.Node") -> Variable | None:
        """Extract var definition (mutable)"""
        return self._extract_variable(node, is_val=False)

    def _extract_variable(
        self, node: "tree_sitter.Node", is_val: bool = True
    ) -> Variable | None:
        """Common extraction logic for val/var"""
        try:
            # Extract name from pattern (usually identifier)
            name = "unknown"

            # val/var definition structure: modifiers? (val|var) pattern_list : type? = expression?
            for child in node.children:
                if child.type == "identifier":
                    name = self._get_node_text(child)
                    break
                elif child.type == "pattern_list":
                    # Extract first pattern
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            name = self._get_node_text(grandchild)
                            break
                    if name != "unknown":
                        break

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract type
            var_type = "Inferred"
            for i, child in enumerate(node.children):
                if child.type == ":":
                    if i + 1 < len(node.children):
                        var_type = self._get_node_text(node.children[i + 1])
                    break

            # Extract visibility
            visibility = "public"
            for child in node.children:
                if child.type == "modifiers":
                    mods = self._get_node_text(child)
                    if "private" in mods:
                        visibility = "private"
                    elif "protected" in mods:
                        visibility = "protected"
                    break

            docstring = self._extract_docstring(node)
            raw_text = self._get_node_text(node)

            var = Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                variable_type=var_type,
                visibility=visibility,
                docstring=docstring,
            )
            var.is_val = is_val
            var.is_var = not is_val

            return var

        except Exception as e:
            log_error(f"Error extracting Scala variable: {e}")
            return None

    def _extract_import(self, node: "tree_sitter.Node") -> Import | None:
        """Extract import declaration"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Parse import path
            # import_declaration -> 'import' import_expression
            name = "unknown"
            for child in node.children:
                if child.type != "import":
                    # Take the import expression text
                    name = self._get_node_text(child)
                    break

            return Import(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                import_statement=raw_text,
            )
        except Exception as e:
            log_error(f"Error extracting Scala import: {e}")
            return None

    def _extract_comment(self, node: "tree_sitter.Node") -> Expression | None:
        """Extract Scala block comment"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Get preview (first 50 chars)
            preview = raw_text[:50] if len(raw_text) > 50 else raw_text

            return Expression(
                name="block_comment",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                expression_kind="block_comment",
                preview=preview,
            )
        except Exception as e:
            log_error(f"Error extracting Scala comment: {e}")
            return None

    def _extract_annotation(self, node: "tree_sitter.Node") -> Expression | None:
        """Extract Scala annotation"""
        try:
            raw_text = self._get_node_text(node)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract annotation name from the tree
            # annotation -> @ stable_type_identifier
            annotation_name = "unknown"
            for child in node.children:
                if child.type in (
                    "stable_type_identifier",
                    "type_identifier",
                    "identifier",
                ):
                    annotation_name = self._get_node_text(child)
                    break
                # Handle simple identifier after @
                if child.type == "identifier":
                    annotation_name = self._get_node_text(child)
                    break

            return Expression(
                name=annotation_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                expression_kind="annotation",
                node_type="annotation",
            )
        except Exception as e:
            log_error(f"Error extracting Scala annotation: {e}")
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
        """Extract Scaladoc comments (/** ... */)"""
        # Scala uses /** ... */ for documentation comments
        # Look for block_comment nodes that immediately precede this node
        if not node.parent:
            return None

        # Find the immediately preceding block_comment sibling
        prev_comment = None
        prev_sibling = None

        for sibling in node.parent.children:
            if sibling == node:
                break
            prev_sibling = sibling

        # Check if the previous sibling is a block_comment
        if prev_sibling and prev_sibling.type == "block_comment":
            prev_comment = prev_sibling
        # Also check for block_comment that might be separated by whitespace
        elif prev_sibling and prev_sibling.type != "block_comment":
            # Look for the last block_comment before this node
            for sibling in node.parent.children:
                if sibling == node:
                    break
                if sibling.type == "block_comment":
                    # Only use it if it's close to our node (within a few lines)
                    if node.start_point[0] - sibling.end_point[0] <= 2:
                        prev_comment = sibling

        if prev_comment:
            comment_text = self._get_node_text(prev_comment)
            if comment_text.startswith("/**") and not comment_text.startswith("/***"):
                # Extract content without /** and */
                content = comment_text[3:]
                if content.endswith("*/"):
                    content = content[:-2]
                # Clean up leading * on each line
                lines = content.split("\n")
                cleaned_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("*"):
                        stripped = stripped[1:].strip()
                    if stripped:  # Only add non-empty lines
                        cleaned_lines.append(stripped)
                if cleaned_lines:
                    return "\n".join(cleaned_lines)

        return None


class ScalaPlugin(LanguagePlugin):
    """Scala language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Scala language plugin."""
        super().__init__()
        self.extractor = ScalaElementExtractor()
        self.language = "scala"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "scala"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".scala", ".sc"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return ScalaElementExtractor()

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze Scala code and return structured results."""

        from ..models import AnalysisResult

        try:
            from ..encoding_utils import read_file_safe

            file_content, detected_encoding = read_file_safe(file_path)

            # Get tree-sitter language and parse
            language = self.get_tree_sitter_language()
            if language is None:
                return AnalysisResult(
                    file_path=file_path,
                    language="scala",
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
            all_elements.extend(elements_dict.get("comments", []))
            all_elements.extend(elements_dict.get("annotations", []))

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
                language="scala",
                line_count=len(file_content.split("\n")),
                elements=all_elements,
                node_count=node_count,
                source_code=file_content,
                package=package,
            )

        except Exception as e:
            log_error(f"Error analyzing Scala file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="scala",
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
        """Get the tree-sitter language for Scala."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_scala

            caps_or_lang = tree_sitter_scala.language()

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
            log_error(f"tree-sitter-scala not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Scala: {e}")
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
                "comments": [],
                "annotations": [],
            }

        try:
            extractor = self.create_extractor()

            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "packages": extractor.extract_packages(tree, source_code),
                "comments": extractor.extract_comments(tree, source_code),  # type: ignore[attr-defined]
                "annotations": extractor.extract_annotations(tree, source_code),
            }

        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "packages": [],
                "comments": [],
                "annotations": [],
            }

    def supports_file(self, file_path: str) -> bool:
        """Check if this plugin supports the given file."""
        return any(
            file_path.lower().endswith(ext) for ext in self.get_file_extensions()
        )
