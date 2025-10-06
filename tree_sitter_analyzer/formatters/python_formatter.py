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
        return self.format_structure(data)

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Python"""
        lines = []

        # Header - Python (module/package based)
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        module_name = file_name.replace(".py", "").replace(".pyw", "").replace(".pyi", "")

        # Check if this is a package module
        classes = data.get("classes", [])
        functions = data.get("functions", [])
        imports = data.get("imports", [])
        
        # Determine module type
        is_package = "__init__.py" in file_name
        is_script = any("if __name__ == '__main__'" in func.get("raw_text", "") for func in functions)
        
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

        # Classes - Python (multi-class aware)
        if len(classes) > 1:
            lines.append("## Classes")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(class_info.get("type", "class"))
                visibility = str(class_info.get("visibility", "public"))
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
        else:
            # Single class details
            lines.append("## Class Info")
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")

            class_info = data.get("classes", [{}])[0] if data.get("classes") else {}
            stats = data.get("statistics") or {}

            lines.append("| Package | (default) |")
            lines.append(f"| Type | {str(class_info.get('type', 'class'))} |")
            lines.append(
                f"| Visibility | {str(class_info.get('visibility', 'public'))} |"
            )
            lines.append(
                f"| Lines | {class_info.get('line_range', {}).get('start', 0)}-{class_info.get('line_range', {}).get('end', 0)} |"
            )
            lines.append(f"| Total Methods | {stats.get('method_count', 0)} |")
            lines.append(f"| Total Fields | {stats.get('field_count', 0)} |")

        lines.append("")

        # Fields
        fields = data.get("fields", [])
        if fields:
            lines.append("## Fields")
            lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
            lines.append("|------|------|-----|-----------|------|-----|")

            for field in fields:
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

        # Methods - Python (with decorators and async support)
        methods = data.get("methods", []) or functions  # Use functions if methods not available
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Decorators | Doc |")
            lines.append("|--------|-----------|-----|-------|------|----|-----------|----|")

            for method in methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Python"""
        lines = []

        # Header
        classes = data.get("classes", [])
        if len(classes) > 1:
            file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
            lines.append(f"# {file_name}")
        else:
            class_name = classes[0].get("name", "Unknown") if classes else "Unknown"
            lines.append(f"# {class_name}")
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
        
        line_range = method.get("line_range", {})
        if not line_range:
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
        params = method.get("parameters", [])
        param_types = []

        for p in params:
            if isinstance(p, dict):
                param_types.append(self._shorten_type(p.get("type", "Any")))
            else:
                param_types.append("Any")

        params_str = ",".join(param_types)
        return_type = self._shorten_type(method.get("return_type", "Any"))

        return f"({params_str}):{return_type}"

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name for Python tables"""
        if type_name is None:
            return "Any"

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
            "Union": "U",
        }

        # List[str] -> L[s]
        if "List[" in type_name:
            result = (
                type_name.replace("List[", "L[").replace("str", "s").replace("int", "i")
            )
            return str(result)

        # Dict[str, int] -> D[s,i]
        if "Dict[" in type_name:
            result = (
                type_name.replace("Dict[", "D[").replace("str", "s").replace("int", "i")
            )
            return str(result)

        # Optional[str] -> O[s]
        if "Optional[" in type_name:
            result = type_name.replace("Optional[", "O[").replace("str", "s")
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
                    return stripped.replace(quote_type, "").strip()
                
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
        important = ["property", "staticmethod", "classmethod", "dataclass", "abstractmethod"]
        shown_decorators = []
        
        for dec in decorators:
            if any(imp in dec for imp in important):
                shown_decorators.append(f"@{dec}")
        
        if shown_decorators:
            return ", ".join(shown_decorators)
        elif len(decorators) == 1:
            return f"@{decorators[0]}"
        else:
            return f"@{decorators[0]} (+{len(decorators)-1})"
