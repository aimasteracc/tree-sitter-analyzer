#!/usr/bin/env python3
"""
JavaScript Language Plugin

Provides JavaScript-specific parsing and element extraction functionality.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import tree_sitter

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..core.analysis_engine import AnalysisRequest
from ..language_loader import loader
from ..models import AnalysisResult, Class, CodeElement, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_error, log_warning


class JavaScriptElementExtractor(ElementExtractor):
    """JavaScript-specific element extractor"""

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract JavaScript function definitions"""
        functions = []

        # Multiple function patterns in JavaScript
        queries = [
            # Regular function declarations
            """
            (function_declaration
                name: (identifier) @func.name
                parameters: (formal_parameters) @func.params
                body: (statement_block) @func.body) @func.declaration
            """,
            # Method definitions (class methods)
            """
            (method_definition
                name: (property_identifier) @func.name
                parameters: (formal_parameters) @func.params
                body: (statement_block) @func.body) @func.method
            """,
            # Arrow functions
            """
            (variable_declarator
                name: (identifier) @func.name
                value: (arrow_function
                    parameters: (formal_parameters) @func.params
                    body: (_) @func.body)) @func.arrow
            """,
            # Function expressions
            """
            (variable_declarator
                name: (identifier) @func.name
                value: (function_expression
                    parameters: (formal_parameters) @func.params
                    body: (statement_block) @func.body)) @func.expression
            """,
        ]

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                for query_string in queries:
                    query = language.query(query_string)
                    captures = query.captures(tree.root_node)

                    if isinstance(captures, dict):
                        # Handle different function types
                        for capture_key in [
                            "func.declaration",
                            "func.method",
                            "func.arrow",
                            "func.expression",
                        ]:
                            func_nodes = captures.get(capture_key, [])
                            for node in func_nodes:
                                function = self._extract_function_info(
                                    node, source_code
                                )
                                if function:
                                    functions.append(function)

        except Exception as e:
            log_warning(f"Could not extract JavaScript functions: {e}")

        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract JavaScript class definitions"""
        classes = []

        query_string = """
        (class_declaration
            name: (identifier) @class.name
            body: (class_body) @class.body) @class.declaration
        """

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if isinstance(captures, dict):
                    class_nodes = captures.get("class.declaration", [])
                    for node in class_nodes:
                        cls = self._extract_class_info(node, source_code)
                        if cls:
                            classes.append(cls)

        except Exception as e:
            log_warning(f"Could not extract JavaScript classes: {e}")

        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract JavaScript variable definitions"""
        variables = []

        # Variable declarations (let, const, var)
        queries = [
            # var declarations
            """
            (variable_declaration
                (variable_declarator
                    name: (identifier) @var.name
                    value: (_)? @var.value)) @var.declaration
            """,
            # let/const declarations
            """
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @var.name
                    value: (_)? @var.value)) @var.lexical
            """,
        ]

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                for query_string in queries:
                    query = language.query(query_string)
                    captures = query.captures(tree.root_node)

                    if isinstance(captures, dict):
                        # Handle both var and lexical declarations
                        for capture_key in ["var.declaration", "var.lexical"]:
                            var_nodes = captures.get(capture_key, [])
                            for node in var_nodes:
                                variable = self._extract_variable_info(
                                    node, source_code
                                )
                                if variable:
                                    variables.append(variable)

        except Exception as e:
            log_warning(f"Could not extract JavaScript variables: {e}")

        return variables

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract JavaScript import statements"""
        imports = []

        # ES6 import statements
        query_string = """
        (import_statement
            source: (string) @import.source) @import.declaration
        """

        try:
            language = tree.language if hasattr(tree, "language") else None
            if language:
                query = language.query(query_string)
                captures = query.captures(tree.root_node)

                if isinstance(captures, dict):
                    import_nodes = captures.get("import.declaration", [])
                    for node in import_nodes:
                        imp = self._extract_import_info(node, source_code)
                        if imp:
                            imports.append(imp)

        except Exception as e:
            log_warning(f"Could not extract JavaScript imports: {e}")

        return imports

    def _extract_function_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Function | None:
        """Extract function information from AST node"""
        try:
            name_node = None
            params_node = None

            # Navigate the node structure to find name and parameters
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                elif child.type == "property_identifier":  # For method definitions
                    name_node = child
                elif child.type == "formal_parameters":
                    params_node = child
                elif child.type == "variable_declarator":
                    # For arrow functions and function expressions
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            name_node = subchild
                        elif subchild.type in ["arrow_function", "function_expression"]:
                            for funcchild in subchild.children:
                                if funcchild.type == "formal_parameters":
                                    params_node = funcchild

            if not name_node:
                return None

            name = source_code[name_node.start_byte : name_node.end_byte]

            # Extract parameters
            parameters = []
            if params_node:
                for child in params_node.children:
                    if child.type == "identifier":
                        param_name = source_code[child.start_byte : child.end_byte]
                        parameters.append(param_name)

            return Function(
                name=name,
                parameters=parameters,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="javascript",
            )

        except Exception as e:
            log_warning(f"Could not extract function info: {e}")
            return None

    def _extract_class_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Class | None:
        """Extract class information from AST node"""
        try:
            name_node = None

            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break

            if not name_node:
                return None

            name = source_code[name_node.start_byte : name_node.end_byte]

            return Class(
                name=name,
                class_type="class",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="javascript",
            )

        except Exception as e:
            log_warning(f"Could not extract class info: {e}")
            return None

    def _extract_variable_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Variable | None:
        """Extract variable information from AST node"""
        try:
            name_node = None

            # Find the identifier in variable declarator
            for child in node.children:
                if child.type == "variable_declarator":
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            name_node = subchild
                            break
                    break

            if not name_node:
                return None

            name = source_code[name_node.start_byte : name_node.end_byte]

            return Variable(
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="javascript",
            )

        except Exception as e:
            log_warning(f"Could not extract variable info: {e}")
            return None

    def _extract_import_info(
        self, node: "tree_sitter.Node", source_code: str
    ) -> Import | None:
        """Extract import information from AST node"""
        try:
            source_node = None

            for child in node.children:
                if child.type == "string":
                    source_node = child
                    break

            if not source_node:
                return None

            module_path = source_code[source_node.start_byte : source_node.end_byte]
            # Remove quotes from string
            module_path = module_path.strip("\"'")

            return Import(
                name="import",
                module_path=module_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=source_code[node.start_byte : node.end_byte],
                language="javascript",
            )

        except Exception as e:
            log_warning(f"Could not extract import info: {e}")
            return None


class JavaScriptPlugin(LanguagePlugin):
    """JavaScript language plugin"""

    def __init__(self) -> None:
        self._extractor = JavaScriptElementExtractor()
        self._language: tree_sitter.Language | None = None

    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> list[str]:
        return [".js", ".mjs", ".jsx"]

    def get_language_name(self) -> str:
        """Return the name of the programming language this plugin supports"""
        return "javascript"

    def get_file_extensions(self) -> list[str]:
        """Return list of file extensions this plugin supports"""
        return [".js", ".mjs", ".jsx"]

    def create_extractor(self) -> ElementExtractor:
        """Create and return an element extractor for this language"""
        return JavaScriptElementExtractor()

    def get_extractor(self) -> ElementExtractor:
        return self._extractor

    def get_tree_sitter_language(self) -> Optional["tree_sitter.Language"]:
        """Load and return JavaScript tree-sitter language"""
        if self._language is None:
            self._language = loader.load_language("javascript")
        return self._language

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze a JavaScript file and return the analysis results."""
        if not TREE_SITTER_AVAILABLE:
            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=False,
                error_message="Tree-sitter library not available.",
            )

        language = self.get_tree_sitter_language()
        if not language:
            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=False,
                error_message="Could not load JavaScript language for parsing.",
            )

        try:
            with open(file_path, encoding="utf-8") as f:
                source_code = f.read()

            parser = tree_sitter.Parser()
            parser.language = language
            tree = parser.parse(bytes(source_code, "utf8"))

            extractor = self.create_extractor()
            elements: list[CodeElement] = []
            elements.extend(extractor.extract_functions(tree, source_code))
            elements.extend(extractor.extract_classes(tree, source_code))
            elements.extend(extractor.extract_variables(tree, source_code))
            elements.extend(extractor.extract_imports(tree, source_code))

            def count_nodes(node: "tree_sitter.Node") -> int:
                count = 1
                for child in node.children:
                    count += count_nodes(child)
                return count

            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=True,
                elements=elements,
                line_count=len(source_code.splitlines()),
                node_count=count_nodes(tree.root_node),
            )
        except Exception as e:
            log_error(f"Error analyzing JavaScript file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language=self.language_name,
                success=False,
                error_message=str(e),
            )
