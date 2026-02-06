"""
Python language parser - extracts functions, classes, imports from Python source.

Uses tree-sitter for AST parsing and walks the tree to extract
structured information about Python code elements.
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser


class PythonParser:
    """
    Python-specific parser that extracts structured code elements.

    Returns a dict with keys: ast, metadata, functions, classes, imports.
    """

    def __init__(self) -> None:
        self._parser = TreeSitterParser("python")

    def parse(self, code: str, file_path: str | None = None) -> dict[str, Any]:
        """
        Parse Python code and extract structured elements.

        Args:
            code: Python source code
            file_path: Optional file path

        Returns:
            Dict with ast, metadata, functions, classes, imports
        """
        result = self._parser.parse(code, file_path)
        source_bytes = code.encode("utf-8")

        functions: list[dict[str, Any]] = []
        classes: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []

        # Walk the raw tree-sitter tree for extraction
        self._parser._ensure_initialized()
        ts_tree = self._parser._ts_parser.parse(source_bytes)
        root = ts_tree.root_node

        self._extract_from_node(root, source_bytes, functions, classes, imports)

        lines = code.split("\n")
        total_lines = len(lines)

        # Check for __main__ block
        has_main = any(
            child.type == "if_statement"
            and b'__name__' in source_bytes[child.start_byte:child.end_byte]
            and b'__main__' in source_bytes[child.start_byte:child.end_byte]
            for child in root.children
        )

        metadata = {
            "total_functions": len(functions),
            "total_classes": len(classes),
            "total_imports": len(imports),
            "total_lines": total_lines,
            "has_errors": result.has_errors,
            "has_main_block": has_main,
        }

        parse_result: dict[str, Any] = {
            "ast": result.tree,
            "metadata": metadata,
            "functions": functions,
            "classes": classes,
            "imports": imports,
        }

        if result.has_errors:
            parse_result["errors"] = True

        return parse_result

    def _extract_from_node(
        self,
        node: Any,
        source_bytes: bytes,
        functions: list[dict[str, Any]],
        classes: list[dict[str, Any]],
        imports: list[dict[str, Any]],
        parent_class: str | None = None,
    ) -> None:
        """Walk tree-sitter AST and extract elements at module level."""
        for child in node.children:
            if child.type == "function_definition" and parent_class is None:
                functions.append(self._extract_function(child, source_bytes))
            elif child.type == "class_definition":
                classes.append(self._extract_class(child, source_bytes))
            elif child.type in ("import_statement", "import_from_statement"):
                imports.append(self._extract_import(child, source_bytes))
            elif child.type == "decorated_definition" and parent_class is None:
                # decorated function or class at module level
                for sub in child.children:
                    if sub.type == "function_definition":
                        func = self._extract_function(sub, source_bytes)
                        func["decorators"] = self._extract_decorators(child, source_bytes)
                        functions.append(func)
                    elif sub.type == "class_definition":
                        cls = self._extract_class(sub, source_bytes)
                        cls["decorators"] = self._extract_decorators(child, source_bytes)
                        classes.append(cls)

    def _extract_function(self, node: Any, source_bytes: bytes) -> dict[str, Any]:
        """Extract function information from a function_definition node."""
        name = ""
        parameters: list[str] = []
        return_type: str | None = None
        decorators: list[str] = []
        is_async = False
        docstring: str | None = None

        for child in node.children:
            if child.type == "identifier":
                name = self._get_text(child, source_bytes)
            elif child.type == "parameters":
                parameters = self._extract_parameters(child, source_bytes)
            elif child.type == "type":
                return_type = self._get_text(child, source_bytes)
            elif child.type == "block":
                docstring = self._extract_docstring(child, source_bytes)

        # Check for return type annotation via field name
        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            return_type = self._get_text(ret_node, source_bytes)

        # Check if this is an async function
        # In tree-sitter, async functions have the full source starting with "async def"
        full_text = self._get_text(node, source_bytes)
        if full_text.lstrip().startswith("async "):
            is_async = True
        # Also check prev sibling (in some tree-sitter versions)
        if node.prev_sibling and self._get_text(node.prev_sibling, source_bytes).strip() == "async":
            is_async = True

        func_result: dict[str, Any] = {
            "name": name,
            "parameters": parameters,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
            "is_async": is_async,
        }

        if return_type:
            func_result["return_type"] = return_type
        if decorators:
            func_result["decorators"] = decorators
        if docstring:
            func_result["docstring"] = docstring

        return func_result

    def _extract_class(self, node: Any, source_bytes: bytes) -> dict[str, Any]:
        """Extract class information from a class_definition node."""
        name = ""
        bases: list[str] = []
        methods: list[dict[str, Any]] = []
        attributes: list[dict[str, Any]] = []
        decorators: list[str] = []
        docstring: str | None = None
        nested_classes: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "identifier":
                name = self._get_text(child, source_bytes)
            elif child.type == "argument_list":
                bases = self._extract_bases(child, source_bytes)
            elif child.type == "block":
                docstring = self._extract_docstring(child, source_bytes)
                # Extract methods, attributes, and nested classes from class body
                for stmt in child.children:
                    if stmt.type == "function_definition":
                        methods.append(self._extract_function(stmt, source_bytes))
                    elif stmt.type == "decorated_definition":
                        for sub in stmt.children:
                            if sub.type == "function_definition":
                                method = self._extract_function(sub, source_bytes)
                                method["decorators"] = self._extract_decorators(stmt, source_bytes)
                                # Check for @property
                                if "property" in method.get("decorators", []):
                                    method["is_property"] = True
                                methods.append(method)
                    elif stmt.type == "expression_statement":
                        attr = self._extract_attribute(stmt, source_bytes)
                        if attr:
                            attributes.append(attr)
                    elif stmt.type == "class_definition":
                        nested_classes.append(self._extract_class(stmt, source_bytes))

        result: dict[str, Any] = {
            "name": name,
            "methods": methods,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        if bases:
            result["bases"] = bases
        if attributes:
            result["attributes"] = attributes
        if decorators:
            result["decorators"] = decorators
        if docstring:
            result["docstring"] = docstring
        if nested_classes:
            result["nested_classes"] = nested_classes

        return result

    def _extract_import(self, node: Any, source_bytes: bytes) -> dict[str, Any]:
        """Extract import information."""
        result: dict[str, Any] = {}

        if node.type == "import_statement":
            # import X / import X as Y
            for child in node.children:
                if child.type == "dotted_name":
                    result["module"] = self._get_text(child, source_bytes)
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node:
                        result["module"] = self._get_text(name_node, source_bytes)
                    if alias_node:
                        result["alias"] = self._get_text(alias_node, source_bytes)

        elif node.type == "import_from_statement":
            # from X import Y, Z
            # Structure: from, dotted_name(module), import, dotted_name(name1), dotted_name(name2)...
            names: list[str] = []
            module_name: str | None = None
            seen_import_keyword = False

            for child in node.children:
                if child.type == "from":
                    continue
                elif child.type == "import":
                    seen_import_keyword = True
                    continue
                elif child.type == ",":
                    continue

                if not seen_import_keyword:
                    # Before 'import' keyword = module name
                    if child.type in ("dotted_name", "relative_import"):
                        module_name = self._get_text(child, source_bytes)
                else:
                    # After 'import' keyword = imported names
                    if child.type == "dotted_name":
                        names.append(self._get_text(child, source_bytes))
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            names.append(self._get_text(name_node, source_bytes))

            if module_name:
                result["module"] = module_name
            if names:
                result["names"] = names

        return result

    def _extract_parameters(self, node: Any, source_bytes: bytes) -> list[str]:
        """Extract parameter names from a parameters node."""
        params: list[str] = []
        for child in node.children:
            if child.type == "identifier":
                name = self._get_text(child, source_bytes)
                if name != "self" and name != "cls":
                    params.append(name)
            elif child.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = self._get_text(name_node, source_bytes)
                else:
                    # Fallback: first identifier child
                    for sub in child.children:
                        if sub.type == "identifier":
                            name = self._get_text(sub, source_bytes)
                            break
                    else:
                        continue
                if name != "self" and name != "cls":
                    params.append(name)
            elif child.type == "list_splat_pattern":
                # *args
                for sub in child.children:
                    if sub.type == "identifier":
                        params.append("*" + self._get_text(sub, source_bytes))
            elif child.type == "dictionary_splat_pattern":
                # **kwargs
                for sub in child.children:
                    if sub.type == "identifier":
                        params.append("**" + self._get_text(sub, source_bytes))
        return params

    def _extract_bases(self, node: Any, source_bytes: bytes) -> list[str]:
        """Extract base class names from argument_list."""
        bases: list[str] = []
        for child in node.children:
            if child.type == "identifier":
                bases.append(self._get_text(child, source_bytes))
            elif child.type == "attribute":
                bases.append(self._get_text(child, source_bytes))
        return bases

    def _extract_decorators(self, node: Any, source_bytes: bytes) -> list[str]:
        """Extract decorator names from a decorated_definition node."""
        decorators: list[str] = []
        for child in node.children:
            if child.type == "decorator":
                # Get the decorator name (skip @)
                for sub in child.children:
                    if sub.type == "identifier":
                        decorators.append(self._get_text(sub, source_bytes))
                    elif sub.type == "attribute":
                        decorators.append(self._get_text(sub, source_bytes))
                    elif sub.type == "call":
                        # @decorator(args)
                        for call_child in sub.children:
                            if call_child.type == "identifier":
                                decorators.append(self._get_text(call_child, source_bytes))
                                break
                            elif call_child.type == "attribute":
                                decorators.append(self._get_text(call_child, source_bytes))
                                break
        return decorators

    def _extract_docstring(self, block_node: Any, source_bytes: bytes) -> str | None:
        """Extract docstring from the first statement in a block."""
        for child in block_node.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        text = self._get_text(sub, source_bytes)
                        # Remove quotes
                        if text.startswith('"""') and text.endswith('"""'):
                            return text[3:-3].strip()
                        elif text.startswith("'''") and text.endswith("'''"):
                            return text[3:-3].strip()
                        elif text.startswith('"') and text.endswith('"'):
                            return text[1:-1].strip()
                        elif text.startswith("'") and text.endswith("'"):
                            return text[1:-1].strip()
                return None  # First statement is not a string
        return None

    def _extract_attribute(self, node: Any, source_bytes: bytes) -> dict[str, Any] | None:
        """Extract class attribute from expression_statement."""
        for child in node.children:
            if child.type == "assignment":
                left = child.child_by_field_name("left")
                right = child.child_by_field_name("right")
                if left:
                    name = self._get_text(left, source_bytes)
                else:
                    # Fallback
                    for sub in child.children:
                        if sub.type == "identifier":
                            name = self._get_text(sub, source_bytes)
                            break
                    else:
                        return None
                result: dict[str, Any] = {"name": name}
                if right:
                    result["value"] = self._get_text(right, source_bytes)
                return result
            elif child.type == "type_alias_statement":
                return None
        return None

    def _get_text(self, node: Any, source_bytes: bytes) -> str:
        """Get text content of a node."""
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8")
