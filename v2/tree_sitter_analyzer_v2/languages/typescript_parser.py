"""
TypeScript language parser for extracting structured information.

This module provides high-level parsing for TypeScript code, extracting:
- Interfaces (with properties and methods)
- Type aliases
- Classes (with methods and implements)
- Functions (including arrow functions)
- Imports and exports
- Metadata (line numbers, counts)
"""

from typing import Any

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
from tree_sitter_analyzer_v2.core.types import ASTNode, LanguageParseResult


class TypeScriptParser:
    """
    High-level parser for TypeScript code.

    Extracts structured information from TypeScript source code using tree-sitter.
    """

    def __init__(self) -> None:
        """Initialize TypeScript parser."""
        self._parser = TreeSitterParser("typescript")

    def parse(self, source_code: str, file_path: str = "") -> LanguageParseResult:
        """
        Parse TypeScript source code and extract structured information.

        Args:
            source_code: TypeScript source code to parse
            file_path: Optional file path for metadata

        Returns:
            Dict containing:
            - ast: Raw AST from tree-sitter
            - functions: List of function definitions
            - classes: List of class definitions
            - interfaces: List of interface definitions
            - types: List of type aliases
            - imports: List of import statements
            - exports: List of export statements
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
            "interfaces": [],
            "types": [],
            "enums": [],
            "variables": [],
            "imports": [],
            "exports": [],
            "metadata": {
                "total_functions": 0,
                "total_classes": 0,
                "total_interfaces": 0,
                "total_types": 0,
                "total_enums": 0,
                "total_variables": 0,
                "total_imports": 0,
                "total_exports": 0,
            },
            "errors": parse_result.has_errors,
        }

        # Extract structured information if parsing succeeded
        if parse_result.tree:
            self._extract_all(parse_result.tree, result)

            # Update metadata counts
            result["metadata"]["total_functions"] = len(result["functions"])
            result["metadata"]["total_classes"] = len(result["classes"])
            result["metadata"]["total_interfaces"] = len(result["interfaces"])
            result["metadata"]["total_types"] = len(result["types"])
            result["metadata"]["total_enums"] = len(result["enums"])
            result["metadata"]["total_variables"] = len(result["variables"])
            result["metadata"]["total_imports"] = len(result["imports"])
            result["metadata"]["total_exports"] = len(result["exports"])

        return result

    def _extract_all(self, root: ASTNode, result: dict[str, Any]) -> None:
        """Extract all TypeScript constructs from AST."""
        self._traverse(root, result)

    def _traverse(self, node: ASTNode, result: dict[str, Any]) -> None:
        """Recursively traverse AST to extract all constructs."""
        # Check node type and extract accordingly
        if node.type == "interface_declaration":
            interface_info = self._extract_interface(node)
            if interface_info:
                result["interfaces"].append(interface_info)

        elif node.type == "type_alias_declaration":
            type_info = self._extract_type_alias(node)
            if type_info:
                result["types"].append(type_info)

        elif node.type == "class_declaration":
            class_info = self._extract_class(node)
            if class_info:
                result["classes"].append(class_info)

        elif node.type == "function_declaration":
            func_info = self._extract_function(node)
            if func_info:
                result["functions"].append(func_info)

        elif node.type == "lexical_declaration":
            # Check if it's an arrow function assignment
            func_info = self._extract_arrow_function(node)
            if func_info:
                result["functions"].append(func_info)
            else:
                # Otherwise, treat as variable declaration
                variables = self._extract_variables(node)
                result["variables"].extend(variables)

        elif node.type == "import_statement":
            import_info = self._extract_import(node)
            if import_info:
                result["imports"].append(import_info)

        elif node.type == "export_statement":
            export_info = self._extract_export(node)
            if export_info:
                result["exports"].append(export_info)

        elif node.type == "enum_declaration":
            enum_info = self._extract_enum(node)
            if enum_info:
                result["enums"].append(enum_info)

        elif node.type in ["variable_declaration", "lexical_declaration"]:
            variables = self._extract_variables(node)
            result["variables"].extend(variables)

        # Recursively traverse children
        for child in node.children:
            self._traverse(child, result)

    def _extract_interface(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract information from interface declaration."""
        interface_info: dict[str, Any] = {
            "name": "",
            "properties": [],
            "methods": [],
            "generics": [],
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        for child in node.children:
            if child.type == "type_identifier":
                interface_info["name"] = child.text or ""
            elif child.type == "type_parameters":
                interface_info["generics"] = self._extract_generic_params(child)
            elif child.type in ["object_type", "interface_body"]:
                # Extract properties and methods from object type or interface body
                self._extract_interface_members(child, interface_info)

        return interface_info if interface_info["name"] else None

    def _extract_interface_members(
        self, object_type_node: ASTNode, interface_info: dict[str, Any]
    ) -> None:
        """Extract properties and methods from interface object type."""
        for child in object_type_node.children:
            if child.type == "property_signature":
                prop_info = self._extract_property_signature(child)
                if prop_info:
                    interface_info["properties"].append(prop_info)
            elif child.type == "method_signature":
                method_info = self._extract_method_signature(child)
                if method_info:
                    interface_info["methods"].append(method_info)

    def _extract_property_signature(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract property signature from interface."""
        prop_info: dict[str, Any] = {"name": "", "type": None, "optional": False}

        for child in node.children:
            if child.type == "property_identifier":
                prop_info["name"] = child.text or ""
            elif child.type == "type_annotation":
                # Extract type
                for grandchild in child.children:
                    if grandchild.type != ":":
                        prop_info["type"] = grandchild.text

        # Check if property is optional (name contains '?')
        if node.text and "?" in node.text:
            prop_info["optional"] = True

        return prop_info if prop_info["name"] else None

    def _extract_method_signature(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract method signature from interface."""
        method_info: dict[str, Any] = {"name": "", "parameters": [], "return_type": None}

        for child in node.children:
            if child.type == "property_identifier":
                method_info["name"] = child.text or ""
            elif child.type == "formal_parameters":
                method_info["parameters"] = self._extract_parameters(child)
            elif child.type == "type_annotation":
                # Extract return type
                for grandchild in child.children:
                    if grandchild.type != ":":
                        method_info["return_type"] = grandchild.text

        return method_info if method_info["name"] else None

    def _extract_type_alias(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract type alias declaration."""
        type_info: dict[str, Any] = {
            "name": "",
            "definition": None,
            "generics": [],
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        for child in node.children:
            if child.type == "type_identifier":
                type_info["name"] = child.text or ""
            elif child.type == "type_parameters":
                type_info["generics"] = self._extract_generic_params(child)
            elif child.type in ["union_type", "object_type", "type_identifier"]:
                type_info["definition"] = child.text

        return type_info if type_info["name"] else None

    def _extract_class(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract class declaration."""
        class_info: dict[str, Any] = {
            "name": "",
            "implements": [],
            "methods": [],
            "properties": [],
            "generics": [],
            "decorators": [],
            "framework_type": None,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        decorators: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "decorator":
                decorator_info = self._extract_decorator(child)
                if decorator_info:
                    decorators.append(decorator_info)
            elif child.type == "type_identifier":
                class_info["name"] = child.text or ""
            elif child.type == "type_parameters":
                class_info["generics"] = self._extract_generic_params(child)
            elif child.type == "class_heritage":
                # Extract implements clause
                class_info["implements"] = self._extract_implements(child)
            elif child.type == "class_body":
                # Extract methods and properties
                self._extract_class_members(child, class_info)

        class_info["decorators"] = decorators

        # Detect framework type from decorators
        if decorators:
            class_info["framework_type"] = self._detect_framework_type(decorators)

        return class_info if class_info["name"] else None

    def _extract_implements(self, heritage_node: ASTNode) -> list[str]:
        """Extract implemented interfaces from class heritage."""
        implements: list[str] = []

        for child in heritage_node.children:
            if child.type == "implements_clause":
                for grandchild in child.children:
                    if grandchild.type == "type_identifier":
                        implements.append(grandchild.text or "")

        return implements

    def _extract_class_members(self, class_body_node: ASTNode, class_info: dict[str, Any]) -> None:
        """Extract methods and properties from class body."""
        children = class_body_node.children
        i = 0

        while i < len(children):
            # Collect decorators
            decorators: list[dict[str, Any]] = []
            while i < len(children) and children[i].type == "decorator":
                decorator_info = self._extract_decorator(children[i])
                if decorator_info:
                    decorators.append(decorator_info)
                i += 1

            # Extract the member if it exists
            if i < len(children):
                child = children[i]

                if child.type == "method_definition":
                    method_info = self._extract_method_definition(child)
                    if method_info:
                        method_info["decorators"] = decorators
                        class_info["methods"].append(method_info)

                elif child.type in ["public_field_definition", "field_definition"]:
                    # Properties already extract decorators internally
                    property_info = self._extract_property_definition_with_decorators(child)
                    if property_info:
                        # Add any external decorators
                        property_info["decorators"] = decorators + property_info["decorators"]
                        class_info["properties"].append(property_info)

            i += 1

    def _extract_method_definition(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract method definition from class."""
        method_info: dict[str, Any] = {
            "name": "",
            "parameters": [],
            "return_type": None,
            "decorators": [],
        }

        for child in node.children:
            if child.type == "property_identifier":
                method_info["name"] = child.text or ""
            elif child.type == "formal_parameters":
                method_info["parameters"] = self._extract_parameters(child)
            elif child.type == "type_annotation":
                for grandchild in child.children:
                    if grandchild.type != ":":
                        method_info["return_type"] = grandchild.text

        return method_info if method_info["name"] else None

    def _extract_property_definition_with_decorators(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract property definition with decorators from class."""
        property_info: dict[str, Any] = {
            "name": "",
            "type": None,
            "decorators": [],
        }

        decorators: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "decorator":
                decorator_info = self._extract_decorator(child)
                if decorator_info:
                    decorators.append(decorator_info)
            elif child.type == "property_identifier":
                property_info["name"] = child.text or ""
            elif child.type == "type_annotation":
                for grandchild in child.children:
                    if grandchild.type != ":":
                        property_info["type"] = grandchild.text

        property_info["decorators"] = decorators
        return property_info if property_info["name"] else None

    def _extract_function(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract function declaration."""
        func_info: dict[str, Any] = {
            "name": "",
            "parameters": [],
            "return_type": None,
            "generics": [],
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        for child in node.children:
            if child.type == "identifier":
                func_info["name"] = child.text or ""
            elif child.type == "type_parameters":
                func_info["generics"] = self._extract_generic_params(child)
            elif child.type == "formal_parameters":
                func_info["parameters"] = self._extract_parameters(child)
            elif child.type == "type_annotation":
                for grandchild in child.children:
                    if grandchild.type != ":":
                        func_info["return_type"] = grandchild.text

        return func_info if func_info["name"] else None

    def _extract_arrow_function(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract arrow function from lexical declaration."""
        # Look for pattern: const name = (params) => { ... }
        func_name = None
        has_arrow = False

        for child in node.children:
            if child.type == "variable_declarator":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        func_name = grandchild.text
                    elif grandchild.type == "arrow_function":
                        has_arrow = True

        if func_name and has_arrow:
            return {
                "name": func_name,
                "parameters": [],
                "return_type": None,
                "type": "arrow",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
            }

        return None

    def _extract_parameters(self, params_node: ASTNode) -> list[str]:
        """Extract parameter names from formal parameters."""
        params: list[str] = []

        for child in params_node.children:
            if child.type == "required_parameter":
                # Extract parameter name
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        params.append(grandchild.text or "")
                        break
            elif child.type == "optional_parameter":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        params.append(grandchild.text or "")
                        break

        return params

    def _extract_import(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract import statement."""
        import_info: dict[str, Any] = {"source": None, "specifiers": []}

        for child in node.children:
            if child.type == "string":
                # Import source (remove quotes)
                source = child.text or ""
                import_info["source"] = source.strip("'\"")

        return import_info if import_info["source"] else None

    def _extract_export(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract export statement."""
        export_info: dict[str, Any] = {"type": "export", "name": None}

        # Check what is being exported
        for child in node.children:
            if child.type == "interface_declaration":
                interface_info = self._extract_interface(child)
                if interface_info:
                    export_info["name"] = interface_info["name"]
                    export_info["kind"] = "interface"
            elif child.type == "function_declaration":
                func_info = self._extract_function(child)
                if func_info:
                    export_info["name"] = func_info["name"]
                    export_info["kind"] = "function"
            elif child.type == "class_declaration":
                class_info = self._extract_class(child)
                if class_info:
                    export_info["name"] = class_info["name"]
                    export_info["kind"] = "class"

        return export_info if export_info["name"] else None

    def _extract_enum(self, node: ASTNode) -> dict[str, Any] | None:
        """Extract enum declaration."""
        enum_info: dict[str, Any] = {
            "name": "",
            "members": [],
            "is_const": False,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }

        # Check if it's a const enum
        parent_text = ""
        if hasattr(node, "text") and node.text:
            parent_text = node.text or ""
            if parent_text.startswith("const "):
                enum_info["is_const"] = True

        for child in node.children:
            if child.type in ["identifier", "type_identifier"]:
                enum_info["name"] = child.text or ""
            elif child.type == "enum_body":
                # Extract enum members
                enum_info["members"] = self._extract_enum_members(child)

        return enum_info if enum_info["name"] else None

    def _extract_enum_members(self, enum_body_node: ASTNode) -> list[dict[str, Any]]:
        """Extract enum members from enum body."""
        members: list[dict[str, Any]] = []

        for child in enum_body_node.children:
            if child.type == "property_identifier":
                # Simple enum member without value
                members.append({"name": child.text or "", "value": None})
            elif child.type in ["enum_assignment", "pair"]:
                # Enum member with value
                member_name = None
                member_value = None

                for grandchild in child.children:
                    if grandchild.type == "property_identifier":
                        member_name = grandchild.text or ""
                    elif grandchild.type in ["string", "number", "identifier"]:
                        member_value = grandchild.text

                if member_name:
                    members.append({"name": member_name, "value": member_value})

        return members

    def _extract_generic_params(self, type_params_node: ASTNode) -> list[str]:
        """Extract generic type parameters."""
        generics: list[str] = []

        for child in type_params_node.children:
            if child.type == "type_parameter":
                generic_text = child.text or ""
                generics.append(generic_text)

        return generics

    def _extract_decorator(self, decorator_node: ASTNode) -> dict[str, Any] | None:
        """Extract decorator information."""
        decorator_info: dict[str, Any] = {"name": "", "arguments": None}

        for child in decorator_node.children:
            if child.type == "identifier":
                decorator_info["name"] = child.text or ""
            elif child.type == "call_expression":
                # Decorator with arguments like @Component(...)
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        decorator_info["name"] = grandchild.text or ""
                    elif grandchild.type == "arguments":
                        # Capture arguments as raw text
                        decorator_info["arguments"] = grandchild.text or ""

        return decorator_info if decorator_info["name"] else None

    def _detect_framework_type(self, decorators: list[dict[str, Any]]) -> str | None:
        """Detect framework type from decorators."""
        angular_decorators = {
            "Component",
            "Directive",
            "Pipe",
            "Injectable",
            "NgModule",
        }
        nestjs_decorators = {
            "Controller",
            "Injectable",
            "Module",
            "Get",
            "Post",
            "Put",
            "Delete",
            "Patch",
        }
        typeorm_decorators = {
            "Entity",
            "Column",
            "PrimaryGeneratedColumn",
            "OneToMany",
            "ManyToOne",
        }

        decorator_names = {d["name"] for d in decorators}

        # Priority: angular > nestjs > typeorm
        if decorator_names & angular_decorators:
            return "angular"
        elif decorator_names & nestjs_decorators:
            return "nestjs"
        elif decorator_names & typeorm_decorators:
            return "typeorm"

        return None

    def _extract_variables(self, node: ASTNode) -> list[dict[str, Any]]:
        """Extract variable declarations (let, const, var)."""
        variables: list[dict[str, Any]] = []

        # Determine kind (let, const, var)
        kind = "let"  # default
        if node.type == "variable_declaration":
            kind = "var"
        else:
            # For lexical_declaration, check first keyword
            for child in node.children:
                if child.type in ["const", "let"]:
                    kind = child.type
                    break

        # Extract variable declarators
        for child in node.children:
            if child.type == "variable_declarator":
                var_info = self._extract_variable_declarator(child, kind)
                if var_info:
                    if isinstance(var_info, list):
                        variables.extend(var_info)
                    else:
                        variables.append(var_info)

        return variables

    def _extract_variable_declarator(
        self, node: ASTNode, kind: str
    ) -> dict[str, Any] | None | list[dict[str, Any]]:
        """Extract variable from declarator node."""
        var_name = None
        var_type = None

        for child in node.children:
            if child.type == "identifier":
                var_name = child.text or ""
            elif child.type == "type_annotation":
                # Extract type
                for grandchild in child.children:
                    if grandchild.type != ":":
                        var_type = grandchild.text
            elif child.type in ["object_pattern", "array_pattern"]:
                # Destructuring assignment
                return self._extract_destructuring_variables(child, kind, var_type)

        if var_name:
            return {
                "name": var_name,
                "kind": kind,
                "type": var_type,
                "line": node.start_point[0] + 1,
            }

        return None

    def _extract_destructuring_variables(
        self, pattern_node: ASTNode, kind: str, var_type: str | None
    ) -> list[dict[str, Any]]:
        """Extract variables from destructuring pattern."""
        variables: list[dict[str, Any]] = []

        for child in pattern_node.children:
            if child.type == "shorthand_property_identifier_pattern":
                # {name, age}
                var_name = child.text or ""
                if var_name:
                    variables.append(
                        {
                            "name": var_name,
                            "kind": kind,
                            "type": var_type,
                            "line": child.start_point[0] + 1,
                        }
                    )
            elif child.type == "identifier":
                # [first, second]
                var_name = child.text or ""
                if var_name and var_name not in ["...", ","]:
                    variables.append(
                        {
                            "name": var_name,
                            "kind": kind,
                            "type": var_type,
                            "line": child.start_point[0] + 1,
                        }
                    )
            elif child.type == "rest_pattern":
                # ...rest
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        var_name = grandchild.text or ""
                        if var_name:
                            variables.append(
                                {
                                    "name": var_name,
                                    "kind": kind,
                                    "type": var_type,
                                    "line": grandchild.start_point[0] + 1,
                                }
                            )

        return variables
