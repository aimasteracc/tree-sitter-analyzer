"""
Language-specific call extractors for code graph construction.

This module provides implementations for extracting function/method
calls from AST nodes in different programming languages. Each language has its own
call syntax and AST representation, so extractors encapsulate language-specific logic.

Protocol definition: see core/call_extractor_registry.CallExtractorProtocol
(single source of truth — DIP: graph/ implements core/ protocol).
"""

from typing import Any


class PythonCallExtractor:
    """
    Extract Python function and method calls from AST.

    Handles Python-specific call syntax:
    - Simple function calls: func()
    - Method calls: obj.method()
    - Module/class calls: Module.function()
    """

    def get_call_node_types(self) -> list[str]:
        """Return Python call node types."""
        return ["call"]

    def extract_calls(self, ast_node: Any) -> list[dict[str, Any]]:
        """
        Extract all Python function/method calls from AST.

        Args:
            ast_node: Root AST node to traverse

        Returns:
            List of call dictionaries with name, line, type, qualifier
        """
        calls: list[dict[str, Any]] = []

        def traverse(node: Any) -> None:
            """Recursively traverse AST to find call nodes."""
            if not node or not hasattr(node, "type"):
                return

            # Check if this is a call node
            if node.type == "call":
                call_info = self._parse_call_node(node)
                if call_info:
                    calls.append(call_info)

            # Traverse children
            if hasattr(node, "children"):
                for child in node.children:
                    traverse(child)

        traverse(ast_node)
        return calls

    def _parse_call_node(self, node: Any) -> dict[str, Any] | None:
        """
        Parse Python call node and extract call information.

        Args:
            node: AST node of type 'call'

        Returns:
            Dictionary with call details or None if parsing fails
        """
        if not hasattr(node, "children") or len(node.children) == 0:
            return None

        # The first child of call is the function expression
        func_expr = node.children[0]

        # Get line number (1-indexed)
        line_num = node.start_point[0] + 1 if hasattr(node, "start_point") else 0

        # Simple function call: func()
        if func_expr.type == "identifier":
            func_name = self._get_node_text(func_expr)
            if func_name:
                return {"name": func_name, "line": line_num, "type": "simple", "qualifier": None}

        # Attribute access: obj.method() or Module.function()
        elif func_expr.type == "attribute":
            method_info = self._parse_attribute_call(func_expr)
            if method_info:
                return {
                    "name": method_info["name"],
                    "line": line_num,
                    "type": "method",
                    "qualifier": method_info["qualifier"],
                }

        return None

    def _parse_attribute_call(self, attr_node: Any) -> dict[str, str] | None:
        """
        Parse attribute access to extract object/module and method name.

        Handles: obj.method, Module.function

        Args:
            attr_node: AST node of type 'attribute'

        Returns:
            Dictionary with 'name' and 'qualifier' or None
        """
        if not hasattr(attr_node, "children") or len(attr_node.children) < 2:
            return None

        # First child is the object/module
        qualifier_node = attr_node.children[0]
        qualifier = self._get_node_text(qualifier_node)

        # Last identifier child is the method/function name
        method_name = None
        for child in attr_node.children:
            if child.type == "identifier" and child != qualifier_node:
                method_name = self._get_node_text(child)

        if method_name:
            return {"name": method_name, "qualifier": qualifier}

        return None

    def _get_node_text(self, node: Any) -> str:
        """
        Get text content of an AST node.

        Args:
            node: AST node

        Returns:
            Text content or empty string
        """
        if hasattr(node, "text"):
            text = node.text
            if isinstance(text, bytes):
                return text.decode("utf-8")
            return str(text)
        return ""


