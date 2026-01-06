#!/usr/bin/env python3
"""
PHP-specific table formatter.
Follows Java golden master format for consistency.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class PHPTableFormatter(BaseTableFormatter):
    """Table formatter specialized for PHP, following Java golden master format."""

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Convert visibility to symbol."""
        visibility_map = {
            "public": "+",
            "private": "-",
            "protected": "#",
        }
        return visibility_map.get(str(visibility).lower(), "+")

    def _format_signature(self, method: dict[str, Any]) -> str:
        """Format method signature like Java: ($param:type):returnType."""
        params = method.get("parameters", [])
        param_strs = []
        for p in params:
            if isinstance(p, dict):
                name = p.get("name", "")
                ptype = p.get("type", "mixed")
                if name:
                    # Remove leading $ if already present to avoid $$
                    clean_name = name.lstrip("$")
                    param_strs.append(f"${clean_name}:{ptype}")
                else:
                    param_strs.append(str(ptype))
            else:
                param_strs.append(str(p))

        return_type = method.get("return_type", "void")
        return f"({', '.join(param_strs)}):{return_type}"

    def _format_compact_signature(self, method: dict[str, Any]) -> str:
        """Format compact method signature."""
        params = method.get("parameters", [])
        param_strs = []
        for p in params:
            if isinstance(p, dict):
                ptype = p.get("type", "Any")
                param_strs.append(str(ptype))
            else:
                param_strs.append(str(p))

        return_type = method.get("return_type", "")
        return (
            f"({', '.join(param_strs)}):{return_type}"
            if return_type
            else f"({', '.join(param_strs)}):"
        )

    def _extract_namespace(self, data: dict[str, Any]) -> str:
        """Extract namespace from data."""
        classes = data.get("classes", [])
        if classes:
            for class_info in classes:
                # Check for full_qualified_name
                fqn = class_info.get("full_qualified_name", "")
                if fqn and "\\" in fqn:
                    return "\\".join(fqn.split("\\")[:-1])
                # Check metadata
                metadata = class_info.get("metadata", {})
                namespace = metadata.get("namespace", "")
                if namespace:
                    return str(namespace)
        return ""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for PHP, following Java golden master format."""
        lines = []

        # Header
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Use statements (imports)
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```php")
            for imp in imports:
                import_text = imp.get("raw_text", "").strip()
                if import_text:
                    lines.append(import_text)
            lines.append("```")
            lines.append("")

        # Classes Overview - following Java format
        classes = data.get("classes", [])
        if classes:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            methods = data.get("methods", [])
            fields = data.get("fields", [])

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(
                    class_info.get("class_type", class_info.get("type", "class"))
                )
                visibility = str(class_info.get("visibility", "public"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                # Count methods/fields within the class range
                start_line = line_range.get("start", 0)
                end_line = line_range.get("end", 0)

                class_methods = [
                    m
                    for m in methods
                    if start_line <= m.get("line_range", {}).get("start", 0) <= end_line
                ]
                class_fields = [
                    f
                    for f in fields
                    if start_line <= f.get("line_range", {}).get("start", 0) <= end_line
                ]

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | "
                    f"{len(class_methods)} | {len(class_fields)} |"
                )
            lines.append("")

        # Per-class details
        methods = data.get("methods", [])
        fields = data.get("fields", [])

        for class_info in classes:
            class_name = str(class_info.get("name", "Unknown"))
            class_range = class_info.get("line_range", {})
            start_line = class_range.get("start", 0)
            end_line = class_range.get("end", 0)

            lines.append(f"## {class_name} ({start_line}-{end_line})")

            # Fields for this class
            class_fields = [
                f
                for f in fields
                if start_line <= f.get("line_range", {}).get("start", 0) <= end_line
            ]
            if class_fields:
                lines.append("### Fields")
                lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
                lines.append("|------|------|-----|-----------|------|-----|")

                # Get simple class name (without namespace)
                simple_class_name = (
                    class_name.split("\\")[-1] if "\\" in class_name else class_name
                )

                for field in class_fields:
                    field_name = str(field.get("name", "Unknown"))
                    # Only add class prefix if not already present
                    if "::" not in field_name:
                        fname = f"{simple_class_name}::{field_name}"
                    else:
                        fname = field_name
                    ftype = str(field.get("variable_type", field.get("type", "mixed")))
                    fvis = self._get_visibility_symbol(
                        field.get("visibility", "public")
                    )

                    # Build modifiers
                    modifiers = []
                    if field.get("visibility"):
                        modifiers.append(str(field.get("visibility")))
                    if field.get("is_static"):
                        modifiers.append("static")
                    if field.get("is_readonly"):
                        modifiers.append("readonly")
                    modifiers_str = ",".join(modifiers)

                    fline = field.get("line_range", {}).get("start", 0)
                    fdoc = field.get("documentation", "-") or "-"
                    if fdoc and len(fdoc) > 30:
                        fdoc = fdoc[:27] + "..."

                    lines.append(
                        f"| {fname} | {ftype} | {fvis} | {modifiers_str} | {fline} | {fdoc} |"
                    )
                lines.append("")

            # Methods for this class, grouped by visibility
            class_methods = [
                m
                for m in methods
                if start_line <= m.get("line_range", {}).get("start", 0) <= end_line
            ]

            # Group by visibility
            constructors = [
                m
                for m in class_methods
                if m.get("is_constructor")
                or m.get("name", "").startswith("__construct")
            ]
            public_methods = [
                m
                for m in class_methods
                if m.get("visibility", "public") == "public" and m not in constructors
            ]
            protected_methods = [
                m for m in class_methods if m.get("visibility") == "protected"
            ]
            private_methods = [
                m for m in class_methods if m.get("visibility") == "private"
            ]

            method_groups = [
                ("Constructors", constructors),
                ("Public Methods", public_methods),
                ("Protected Methods", protected_methods),
                ("Private Methods", private_methods),
            ]

            # Get simple class name (without namespace)
            simple_class_name = (
                class_name.split("\\")[-1] if "\\" in class_name else class_name
            )

            for group_name, group_methods in method_groups:
                if group_methods:
                    lines.append(f"### {group_name}")
                    header = "Constructor" if group_name == "Constructors" else "Method"
                    lines.append(f"| {header} | Signature | Vis | Lines | Cx | Doc |")
                    lines.append("|--------|-----------|-----|-------|----|----|")

                    for method in group_methods:
                        method_name = str(method.get("name", "Unknown"))
                        # Only add class prefix if not already present
                        if "::" not in method_name:
                            mname = f"{simple_class_name}::{method_name}"
                        else:
                            mname = method_name
                        sig = self._format_signature(method)
                        mvis = self._get_visibility_symbol(
                            method.get("visibility", "public")
                        )

                        # Add static marker if applicable
                        if method.get("is_static"):
                            sig += " [static]"

                        mrange = method.get("line_range", {})
                        mlines = f"{mrange.get('start', 0)}-{mrange.get('end', 0)}"
                        mcx = method.get(
                            "complexity_score", method.get("complexity", 1)
                        )
                        mdoc = method.get("documentation", "-") or "-"
                        if mdoc and len(mdoc) > 30:
                            mdoc = mdoc[:27] + "..."

                        lines.append(
                            f"| {mname} | {sig} | {mvis} | {mlines} | {mcx} | {mdoc} |"
                        )
                    lines.append("")

        # Module-level functions (not in any class)
        if classes:
            all_class_ranges = [
                (
                    c.get("line_range", {}).get("start", 0),
                    c.get("line_range", {}).get("end", 0),
                )
                for c in classes
            ]
            module_level_methods = [
                m
                for m in methods
                if not any(
                    start <= m.get("line_range", {}).get("start", 0) <= end
                    for start, end in all_class_ranges
                )
            ]
            if module_level_methods:
                lines.append("## Functions")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")
                for method in module_level_methods:
                    mname = str(method.get("name", "Unknown"))
                    sig = self._format_signature(method)
                    mvis = self._get_visibility_symbol(
                        method.get("visibility", "public")
                    )
                    mrange = method.get("line_range", {})
                    mlines = f"{mrange.get('start', 0)}-{mrange.get('end', 0)}"
                    mcx = method.get("complexity_score", method.get("complexity", 1))
                    mdoc = method.get("documentation", "-") or "-"
                    if mdoc and len(mdoc) > 30:
                        mdoc = mdoc[:27] + "..."
                    lines.append(
                        f"| {mname} | {sig} | {mvis} | {mlines} | {mcx} | {mdoc} |"
                    )
                lines.append("")

        return "\n".join(lines)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for PHP, following Java golden master format."""
        lines = []

        # Header
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        lines.append(f"# {file_name}")
        lines.append("")

        # Info table
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        namespace = self._extract_namespace(data)
        lines.append(f"| Namespace | {namespace if namespace else ''} |")
        lines.append(
            f"| Methods | {stats.get('method_count', len(data.get('methods', [])))} |"
        )
        lines.append(
            f"| Fields | {stats.get('field_count', len(data.get('fields', [])))} |"
        )
        lines.append("")

        # Methods table
        methods = data.get("methods", [])
        if methods:
            lines.append("## Methods")
            lines.append("| Method | Sig | V | L | Cx | Doc |")
            lines.append("|--------|-----|---|---|----|----|")

            for method in methods:
                mname = str(method.get("name", "Unknown"))
                parent_class = method.get("parent_class", "")
                if parent_class:
                    mname = f"{parent_class}::{mname}"

                sig = self._format_compact_signature(method)
                mvis = self._get_visibility_symbol(method.get("visibility", "public"))
                mrange = method.get("line_range", {})
                mlines = f"{mrange.get('start', 0)}-{mrange.get('end', 0)}"
                mcx = method.get("complexity_score", method.get("complexity", 1))
                mdoc = method.get("documentation", "-") or "-"
                if mdoc and len(mdoc) > 20:
                    mdoc = mdoc[:17] + "..."

                lines.append(
                    f"| {mname} | {sig} | {mvis} | {mlines} | {mcx} | {mdoc} |"
                )

        return "\n".join(lines)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for PHP, following Java golden master format."""
        lines = []

        # Header - matching Java format
        lines.append("Type,Name,Signature,Visibility,Lines,Complexity,Doc")

        # Fields
        for field in data.get("fields", []):
            fname = str(field.get("name", "Unknown"))
            parent = field.get("parent_class", "")
            full_name = f"{parent}::{fname}" if parent else fname
            ftype = str(field.get("variable_type", field.get("type", "mixed")))
            sig = f"{full_name}:{ftype}"
            vis = str(field.get("visibility", "public"))
            frange = field.get("line_range", {})
            flines = f"{frange.get('start', 0)}-{frange.get('end', 0)}"
            fdoc = field.get("documentation", "-") or "-"
            lines.append(f"Field,{full_name},{sig},{vis},{flines},,{fdoc}")

        # Methods
        for method in data.get("methods", []):
            mname = str(method.get("name", "Unknown"))
            parent = method.get("parent_class", "")
            full_name = f"{parent}::{mname}" if parent else mname

            sig = self._format_signature(method)
            if method.get("is_static"):
                sig += " [static]"

            vis = str(method.get("visibility", "public"))
            mrange = method.get("line_range", {})
            mlines = f"{mrange.get('start', 0)}-{mrange.get('end', 0)}"
            mcx = method.get("complexity_score", method.get("complexity", 1))
            mdoc = method.get("documentation", "-") or "-"

            entry_type = (
                "Constructor"
                if method.get("is_constructor") or mname.startswith("__construct")
                else "Method"
            )
            lines.append(f"{entry_type},{full_name},{sig},{vis},{mlines},{mcx},{mdoc}")

        return "\n".join(lines)


class PHPFullFormatter(PHPTableFormatter):
    """Full table formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as full table"""
        return self._format_full_table(data)


class PHPCompactFormatter(PHPTableFormatter):
    """Compact table formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as compact table"""
        return self._format_compact_table(data)


class PHPCSVFormatter(PHPTableFormatter):
    """CSV formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as CSV"""
        return self._format_csv(data)
