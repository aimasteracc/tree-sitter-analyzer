#!/usr/bin/env python3
"""
Ruby-specific table formatter.
Follows Java golden master format for consistency.
"""

from typing import Any

from .base_formatter import BaseTableFormatter


class RubyTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Ruby, following Java golden master format."""

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Convert visibility to symbol."""
        visibility_map = {
            "public": "+",
            "private": "-",
            "protected": "#",
            "module": "~",
        }
        return visibility_map.get(str(visibility).lower(), "+")

    def _format_signature(self, method: dict[str, Any]) -> str:
        """Format method signature like Java: (param:type):returnType."""
        params = method.get("parameters", [])
        param_strs = []
        for p in params:
            if isinstance(p, dict):
                name = p.get("name", "")
                ptype = p.get("type", "Any")
                param_strs.append(f"{name}:{ptype}" if name else str(ptype))
            else:
                param_strs.append(str(p))

        return_type = method.get("return_type", "")
        return (
            f"({', '.join(param_strs)}):{return_type}"
            if return_type
            else f"({', '.join(param_strs)}):"
        )

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

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Ruby, following Java golden master format."""
        lines = []

        # Header - use module/class name or file name
        classes = data.get("classes", [])
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]

        if len(classes) == 1:
            class_name = classes[0].get("name", file_name)
            lines.append(f"# {class_name}")
        else:
            lines.append(f"# {file_name}")
        lines.append("")

        # Require statements (imports)
        imports = data.get("imports", [])
        if imports:
            lines.append("## Imports")
            lines.append("```ruby")
            for imp in imports:
                import_text = imp.get("raw_text", "").strip()
                if import_text:
                    lines.append(import_text)
            lines.append("```")
            lines.append("")

        methods = data.get("methods", [])
        fields = data.get("fields", [])

        # Build a map of which class each method/field belongs to
        # For nested classes, methods/fields should belong to the innermost class
        def get_parent_class(item_start: int) -> str | None:
            """Find the innermost class that contains this item."""
            containing_classes = []
            for c in classes:
                c_range = c.get("line_range", {})
                c_start = c_range.get("start", 0)
                c_end = c_range.get("end", 0)
                if c_start <= item_start <= c_end:
                    containing_classes.append((c, c_end - c_start))

            if not containing_classes:
                return None

            # Return the smallest (innermost) class
            containing_classes.sort(key=lambda x: x[1])
            name = containing_classes[0][0].get("name")
            return str(name) if name else None

        # Count methods/fields per class (only direct members, not nested)
        class_method_counts: dict[str, int] = {c.get("name", ""): 0 for c in classes}
        class_field_counts: dict[str, int] = {c.get("name", ""): 0 for c in classes}

        for m in methods:
            m_start = m.get("line_range", {}).get("start", 0)
            parent = get_parent_class(m_start)
            if parent and parent in class_method_counts:
                class_method_counts[parent] += 1

        for f in fields:
            f_start = f.get("line_range", {}).get("start", 0)
            parent = get_parent_class(f_start)
            if parent and parent in class_field_counts:
                class_field_counts[parent] += 1

        # Classes Overview - following Java format
        if classes:
            lines.append("## Classes Overview")
            lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
            lines.append("|-------|------|------------|-------|---------|--------|")

            for class_info in classes:
                name = str(class_info.get("name", "Unknown"))
                class_type = str(
                    class_info.get("class_type", class_info.get("type", "class"))
                )
                visibility = str(class_info.get("visibility", "public"))
                line_range = class_info.get("line_range", {})
                lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

                method_count = class_method_counts.get(name, 0)
                field_count = class_field_counts.get(name, 0)

                lines.append(
                    f"| {name} | {class_type} | {visibility} | {lines_str} | "
                    f"{method_count} | {field_count} |"
                )
            lines.append("")

        # Per-class details
        for class_info in classes:
            class_name = str(class_info.get("name", "Unknown"))
            class_range = class_info.get("line_range", {})
            start_line = class_range.get("start", 0)
            end_line = class_range.get("end", 0)

            lines.append(f"## {class_name} ({start_line}-{end_line})")

            # Fields for this class (only direct members)
            class_fields = [
                f
                for f in fields
                if get_parent_class(f.get("line_range", {}).get("start", 0))
                == class_name
            ]
            if class_fields:
                lines.append("### Fields")
                lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
                lines.append("|------|------|-----|-----------|------|-----|")

                for field in class_fields:
                    fname = str(field.get("name", "Unknown"))
                    ftype = str(field.get("variable_type", field.get("type", "None")))
                    fvis = self._get_visibility_symbol(
                        field.get("visibility", "public")
                    )
                    modifiers = field.get("modifiers", [])
                    if isinstance(modifiers, list):
                        modifiers_str = ",".join(str(m) for m in modifiers)
                    else:
                        modifiers_str = str(modifiers) if modifiers else ""
                    fline = field.get("line_range", {}).get("start", 0)
                    fdoc = field.get("documentation", "-") or "-"
                    if fdoc and len(fdoc) > 30:
                        fdoc = fdoc[:27] + "..."

                    lines.append(
                        f"| {fname} | {ftype} | {fvis} | {modifiers_str} | {fline} | {fdoc} |"
                    )
                lines.append("")

            # Methods for this class (only direct members)
            class_methods = [
                m
                for m in methods
                if get_parent_class(m.get("line_range", {}).get("start", 0))
                == class_name
            ]

            # Group by visibility - for Ruby, combine all public methods
            constructors = [
                m
                for m in class_methods
                if m.get("is_constructor") or m.get("name") == "initialize"
            ]
            public_methods = [m for m in class_methods if m not in constructors]

            # In Ruby golden master, all methods are shown as "Public Methods"
            if public_methods or constructors:
                all_methods = constructors + public_methods
                lines.append("### Public Methods")
                lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
                lines.append("|--------|-----------|-----|-------|----|----|")

                for method in all_methods:
                    mname = str(method.get("name", "Unknown"))

                    # Ruby method naming: Class#method for instance, Class.method for class methods
                    # Check if name already has class prefix
                    metadata = method.get("metadata", {})
                    method_type = metadata.get("method_type", "instance")

                    # Only add prefix if not already present
                    if "#" not in mname and "." not in mname:
                        if method_type == "class" or method.get("is_static"):
                            mname = f"{class_name}.{mname}"
                        else:
                            mname = f"{class_name}#{mname}"

                    sig = self._format_signature(method)
                    mvis = self._get_visibility_symbol(
                        method.get("visibility", "public")
                    )

                    # Add static marker if applicable
                    if method.get("is_static") or method_type == "class":
                        sig += " [static]"

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

        # Module-level methods (not in any class)
        module_level_methods = [
            m
            for m in methods
            if get_parent_class(m.get("line_range", {}).get("start", 0)) is None
        ]
        if module_level_methods:
            lines.append("## Module Functions")
            lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
            lines.append("|--------|-----------|-----|-------|----|----|")
            for method in module_level_methods:
                mname = str(method.get("name", "Unknown"))
                sig = self._format_signature(method)
                mvis = self._get_visibility_symbol(method.get("visibility", "public"))
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
        """Compact table format for Ruby, following Java golden master format."""
        lines = []

        # Header
        classes = data.get("classes", [])
        file_path = data.get("file_path", "Unknown")
        file_name = file_path.split("/")[-1].split("\\")[-1]

        if len(classes) == 1:
            class_name = classes[0].get("name", file_name)
            lines.append(f"# {class_name}")
        else:
            lines.append(f"# {file_name}")
        lines.append("")

        # Info table
        stats = data.get("statistics") or {}
        lines.append("## Info")
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append("| Package |  |")
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
                # Build method name with class prefix
                mname = str(method.get("name", "Unknown"))
                parent_class = method.get("parent_class", "")
                if parent_class:
                    metadata = method.get("metadata", {})
                    method_type = metadata.get("method_type", "instance")
                    prefix = "." if method_type == "class" else "#"
                    mname = f"{parent_class}{prefix}{mname}"

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
        """CSV format for Ruby, following Java golden master format."""
        lines = []

        # Header - matching Java format
        lines.append("Type,Name,Signature,Visibility,Lines,Complexity,Doc")

        # Fields
        for field in data.get("fields", []):
            fname = str(field.get("name", "Unknown"))
            parent = field.get("parent_class", "")
            full_name = f"{parent}::{fname}" if parent else fname
            ftype = str(field.get("variable_type", field.get("type", "None")))
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
            metadata = method.get("metadata", {})
            method_type = metadata.get("method_type", "instance")

            # Ruby method naming convention
            if parent:
                prefix = "." if method_type == "class" else "#"
                full_name = f"{parent}{prefix}{mname}"
            else:
                full_name = mname

            sig = self._format_signature(method)
            if method.get("is_static") or method_type == "class":
                sig += " [static]"

            vis = str(method.get("visibility", "public"))
            mrange = method.get("line_range", {})
            mlines = f"{mrange.get('start', 0)}-{mrange.get('end', 0)}"
            mcx = method.get("complexity_score", method.get("complexity", 1))
            mdoc = method.get("documentation", "-") or "-"

            entry_type = (
                "Constructor"
                if method.get("is_constructor") or mname == "initialize"
                else "Method"
            )
            lines.append(f"{entry_type},{full_name},{sig},{vis},{mlines},{mcx},{mdoc}")

        return "\n".join(lines)


class RubyFullFormatter(RubyTableFormatter):
    """Full table formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as full table"""
        return self._format_full_table(data)


class RubyCompactFormatter(RubyTableFormatter):
    """Compact table formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as compact table"""
        return self._format_compact_table(data)


class RubyCSVFormatter(RubyTableFormatter):
    """CSV formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as CSV"""
        return self._format_csv(data)
