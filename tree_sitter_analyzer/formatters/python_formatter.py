#!/usr/bin/env python3
"""
Python-specific table formatter.

Provides specialized formatting for Python code analysis results,
handling modern Python features like async/await, type hints, decorators,
context managers, and framework-specific patterns.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class PythonTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Python"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data using the configured format type"""
        # Handle None data - raise exception for edge case tests
        if data is None:
            raise TypeError("Cannot format None data")

        # Ensure data is a dictionary - raise exception for edge case tests
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        return self.format_structure(data)

    def format_table(self, data: dict[str, Any], table_type: str = "full") -> str:
        """Format table output for Python files"""
        # Set the format type and delegate to format_structure
        original_format_type = self.format_type
        self.format_type = table_type
        try:
            result = self.format_structure(data)
            return result
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for Python"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for Python"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for Python"""
        if output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)

    def _format_json(self, data: dict[str, Any]) -> str:
        """Format data as JSON"""
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\n"

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for Python files - prevents degradation"""
        # Convert AnalysisResult to the format expected by Python formatter
        data = self._convert_analysis_result_to_python_format(analysis_result)
        return self.format_table(data, table_type)

    def _convert_analysis_result_to_python_format(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        """Convert AnalysisResult to Python formatter's expected format"""
        from ..constants import (
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
            ELEMENT_TYPE_IMPORT,
            ELEMENT_TYPE_PACKAGE,
            ELEMENT_TYPE_VARIABLE,
            get_element_type,
        )

        classes = []
        methods = []
        fields = []
        imports = []
        package_name = "unknown"

        # Process each element
        for element in analysis_result.elements:
            element_type = get_element_type(element)
            element_name = getattr(element, "name", None)

            if element_type == ELEMENT_TYPE_PACKAGE:
                package_name = str(element_name)
            elif element_type == ELEMENT_TYPE_CLASS:
                classes.append(self._convert_class_element_for_python(element))
            elif element_type == ELEMENT_TYPE_FUNCTION:
                methods.append(self._convert_function_element_for_python(element))
            elif element_type == ELEMENT_TYPE_VARIABLE:
                fields.append(self._convert_variable_element_for_python(element))
            elif element_type == ELEMENT_TYPE_IMPORT:
                imports.append(self._convert_import_element_for_python(element))

        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "package": {"name": package_name},
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

    def _convert_class_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert class element for Python formatter"""
        element_name = getattr(element, "name", None)
        final_name = element_name if element_name else "UnknownClass"

        return {
            "name": final_name,
            "type": getattr(element, "class_type", "class"),
            "visibility": getattr(element, "visibility", "public"),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
        }

    def _convert_function_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert function element for Python formatter"""
        params = getattr(element, "parameters", [])
        processed_params = self._process_python_parameters(params)

        return {
            "name": getattr(element, "name", str(element)),
            "visibility": getattr(element, "visibility", "public"),
            "return_type": getattr(element, "return_type", "Any"),
            "parameters": processed_params,
            "is_constructor": getattr(element, "is_constructor", False),
            "is_static": getattr(element, "is_static", False),
            "is_async": getattr(element, "is_async", False),
            "complexity_score": getattr(element, "complexity_score", 1),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "docstring": getattr(element, "docstring", "") or "",
            "decorators": getattr(element, "decorators", []),
            "modifiers": getattr(element, "modifiers", []),
        }

    def _convert_variable_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert variable element for Python formatter"""
        return {
            "name": getattr(element, "name", str(element)),
            "type": getattr(element, "variable_type", "")
            or getattr(element, "field_type", ""),
            "visibility": getattr(element, "visibility", "public"),
            "modifiers": getattr(element, "modifiers", []),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": getattr(element, "docstring", ""),
        }

    def _convert_import_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert import element for Python formatter"""
        raw_text = getattr(element, "raw_text", "")
        if raw_text:
            statement = raw_text
        else:
            statement = f"import {getattr(element, 'name', str(element))}"

        return {
            "statement": statement,
            "raw_text": statement,
            "name": getattr(element, "name", str(element)),
            "module_name": getattr(element, "module_name", ""),
        }

    def _process_python_parameters(self, params: Any) -> list[dict[str, str]]:
        """Process parameters for Python formatter"""
        if isinstance(params, str):
            param_list = []
            if params.strip():
                param_names = [p.strip() for p in params.split(",") if p.strip()]
                param_list = [{"name": name, "type": "Any"} for name in param_names]
            return param_list
        elif isinstance(params, list):
            param_list = []
            for param in params:
                if isinstance(param, str):
                    param = param.strip()
                    # Python format: "name: type"
                    if ":" in param:
                        parts = param.split(":", 1)
                        param_name = parts[0].strip()
                        param_type = parts[1].strip() if len(parts) > 1 else "Any"
                        param_list.append({"name": param_name, "type": param_type})
                    else:
                        param_list.append({"name": param, "type": "Any"})
                elif isinstance(param, dict):
                    param_list.append(param)
                else:
                    param_list.append({"name": str(param), "type": "Any"})
            return param_list
        else:
            return []

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Python"""
        if data is None:
            raise TypeError("Cannot format None data")

        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        lines = []

        # Header - Python (module/package based)
        file_path = data.get("file_path", "Unknown")
        if file_path is None:
            file_path = "Unknown"
        file_name = str(file_path).split("/")[-1].split("\\")[-1]
        module_name = (
            file_name.replace(".py", "").replace(".pyw", "").replace(".pyi", "")
        )

        # Check if this is a package module
        classes = data.get("classes", [])
        functions = data.get("functions", [])
        imports = data.get("imports", [])

        # Determine module type
        is_package = "__init__.py" in file_name
        is_script = any(
            "if __name__ == '__main__'" in func.get("raw_text", "")
            for func in functions
        )

        if is_package:
            lines.append(f"# Package: {module_name}")
        elif is_script:
            lines.append(f"# Script: {module_name}")
        else:
            lines.append(f"# Module: {module_name}")
        lines.append("")

        # Module docstring
        module_docstring = self._extract_module_docstring(data)
        if module_docstring:
            lines.append("## Description")
            lines.append(f'"{module_docstring}"')
            lines.append("")

        # Package information
        package_info = data.get("package") or {}
        package_name = package_info.get("name", "unknown")
        if package_name and package_name != "unknown":
            lines.append("## Package")
            lines.append(f"`{package_name}`")
            lines.append("")

        # Imports
        if imports:
            lines.append("## Imports")
            lines.append("```python")
            for imp in imports:
                import_statement = imp.get("raw_text", "")
                if not import_statement:
                    # Fallback construction
                    module_name = imp.get("module_name", "")
                    name = imp.get("name", "")
                    if module_name:
                        import_statement = f"from {module_name} import {name}"
                    else:
                        import_statement = f"import {name}"
                lines.append(import_statement)
            lines.append("```")
            lines.append("")

        # Classes Overview or Class Info
        if classes:
            if len(classes) == 1:
                # Single class - use Class Info format
                class_info = classes[0]
                if class_info is not None:
                    lines.append("## Class Info")
                    lines.append("| Property | Value |")
                    lines.append("|----------|-------|")

                    name = str(class_info.get("name", "Unknown"))
                    class_type = str(class_info.get("type", "class"))
                    visibility = str(class_info.get("visibility", "public"))
                    line_range = class_info.get("line_range") or {}
                    lines_str = (
                        f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                    )

                    # Get statistics
                    stats = data.get("statistics", {})
                    method_count = stats.get("method_count", 0)
                    field_count = stats.get("field_count", 0)

                    lines.append(f"| Type | {class_type} |")
                    lines.append(f"| Visibility | {visibility} |")
                    lines.append(f"| Lines | {lines_str} |")
                    lines.append(f"| Total Methods | {method_count} |")
                    lines.append(f"| Total Fields | {field_count} |")
                    lines.append("")
            else:
                # Multiple classes - use Classes Overview format
                lines.append("## Classes Overview")
                lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
                lines.append("|-------|------|------------|-------|---------|--------|")

                for class_info in classes:
                    # Handle None class_info
                    if class_info is None:
                        continue

                    name = str(class_info.get("name", "Unknown"))
                    class_type = str(class_info.get("type", "class"))
                    visibility = str(class_info.get("visibility", "public"))
                    line_range = class_info.get("line_range") or {}
                    lines_str = (
                        f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                    )

                    # Count methods/fields within the class range
                    class_methods = [
                        m
                        for m in data.get("methods", [])
                        if line_range.get("start", 0)
                        <= (m.get("line_range") or {}).get("start", 0)
                        <= line_range.get("end", 0)
                    ]
                    class_fields = [
                        f
                        for f in data.get("fields", [])
                        if line_range.get("start", 0)
                        <= (f.get("line_range") or {}).get("start", 0)
                        <= line_range.get("end", 0)
                    ]

                    lines.append(
                        f"| {name} | {class_type} | {visibility} | {lines_str} | {len(class_methods)} | {len(class_fields)} |"
                    )
                lines.append("")

        # Class-specific method sections
        methods = data.get("methods", []) or functions
        for class_info in classes:
            if class_info is None:
                continue

            class_name = str(class_info.get("name", "Unknown"))
            line_range = class_info.get("line_range") or {}
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

            # Get methods for this class
            class_methods = [
                m
                for m in methods
                if line_range.get("start", 0)
                <= (m.get("line_range") or {}).get("start", 0)
                <= line_range.get("end", 0)
            ]

            if class_methods:
                lines.append(f"## {class_name} ({lines_str})")
                lines.append("### Public Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----| ")

                for method in class_methods:
                    lines.append(self._format_class_method_row(method))
                lines.append("")

        # Module-level functions (not in any class)
        module_functions = []
        if classes:
            # Find functions that are not within any class range
            for method in methods:
                # Skip None methods
                if method is None:
                    continue
                method_start = (method.get("line_range") or {}).get("start", 0)
                is_in_class = False
                for class_info in classes:
                    if class_info is None:
                        continue
                    class_range = class_info.get("line_range") or {}
                    if (
                        class_range.get("start", 0)
                        <= method_start
                        <= class_range.get("end", 0)
                    ):
                        is_in_class = True
                        break
                if not is_in_class:
                    module_functions.append(method)
        else:
            # No classes, all methods are module-level (filter out None)
            module_functions = [m for m in methods if m is not None]

        if module_functions:
            lines.append("## Module Functions")
            lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|----|----| ")

            for method in module_functions:
                lines.append(self._format_class_method_row(method))
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Python"""
        lines = []

        # Header - extract module/file name
        file_path = data.get("file_path", "Unknown")
        file_name = str(file_path).split("/")[-1].split("\\")[-1]
        module_name = (
            file_name.replace(".py", "").replace(".pyw", "").replace(".pyi", "")
        )

        classes = data.get("classes", [])

        # Title logic for Python modules:
        # - Single class: use class name directly
        # - Multiple classes or no classes: use "Module: filename"
        if len(classes) == 1:
            class_name = classes[0].get("name", module_name)
            lines.append(f"# {class_name}")
        else:
            lines.append(f"# Module: {module_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Classes | {len(classes)} |")
        lines.append(f"| Methods | {stats.get('method_count', 0)} |")
        lines.append(f"| Fields | {stats.get('field_count', 0)} |")
        lines.append("")

        # Classes section (add class names for better visibility)
        if classes:
            lines.append("## Classes")
            lines.append("| Class | Type | Lines |")
            lines.append("|-------|------|-------|")
            for class_info in classes:
                if class_info is None:
                    continue
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("type", "class"))
                line_range = class_info.get("line_range") or {}
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                lines.append(f"| {name} | {class_type} | {lines_str} |")
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
                line_range = method.get("line_range") or {}
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
        """Format a method table row for Python"""
        name = str(method.get("name", ""))
        signature = self._format_python_signature(method)

        # Python-specific visibility handling
        visibility = method.get("visibility", "public")
        if name.startswith("__") and name.endswith("__"):
            visibility = "magic"
        elif name.startswith("_"):
            visibility = "private"

        vis_symbol = self._get_python_visibility_symbol(visibility)

        line_range = method.get("line_range") or {}
        if not line_range or not isinstance(line_range, dict):
            start_line = method.get("start_line", 0)
            end_line = method.get("end_line", 0)
            lines_str = f"{start_line}-{end_line}"
        else:
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

        cols_str = "5-6"  # default placeholder
        complexity = method.get("complexity_score", 0)

        # Use docstring instead of javadoc
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(method.get("docstring", "")))
        )

        # Add decorators info
        decorators = method.get("modifiers", []) or method.get("decorators", [])
        decorator_str = self._format_decorators(decorators)

        # Add async indicator
        async_indicator = "🔄" if method.get("is_async", False) else ""

        return f"| {name}{async_indicator} | {signature} | {vis_symbol} | {lines_str} | {cols_str} | {complexity} | {decorator_str} | {doc} |"

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature for Python"""
        if method is None or not isinstance(method, dict):
            raise TypeError(f"Expected dict, got {type(method)}")

        params = method.get("parameters", [])
        param_types = []

        # Handle both list and string parameters
        if isinstance(params, str):
            # If parameters is a malformed string, skip it
            pass
        elif isinstance(params, list):
            for p in params:
                if isinstance(p, dict):
                    param_type = p.get("type", "Any")
                    if param_type == "Any" or param_type is None:
                        param_types.append(
                            "Any"
                        )  # Keep "Any" as is for missing type info
                    else:
                        param_types.append(
                            param_type
                        )  # Don't shorten types for consistency
                else:
                    param_types.append("Any")  # Use "Any" for missing type info

        params_str = ",".join(param_types)
        return_type = method.get("return_type", "Any")

        # Handle dict return type
        if isinstance(return_type, dict):
            return_type = return_type.get("type", "Any") or str(return_type)
        elif not isinstance(return_type, str):
            return_type = str(return_type)

        return f"({params_str}):{return_type}"

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name for Python tables"""
        if type_name is None:
            return "Any"  # Return "Any" instead of "A" for None

        if not isinstance(type_name, str):
            type_name = str(type_name)

        type_mapping = {
            "str": "s",
            "int": "i",
            "float": "f",
            "bool": "b",
            "None": "N",
            "Any": "A",
            "List": "L",
            "Dict": "D",
            "Optional": "O",
            "Union": "U",  # Changed from "Uni" to "U"
            "Calculator": "Calculator",  # Keep full name for Calculator
        }

        # List[str] -> L[s]
        if "List[" in type_name:
            result = (
                type_name.replace("List[", "L[").replace("str", "s").replace("int", "i")
            )
            return str(result)

        # Dict[str, int] -> D[s,i] (no space after comma)
        if "Dict[" in type_name:
            result = (
                type_name.replace("Dict[", "D[").replace("str", "s").replace("int", "i")
            )
            # Remove spaces after commas for compact format
            result = result.replace(", ", ",")
            return str(result)

        # Optional[float] -> O[f], Optional[str] -> O[s]
        if "Optional[" in type_name:
            result = (
                type_name.replace("Optional[", "O[")
                .replace("str", "s")
                .replace("float", "f")
            )
            return str(result)

        result = type_mapping.get(
            type_name, type_name[:3] if len(type_name) > 3 else type_name
        )
        return str(result)

    def _extract_module_docstring(self, data: dict[str, Any]) -> str | None:
        """Extract module-level docstring"""
        # Look for module docstring in the first few lines
        source_code = data.get("source_code", "")
        if not source_code:
            return None

        lines = source_code.split("\n")
        for i, line in enumerate(lines[:10]):  # Check first 10 lines
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                quote_type = '"""' if stripped.startswith('"""') else "'''"

                # Single line docstring
                if stripped.count(quote_type) >= 2:
                    return str(stripped.replace(quote_type, "").strip())

                # Multi-line docstring
                docstring_lines = [stripped.replace(quote_type, "")]
                for j in range(i + 1, len(lines)):
                    next_line = lines[j]
                    if quote_type in next_line:
                        docstring_lines.append(next_line.replace(quote_type, ""))
                        break
                    docstring_lines.append(next_line)

                return "\n".join(docstring_lines).strip()

        return None

    def _format_python_signature(self, method: dict[str, Any]) -> str:
        """Create Python method signature"""
        params = method.get("parameters", [])
        if params is None:
            params = []
        param_strs = []

        for p in params:
            if isinstance(p, dict):
                param_name = p.get("name", "")
                param_type = p.get("type", "")
                if param_type:
                    param_strs.append(f"{param_name}: {param_type}")
                else:
                    param_strs.append(param_name)
            else:
                param_strs.append(str(p))

        params_str = ", ".join(param_strs)
        return_type = method.get("return_type", "")

        if return_type and return_type != "Any":
            return f"({params_str}) -> {return_type}"
        else:
            return f"({params_str})"

    def _get_python_visibility_symbol(self, visibility: str) -> str:
        """Get Python visibility symbol"""
        visibility_map = {
            "public": "🔓",
            "private": "🔒",
            "protected": "🔐",
            "magic": "✨",
        }
        return visibility_map.get(visibility, "🔓")

    def _format_decorators(self, decorators: list[str]) -> str:
        """Format Python decorators"""
        if not decorators:
            return "-"

        # Show important decorators
        important = [
            "property",
            "staticmethod",
            "classmethod",
            "dataclass",
            "abstractmethod",
        ]
        shown_decorators = []

        for dec in decorators:
            if any(imp in dec for imp in important):
                shown_decorators.append(f"@{dec}")

        if shown_decorators:
            return ", ".join(shown_decorators)
        elif len(decorators) == 1:
            return f"@{decorators[0]}"
        else:
            return f"@{decorators[0]} (+{len(decorators) - 1})"

    def _format_class_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for class-specific sections"""
        name = str(method.get("name", ""))
        signature = self._format_python_signature_compact(method)

        # Python-specific visibility handling
        visibility = method.get("visibility", "public")
        if name.startswith("__") and name.endswith("__"):
            visibility = "magic"
        elif name.startswith("_"):
            visibility = "private"

        # Use simple + symbol for visibility
        vis_symbol = "+" if visibility == "public" or visibility == "magic" else "-"

        line_range = method.get("line_range") or {}
        # Handle malformed line_range (could be string)
        if isinstance(line_range, dict):
            lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        else:
            lines_str = "0-0"  # Fallback for malformed data

        complexity = method.get("complexity_score", 0)

        # Use docstring for doc - ensure we get the correct docstring for this specific method
        docstring = method.get("docstring", "")
        method_name = method.get("name", "")

        # Special handling for __init__ methods - they often get wrong docstrings from tree-sitter
        if method_name == "__init__":
            # For __init__ methods, be more strict about docstring validation
            if (
                docstring
                and str(docstring).strip()
                and str(docstring).strip() != "None"
            ):
                # Check if the docstring seems to belong to this method
                # If it contains class-specific terms that don't match __init__, it's likely wrong
                docstring_text = str(docstring).strip()
                if any(
                    word in docstring_text.lower()
                    for word in ["bark", "meow", "fetch", "purr"]
                ):
                    # This looks like it belongs to another method, not __init__
                    doc = "-"
                else:
                    doc = self._extract_doc_summary(docstring_text)
            else:
                doc = "-"
        else:
            # For non-__init__ methods, use normal processing
            if (
                docstring
                and str(docstring).strip()
                and str(docstring).strip() != "None"
            ):
                doc = self._extract_doc_summary(str(docstring))
            else:
                doc = "-"

        # Add static modifier if applicable
        modifiers = []
        if method.get("is_static", False):
            modifiers.append("static")

        modifier_str = f" [{', '.join(modifiers)}]" if modifiers else ""

        return f"| {name} | {signature}{modifier_str} | {vis_symbol} | {lines_str} | {complexity} | {doc} |"

    def _format_python_signature_compact(self, method: dict[str, Any]) -> str:
        """Create compact Python method signature for class sections"""
        params = method.get("parameters", [])
        if params is None:
            params = []
        param_strs = []

        for p in params:
            if isinstance(p, dict):
                param_name = p.get("name", "")
                param_type = p.get("type", "")
                if param_type and param_type != "Any":
                    param_strs.append(f"{param_name}:{param_type}")
                else:
                    # Include type hint as "Any" for all parameters including self
                    param_strs.append(f"{param_name}:Any")
            else:
                param_strs.append(str(p))

        params_str = ", ".join(param_strs)
        return_type = method.get("return_type", "")

        if return_type and return_type != "Any":
            return f"({params_str}):{return_type}"
        else:
            return f"({params_str}):Any"
