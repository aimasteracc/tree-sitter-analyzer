#!/usr/bin/env python3
"""
JavaScript-specific table formatter.

Provides specialized formatting for JavaScript code analysis results,
handling modern JavaScript features like ES6+ syntax, async/await,
classes, modules, and framework-specific patterns.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class JavaScriptTableFormatter(BaseTableFormatter):
    """Table formatter specialized for JavaScript"""

    def format(self, data: dict[str, Any] | None, format_type: str = "full") -> str:
        """Format data using the configured format type"""
        # Handle None data gracefully
        if data is None:
            data = {}

        # Ensure data is a dictionary
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        if format_type:
            # Check for supported format types
            supported_formats = ["full", "compact", "csv", "json"]
            if format_type not in supported_formats:
                raise ValueError(
                    f"Unsupported format type: {format_type}. Supported formats: {supported_formats}"
                )

            # Handle json format separately
            if format_type == "json":
                return self._format_json(data)

            # Temporarily change format type for this call
            original_format = self.format_type
            self.format_type = format_type
            result = self.format_structure(data)
            self.format_type = original_format
            return result
        return self.format_structure(data)

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for JavaScript - matches golden master format"""
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        lines: list[str] = []

        # Get classes
        classes = data.get("classes", [])
        if classes is None:
            classes = []
        methods = data.get("methods", [])
        if methods is None:
            methods = []

        # Header - use first class name if classes exist
        if classes:
            first_class = classes[0]
            class_name = first_class.get("name", "Unknown")
            lines.append(f"# {class_name}")
        else:
            # Fallback to file name
            file_path = data.get("file_path", "Unknown")
            if file_path is None:
                file_path = "Unknown"
            file_name = str(file_path).split("/")[-1].split("\\")[-1]
            module_name = (
                file_name.replace(".js", "").replace(".jsx", "").replace(".mjs", "")
            )
            lines.append(f"# {module_name}")
        lines.append("")

        # Classes Overview table (if classes exist)
        if classes:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = "class"
                visibility = "public"  # JavaScript classes are public by default
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods within the class
                class_methods = [
                    m
                    for m in methods
                    if line_range.get("start", 0)
                    <= m.get("line_range", {}).get("start", 0)
                    <= line_range.get("end", 0)
                ]

                lines.append(
                    f"| {name} | {class_type} | {visibility} | "
                    f"{lines_str} | {len(class_methods)} | 0 |"
                )
            lines.append("")

            # Generate per-class sections
            for class_info in classes:
                class_lines = self._format_class_section(class_info, data)
                lines.extend(class_lines)

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_class_section(
        self, class_info: dict[str, Any], data: dict[str, Any]
    ) -> list[str]:
        """Format a single class section with its methods"""
        lines: list[str] = []

        name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        start = line_range.get("start", 0)
        end = line_range.get("end", 0)

        # Section header with line range
        lines.append(f"## {name} ({start}-{end})")

        # Get methods for this class
        methods = data.get("methods", [])
        if methods is None:
            methods = []
        class_methods = [
            m
            for m in methods
            if start <= m.get("line_range", {}).get("start", 0) <= end
        ]

        # Constructors section
        constructors = [m for m in class_methods if m.get("is_constructor", False)]
        if constructors:
            lines.append("### Constructors")
            lines.append("| Constructor | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|-------------|-----------|-----|-------|----|----|")

            for method in constructors:
                lines.append(self._format_method_table_row(method))
            lines.append("")

        # Public Methods section
        public_methods = [
            m for m in class_methods if not m.get("is_constructor", False)
        ]
        if public_methods:
            lines.append("### Public Methods")
            lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|----|----|")

            for method in public_methods:
                lines.append(self._format_method_table_row(method))
            lines.append("")

        return lines

    def _format_method_table_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for JavaScript (golden master format)"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = "+"  # JavaScript methods are public by default
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 1)
        doc = "-"  # Default to no doc

        return f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create full method signature for JavaScript"""
        params = method.get("parameters", [])
        if not params:
            return "():unknown"

        # Handle malformed data
        if isinstance(params, str):
            return "():unknown"

        param_strs = []
        for param in params:
            if isinstance(param, dict):
                param_name = param.get("name", "")
                param_type = param.get("type", "Any")
                param_strs.append(f"{param_name}:{param_type}")
            else:
                param_strs.append(f"{param}:Any")

        params_str = ", ".join(param_strs)
        return_type = method.get("return_type", "unknown")
        return f"({params_str}):{return_type}"

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for JavaScript - matches golden master format"""
        lines: list[str] = []

        # Get classes
        classes = data.get("classes", [])
        if classes is None:
            classes = []
        methods = data.get("methods", [])
        if methods is None:
            methods = []

        # Header - use first class name if classes exist
        if classes:
            first_class = classes[0]
            class_name = first_class.get("name", "Unknown")
            lines.append(f"# {class_name}")
        else:
            file_path = data.get("file_path", "Unknown")
            if file_path is None:
                file_path = "Unknown"
            file_name = str(file_path).split("/")[-1].split("\\")[-1]
            module_name = (
                file_name.replace(".js", "").replace(".jsx", "").replace(".mjs", "")
            )
            lines.append(f"# {module_name}")
        lines.append("")

        # Info section
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append("| Package |  |")
        lines.append(f"| Methods | {len(methods)} |")
        lines.append("| Fields | 0 |")
        lines.append("")

        # Methods section
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")

            for method in methods:
                name = str(method.get("name", ""))
                signature = self._create_compact_signature(method)
                visibility = "+"
                line_range = method.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                complexity = method.get("complexity_score", 1)
                doc = "-"

                lines.append(
                    f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | {doc} |"
                )

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature for JavaScript"""
        params = method.get("parameters", [])
        if not params:
            return "():unknown"

        # Handle malformed data
        if isinstance(params, str):
            return "():unknown"

        param_types = []
        for param in params:
            if isinstance(param, dict):
                param_type = param.get("type", "Any")
                param_types.append(param_type)
            else:
                param_types.append("Any")

        params_str = ",".join(param_types)
        return_type = method.get("return_type", "unknown")
        return f"({params_str}):{return_type}"

    def _format_function_row(self, func: dict[str, Any]) -> str:
        """Format a function table row for JavaScript"""
        name = str(func.get("name", ""))
        params = self._create_full_params(func)
        func_type = self._get_function_type(func)
        line_range = func.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = func.get("complexity_score", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(func.get("jsdoc", "")))
        )

        return (
            f"| {name} | {params} | {func_type} | {lines_str} | {complexity} | {doc} |"
        )

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for JavaScript"""
        name = str(method.get("name", ""))
        class_name = self._get_method_class(method)
        params = self._create_full_params(method)
        method_type = self._get_method_type(method)
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(method.get("jsdoc", "")))
        )

        return f"| {name} | {class_name} | {params} | {method_type} | {lines_str} | {complexity} | {doc} |"

    def _create_full_params(self, func: dict[str, Any]) -> str:
        """Create full parameter list for JavaScript functions"""
        params = func.get("parameters", [])
        if not params:
            return "()"

        # Handle malformed data where parameters might be a string
        if isinstance(params, str):
            # If parameters is a malformed string, return empty params
            return "()"

        param_strs = []
        for param in params:
            if isinstance(param, dict):
                param_name = param.get("name", "")
                param_type = param.get("type", "")
                if param_type:
                    param_strs.append(f"{param_name}: {param_type}")
                else:
                    param_strs.append(param_name)
            else:
                param_strs.append(str(param))

        params_str = ", ".join(param_strs)
        if len(params_str) > 50:
            params_str = params_str[:47] + "..."

        return f"({params_str})"

    def _create_compact_params(self, func: dict[str, Any]) -> str:
        """Create compact parameter list for JavaScript functions"""
        params = func.get("parameters", [])
        if not params:
            return "()"

        # Handle malformed data where parameters might be a string
        if isinstance(params, str):
            # If parameters is a malformed string, return empty params
            return "()"

        param_count = len(params)
        if param_count <= 3:
            param_names = [
                param.get("name", str(param)) if isinstance(param, dict) else str(param)
                for param in params
            ]
            return f"({','.join(param_names)})"
        else:
            return f"({param_count} params)"

    def _get_function_type(self, func: dict[str, Any]) -> str:
        """Get full function type for JavaScript"""
        if func.get("is_async", False):
            return "async function"
        elif func.get("is_generator", False):
            return "generator"
        elif func.get("is_arrow", False):
            return "arrow"
        elif self._is_method(func):
            if func.get("is_constructor", False):
                return "constructor"
            elif func.get("is_getter", False):
                return "getter"
            elif func.get("is_setter", False):
                return "setter"
            elif func.get("is_static", False):
                return "static method"
            else:
                return "method"
        else:
            return "function"

    def _get_function_type_short(self, func: dict[str, Any]) -> str:
        """Get short function type for JavaScript"""
        if func.get("is_async", False):
            return "async"
        elif func.get("is_generator", False):
            return "gen"
        elif func.get("is_arrow", False):
            return "arrow"
        elif self._is_method(func):
            return "method"
        else:
            return "func"

    def _get_method_type(self, method: dict[str, Any]) -> str:
        """Get method type for JavaScript"""
        if method.get("is_constructor", False):
            return "constructor"
        elif method.get("is_getter", False):
            return "getter"
        elif method.get("is_setter", False):
            return "setter"
        elif method.get("is_static", False):
            return "static"
        elif method.get("is_async", False):
            return "async"
        else:
            return "method"

    def _is_method(self, func: dict[str, Any]) -> bool:
        """Check if function is a class method"""
        return func.get("is_method", False) or func.get("class_name") is not None

    def _get_method_class(self, method: dict[str, Any]) -> str:
        """Get the class name for a method"""
        return str(method.get("class_name", "Unknown"))

    def _infer_js_type(self, value: Any) -> str:
        """Infer JavaScript type from value"""
        if value is None:
            return "undefined"

        value_str = str(value).strip()

        # Check for specific patterns
        if value_str == "undefined":
            return "undefined"
        elif value_str == "NaN":
            return "number"  # NaN is a number type in JavaScript
        elif value_str in ["Infinity", "-Infinity"]:
            return "number"  # Infinity is a number type in JavaScript
        elif (
            value_str.startswith('"')
            or value_str.startswith("'")
            or value_str.startswith("`")
        ):
            return "string"
        elif value_str in ["true", "false"]:
            return "boolean"
        elif value_str == "null":
            return "null"
        elif value_str.startswith("[") and value_str.endswith("]"):
            return "array"
        elif value_str.startswith("{") and value_str.endswith("}"):
            return "object"
        elif (
            value_str.startswith("function")
            or value_str.startswith("async function")
            or value_str.startswith("new Function")
            or "=>" in value_str
        ):
            return "function"
        elif value_str.startswith("class"):
            return "class"
        elif value_str.replace(".", "").replace("-", "").isdigit():
            return "number"
        else:
            return "unknown"

    def _determine_scope(self, var: dict[str, Any]) -> str:
        """Determine variable scope"""
        # This would need more context from the parser
        # For now, return basic scope info
        kind = self._get_variable_kind(var)
        if kind == "const" or kind == "let":
            return "block"
        elif kind == "var":
            return "function"
        else:
            return "unknown"

    def _get_variable_kind(self, var: dict[str, Any]) -> str:
        """Get variable declaration kind (const, let, var)"""
        # Check if variable has is_constant flag
        if var.get("is_constant", False):
            return "const"

        # Fall back to parsing raw text
        raw_text = str(var.get("raw_text", "")).strip()
        if raw_text.startswith("const"):
            return "const"
        elif raw_text.startswith("let"):
            return "let"
        elif raw_text.startswith("var"):
            return "var"
        else:
            return "unknown"

    def _get_export_type(self, export: Any) -> str:
        """Get export type"""
        if not isinstance(export, dict):
            return "unknown"
        if export.get("is_default", False):
            return "default"
        elif export.get("is_named", False):
            return "named"
        elif export.get("is_all", False):
            return "all"
        else:
            return "unknown"

    def _get_function_signature(self, func: dict[str, Any]) -> str:
        """Get function signature"""
        name = str(func.get("name", ""))
        params = self._create_full_params(func)
        return_type = func.get("return_type", "")
        if return_type:
            return f"{name}{params} -> {return_type}"
        return f"{name}{params}"

    def _get_class_info(self, cls: dict[str, Any]) -> str:
        """Get class information as formatted string"""
        if cls is None:
            raise TypeError("Cannot format None data")

        if not isinstance(cls, dict):
            raise TypeError(f"Expected dict, got {type(cls)}")

        name = str(cls.get("name", "Unknown"))
        methods = cls.get("methods", [])
        method_count = len(methods) if isinstance(methods, list) else 0

        return f"{name} ({method_count} methods)"

    def _format_json(self, data: dict[str, Any]) -> str:
        """Format data as JSON"""
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\n"

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for JavaScript"""
        # Set the format type based on table_type parameter
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            # Use the existing format_structure method
            return self.format_structure(analysis_result)
        finally:
            # Restore original format type
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for JavaScript"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for JavaScript"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for JavaScript"""
        if output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)
