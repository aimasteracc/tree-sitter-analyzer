#!/usr/bin/env python3
"""
C/C++ specific table formatter.
Supports files with mixed classes/structs and global functions.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class CppTableFormatter(BaseTableFormatter):
    """Table formatter specialized for C and C++"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for C/C++"""
        lines = []

        # Header
        package_name = (data.get("package") or {}).get("name", "unknown")
        classes = data.get("classes", [])
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]

        # Title Logic
        # If we have a package/namespace, show it
        if package_name and package_name != "unknown":
            # If pure C, package might be empty. If C++, might be namespace.
            lines.append(f"# {file_name}")
        else:
            lines.append(f"# {file_name}")

        lines.append("")

        # Namespaces (Packages)
        packages = data.get("packages", [])
        if packages:
            lines.append("## Namespaces")
            for pkg in packages:
                lines.append(
                    f"- `{pkg.get('name')}` ({pkg.get('line_range', {}).get('start', 0)}-{pkg.get('line_range', {}).get('end', 0)})"
                )
            lines.append("")
        elif package_name and package_name != "unknown":
            lines.append("## Package")
            lines.append(f"`{package_name}`")
            lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append(f"```{data.get('language', 'cpp')}")
            for imp in imports:
                stmt = str(imp.get("statement", "")).strip()
                if stmt:
                    lines.append(stmt)
            lines.append("```")
            lines.append("")

        # Classes Overview
        if len(classes) > 0:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("type", "class"))
                visibility = str(
                    class_info.get("visibility", "public")
                )  # C/C++ default public for structs
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods/fields within the class range
                class_methods = [
                    m
                    for m in data.get("methods", [])
                    if line_range.get("start", 0)
                    <= m.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]
                class_fields = [
                    f
                    for f in data.get("fields", [])
                    if line_range.get("start", 0)
                    <= f.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | {len(class_methods)} | {len(class_fields)} |"
                )
            lines.append("")

            # Detailed Class Info
            for class_info in classes:
                lines.extend(self._format_class_details(class_info, data))

        # Global Functions (Orphans)
        # Identify methods that are not inside any class
        global_methods = []
        for m in data.get("methods", []):
            is_inside_class = False
            m_start = m.get("line_range", {}).get("start", 0)
            for c in classes:
                c_start = c.get("line_range", {}).get("start", 0)
                c_end = c.get("line_range", {}).get("end", 0)
                if c_start <= m_start <= c_end:
                    is_inside_class = True
                    break
            if not is_inside_class:
                global_methods.append(m)

        if global_methods:
            lines.append("## Global Functions")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|----|")
            for method in global_methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Global Variables (Fields)
        global_fields = []
        for f in data.get("fields", []):
            is_inside_class = False
            f_start = f.get("line_range", {}).get("start", 0)
            for c in classes:
                c_start = c.get("line_range", {}).get("start", 0)
                c_end = c.get("line_range", {}).get("end", 0)
                if c_start <= f_start <= c_end:
                    is_inside_class = True
                    break
            if not is_inside_class:
                global_fields.append(f)

        if global_fields:
            lines.append("## Global Variables")
            lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
            lines.append("|------|------|-----|-----------|------|-----|")
            for field in global_fields:
                name = str(field.get("name", ""))
                field_type = str(field.get("type", ""))
                visibility = self._convert_visibility(str(field.get("visibility", "")))
                modifiers = ",".join([str(m) for m in field.get("modifiers", [])])
                line = field.get("line_range", {}).get("start", 0)
                doc = str(field.get("javadoc", "")) or "-"
                doc = doc.replace("\n", " ").replace("|", "\\|")[:50]
                lines.append(
                    f"| {name} | {field_type} | {visibility} | {modifiers} | {line} | {doc} |"
                )
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_class_details(
        self, class_info: dict[str, Any], data: dict[str, Any]
    ) -> list[str]:
        """Format details for a single class"""
        lines = []
        name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

        lines.append(f"## {name} ({lines_str})")

        # Get methods/fields for this class
        class_methods = [
            m
            for m in data.get("methods", [])
            if line_range.get("start", 0)
            <= m.get("line_range", {}).get("start", 0)
            <= line_range.get("end", 0)
        ]
        class_fields = [
            f
            for f in data.get("fields", [])
            if line_range.get("start", 0)
            <= f.get("line_range", {}).get("start", 0)
            <= line_range.get("end", 0)
        ]

        if class_fields:
            lines.append("### Fields")
            lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
            lines.append("|------|------|-----|-----------|------|-----|")
            for field in class_fields:
                name_f = str(field.get("name", ""))
                type_f = str(field.get("type", ""))
                vis_f = self._convert_visibility(str(field.get("visibility", "")))
                mod_f = ",".join([str(m) for m in field.get("modifiers", [])])
                line_f = field.get("line_range", {}).get("start", 0)
                doc_f = str(field.get("javadoc", "")) or "-"
                lines.append(
                    f"| {name_f} | {type_f} | {vis_f} | {mod_f} | {line_f} | {doc_f} |"
                )
            lines.append("")

        if class_methods:
            # Just list all methods for simplicity, or split by visibility?
            # C structs usually public. C++ classes mixed.
            # Let's split by Private/Public like Java for consistency
            public_methods = [
                m
                for m in class_methods
                if "public" in m.get("modifiers", []) or m.get("visibility") == "public"
            ]
            private_methods = [
                m
                for m in class_methods
                if "private" in m.get("modifiers", [])
                or m.get("visibility") == "private"
            ]
            # Others?
            other_methods = [
                m
                for m in class_methods
                if m not in public_methods and m not in private_methods
            ]

            if public_methods:
                lines.append("### Public Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")
                for m in public_methods:
                    lines.append(self._format_method_row(m))
                lines.append("")

            if private_methods:
                lines.append("### Private Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")
                for m in private_methods:
                    lines.append(self._format_method_row(m))
                lines.append("")

            if other_methods:
                lines.append("### Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")
                for m in other_methods:
                    lines.append(self._format_method_row(m))
                lines.append("")

        return lines

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for C/C++"""
        lines = []

        # Header
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        package_name = (data.get("package") or {}).get("name", "unknown")
        language = data.get("language", "").lower()

        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")

        # Only show Package for C++ (which has namespaces)
        # C language doesn't have packages, so skip this row
        if language in ("cpp", "c++") or (package_name and package_name != "unknown"):
            lines.append(f"| Package | {package_name} |")

        lines.append(f"| Methods | {stats.get('method_count', 0)} |")
        lines.append(f"| Fields | {stats.get('field_count', 0)} |")
        lines.append("")

        # Methods (compact)
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")

            for method in methods:
                name = str(method.get("name", ""))
                signature = self._create_compact_signature(method)
                visibility = self._convert_visibility(str(method.get("visibility", "")))
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get("complexity_score", 0)
                doc = self._clean_csv_text(
                    self._extract_doc_summary(str(method.get("javadoc", "")))
                )

                lines.append(
                    f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"
                )
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self._convert_visibility(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        cols_str = "5-6"  # default placeholder
        complexity = method.get("complexity_score", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(method.get("javadoc", "")))
        )

        return f"| {name} | {signature} | {visibility} | {lines_str} | {cols_str} | {complexity} | {doc} |"

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature"""
        params = method.get("parameters", [])
        param_types = []

        for p in params:
            if isinstance(p, dict):
                # Dict format: {"name": "a", "type": "int"}
                type_str = p.get("type", "Any")
                name_str = p.get("name", "")

                # Check if name implies array (e.g. arr[])
                if "[]" in name_str:
                    type_str += "[]"

                # Check if name implies pointer (e.g. *ptr)
                # If TableCommand parsed "int *ptr" -> type="int", name="*ptr"
                if name_str.startswith("*") and not type_str.endswith("*"):
                    type_str += "*"
            elif isinstance(p, str):
                # String format: "a:int" or "int a" or "int* a"
                if ":" in p:
                    # Format: "name:type"
                    parts = p.split(":", 1)
                    type_str = parts[1].strip()
                else:
                    # Format: "type name" (C style)
                    # Split by space and take everything except last token (name)
                    tokens = p.strip().split()
                    if len(tokens) >= 2:
                        # Last token is name, everything before is type
                        type_str = " ".join(tokens[:-1])
                        name_part = tokens[-1]

                        # Check if name part implies array (e.g. arr[])
                        if "[]" in name_part:
                            type_str += "[]"

                        # Check if name part implies pointer (e.g. *ptr)
                        if name_part.startswith("*") and not type_str.endswith("*"):
                            type_str += "*"
                    else:
                        # Only one token, might be type-only or name-only
                        type_str = tokens[0] if tokens else "Any"
            else:
                type_str = "Any"

            # DEBUG
            # print(f"DEBUG: type_str='{type_str}' shortened='{self._shorten_type(type_str)}'")
            param_types.append(self._shorten_type(type_str))

        params_str = ",".join(param_types)
        return_type = self._shorten_type(method.get("return_type", "void"))

        return f"({params_str}):{return_type}"

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name for C/C++ compact display"""
        if type_name is None:
            return "void"

        s = str(type_name).strip()

        # Keep pointers, references, arrays as-is (important info)
        if any(x in s for x in ["*", "&", "["]):
            return s

        # Remove const/volatile/static qualifiers for brevity
        s = (
            s.replace("const ", "")
            .replace("volatile ", "")
            .replace("static ", "")
            .strip()
        )

        # Shorten common primitive types
        type_map = {
            "int": "i",
            "double": "d",
            "float": "f",
            "char": "c",
            "long": "l",
            "short": "s",
            "bool": "b",
            "void": "void",
            "size_t": "size_t",
            "string": "str",
        }

        return type_map.get(s, s)  # Return shortened or original

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output"""
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            if table_type == "json":
                return self._format_json(analysis_result)
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output"""
        return self._format_compact_table(analysis_result)

    def format_analysis_result(self, analysis_result: Any, table_type: str) -> str:
        """
        Format analysis result directly (C++ specific).
        Converts AnalysisResult to structure format with all namespaces extracted.
        """
        # Convert analysis result to structure format (with namespace extraction)
        formatted_data = self._convert_analysis_result_to_format(analysis_result)

        # Format based on table type
        if table_type == "full":
            return self._format_full_table(formatted_data)
        elif table_type == "compact":
            return self._format_compact_table(formatted_data)
        elif table_type == "csv":
            return self._format_csv(formatted_data)
        else:
            return self._format_full_table(formatted_data)

    def _convert_analysis_result_to_format(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        """
        Convert AnalysisResult to the format expected by C++ formatters.
        Extracts all namespaces (C++ specific) and categorizes elements.
        """
        from ..constants import (
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
            ELEMENT_TYPE_IMPORT,
            ELEMENT_TYPE_VARIABLE,
            get_element_type,
        )
        from ..models import Package

        classes = []
        methods = []
        fields = []
        imports = []
        packages = []  # For C++ namespaces

        _language = analysis_result.language  # noqa: F841 - stored for potential future use
        package_name = "unknown"  # Default for C/C++

        # Process each element
        for i, element in enumerate(analysis_result.elements):
            try:
                # First, check if element is a Package instance (most reliable check)
                # This avoids issues with get_element_type() misidentifying elements
                if isinstance(element, Package):
                    element_name = getattr(element, "name", None)
                    raw_text = getattr(element, "raw_text", "")

                    # Additional validation: raw_text should contain "namespace" keyword for C++
                    # This helps filter out misidentified elements
                    is_likely_namespace = (
                        not raw_text  # If no raw_text, trust the Package instance
                        or "namespace"
                        in raw_text.lower()  # Or raw_text contains "namespace"
                    )

                    if element_name and is_likely_namespace:
                        namespace_name = str(element_name).strip()

                        # Reject obviously invalid names:
                        # - Single letters (likely template parameters: T, U, V, or variables: x, y, z)
                        # - Common type names that are definitely not namespaces
                        if len(namespace_name) == 1:
                            continue

                        common_type_names = {
                            "int",
                            "double",
                            "float",
                            "char",
                            "bool",
                            "void",
                        }
                        if namespace_name.lower() in common_type_names:
                            continue

                        # Must be a valid identifier and have reasonable length (at least 2 characters)
                        if (
                            namespace_name
                            and namespace_name.isidentifier()
                            and len(namespace_name) >= 2
                        ):
                            package_name = namespace_name
                            packages.append(
                                {
                                    "name": namespace_name,
                                    "line_range": {
                                        "start": getattr(element, "start_line", 0),
                                        "end": getattr(element, "end_line", 0),
                                    },
                                }
                            )
                    continue  # Skip to next element, already processed as Package

                # For non-Package elements, use get_element_type() for categorization
                element_type = get_element_type(element)
                element_name = getattr(element, "name", None)

                if element_type == ELEMENT_TYPE_CLASS:
                    classes.append(self._convert_class_element(element, i))
                elif element_type == ELEMENT_TYPE_FUNCTION:
                    methods.append(self._convert_function_element(element))
                elif element_type == ELEMENT_TYPE_VARIABLE:
                    fields.append(self._convert_variable_element(element))
                elif element_type == ELEMENT_TYPE_IMPORT:
                    imports.append(self._convert_import_element(element))
            except Exception:  # nosec
                # Skip problematic elements silently
                continue

        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "package": {"name": package_name},
            "packages": packages,  # All C++ namespaces
            "classes": classes,
            "methods": methods,
            "fields": fields,
            "imports": imports,
            "statistics": {
                "method_count": len(methods),
                "field_count": len(fields),
                "class_count": len(classes),
                "import_count": len(imports),
            },
        }

    def _convert_class_element(self, element: Any, index: int) -> dict[str, Any]:
        """Convert class element to table format."""
        element_name = getattr(element, "name", None)
        final_name = element_name if element_name else f"UnknownClass_{index}"
        class_type = getattr(element, "class_type", "class")
        visibility = getattr(element, "visibility", "public")

        return {
            "name": final_name,
            "type": class_type,
            "visibility": visibility,
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
        }

    def _convert_function_element(self, element: Any) -> dict[str, Any]:
        """Convert function element to table format."""
        params = getattr(element, "parameters", [])

        # Parse parameters from string format to dict format for consistency
        # C++ parameters are in "type name" format (e.g., "int a", "T* ptr")
        processed_params = []
        for param in params:
            if isinstance(param, str):
                param = param.strip()
                # Split "type name" format
                # Find the last space to separate type from name
                last_space_idx = param.rfind(" ")
                if last_space_idx != -1:
                    param_type = param[:last_space_idx].strip()
                    param_name = param[last_space_idx + 1 :].strip()

                    # Handle array notation: name might be "arr[]"
                    # In this case, move [] to type
                    if "[]" in param_name:
                        param_type += "[]"
                        param_name = param_name.replace("[]", "")

                    if param_type and param_name:
                        processed_params.append(
                            {"name": param_name, "type": param_type}
                        )
                    else:
                        # Fallback: treat entire string as type
                        processed_params.append({"name": "param", "type": param})
                else:
                    # No space, treat as type-only (e.g., "void")
                    processed_params.append({"name": "param", "type": param})
            elif isinstance(param, dict):
                processed_params.append(param)
            else:
                processed_params.append({"name": str(param), "type": "Any"})

        visibility = getattr(element, "visibility", "public")

        return {
            "name": getattr(element, "name", str(element)),
            "visibility": visibility,
            "return_type": getattr(element, "return_type", "Any"),
            "parameters": processed_params,
            "is_constructor": getattr(element, "is_constructor", False),
            "is_static": getattr(element, "is_static", False),
            "complexity_score": getattr(element, "complexity_score", 1),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": "",
        }

    def _convert_variable_element(self, element: Any) -> dict[str, Any]:
        """Convert variable element to table format."""
        field_type = getattr(element, "variable_type", "")
        visibility = getattr(element, "visibility", "public")

        return {
            "name": getattr(element, "name", str(element)),
            "type": field_type,
            "visibility": visibility,
            "modifiers": getattr(element, "modifiers", []),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": "",
        }

    def _convert_import_element(self, element: Any) -> dict[str, Any]:
        """Convert import element to table format."""
        raw_text = getattr(element, "raw_text", "")
        statement = (
            raw_text
            if raw_text
            else f"#include {getattr(element, 'name', str(element))}"
        )

        return {
            "statement": statement,
            "raw_text": statement,
            "name": getattr(element, "name", str(element)),
            "module_name": getattr(element, "module_name", ""),
        }

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output"""
        if output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)

    def _format_json(self, data: dict[str, Any]) -> str:
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\\n"
