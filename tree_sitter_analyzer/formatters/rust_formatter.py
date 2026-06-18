#!/usr/bin/env python3
"""
Rust-specific table formatter.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


def _count_items_in_line_range(
    items: list[dict[str, Any]], line_range: dict[str, Any]
) -> int:
    """Count items whose ``line_range.start`` falls inside ``line_range``.

    r37dj (dogfood): extracted to flatten the field-count list-comprehension
    in ``_format_full_table``. Mirror of kotlin_formatter's helper —
    both formatters have the same in-class element-count pattern.
    """
    cls_start = line_range.get("start", 0)
    cls_end = line_range.get("end", 0)
    count = 0
    for item in items:
        item_start = item.get("line_range", {}).get("start", 0)
        if cls_start <= item_start <= cls_end:
            count += 1
    return count


class RustTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Rust"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Rust"""
        lines = []

        # Header - Rust (module-centric)
        file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Module Info
        modules = data.get("modules", [])
        if modules:
            lines.append("## Modules")
            lines.append("| Name | Visibility | Lines |")
            lines.append("|------|------------|-------|")
            for mod in modules:
                lines.append(
                    f"| {mod.get('name')} | {mod.get('visibility')} | {mod.get('line_range', {}).get('start')}-{mod.get('line_range', {}).get('end')} |"
                )
            lines.append("")

        # Structs (mapped from classes)
        structs = data.get("classes", [])
        if structs:
            lines.append("## Structs")
            lines.append("| Name | Type | Visibility | Lines | Fields | Traits |")
            lines.append("|------|------|------------|-------|--------|--------|")

            # r37dj (dogfood): flattened nesting 6 → 3 via
            # _count_items_in_line_range helper.
            for struct in structs:
                name = str(struct.get("name", "Unknown"))
                struct_type = str(struct.get("type", "struct"))  # struct, enum, trait
                visibility = str(struct.get("visibility", "private"))
                line_range = struct.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                fields_count = _count_items_in_line_range(
                    data.get("fields", []), line_range
                )
                traits = struct.get("implements_interfaces", [])
                traits_str = ", ".join(traits) if traits else "-"
                lines.append(
                    f"| {name} | {struct_type} | {visibility} | {lines_str} | {fields_count} | {traits_str} |"
                )
            lines.append("")

        # Functions (mapped from methods)
        fns = data.get("methods", [])
        if fns:
            lines.append("## Functions")
            lines.append("| Function | Signature | Vis | Async | Lines | Doc |")
            lines.append("|----------|-----------|-----|-------|-------|-----|")

            for fn in fns:
                lines.append(self._format_fn_row(fn))
            lines.append("")

        # Traits (if mapped separately or included in classes)
        # Note: The extractor maps traits to classes with type="trait"

        # Impl blocks
        impls = data.get("impls", [])
        if impls:
            lines.append("## Implementations")
            lines.append("| Type | Trait | Lines |")
            lines.append("|------|-------|-------|")
            for impl in impls:
                trait_name = impl.get("trait", "-")
                type_name = impl.get("type", "Unknown")
                line_range = impl.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                lines.append(f"| {type_name} | {trait_name} | {lines_str} |")
            lines.append("")

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Rust"""
        lines = []

        # Header
        file_name = data.get("file_path", "Unknown").split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Info
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| Structs | {len(data.get('classes', []))} |")
        lines.append(f"| Functions | {stats.get('method_count', 0)} |")
        lines.append(f"| Lines | {stats.get('lines', 0)} |")
        lines.append("")

        # Functions (compact)
        fns = data.get("methods", [])
        if fns:
            lines.append("## Functions")
            lines.append("| Fn | Sig | V | A | L | Doc |")
            lines.append("|----|-----|---|---|---|-----|")

            for fn in fns:
                name = str(fn.get("name", ""))
                signature = self._create_compact_signature(fn)
                visibility = self._convert_visibility(str(fn.get("visibility", "")))
                is_async = "Y" if fn.get("is_async", False) else "-"
                line_range = fn.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
                doc = self._clean_csv_text(
                    self._extract_doc_summary(str(fn.get("docstring", "") or ""))
                )

                lines.append(
                    f"| {name} | {signature} | {visibility} | {is_async} | {lines_str} | {doc} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _format_fn_row(self, fn: dict[str, Any]) -> str:
        """Format a function table row for Rust"""
        name = str(fn.get("name", ""))
        signature = self._create_full_signature(fn)
        visibility = self._convert_visibility(str(fn.get("visibility", "")))
        is_async = "Yes" if fn.get("is_async", False) else "-"
        line_range = fn.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(fn.get("docstring", "") or ""))
        )

        return f"| {name} | {signature} | {visibility} | {is_async} | {lines_str} | {doc} |"

    @staticmethod
    def _format_rust_param(param: Any) -> str:
        """Render one Rust parameter as proper Rust syntax (never a raw dict repr).

        Handles three cases:
        - Receiver params (``self`` / ``&self`` / ``&mut self``): the extractor
          sets ``type`` to the placeholder ``'Any'``; render as the bare name only.
        - Typed dict ``{"name": "value", "type": "&T"}`` → ``"value: &T"``.
        - String (already formatted by the extractor) → pass through unchanged.
        """
        if isinstance(param, dict):
            name = param.get("name", "")
            ptype = param.get("type", "")
            # Receiver params and Any-typed params: return bare name
            if ptype in ("Any", "", None) or name in ("self", "&self", "&mut self"):
                return name or ptype or str(param)
            if name and ptype:
                return f"{name}: {ptype}"
            return name or ptype or str(param)
        return str(param)

    def _create_full_signature(self, fn: dict[str, Any]) -> str:
        """Create full function signature for Rust"""
        params = fn.get("parameters", [])
        params_str = ", ".join(self._format_rust_param(p) for p in params)
        return_type = fn.get("return_type", "")
        ret_str = f" -> {return_type}" if return_type and return_type != "()" else ""

        return f"fn({params_str}){ret_str}"

    def _create_compact_signature(self, fn: dict[str, Any]) -> str:
        """Create compact function signature for Rust"""
        params = fn.get("parameters", [])
        # Simply count parameters or use short types if available
        params_summary = f"({len(params)})"
        return_type = fn.get("return_type", "")
        ret_str = f"->{return_type}" if return_type and return_type != "()" else ""

        return f"{params_summary}{ret_str}"

    def _convert_visibility(self, visibility: str) -> str:
        """Convert visibility to short symbol"""
        if visibility == "pub":
            return "pub"
        elif visibility == "pub(crate)":
            return "crate"
        elif visibility == "private":  # Default
            return "priv"
        return visibility

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Rust"""
        # Set the format type based on table_type parameter
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            # Handle json format separately
            if table_type == "json":
                return self._format_json(analysis_result)
            # Use the existing format_structure method
            return self.format_structure(analysis_result)
        finally:
            # Restore original format type
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for Rust"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for Rust"""
        if self.format_type == "compact":
            return self._format_compact_table(analysis_result)
        return self._format_full_table(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for Rust"""
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
