"""
TypeScript language parser - extracts functions, classes, interfaces, types, enums from TS source.

Uses tree-sitter for AST parsing and walks the tree to extract
structured information about TypeScript code elements.
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser


class TypeScriptParser:
    """
    TypeScript-specific parser that extracts structured code elements.

    Returns a dict with keys: ast, metadata, functions, classes, interfaces,
    types, enums, variables, imports, exports, errors.
    """

    def __init__(self) -> None:
        self._parser = TreeSitterParser("typescript")

    def parse(self, code: str, filename: str | None = None) -> dict[str, Any]:
        """Parse TypeScript code and extract structured elements."""
        result = self._parser.parse(code, filename)
        source_bytes = code.encode("utf-8")

        functions: list[dict[str, Any]] = []
        classes: list[dict[str, Any]] = []
        interfaces: list[dict[str, Any]] = []
        types: list[dict[str, Any]] = []
        enums: list[dict[str, Any]] = []
        variables: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []
        exports: list[dict[str, Any]] = []

        self._parser._ensure_initialized()
        ts_tree = self._parser._ts_parser.parse(source_bytes)
        root = ts_tree.root_node

        self._extract_from_node(
            root, source_bytes, functions, classes, interfaces,
            types, enums, variables, imports, exports
        )

        metadata = {
            "total_functions": len(functions),
            "total_classes": len(classes),
            "total_interfaces": len(interfaces),
            "total_types": len(types),
            "total_variables": len(variables),
        }

        parse_result: dict[str, Any] = {
            "ast": result.tree,
            "metadata": metadata,
            "functions": functions,
            "classes": classes,
            "interfaces": interfaces,
            "types": types,
            "enums": enums,
            "variables": variables,
            "imports": imports,
            "exports": exports,
        }

        if result.has_errors:
            parse_result["errors"] = True

        return parse_result

    def _extract_from_node(
        self, node: Any, src: bytes,
        functions: list, classes: list, interfaces: list,
        types: list, enums: list, variables: list,
        imports: list, exports: list,
    ) -> None:
        """Walk tree and extract top-level elements."""
        for child in node.children:
            t = child.type
            if t == "function_declaration":
                functions.append(self._extract_function(child, src))
            elif t == "class_declaration":
                classes.append(self._extract_class(child, src))
            elif t == "interface_declaration":
                interfaces.append(self._extract_interface(child, src))
            elif t == "type_alias_declaration":
                types.append(self._extract_type_alias(child, src))
            elif t == "enum_declaration":
                enums.append(self._extract_enum(child, src))
            elif t in ("lexical_declaration", "variable_declaration"):
                variables.extend(self._extract_variables(child, src, functions_out=functions))
            elif t == "import_statement":
                imports.append(self._extract_import(child, src))
            elif t == "export_statement":
                exp = self._extract_export(child, src)
                if exp:
                    exports.append(exp)
                # Also extract nested declarations from exports
                for sub in child.children:
                    if sub.type == "function_declaration":
                        functions.append(self._extract_function(sub, src))
                    elif sub.type == "class_declaration":
                        classes.append(self._extract_class(sub, src))
                    elif sub.type == "interface_declaration":
                        interfaces.append(self._extract_interface(sub, src))
                    elif sub.type == "type_alias_declaration":
                        types.append(self._extract_type_alias(sub, src))
                    elif sub.type == "enum_declaration":
                        enums.append(self._extract_enum(sub, src))
                    elif sub.type in ("lexical_declaration", "variable_declaration"):
                        variables.extend(self._extract_variables(sub, src, functions_out=functions))
            elif t == "expression_statement":
                # Could be arrow function assigned to variable
                pass

    def _extract_function(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract function information."""
        name = ""
        params: list[str] = []
        return_type: str | None = None
        generics: list[str] = []

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "formal_parameters":
                params = self._extract_params(child, src)
            elif child.type == "type_annotation":
                return_type = self._extract_type_annotation(child, src)
            elif child.type == "type_parameters":
                generics = self._extract_type_params(child, src)

        func: dict[str, Any] = {
            "name": name,
            "parameters": params,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }
        if return_type:
            func["return_type"] = return_type
        if generics:
            func["generics"] = generics
        return func

    def _extract_class(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract class information."""
        name = ""
        methods: list[dict[str, Any]] = []
        properties: list[dict[str, Any]] = []
        implements_list: list[str] = []
        generics: list[str] = []
        decorators: list[dict[str, Any]] = []

        # Check for decorators on parent
        if node.parent and node.parent.type == "export_statement":
            decorators = self._get_decorators(node.parent, src)
        decorators.extend(self._get_decorators(node, src))

        for child in node.children:
            if child.type == "type_identifier":
                name = self._text(child, src)
            elif child.type == "type_parameters":
                generics = self._extract_type_params(child, src)
            elif child.type == "class_body":
                pending_decorators: list[dict[str, Any]] = []
                for member in child.children:
                    if member.type == "decorator":
                        dec = self._extract_decorator(member, src)
                        if dec:
                            pending_decorators.append(dec)
                    elif member.type in ("method_definition", "method_signature"):
                        method = self._extract_method(member, src)
                        if pending_decorators:
                            method["decorators"] = pending_decorators
                            pending_decorators = []
                        methods.append(method)
                    elif member.type == "public_field_definition":
                        prop = self._extract_property(member, src)
                        if pending_decorators:
                            prop["decorators"] = pending_decorators
                            pending_decorators = []
                        properties.append(prop)
                    else:
                        pending_decorators = []  # Reset if unmatched

        # Extract implements clause (inside class_heritage > implements_clause)
        for child in node.children:
            if child.type == "class_heritage":
                for sub in child.children:
                    if sub.type == "implements_clause":
                        for impl_child in sub.children:
                            if impl_child.type == "type_identifier":
                                implements_list.append(self._text(impl_child, src))
                            elif impl_child.type == "generic_type":
                                for gsub in impl_child.children:
                                    if gsub.type == "type_identifier":
                                        implements_list.append(self._text(gsub, src))
                                        break

        cls: dict[str, Any] = {
            "name": name,
            "methods": methods,
            "properties": properties,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }
        if implements_list:
            cls["implements"] = implements_list
        if generics:
            cls["generics"] = generics
        if decorators:
            cls["decorators"] = decorators
            framework = self._detect_framework(decorators)
            if framework:
                cls["framework_type"] = framework
        return cls

    def _extract_interface(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract interface information."""
        name = ""
        properties: list[dict[str, Any]] = []
        methods: list[dict[str, Any]] = []
        generics: list[str] = []

        for child in node.children:
            if child.type == "type_identifier":
                name = self._text(child, src)
            elif child.type == "type_parameters":
                generics = self._extract_type_params(child, src)
            elif child.type in ("interface_body", "object_type"):
                for member in child.children:
                    if member.type == "property_signature":
                        prop = self._extract_prop_signature(member, src)
                        if prop:
                            properties.append(prop)
                    elif member.type == "method_signature":
                        meth = self._extract_method_signature(member, src)
                        if meth:
                            methods.append(meth)

        iface: dict[str, Any] = {
            "name": name,
            "properties": properties,
            "methods": methods,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }
        if generics:
            iface["generics"] = generics
        return iface

    def _extract_type_alias(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract type alias information."""
        name = ""
        generics: list[str] = []

        for child in node.children:
            if child.type == "type_identifier":
                name = self._text(child, src)
            elif child.type == "type_parameters":
                generics = self._extract_type_params(child, src)

        ta: dict[str, Any] = {"name": name}
        if generics:
            ta["generics"] = generics
        return ta

    def _extract_enum(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract enum information."""
        name = ""
        members: list[dict[str, Any]] = []
        is_const = False

        # Check for const keyword
        full_text = self._text(node, src)
        if full_text.strip().startswith("const "):
            is_const = True
        # Also check parent for const
        if node.parent and node.parent.type == "export_statement":
            parent_text = self._text(node.parent, src)
            if "const enum" in parent_text:
                is_const = True

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "enum_body":
                for member in child.children:
                    if member.type == "enum_assignment":
                        m = self._extract_enum_member(member, src)
                        if m:
                            members.append(m)
                    elif member.type == "property_identifier":
                        members.append({"name": self._text(member, src)})

        return {
            "name": name,
            "members": members,
            "is_const": is_const,
        }

    def _extract_enum_member(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Extract enum member."""
        name = ""
        value: str | None = None
        for child in node.children:
            if child.type == "property_identifier":
                name = self._text(child, src)
            elif child.type in ("string", "number", "identifier"):
                value = self._text(child, src)
        if name:
            result: dict[str, Any] = {"name": name}
            if value is not None:
                result["value"] = value
            return result
        return None

    def _extract_variables(self, node: Any, src: bytes,
                           functions_out: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Extract variable declarations. Also captures arrow functions."""
        variables: list[dict[str, Any]] = []
        kind = ""

        for child in node.children:
            if child.type in ("let", "const", "var"):
                kind = self._text(child, src)
            elif child.type == "variable_declarator":
                # Check if this is an arrow function assignment
                arrow = self._find_arrow_function(child, src)
                if arrow and functions_out is not None:
                    functions_out.append(arrow)
                else:
                    vars_list = self._extract_variable_declarator(child, src, kind)
                    variables.extend(vars_list)

        return variables

    def _find_arrow_function(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Check if a variable_declarator contains an arrow function."""
        name = ""
        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "arrow_function":
                func = self._extract_arrow_func(child, src, name)
                return func
        return None

    def _extract_arrow_func(self, node: Any, src: bytes, name: str) -> dict[str, Any]:
        """Extract arrow function info."""
        params: list[str] = []
        return_type: str | None = None
        generics: list[str] = []

        for child in node.children:
            if child.type == "formal_parameters":
                params = self._extract_params(child, src)
            elif child.type == "type_annotation":
                return_type = self._extract_type_annotation(child, src)
            elif child.type == "type_parameters":
                generics = self._extract_type_params(child, src)
            elif child.type == "identifier" and not name:
                name = self._text(child, src)

        func: dict[str, Any] = {
            "name": name,
            "parameters": params,
            "line_start": node.start_point[0] + 1,
            "line_end": node.end_point[0] + 1,
        }
        if return_type:
            func["return_type"] = return_type
        if generics:
            func["generics"] = generics
        return func

    def _extract_variable_declarator(self, node: Any, src: bytes, kind: str) -> list[dict[str, Any]]:
        """Extract variable(s) from a declarator, handling destructuring."""
        name = ""
        type_ann: str | None = None
        destructured_names: list[str] = []

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "type_annotation":
                type_ann = self._extract_type_annotation(child, src)
            elif child.type in ("object_pattern", "array_pattern"):
                destructured_names = self._extract_destructuring_names(child, src)

        if destructured_names:
            # Create separate variables for each destructured name
            results: list[dict[str, Any]] = []
            for dname in destructured_names:
                var: dict[str, Any] = {"name": dname, "kind": kind}
                if type_ann:
                    var["type"] = type_ann
                results.append(var)
            return results
        elif name:
            var = {"name": name, "kind": kind}
            if type_ann:
                var["type"] = type_ann
            return [var]
        return []

    def _extract_destructuring_names(self, node: Any, src: bytes) -> list[str]:
        """Extract individual names from destructuring patterns."""
        names: list[str] = []
        for child in node.children:
            if child.type == "shorthand_property_identifier_pattern":
                names.append(self._text(child, src))
            elif child.type == "identifier":
                names.append(self._text(child, src))
            elif child.type == "pair_pattern":
                # {key: value} pattern
                for sub in child.children:
                    if sub.type == "identifier":
                        names.append(self._text(sub, src))
        return names

    def _extract_import(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract import statement."""
        text = self._text(node, src)
        return {"text": text}

    def _extract_export(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Extract export statement."""
        text = self._text(node, src)
        return {"text": text}

    def _extract_method(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract class method."""
        name = ""
        params: list[str] = []
        decorators: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "property_identifier":
                name = self._text(child, src)
            elif child.type == "formal_parameters":
                params = self._extract_params(child, src)

        decorators = self._get_decorators(node, src)

        method: dict[str, Any] = {
            "name": name,
            "parameters": params,
        }
        if decorators:
            method["decorators"] = decorators
        return method

    def _extract_property(self, node: Any, src: bytes) -> dict[str, Any]:
        """Extract class property."""
        name = ""
        decorators: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "property_identifier":
                name = self._text(child, src)

        decorators = self._get_decorators(node, src)

        prop: dict[str, Any] = {"name": name}
        if decorators:
            prop["decorators"] = decorators
        return prop

    def _extract_prop_signature(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Extract interface property signature."""
        name = ""
        for child in node.children:
            if child.type == "property_identifier":
                name = self._text(child, src)
        if name:
            return {"name": name}
        return None

    def _extract_method_signature(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Extract interface method signature."""
        name = ""
        for child in node.children:
            if child.type == "property_identifier":
                name = self._text(child, src)
        if name:
            return {"name": name}
        return None

    def _extract_params(self, node: Any, src: bytes) -> list[str]:
        """Extract parameter names."""
        params: list[str] = []
        for child in node.children:
            if child.type == "required_parameter" or child.type == "optional_parameter":
                for sub in child.children:
                    if sub.type == "identifier":
                        params.append(self._text(sub, src))
                        break
            elif child.type == "identifier":
                params.append(self._text(child, src))
        return params

    def _extract_type_annotation(self, node: Any, src: bytes) -> str:
        """Extract type from type_annotation node."""
        # Skip the ':' and get the type
        for child in node.children:
            if child.type != ":":
                return self._text(child, src)
        return ""

    def _extract_type_params(self, node: Any, src: bytes) -> list[str]:
        """Extract generic type parameters."""
        params: list[str] = []
        for child in node.children:
            if child.type == "type_parameter":
                for sub in child.children:
                    if sub.type == "type_identifier":
                        params.append(self._text(sub, src))
                        break
        return params

    def _get_decorators(self, node: Any, src: bytes) -> list[dict[str, Any]]:
        """Get decorators from a node."""
        decorators: list[dict[str, Any]] = []
        for child in node.children:
            if child.type == "decorator":
                dec = self._extract_decorator(child, src)
                if dec:
                    decorators.append(dec)
        return decorators

    def _extract_decorator(self, node: Any, src: bytes) -> dict[str, Any] | None:
        """Extract decorator information."""
        name = ""
        arguments: str | None = None

        for child in node.children:
            if child.type == "identifier":
                name = self._text(child, src)
            elif child.type == "call_expression":
                for sub in child.children:
                    if sub.type == "identifier":
                        name = self._text(sub, src)
                    elif sub.type == "arguments":
                        arguments = self._text(sub, src)

        if name:
            dec: dict[str, Any] = {"name": name}
            if arguments:
                dec["arguments"] = arguments
            return dec
        return None

    def _detect_framework(self, decorators: list[dict[str, Any]]) -> str | None:
        """Detect framework from decorators."""
        angular = {"Component", "Injectable", "NgModule", "Directive", "Pipe", "Input", "Output"}
        for dec in decorators:
            if dec.get("name") in angular:
                return "angular"
        return None

    def _text(self, node: Any, src: bytes) -> str:
        """Get text content of a node."""
        return src[node.start_byte:node.end_byte].decode("utf-8")
