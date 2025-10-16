#!/usr/bin/env python3
"""
TypeScript-specific table formatter.

Provides specialized formatting for TypeScript code analysis results,
handling TypeScript-specific features like interfaces, type aliases, enums,
generics, decorators, and modern JavaScript features with type annotations.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class TypeScriptTableFormatter(BaseTableFormatter):
    """Table formatter specialized for TypeScript"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data using the configured format type"""
        return self.format_structure(data)

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for TypeScript"""
        lines = []

        # Header - TypeScript (module/file based)
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        module_name = (
            file_name.replace(".ts", "").replace(".tsx", "").replace(".d.ts", "")
        )

        # Check if this is a module (has exports, classes, interfaces, or functions)
        exports = data.get("exports", [])
        classes = data.get("classes", [])
        interfaces = data.get("interfaces", [])
        functions = data.get("functions", [])
        is_module = (
            len(exports) > 0
            or len(classes) > 0
            or len(interfaces) > 0
            or len(functions) > 0
        )
        is_declaration_file = file_name.endswith(".d.ts")
        is_tsx = file_name.endswith(".tsx")

        if is_declaration_file:
            lines.append(f"# Declaration File: {module_name}")
        elif is_tsx:
            lines.append(f"# TSX Module: {module_name}")
        elif is_module:
            lines.append(f"# TypeScript Module: {module_name}")
        else:
            lines.append(f"# TypeScript Script: {module_name}")
        lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```typescript")
            for imp in imports:
                import_statement = imp.get("statement", "")
                if not import_statement:
                    # Construct import statement from parts
                    source = imp.get("source", "")
                    name = imp.get("name", "")
                    is_type_import = imp.get("is_type_import", False)
                    if name and source:
                        type_prefix = "type " if is_type_import else ""
                        import_statement = f"import {type_prefix}{name} from {source};"
                lines.append(import_statement)
            lines.append("```")
            lines.append("")

        # Module Info
        stats = data.get("statistics", {})
        classes = data.get("classes", [])
        interfaces = [c for c in classes if c.get("class_type") == "interface"]
        type_aliases = [c for c in classes if c.get("class_type") == "type"]
        enums = [c for c in classes if c.get("class_type") == "enum"]
        actual_classes = [
            c for c in classes if c.get("class_type") in ["class", "abstract_class"]
        ]

        lines.append("## Module Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| File | {file_name} |")
        lines.append(
            f"| Type | {'Declaration File' if is_declaration_file else 'TSX Module' if is_tsx else 'TypeScript Module' if is_module else 'TypeScript Script'} |"
        )
        lines.append(f"| Functions | {stats.get('function_count', 0)} |")
        lines.append(f"| Classes | {len(actual_classes)} |")
        lines.append(f"| Interfaces | {len(interfaces)} |")
        lines.append(f"| Type Aliases | {len(type_aliases)} |")
        lines.append(f"| Enums | {len(enums)} |")
        lines.append(f"| Variables | {stats.get('variable_count', 0)} |")
        lines.append(f"| Exports | {len(exports)} |")
        lines.append("")

        # Interfaces (TypeScript specific)
        if interfaces:
            lines.append("## Interfaces")
            lines.append(
                "| Interface | Extends | Lines | Properties | Methods | Generics |"
            )
            lines.append(
                "|-----------|---------|-------|------------|---------|----------|"
            )

            for interface in interfaces:
                name = str(interface.get("name", "Unknown"))
                extends = ", ".join(interface.get("interfaces", [])) or "-"
                line_range = interface.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count properties and methods within the interface
                interface_properties = [
                    v
                    for v in data.get("variables", [])
                    if line_range.get("start", 0)
                    <= v.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                    and v.get("declaration_kind") == "property_signature"
                ]

                interface_methods = [
                    m
                    for m in data.get("methods", [])
                    if line_range.get("start", 0)
                    <= m.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                    and m.get("is_signature", False)
                ]

                generics = ", ".join(interface.get("generics", [])) or "-"

                lines.append(
                    f"| {name} | {extends} | {lines_str} | {len(interface_properties)} | {len(interface_methods)} | {generics} |"
                )
            lines.append("")

        # Type Aliases (TypeScript specific)
        if type_aliases:
            lines.append("## Type Aliases")
            lines.append("| Type | Lines | Generics | Definition |")
            lines.append("|------|-------|----------|------------|")

            for type_alias in type_aliases:
                name = str(type_alias.get("name", "Unknown"))
                line_range = type_alias.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                generics = ", ".join(type_alias.get("generics", [])) or "-"

                # Extract type definition from raw text
                raw_text = type_alias.get("raw_text", "")
                if "=" in raw_text:
                    definition = raw_text.split("=", 1)[1].strip().rstrip(";")[:50]
                    if len(definition) > 47:
                        definition = definition[:47] + "..."
                else:
                    definition = "-"

                lines.append(f"| {name} | {lines_str} | {generics} | {definition} |")
            lines.append("")

        # Enums (TypeScript specific)
        if enums:
            lines.append("## Enums")
            lines.append("| Enum | Lines | Values |")
            lines.append("|------|-------|--------|")

            for enum in enums:
                name = str(enum.get("name", "Unknown"))
                line_range = enum.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count enum values (simplified)
                raw_text = enum.get("raw_text", "")
                value_count = raw_text.count(",") + 1 if raw_text.count("{") > 0 else 0

                lines.append(f"| {name} | {lines_str} | {value_count} |")
            lines.append("")

        # Classes
        if actual_classes:
            lines.append("## Classes")
            lines.append(
                "| Class | Type | Extends | Implements | Lines | Methods | Properties | Generics |"
            )
            lines.append(
                "|-------|------|---------|------------|-------|---------|------------|----------|"
            )

            for class_info in actual_classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = class_info.get("class_type", "class")
                extends = str(class_info.get("superclass", "")) or "-"
                implements = ", ".join(class_info.get("interfaces", [])) or "-"
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                generics = ", ".join(class_info.get("generics", [])) or "-"

                # Count methods within the class
                class_methods = [
                    m
                    for m in data.get("functions", [])
                    if (
                        line_range.get("start", 0)
                        <= m.get("line_range", {}).get("start", 0)
                        <= line_range.get("end", 0)
                        and m.get("is_method", False)
                        and not m.get("is_signature", False)
                    )
                ]

                # Count properties (class fields)
                class_properties = [
                    v
                    for v in data.get("variables", [])
                    if line_range.get("start", 0)
                    <= v.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                    and v.get("declaration_kind") == "property"
                ]

                lines.append(
                    f"| {name} | {class_type} | {extends} | {implements} | {lines_str} | {len(class_methods)} | {len(class_properties)} | {generics} |"
                )
            lines.append("")

        # Functions
        functions = data.get("functions", [])
        if functions:
            lines.append("## Functions")
            lines.append(
                "| Function | Type | Return Type | Parameters | Async | Generic | Lines | Complexity |"
            )
            lines.append(
                "|----------|------|-------------|------------|-------|---------|-------|------------|"
            )

            for func in functions:
                name = str(func.get("name", "Unknown"))
                func_type = (
                    "arrow"
                    if func.get("is_arrow")
                    else "method"
                    if func.get("is_method")
                    else "function"
                )
                return_type = str(func.get("return_type", "any"))
                params = func.get("parameters", [])
                param_count = len(params)
                is_async = "✓" if func.get("is_async") else ""
                has_generics = "✓" if func.get("generics") else ""
                line_range = func.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = func.get("complexity_score", 1)

                lines.append(
                    f"| {name} | {func_type} | {return_type} | {param_count} | {is_async} | {has_generics} | {lines_str} | {complexity} |"
                )
            lines.append("")

        # Variables/Properties
        variables = data.get("variables", [])
        if variables:
            lines.append("## Variables & Properties")
            lines.append(
                "| Name | Type | Kind | Visibility | Static | Optional | Lines |"
            )
            lines.append(
                "|------|------|------|------------|--------|----------|-------|"
            )

            for var in variables:
                name = str(var.get("name", "Unknown"))
                var_type = str(var.get("variable_type", "any"))
                kind = var.get("declaration_kind", "variable")
                visibility = var.get("visibility", "public")
                is_static = "✓" if var.get("is_static") else ""
                is_optional = "✓" if var.get("is_optional") else ""
                line_range = var.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                lines.append(
                    f"| {name} | {var_type} | {kind} | {visibility} | {is_static} | {is_optional} | {lines_str} |"
                )
            lines.append("")

        # Exports
        if exports:
            lines.append("## Exports")
            lines.append("| Export | Type | Default |")
            lines.append("|--------|------|---------|")

            for export in exports:
                names = export.get("names", [])
                export_type = export.get("type", "unknown")
                is_default = "✓" if export.get("is_default") else ""

                for name in names:
                    lines.append(f"| {name} | {export_type} | {is_default} |")
            lines.append("")

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for TypeScript"""
        lines = []

        # Header
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Summary
        classes = data.get("classes", [])
        functions = data.get("functions", [])
        variables = data.get("variables", [])

        interfaces = len([c for c in classes if c.get("class_type") == "interface"])
        type_aliases = len([c for c in classes if c.get("class_type") == "type"])
        enums = len([c for c in classes if c.get("class_type") == "enum"])
        actual_classes = len(
            [c for c in classes if c.get("class_type") in ["class", "abstract_class"]]
        )

        lines.append("## Summary")
        lines.append(f"- **Classes**: {actual_classes}")
        lines.append(f"- **Interfaces**: {interfaces}")
        lines.append(f"- **Type Aliases**: {type_aliases}")
        lines.append(f"- **Enums**: {enums}")
        lines.append(f"- **Functions**: {len(functions)}")
        lines.append(f"- **Variables**: {len(variables)}")
        lines.append("")

        # Main elements
        if classes:
            lines.append("## Types")
            for class_info in classes:
                name = class_info.get("name", "Unknown")
                class_type = class_info.get("class_type", "class")
                line_range = class_info.get("line_range", {})
                lines_str = f"L{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                lines.append(f"- **{name}** ({class_type}) - {lines_str}")
            lines.append("")

        if functions:
            lines.append("## Functions")
            for func in functions:
                name = func.get("name", "Unknown")
                return_type = func.get("return_type", "any")
                line_range = func.get("line_range", {})
                lines_str = f"L{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                async_marker = " (async)" if func.get("is_async") else ""
                lines.append(
                    f"- **{name}**(): {return_type}{async_marker} - {lines_str}"
                )
            lines.append("")

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for TypeScript"""
        lines = []

        # Header
        lines.append("Type,Name,Kind,Return/Type,Lines,Visibility,Static,Async,Generic")

        # Classes, interfaces, types, enums
        classes = data.get("classes", [])
        for class_info in classes:
            name = class_info.get("name", "")
            class_type = class_info.get("class_type", "class")
            line_range = class_info.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            visibility = class_info.get("visibility", "public")
            is_static = "true" if class_info.get("is_static") else "false"
            has_generics = "true" if class_info.get("generics") else "false"

            lines.append(
                f"Class,{name},{class_type},,{lines_str},{visibility},{is_static},,{has_generics}"
            )

        # Functions
        functions = data.get("functions", [])
        for func in functions:
            name = func.get("name", "")
            func_type = (
                "arrow"
                if func.get("is_arrow")
                else "method"
                if func.get("is_method")
                else "function"
            )
            return_type = func.get("return_type", "any")
            line_range = func.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            visibility = func.get("visibility", "public")
            is_static = "true" if func.get("is_static") else "false"
            is_async = "true" if func.get("is_async") else "false"
            has_generics = "true" if func.get("generics") else "false"

            lines.append(
                f"Function,{name},{func_type},{return_type},{lines_str},{visibility},{is_static},{is_async},{has_generics}"
            )

        # Variables
        variables = data.get("variables", [])
        for var in variables:
            name = var.get("name", "")
            kind = var.get("declaration_kind", "variable")
            var_type = var.get("variable_type", "any")
            line_range = var.get("line_range", {})
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
            visibility = var.get("visibility", "public")
            is_static = "true" if var.get("is_static") else "false"

            lines.append(
                f"Variable,{name},{kind},{var_type},{lines_str},{visibility},{is_static},,"
            )

        return "\n".join(lines)

    def _get_element_type_name(self, element: dict[str, Any]) -> str:
        """Get human-readable type name for TypeScript elements"""
        element_type = element.get("element_type", "unknown")

        if element_type == "class":
            class_type = element.get("class_type", "class")
            if class_type == "interface":
                return "Interface"
            elif class_type == "type":
                return "Type Alias"
            elif class_type == "enum":
                return "Enum"
            elif class_type == "abstract_class":
                return "Abstract Class"
            else:
                return "Class"
        elif element_type == "function":
            if element.get("is_arrow"):
                return "Arrow Function"
            elif element.get("is_method"):
                return "Method"
            elif element.get("is_constructor"):
                return "Constructor"
            else:
                return "Function"
        elif element_type == "variable":
            kind = element.get("declaration_kind", "variable")
            if kind == "property":
                return "Property"
            elif kind == "property_signature":
                return "Property Signature"
            else:
                return "Variable"
        elif element_type == "import":
            return "Import"
        else:
            return element_type.title()

    def _format_element_details(self, element: dict[str, Any]) -> str:
        """Format TypeScript-specific element details"""
        details = []

        # Type annotations
        if element.get("has_type_annotations"):
            details.append("typed")

        # Generics
        if element.get("generics"):
            generics = ", ".join(element.get("generics", []))
            details.append(f"<{generics}>")

        # Visibility
        visibility = element.get("visibility")
        if visibility and visibility != "public":
            details.append(visibility)

        # Modifiers
        if element.get("is_static"):
            details.append("static")
        if element.get("is_async"):
            details.append("async")
        if element.get("is_abstract"):
            details.append("abstract")
        if element.get("is_optional"):
            details.append("optional")

        # Framework specific
        framework = element.get("framework_type")
        if framework:
            details.append(f"{framework}")

        return " ".join(details) if details else ""
