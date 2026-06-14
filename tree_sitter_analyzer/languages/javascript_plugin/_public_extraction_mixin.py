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

        # Separate pass: collect prototype-assignment methods.
        # These are NOT picked up by the traversal above because
        # `assignment_expression` is only a container node type there;
        # adding it to `extractors` would also re-process the inner
        # function_expression and create duplicates.
        prototype_methods = self._extract_prototype_methods(tree.root_node)
        functions.extend(prototype_methods)

        log_debug(f"Extracted {len(functions)} JavaScript functions")
        return functions

    def _extract_prototype_methods(self, root_node: tree_sitter.Node) -> list[Function]:
        """Walk top-level expression statements for X.prototype.m = function(){}.

        Only scans the immediate children of the program root (or one level
        inside export_statement) — prototype assignments are always top-level in
        practice and this keeps the pass O(n) where n = top-level statements.
        """
        methods: list[Function] = []
        candidates = list(root_node.children)
        for stmt in candidates:
            # Unwrap export_statement if needed
            if stmt.type == "export_statement":
                inner = stmt.child_by_field_name("declaration")
                if inner:
                    stmt = inner
            if stmt.type != "expression_statement":
                continue
            for child in stmt.children:
                if child.type == "assignment_expression":
                    method = self._extract_prototype_method_optimized(child)
                    if method is not None:
                        methods.append(method)
        return methods

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

        # Synthesise Class objects for constructors defined via prototype pattern.
        # Only add a synthetic class when no ES6 class_declaration with the same
        # name was already found by the traversal above.
        existing_class_names = {c.name for c in classes}
        for proto_class in self._extract_prototype_classes(tree.root_node):
            if proto_class.name not in existing_class_names:
                classes.append(proto_class)
                existing_class_names.add(proto_class.name)

        log_debug(f"Extracted {len(classes)} JavaScript classes")
        return classes

    def _extract_prototype_classes(self, root_node: tree_sitter.Node) -> list[Class]:
        """Synthesise Class objects from X.prototype.m assignments.

        Looks for ``function ClassName(...){}`` declarations in the top-level
        program AND collects class names from prototype assignments.  A synthetic
        Class is created for each unique class name found only via prototype
        assignments (i.e. no ES6 class_declaration exists for that name).
        """
        # Collect constructor lines from function_declaration nodes
        constructor_lines: dict[str, int] = {}
        for stmt in root_node.children:
            if stmt.type == "function_declaration":
                # Check if there is a prototype assignment for this name later
                for id_child in stmt.children:
                    if id_child.type == "identifier":
                        name = self._get_node_text_optimized(id_child)
                        constructor_lines[name] = stmt.start_point[0] + 1
                        break

        # Collect class names referenced in prototype assignments
        proto_class_names: dict[str, int] = {}  # name -> first assignment line
        for stmt in root_node.children:
            if stmt.type != "expression_statement":
                continue
            for child in stmt.children:
                if child.type != "assignment_expression":
                    continue
                left = child.child_by_field_name("left")
                if not left or left.type != "member_expression":
                    continue
                proto_expr = left.child_by_field_name("object")
                if not proto_expr or proto_expr.type != "member_expression":
                    continue
                proto_prop = proto_expr.child_by_field_name("property")
                if (
                    not proto_prop
                    or self._get_node_text_optimized(proto_prop) != "prototype"
                ):
                    continue
                class_id = proto_expr.child_by_field_name("object")
                if not class_id or class_id.type != "identifier":
                    continue
                class_name = self._get_node_text_optimized(class_id)
                if class_name not in proto_class_names:
                    proto_class_names[class_name] = stmt.start_point[0] + 1

        synthetic: list[Class] = []
        for class_name, first_line in proto_class_names.items():
            start_line = constructor_lines.get(class_name, first_line)
            synthetic.append(
                Class(
                    name=class_name,
                    start_line=start_line,
                    end_line=first_line,
                    raw_text="",
                    language="javascript",
                    class_type="class",
                )
            )
        return synthetic

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
