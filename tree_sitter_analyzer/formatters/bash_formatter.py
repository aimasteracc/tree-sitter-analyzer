#!/usr/bin/env python3
"""
Bash-specific table formatter.

Renders shell-script analysis in the standard
  Method | Signature | Vis | Lines | Cx | Doc
column set, mirroring the Java/Ruby/Go formatters.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class BashTableFormatter(BaseTableFormatter):
    """Table formatter specialised for Bash / shell scripts."""

    # ------------------------------------------------------------------ #
    # Public entry points                                                   #
    # ------------------------------------------------------------------ #

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Bash."""
        original = self.format_type
        self.format_type = table_type
        try:
            if table_type == "json":
                return self._format_json(analysis_result)
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Compact table (summary) for Bash."""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Dispatch to the correct sub-formatter."""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Advanced output for Bash."""
        if output_format == "json":
            return self._format_json(analysis_result)
        if output_format == "csv":
            return self._format_csv(analysis_result)
        return self._format_full_table(analysis_result)

    # ------------------------------------------------------------------ #
    # Full table                                                            #
    # ------------------------------------------------------------------ #

    def _format_full_table(self, data: dict[str, Any]) -> str:
        lines: list[str] = []
        file_name = _file_stem(str(data.get("file_path", "Unknown")))
        lines.append(f"# {file_name}")
        lines.append("")

        # Script info
        stats = data.get("statistics") or {}
        lines.append("## Script Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(
            f"| Functions | {stats.get('method_count', len(data.get('methods', [])))} |"
        )
        lines.append(
            f"| Variables | {stats.get('field_count', len(data.get('fields', [])))} |"
        )
        lines.append("")

        # Imports (source/. statements)
        imports = data.get("imports", [])
        if imports:
            lines.append("## Sourced Files")
            lines.append("```bash")
            for imp in imports:
                stmt = imp.get("raw_text", "") or imp.get("import_statement", "")
                if stmt:
                    lines.append(stmt.strip())
            lines.append("```")
            lines.append("")

        # Functions
        methods = data.get("methods", []) or []
        if methods:
            lines.append("## Functions")
            lines.append("| Name | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|------|-----------|-----|-------|----|-----|")
            for method in methods:
                lines.append(self._format_func_row(method))
            lines.append("")

        # Variables / globals
        fields = data.get("fields", []) or []
        if fields:
            lines.append("## Variables")
            lines.append("| Name | Type | Vis | Line |")
            lines.append("|------|------|-----|------|")
            for field in fields:
                lines.append(self._format_field_row(field))
            lines.append("")

        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Compact table                                                         #
    # ------------------------------------------------------------------ #

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        lines: list[str] = []
        file_name = _file_stem(str(data.get("file_path", "Unknown")))
        lines.append(f"# {file_name}")
        lines.append("")

        stats = data.get("statistics") or {}
        methods = data.get("methods", []) or []
        fields = data.get("fields", []) or []

        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Functions | {stats.get('method_count', len(methods))} |")
        lines.append(f"| Variables | {stats.get('field_count', len(fields))} |")
        lines.append("")

        if methods:
            lines.append("## Functions")
            lines.append("| Name | Sig | V | L | Cx | Doc |")
            lines.append("|------|-----|---|---|----|-----|")
            for method in methods:
                lines.append(self._format_compact_func_row(method))
            lines.append("")

        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Row helpers                                                           #
    # ------------------------------------------------------------------ #

    def _format_func_row(self, func: dict[str, Any]) -> str:
        name = str(func.get("name", ""))
        sig = self._create_bash_signature(func)
        vis = self._bash_visibility(name)
        line_range = func.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = func.get("complexity_score", 1)
        doc = self._extract_doc_summary(
            func.get("javadoc", "") or func.get("docstring", "") or ""
        )
        return f"| {name} | {sig} | {vis} | {lines_str} | {complexity} | {doc or '-'} |"

    def _format_compact_func_row(self, func: dict[str, Any]) -> str:
        name = str(func.get("name", ""))
        params = func.get("parameters", [])
        param_count = len(params) if isinstance(params, list) else 0
        vis = "+" if self._bash_visibility(name) == "public" else "-"
        line_range = func.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = func.get("complexity_score", 1)
        doc = self._extract_doc_summary(
            func.get("javadoc", "") or func.get("docstring", "") or ""
        )
        return f"| {name} | ({param_count}) | {vis} | {lines_str} | {complexity} | {doc or '-'} |"

    def _format_field_row(self, field: dict[str, Any]) -> str:
        name = str(field.get("name", ""))
        ftype = str(field.get("type", field.get("variable_type", "-")) or "-")
        vis = self._bash_visibility(name)
        line = field.get("line_range", {}).get("start", 0)
        return f"| {name} | {ftype} | {vis} | {line} |"

    # ------------------------------------------------------------------ #
    # Signature / visibility helpers                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _create_bash_signature(func: dict[str, Any]) -> str:
        params = func.get("parameters", [])
        if not isinstance(params, list) or not params:
            return "()"
        parts = []
        for p in params:
            if isinstance(p, dict):
                parts.append(str(p.get("name", "") or p.get("type", "")))
            else:
                parts.append(str(p))
        return f"({', '.join(parts)})"

    @staticmethod
    def _bash_visibility(name: str) -> str:
        """Bash functions starting with '_' are conventionally private."""
        return "private" if name.startswith("_") else "public"

    # ------------------------------------------------------------------ #
    # Misc helpers                                                          #
    # ------------------------------------------------------------------ #

    def _format_json(self, data: dict[str, Any]) -> str:
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\n"


def _file_stem(file_path: str) -> str:
    """Return just the filename (no directory) from a path."""
    return file_path.replace("\\", "/").split("/")[-1]
