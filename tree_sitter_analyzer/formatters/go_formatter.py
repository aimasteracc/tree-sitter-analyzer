#!/usr/bin/env python3
"""
Go-specific table formatter.

Uses Go-specific terminology:
- package (not module)
- func (not function/method)
- struct (not class)
- interface
- receiver (for methods)
- goroutine, channel, defer
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class GoTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Go"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Go"""
        lines = []

        # Header - Package name
        package_name = self._get_package_name(data)
        file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]

        if package_name:
            lines.append(f"# {package_name}/{file_name}")
        else:
            lines.append(f"# {file_name}")
        lines.append("")

        # Package Info
        lines.append("## Package Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Package | {package_name or 'main'} |")

        stats = data.get("statistics") or {}
        lines.append(f"| Functions | {stats.get('function_count', 0)} |")
        lines.append(f"| Types | {stats.get('class_count', 0)} |")
        lines.append(f"| Variables | {stats.get('variable_count', 0)} |")
        lines.append("")

        # Imports
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```go")
            for imp in imports:
                stmt = imp.get("import_statement", "") or imp.get("raw_text", "")
                if stmt:
                    # Clean up the import statement
                    stmt = stmt.strip()
                    if not stmt.startswith("import"):
                        stmt = f'import "{stmt}"'
                    lines.append(stmt)
            lines.append("```")
            lines.append("")

        # Types (Structs, Interfaces, Type Aliases)
        classes = data.get("classes", [])
        structs = [c for c in classes if c.get("type") == "struct"]
        interfaces = [c for c in classes if c.get("type") == "interface"]
        type_aliases = [c for c in classes if c.get("type") == "type_alias"]

        if structs:
            lines.append("## Structs")
            lines.append("| Name | Visibility | Lines | Embedded | Doc |")
            lines.append("|------|------------|-------|----------|-----|")
            for s in structs:
                name = s.get("name", "")
                vis = self._go_visibility(name)
                line_range = s.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                embedded = ", ".join([str(i) for i in (s.get("interfaces", []) or [])])
                doc = self._extract_doc_summary(s.get("docstring", "") or "")
                lines.append(
                    f"| {name} | {vis} | {lines_str} | {embedded or '-'} | {doc or '-'} |"
                )
            lines.append("")

        if interfaces:
            lines.append("## Interfaces")
            lines.append("| Name | Visibility | Lines | Doc |")
            lines.append("|------|------------|-------|-----|")
            for i in interfaces:
                name = i.get("name", "")
                vis = self._go_visibility(name)
                line_range = i.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                doc = self._extract_doc_summary(i.get("docstring", "") or "")
                lines.append(f"| {name} | {vis} | {lines_str} | {doc or '-'} |")
            lines.append("")

        if type_aliases:
            lines.append("## Type Aliases")
            lines.append("| Name | Visibility | Lines |")
            lines.append("|------|------------|-------|")
            for t in type_aliases:
                name = t.get("name", "")
                vis = self._go_visibility(name)
                line_range = t.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                lines.append(f"| {name} | {vis} | {lines_str} |")
            lines.append("")

        # Functions (non-methods)
        functions = data.get("functions", []) or data.get("methods", [])
        funcs = [
            f
            for f in functions
            if not getattr(f, "is_method", False) and not f.get("is_method", False)
        ]
        methods = [
            f
            for f in functions
            if getattr(f, "is_method", False) or f.get("is_method", False)
        ]

        if funcs:
            lines.append("## Functions")
            lines.append("| Func | Signature | Vis | Lines | Doc |")
            lines.append("|------|-----------|-----|-------|-----|")
            for func in funcs:
                lines.append(self._format_func_row(func))
            lines.append("")

        # Methods (with receiver)
        if methods:
            lines.append("## Methods")
            lines.append("| Receiver | Func | Signature | Vis | Lines | Doc |")
            lines.append("|----------|------|-----------|-----|-------|-----|")
            for method in methods:
                lines.append(self._format_method_row(method))
            lines.append("")

        # Constants
        variables = data.get("variables", []) or data.get("fields", [])
        consts = [v for v in variables if v.get("is_constant", False)]
        vars_list = [v for v in variables if not v.get("is_constant", False)]

        if consts:
            lines.append("## Constants")
            lines.append("| Name | Type | Vis | Line |")
            lines.append("|------|------|-----|------|")
            for c in consts:
                name = c.get("name", "")
                var_type = c.get("variable_type", "") or c.get("type", "") or "-"
                vis = self._go_visibility(name)
                line = c.get("line_range", {}).get("start", 0)
                lines.append(f"| {name} | {var_type} | {vis} | {line} |")
            lines.append("")

        if vars_list:
            lines.append("## Variables")
            lines.append("| Name | Type | Vis | Line |")
            lines.append("|------|------|-----|------|")
            for v in vars_list:
                name = v.get("name", "")
                var_type = v.get("variable_type", "") or v.get("type", "") or "-"
                vis = self._go_visibility(name)
                line = v.get("line_range", {}).get("start", 0)
                lines.append(f"| {name} | {var_type} | {vis} | {line} |")
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Go"""
        lines = []

        # Header
        package_name = self._get_package_name(data)
        file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]

        if package_name:
            lines.append(f"# {package_name}/{file_name}")
        else:
            lines.append(f"# {file_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Package | {package_name or 'main'} |")
        lines.append(f"| Funcs | {stats.get('function_count', 0)} |")
        lines.append(f"| Types | {stats.get('class_count', 0)} |")
        lines.append("")

        # Functions (compact)
        functions = data.get("functions", []) or data.get("methods", [])
        if functions:
            lines.append("## Funcs")
            lines.append("| Func | Sig | V | L | Doc |")
            lines.append("|------|-----|---|---|-----|")
            for func in functions:
                name = func.get("name", "")
                sig = self._create_go_compact_signature(func)
                vis = "E" if self._go_visibility(name) == "exported" else "u"
                line_range = func.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                doc = self._extract_doc_summary(func.get("docstring", "") or "")[:20]
                lines.append(f"| {name} | {sig} | {vis} | {lines_str} | {doc or '-'} |")
            lines.append("")

        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_func_row(self, func: dict[str, Any]) -> str:
        """Format a function table row for Go"""
        name = func.get("name", "")
        sig = self._create_go_signature(func)
        vis = self._go_visibility(name)
        line_range = func.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        doc = self._extract_doc_summary(func.get("docstring", "") or "")

        return f"| {name} | {sig} | {vis} | {lines_str} | {doc or '-'} |"

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for Go (with receiver)"""
        receiver_type = getattr(method, "receiver_type", None) or method.get(
            "receiver_type", "-"
        )
        name = method.get("name", "")
        sig = self._create_go_signature(method)
        vis = self._go_visibility(name)
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        doc = self._extract_doc_summary(method.get("docstring", "") or "")

        return (
            f"| {receiver_type} | {name} | {sig} | {vis} | {lines_str} | {doc or '-'} |"
        )

    def _create_go_signature(self, func: dict[str, Any]) -> str:
        """Create Go function signature"""
        params = func.get("parameters", [])
        if isinstance(params, list):
            params_str = ", ".join(str(p) for p in params)
        else:
            params_str = str(params)

        return_type = func.get("return_type", "")
        if return_type:
            return f"({params_str}) {return_type}"
        return f"({params_str})"

    def _create_go_compact_signature(self, func: dict[str, Any]) -> str:
        """Create compact Go function signature"""
        params = func.get("parameters", [])
        param_count = len(params) if isinstance(params, list) else 0

        return_type = func.get("return_type", "")
        ret = self._shorten_go_type(return_type) if return_type else "-"

        return f"({param_count}):{ret}"

    def _shorten_go_type(self, type_name: str) -> str:
        """Shorten Go type name for compact display"""
        if not type_name:
            return "-"

        type_mapping = {
            "string": "s",
            "int": "i",
            "int64": "i64",
            "int32": "i32",
            "float64": "f64",
            "float32": "f32",
            "bool": "b",
            "error": "err",
            "interface{}": "any",
            "any": "any",
            "[]byte": "[]b",
            "[]string": "[]s",
        }

        # Handle pointer types
        if type_name.startswith("*"):
            inner = type_name[1:]
            short = type_mapping.get(inner, inner[:3])
            return f"*{short}"

        # Handle slice types
        if type_name.startswith("[]"):
            inner = type_name[2:]
            short = type_mapping.get(inner, inner[:3])
            return f"[]{short}"

        return type_mapping.get(
            type_name, type_name[:5] if len(type_name) > 5 else type_name
        )

    def _go_visibility(self, name: str) -> str:
        """Determine Go visibility based on name capitalization"""
        if name and name[0].isupper():
            return "exported"
        return "unexported"

    def _get_package_name(self, data: dict[str, Any]) -> str:
        """Extract package name from data"""
        # Try packages list first
        packages = data.get("packages", [])
        if packages:
            return str(packages[0].get("name", ""))

        # Fallback to general package
        package = data.get("package")
        if package and isinstance(package, dict):
            return str(package.get("name", ""))

        return ""

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Go"""
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            if table_type == "json":
                return self._format_json(analysis_result)
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for Go"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for Go"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for Go"""
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