class JavaCallExtractor:
    """
    Extract Java method calls from AST.

    Handles Java-specific call syntax:
    - Simple method calls: method()
    - Instance method calls: obj.method()
    - Static method calls: Class.method()
    - Constructor calls: new ClassName()
    """

    def get_call_node_types(self) -> list[str]:
        """Return Java call node types."""
        return ["method_invocation", "object_creation_expression"]

    def extract_calls(self, ast_node: Any) -> list[dict[str, Any]]:
        """
        Extract all Java method invocations and constructor calls from AST.

        Args:
            ast_node: Root AST node to traverse

        Returns:
            List of call dictionaries with name, line, type, qualifier
        """
        calls: list[dict[str, Any]] = []

        def traverse(node: Any) -> None:
            """Recursively traverse AST to find call nodes."""
            if not node or not hasattr(node, "type"):
                return

            # Check if this is a method invocation node
            if node.type == "method_invocation":
                call_info = self._parse_method_invocation(node)
                if call_info:
                    calls.append(call_info)
            elif node.type == "object_creation_expression":
                call_info = self._parse_constructor_call(node)
                if call_info:
                    calls.append(call_info)

            # Traverse children
            if hasattr(node, "children"):
                for child in node.children:
                    traverse(child)

        traverse(ast_node)
        return calls

    def _parse_method_invocation(self, node: Any) -> dict[str, Any] | None:
        """
        Parse Java method_invocation node.

        Handles:
        - Simple calls: method()
        - Instance calls: obj.method()
        - Static calls: Class.method()
        - Super calls: super.method()
        - This calls: this.method()

        Args:
            node: AST node of type 'method_invocation'

        Returns:
            Dictionary with call details or None if parsing fails
        """
        if not hasattr(node, "children") or len(node.children) == 0:
            return None

        method_name = None
        qualifier = None
        call_type = "simple"

        # Get line number (1-indexed)
        line_num = node.start_point[0] + 1 if hasattr(node, "start_point") else 0

        # Collect all identifiers and check for field_access, super, this
        identifiers = []
        has_field_access = False
        has_super = False
        has_this = False

        for child in node.children:
            if child.type == "identifier":
                identifiers.append(self._get_node_text(child))
            elif child.type == "field_access":
                has_field_access = True
                # obj.method() or Class.method() or super.method() or this.method()
                field_info = self._parse_field_access(child)
                if field_info:
                    qualifier = field_info["qualifier"]
                    method_name = field_info["name"]

                    # Determine call type based on qualifier
                    if qualifier == "super":
                        call_type = "super"
                    elif qualifier == "this":
                        call_type = "this"
                    else:
                        call_type = "method"  # Could be instance or static
            elif child.type == "super":
                has_super = True
                qualifier = "super"
                call_type = "super"
            elif child.type == "this":
                has_this = True
                qualifier = "this"
                call_type = "this"

        # Handle different calling patterns
        if has_super or has_this:
            # super.method() or this.method() - already set qualifier and call_type
            # Get method name from identifiers
            if len(identifiers) >= 1:
                method_name = identifiers[-1]  # Last identifier is method name
        elif not has_field_access and len(identifiers) >= 2:
            # Pattern: obj.method() where we have [obj, method] as identifiers
            qualifier = identifiers[0]
            method_name = identifiers[-1]  # Last identifier is method name

            # Determine type based on qualifier
            if qualifier == "super":
                call_type = "super"
            elif qualifier == "this":
                call_type = "this"
            else:
                call_type = "method"
        elif not has_field_access and len(identifiers) == 1:
            # Simple call: method()
            method_name = identifiers[0]
            call_type = "simple"

        if not method_name:
            return None

        return {"name": method_name, "line": line_num, "type": call_type, "qualifier": qualifier}

    def _parse_field_access(self, node: Any) -> dict[str, str] | None:
        """
        Parse field_access node to extract object/class and method name.

        Handles: obj.method, Class.method, super.method, this.method

        Args:
            node: AST node of type 'field_access'

        Returns:
            Dictionary with 'name' and 'qualifier' or None
        """
        if not hasattr(node, "children") or len(node.children) < 2:
            return None

        # First child is the object/class/super/this
        qualifier_node = node.children[0]
        qualifier = self._get_node_text(qualifier_node)

        # Look for identifier child (field name)
        method_name = None
        for child in node.children:
            if child.type == "identifier":
                method_name = self._get_node_text(child)

        if method_name:
            return {"name": method_name, "qualifier": qualifier}

        return None

    def _parse_constructor_call(self, node: Any) -> dict[str, Any] | None:
        """
        Parse constructor call: new ClassName()

        Args:
            node: AST node of type 'object_creation_expression'

        Returns:
            Call info with type='constructor' or None
        """
        if not hasattr(node, "children"):
            return None

        class_name = None
        line_num = node.start_point[0] + 1 if hasattr(node, "start_point") else 0

        for child in node.children:
            if child.type == "type_identifier":
                class_name = self._get_node_text(child)
                break
            elif child.type == "generic_type":
                # new List<String>()
                for grandchild in child.children:
                    if grandchild.type == "type_identifier":
                        class_name = self._get_node_text(grandchild)
                        break

        if not class_name:
            return None

        return {"name": class_name, "line": line_num, "type": "constructor", "qualifier": None}

    def _get_node_text(self, node: Any) -> str:
        """
        Get text content of an AST node.

        Args:
            node: AST node

        Returns:
            Text content or empty string
        """
        if hasattr(node, "text"):
            text = node.text
            if isinstance(text, bytes):
                return text.decode("utf-8")
            return str(text)
        return ""
