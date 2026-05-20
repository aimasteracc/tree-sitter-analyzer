"""Public extraction workflow for the JavaScript extractor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...models import Class, CodeElement, Function, Import, Variable
from ...utils import log_debug, log_error

if TYPE_CHECKING:
    import tree_sitter


class JavaScriptPublicExtractionMixin:
    """Public JavaScript extraction entry points."""

    # Extract elements from AST: extract_functions
    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract JavaScript function definitions with comprehensive details."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()
        self._detect_file_characteristics()

        functions: list[Function] = []
        extractors = {
            "function_declaration": self._extract_function_optimized,
            "function_expression": self._extract_function_optimized,
            "arrow_function": self._extract_arrow_function_optimized,
            "method_definition": self._extract_method_optimized,
            "generator_function_declaration": self._extract_generator_function_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node,
            extractors,
            functions,
            "function",
        )

        log_debug(f"Extracted {len(functions)} JavaScript functions")
        return functions

    # Extract elements from AST: extract_classes
    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract JavaScript class definitions with detailed information."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        classes: list[Class] = []
        extractors = {
            "class_declaration": self._extract_class_optimized,
            "class_expression": self._extract_class_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node,
            extractors,
            classes,
            "class",
        )

        log_debug(f"Extracted {len(classes)} JavaScript classes")
        return classes

    # Extract elements from AST: extract_variables
    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract JavaScript variable definitions with modern syntax support."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

        variables: list[Variable] = []
        extractors = {
            "variable_declaration": self._extract_variable_optimized,
            "lexical_declaration": self._extract_lexical_variable_optimized,
            "property_definition": self._extract_property_optimized,
        }

        self._traverse_and_extract_iterative(
            tree.root_node,
            extractors,
            variables,
            "variable",
        )

        log_debug(f"Extracted {len(variables)} JavaScript variables")
        return variables

    # Extract elements from AST: extract_imports
    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract JavaScript import statements with ES6+ support."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        imports: list[Import] = []
        for child in tree.root_node.children:
            if child.type == "import_statement":
                import_info = self._extract_import_info_simple(child)
                if import_info:
                    imports.append(import_info)
            elif child.type == "expression_statement":
                dynamic_import = self._extract_dynamic_import(child)
                if dynamic_import:
                    imports.append(dynamic_import)

        imports.extend(self._extract_commonjs_requires(tree, source_code))

        log_debug(f"Extracted {len(imports)} JavaScript imports")
        return imports

    # Extract elements from AST: extract_exports
    def extract_exports(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[dict[str, Any]]:
        """Extract JavaScript export statements."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")

        exports: list[dict[str, Any]] = []
        for child in tree.root_node.children:
            if child.type == "export_statement":
                export_info = self._extract_export_info(child)
                if export_info:
                    exports.append(export_info)

        exports.extend(self._extract_commonjs_exports(tree, source_code))

        self.exports = exports
        log_debug(f"Extracted {len(exports)} JavaScript exports")
        return exports

    # Extract elements from AST: extract_elements
    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[CodeElement]:
        """Extract elements from source code using tree-sitter AST."""
        elements: list[CodeElement] = []

        try:
            elements.extend(self.extract_functions(tree, source_code))
            elements.extend(self.extract_classes(tree, source_code))
            elements.extend(self.extract_variables(tree, source_code))
            elements.extend(self.extract_imports(tree, source_code))
        except Exception as e:
            log_error(f"Failed to extract elements: {e}")

        return elements
