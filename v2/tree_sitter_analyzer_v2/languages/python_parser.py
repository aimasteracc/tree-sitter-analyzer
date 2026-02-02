"""
Python language parser for extracting structured information.

This module provides high-level parsing for Python code, extracting:
- Classes (with methods, bases, docstrings)
- Functions (with parameters, return types, docstrings)
- Imports (modules and imported names)
- Metadata (line numbers, complexity metrics)
"""

from typing import Any

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
from tree_sitter_analyzer_v2.core.types import ASTNode


class PythonParser:
    """
    High-level parser for Python code.

    Extracts structured information from Python source code using tree-sitter.
    """

    def __init__(self) -> None:
        """Initialize Python parser."""
        self._parser = TreeSitterParser("python")

    def parse(self, source_code: str, file_path: str | None = None) -> dict[str, Any]:
        """
        Parse Python source code and extract structured information.

        Args:
            source_code: Python source code to parse
            file_path: Optional file path for metadata

        Returns:
            Dict containing:
            - ast: Raw AST from tree-sitter
            - functions: List of function definitions
            - classes: List of class definitions
            - imports: List of import statements
            - metadata: File metadata
            - errors: Whether parsing had errors
        """
        # Parse with tree-sitter
        parse_result = self._parser.parse(source_code, file_path)

        # Initialize result structure
        result: dict[str, Any] = {
            "ast": parse_result.tree,
            "functions": [],
            "classes": [],
            "imports": [],
            "metadata": {
                "total_functions": 0,
                "total_classes": 0,
                "total_imports": 0,
            },
            "errors": parse_result.has_errors,
        }

        # Extract structured information if parsing succeeded
        if parse_result.tree:
            self._extract_imports(parse_result.tree, result)
            self._extract_functions(parse_result.tree, result)
            self._extract_classes(parse_result.tree, result)

            # Check for main block
            result["metadata"]["has_main_block"] = self._has_main_block(parse_result.tree)

            # Update metadata counts
            result["metadata"]["total_functions"] = len(result["functions"])
            result["metadata"]["total_classes"] = len(result["classes"])
            result["metadata"]["total_imports"] = len(result["imports"])

        return result

    def _has_main_block(self, root: ASTNode) -> bool:
        """
        Check if the file has a if __name__ == "__main__": block.

        Args:
            root: Root AST node

        Returns:
            True if main block detected, False otherwise
        """
        return self._traverse_for_main_block(root)

    def _traverse_for_main_block(self, node: ASTNode) -> bool:
        """Recursively traverse AST to find main block pattern."""
        if node.type == "if_statement":
            # Check if this is the main block pattern
            if self._is_main_block_pattern(node):
                return True

        # Recursively check children
        for child in node.children:
            if self._traverse_for_main_block(child):
                return True

        return False

    def _is_main_block_pattern(self, if_node: ASTNode) -> bool:
        """
        Check if an if_statement matches the main block pattern.

        Matches: if __name__ == "__main__":
        """
        # Look for comparison with __name__ and "__main__"
        for child in if_node.children:
            if child.type == "comparison_operator":
                # Check if comparison involves __name__ and "__main__"
                has_name = False
                has_main = False

                for grandchild in child.children:
                    if grandchild.type == "identifier" and grandchild.text == "__name__":
                        has_name = True
                    elif grandchild.type == "string":
                        # Check for "__main__" or '__main__'
                        text = grandchild.text or ""
                        if "__main__" in text:
                            has_main = True

                if has_name and has_main:
                    return True

        return False

    def _extract_imports(self, root: ASTNode, result: dict[str, Any]) -> None:
        """
        Extract import statements from AST.

        Args:
            root: Root AST node
            result: Result dict to populate
        """
        self._traverse_for_imports(root, result["imports"])

    def _traverse_for_imports(self, node: ASTNode, imports: list[dict[str, Any]]) -> None:
        """Recursively traverse AST to find import statements."""
        # Check if this is an import statement
        if node.type == "import_statement":
            # Simple import: import os, sys
            import_info = self._extract_import_statement(node)
            if import_info:
                imports.append(import_info)

        elif node.type == "import_from_statement":
            # From import: from pathlib import Path
            import_info = self._extract_from_import(node)
            if import_info:
                imports.append(import_info)

        # Recursively check children
        for child in node.children:
            self._traverse_for_imports(child, imports)

    def _extract_import_statement(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract info from 'import x' or 'import x as y' statement."""
        # Find dotted_name or aliased_import children
        for child in node.children:
            if child.type == "dotted_name":
                return {
                    "module": child.text or "",
                    "type": "import",
                }
            elif child.type == "aliased_import":
                # import x as y
                module_name = None
                alias = None
                for grandchild in child.children:
                    if grandchild.type == "dotted_name":
                        module_name = grandchild.text
                    elif grandchild.type == "identifier" and grandchild.text:
                        alias = grandchild.text

                if module_name:
                    return {
                        "module": module_name,
                        "alias": alias,
                        "type": "import",
                    }

        return None

    def _extract_from_import(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract info from 'from x import y' statement."""
        module_name = None
        imported_names: list[str] = []
        found_import_keyword = False

        for child in node.children:
            # The module name comes after "from" and before "import"
            if child.type == "dotted_name" and not found_import_keyword:
                module_name = child.text
            elif child.text == "import":
                found_import_keyword = True
            elif found_import_keyword:
                # After "import" keyword, collect imported names
                if child.type == "dotted_name" and child.text:
                    imported_names.append(child.text)
                elif child.type == "aliased_import":
                    # from x import y as z
                    for grandchild in child.children:
                        if grandchild.type == "identifier" and grandchild.text:
                            imported_names.append(grandchild.text)
                            break
                elif child.type == "identifier" and child.text:
                    imported_names.append(child.text)

        if module_name:
            return {
                "module": module_name,
                "names": imported_names,
                "type": "from_import",
            }

        return None

    def _extract_functions(self, root: ASTNode, result: dict[str, Any]) -> None:
        """
        Extract function definitions from AST.

        Args:
            root: Root AST node
            result: Result dict to populate
        """
        self._traverse_for_functions(root, result["functions"])

    def _traverse_for_functions(
        self, node: ASTNode, functions: list[dict[str, Any]], inside_class: bool = False
    ) -> None:
        """Recursively traverse AST to find function definitions."""
        if node.type == "function_definition":
            func_info = self._extract_function_definition(node)
            if func_info and not inside_class:
                # Only add if not inside a class (methods handled separately)
                functions.append(func_info)

        elif node.type == "decorated_definition":
            # Handle decorated functions
            decorators = []
            func_node = None

            # Extract decorators and find function
            for child in node.children:
                if child.type == "decorator":
                    dec_name = self._extract_decorator_name(child)
                    if dec_name:
                        decorators.append(dec_name)
                elif child.type == "function_definition":
                    func_node = child

            # Extract function and add decorators
            if func_node and not inside_class:
                func_info = self._extract_function_definition(func_node)
                if func_info:
                    func_info["decorators"] = decorators
                    functions.append(func_info)
                    return  # Don't descend into decorated definition children

        elif node.type == "class_definition":
            # Don't descend into classes when looking for top-level functions
            return

        # Recursively check children
        for child in node.children:
            self._traverse_for_functions(child, functions, inside_class)

    def _extract_decorator_name(self, decorator_node: ASTNode) -> str | None:
        """
        Extract decorator name from a decorator node.

        Args:
            decorator_node: Decorator AST node

        Returns:
            Decorator name or None
        """
        # Extract decorator name
        for child in decorator_node.children:
            if child.type == "identifier" and child.text:
                return child.text
            elif child.type == "attribute" and child.text:
                # Handle @property.setter style decorators
                return child.text
            elif child.type == "call":
                # Handle @decorator(args) style
                for grandchild in child.children:
                    if grandchild.type == "identifier" and grandchild.text:
                        return grandchild.text

        return None

    def _is_async_function(self, node: ASTNode) -> bool:
        """
        Check if a function definition is async.

        Args:
            node: Function definition node

        Returns:
            True if async function, False otherwise
        """
        # Check for "async" keyword before "def"
        for child in node.children:
            if child.text == "async":
                return True
        return False

    def _extract_function_definition(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract information from a function definition node."""
        func_info: dict[str, Any] = {
            "name": "",
            "parameters": [],
            "return_type": None,
            "docstring": None,
            "decorators": [],  # Will be filled by caller if decorated
            "is_async": False,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        # Check if async
        func_info["is_async"] = self._is_async_function(node)

        for child in node.children:
            if child.type == "identifier":
                func_info["name"] = child.text or ""
            elif child.type == "parameters":
                func_info["parameters"] = self._extract_parameters(child)
            elif child.type == "type":
                # Return type annotation
                func_info["return_type"] = child.text
            elif child.type == "block":
                # Extract docstring from first expression if it's a string
                func_info["docstring"] = self._extract_docstring(child)

        return func_info if func_info["name"] else None

    def _extract_parameters(self, params_node: ASTNode) -> list[str]:
        """Extract parameter names from parameters node."""
        params: list[str] = []

        for child in params_node.children:
            if child.type == "identifier" and child.text:
                params.append(child.text)
            elif child.type == "typed_parameter":
                # Parameter with type annotation
                for grandchild in child.children:
                    if grandchild.type == "identifier" and grandchild.text:
                        params.append(grandchild.text)
                        break
            elif child.type == "default_parameter":
                # Parameter with default value
                for grandchild in child.children:
                    if grandchild.type == "identifier" and grandchild.text:
                        params.append(grandchild.text)
                        break

        return params

    def _extract_docstring(self, block_node: ASTNode) -> str | None:
        """Extract docstring from block if present."""
        # Look for first string literal in block
        for child in block_node.children:
            if child.type == "expression_statement":
                for grandchild in child.children:
                    if grandchild.type == "string" and grandchild.text:
                        # Remove quotes from docstring
                        docstring = grandchild.text.strip()
                        if docstring.startswith('"""') or docstring.startswith("'''"):
                            return docstring[3:-3].strip()
                        elif docstring.startswith('"') or docstring.startswith("'"):
                            return docstring[1:-1].strip()
                        return docstring

        return None

    def _extract_classes(self, root: ASTNode, result: dict[str, Any]) -> None:
        """
        Extract class definitions from AST.

        Args:
            root: Root AST node
            result: Result dict to populate
        """
        self._traverse_for_classes(root, result["classes"])

    def _traverse_for_classes(self, node: ASTNode, classes: list[dict[str, Any]]) -> None:
        """Recursively traverse AST to find class definitions."""
        if node.type == "class_definition":
            class_info = self._extract_class_definition(node)
            if class_info:
                classes.append(class_info)

        elif node.type == "decorated_definition":
            # Handle decorated classes
            decorators = []
            class_node = None

            # Extract decorators and find class
            for child in node.children:
                if child.type == "decorator":
                    dec_name = self._extract_decorator_name(child)
                    if dec_name:
                        decorators.append(dec_name)
                elif child.type == "class_definition":
                    class_node = child

            # Extract class and add decorators
            if class_node:
                class_info = self._extract_class_definition(class_node)
                if class_info:
                    class_info["decorators"] = decorators
                    classes.append(class_info)
                    return  # Don't descend into the decorated definition

        # Recursively check children (including nested classes)
        for child in node.children:
            self._traverse_for_classes(child, classes)

    def _extract_class_definition(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract information from a class definition node."""
        class_info: dict[str, Any] = {
            "name": "",
            "bases": [],
            "methods": [],
            "attributes": [],
            "decorators": [],  # Will be filled by caller if decorated
            "docstring": None,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        for child in node.children:
            if child.type == "identifier":
                class_info["name"] = child.text or ""
            elif child.type == "argument_list":
                # Base classes
                class_info["bases"] = self._extract_base_classes(child)
            elif child.type == "block":
                # Extract methods, attributes, and docstring
                class_info["docstring"] = self._extract_docstring(child)
                class_info["methods"] = self._extract_methods(child)
                class_info["attributes"] = self._extract_class_attributes(child)

        return class_info if class_info["name"] else None

    def _extract_base_classes(self, arg_list_node: ASTNode) -> list[str]:
        """Extract base class names from argument list."""
        bases: list[str] = []

        for child in arg_list_node.children:
            if child.type == "identifier" and child.text:
                bases.append(child.text)
            elif child.type == "attribute" and child.text:
                # For cases like Animal.Mammal
                bases.append(child.text)

        return bases

    def _extract_methods(self, block_node: ASTNode) -> list[dict[str, Any]]:
        """Extract method definitions from class block."""
        methods: list[dict[str, Any]] = []

        for child in block_node.children:
            if child.type == "function_definition":
                method_info = self._extract_function_definition(child)
                if method_info:
                    methods.append(method_info)
            elif child.type == "decorated_definition":
                # Handle decorated methods
                decorators = []
                func_node = None

                # Extract decorators and find function
                for grandchild in child.children:
                    if grandchild.type == "decorator":
                        dec_name = self._extract_decorator_name(grandchild)
                        if dec_name:
                            decorators.append(dec_name)
                    elif grandchild.type == "function_definition":
                        func_node = grandchild

                # Extract method and add decorators
                if func_node:
                    method_info = self._extract_function_definition(func_node)
                    if method_info:
                        method_info["decorators"] = decorators
                        methods.append(method_info)

        return methods

    def _extract_class_attributes(self, block_node: ASTNode) -> list[dict[str, Any]]:
        """Extract class-level attributes (not instance attributes)."""
        attributes: list[dict[str, Any]] = []

        for child in block_node.children:
            # Look for expression_statement containing assignment
            if child.type == "expression_statement":
                for grandchild in child.children:
                    if grandchild.type == "assignment":
                        # Extract left side (attribute name)
                        for ggchild in grandchild.children:
                            if ggchild.type == "identifier" and ggchild.text:
                                attributes.append(
                                    {"name": ggchild.text, "line": ggchild.start_point[0] + 1}
                                )
                                break

        return attributes
