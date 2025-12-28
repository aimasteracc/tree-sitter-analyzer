#!/usr/bin/env python3
"""
CSS Formatter

Provides specialized formatting for CSS files, focusing on CSS rules,
selectors, properties, at-rules, and media queries.
"""

from typing import Any

from .base_formatter import BaseFormatter


class CSSFormatter(BaseFormatter):
    """Formatter specialized for CSS documents."""

    def __init__(self) -> None:
        """Initialize the CSS formatter."""
        self.language = "css"

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary for CSS files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])

        # Count different types of CSS elements
        rules = [e for e in elements if self._is_rule(e)]
        at_rules = [e for e in elements if self._is_at_rule(e)]

        # Count selectors by type
        id_selectors = [r for r in rules if self._get_selector(r).startswith("#")]
        class_selectors = [r for r in rules if self._get_selector(r).startswith(".")]
        element_selectors = [
            r for r in rules if not self._get_selector(r).startswith((".", "#", "@"))
        ]

        summary = {
            "total_rules": len(rules),
            "at_rules": len(at_rules),
            "id_selectors": len(id_selectors),
            "class_selectors": len(class_selectors),
            "element_selectors": len(element_selectors),
        }

        result = {"file_path": file_path, "language": "css", "summary": summary}

        return self._format_json_output("Summary Results", result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis for CSS files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        line_count = analysis_result.get("line_count", 0)

        # Organize elements by type
        rules = [e for e in elements if self._is_rule(e)]
        at_rules = [e for e in elements if self._is_at_rule(e)]

        structure = {
            "file_path": file_path,
            "language": "css",
            "rules": [
                {
                    "selector": self._get_selector(r),
                    "properties": self._get_properties(r),
                    "element_class": self._get_element_class(r),
                    "line_range": {
                        "start": self._get_start_line(r),
                        "end": self._get_end_line(r),
                    },
                }
                for r in rules
            ],
            "at_rules": [
                {
                    "name": self._get_name(a),
                    "selector": self._get_selector(a),
                    "line_range": {
                        "start": self._get_start_line(a),
                        "end": self._get_end_line(a),
                    },
                }
                for a in at_rules
            ],
            "statistics": {
                "rule_count": len(rules),
                "at_rule_count": len(at_rules),
                "total_lines": line_count,
            },
            "analysis_metadata": analysis_result.get("analysis_metadata", {}),
        }

        return self._format_json_output("Structure Analysis Results", structure)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis for CSS files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        line_count = analysis_result.get("line_count", 0)
        element_count = len(elements)

        # Calculate CSS-specific metrics
        rules = [e for e in elements if self._is_rule(e)]
        at_rules = [e for e in elements if self._is_at_rule(e)]

        # Property usage analysis
        property_usage: dict[str, int] = {}
        for rule in rules:
            props = self._get_properties(rule)
            for prop_name in props.keys():
                property_usage[prop_name] = property_usage.get(prop_name, 0) + 1

        # Selector complexity
        selector_lengths = [len(self._get_selector(r)) for r in rules]
        avg_selector_length = (
            sum(selector_lengths) / len(selector_lengths) if selector_lengths else 0
        )

        advanced_data = {
            "file_path": file_path,
            "language": "css",
            "line_count": line_count,
            "element_count": element_count,
            "success": True,
            "elements": elements,
            "rule_metrics": {
                "total_rules": len(rules),
                "at_rules": len(at_rules),
                "avg_selector_length": round(avg_selector_length, 2),
            },
            "property_usage": dict(
                sorted(property_usage.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            "content_analysis": {
                "has_media_queries": any(
                    "@media" in self._get_name(a) for a in at_rules
                ),
                "has_keyframes": any(
                    "@keyframes" in self._get_name(a) for a in at_rules
                ),
                "has_imports": any("@import" in self._get_name(a) for a in at_rules),
                "complexity": self._calculate_complexity(rules, at_rules),
            },
        }

        if output_format == "text":
            return self._format_advanced_text(advanced_data)
        else:
            return self._format_json_output("Advanced Analysis Results", advanced_data)

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for CSS files."""
        data = self._convert_analysis_result_to_format(analysis_result)
        return self.format_table(data, table_type)

    def _convert_analysis_result_to_format(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        """Convert AnalysisResult to format expected by format_table."""
        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "elements": [
                {
                    "name": getattr(element, "name", ""),
                    "element_type": getattr(element, "element_type", ""),
                    "selector": getattr(element, "selector", ""),
                    "properties": getattr(element, "properties", {}),
                    "element_class": getattr(element, "element_class", ""),
                    "start_line": getattr(element, "start_line", 0),
                    "end_line": getattr(element, "end_line", 0),
                }
                for element in analysis_result.elements
            ],
            "analysis_metadata": {
                "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
                "language": analysis_result.language,
                "file_path": analysis_result.file_path,
                "analyzer_version": "2.0.0",
            },
        }

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for CSS files."""
        if table_type == "compact":
            return self._format_compact(analysis_result)
        elif table_type == "csv":
            return self._format_csv(analysis_result)
        return self._format_full(analysis_result)

    def _format_full(self, analysis_result: dict[str, Any]) -> str:
        """Format full table output for CSS files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])

        output = [f"# CSS Analysis: {file_path}\n"]

        # Document Overview
        output.append("## Document Overview\n")
        output.append("| Property | Value |")
        output.append("|----------|-------|")
        output.append(f"| File | {file_path} |")
        output.append("| Language | css |")
        output.append(f"| Total Lines | {analysis_result.get('line_count', 0)} |")
        output.append(f"| Total Elements | {len(elements)} |")
        output.append("")

        # Rules Section
        rules = [e for e in elements if self._is_rule(e)]
        if rules:
            output.append("## CSS Rules\n")
            output.append("| Selector | Class | Properties | Lines |")
            output.append("|----------|-------|------------|-------|")
            for rule in rules:
                selector = self._get_selector(rule)[:40]
                element_class = self._get_element_class(rule)
                props = self._get_properties(rule)
                prop_count = len(props)
                start = self._get_start_line(rule)
                end = self._get_end_line(rule)
                output.append(
                    f"| `{selector}` | {element_class} | {prop_count} props | {start}-{end} |"
                )
            output.append("")

        # At-Rules Section
        at_rules = [e for e in elements if self._is_at_rule(e)]
        if at_rules:
            output.append("## At-Rules\n")
            output.append("| Type | Name | Lines |")
            output.append("|------|------|-------|")
            for at_rule in at_rules:
                name = self._get_name(at_rule)[:50]
                start = self._get_start_line(at_rule)
                end = self._get_end_line(at_rule)
                output.append(f"| at-rule | `{name}` | {start}-{end} |")
            output.append("")

        # Property Usage Section (top properties)
        if rules:
            output.append("## Top Properties\n")
            property_usage: dict[str, int] = {}
            for rule in rules:
                props = self._get_properties(rule)
                for prop_name in props.keys():
                    property_usage[prop_name] = property_usage.get(prop_name, 0) + 1

            top_props = sorted(
                property_usage.items(), key=lambda x: x[1], reverse=True
            )[:10]
            output.append("| Property | Usage Count |")
            output.append("|----------|-------------|")
            for prop, count in top_props:
                output.append(f"| {prop} | {count} |")
            output.append("")

        return "\n".join(output)

    def _format_compact(self, analysis_result: dict[str, Any]) -> str:
        """Format compact table output for CSS files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])

        # Count elements by type
        rules = [e for e in elements if self._is_rule(e)]
        at_rules = [e for e in elements if self._is_at_rule(e)]

        # Count selector types
        id_selectors = [r for r in rules if self._get_selector(r).startswith("#")]
        class_selectors = [r for r in rules if self._get_selector(r).startswith(".")]
        element_selectors = [
            r for r in rules if not self._get_selector(r).startswith((".", "#", "@"))
        ]

        # Extract filename from path
        filename = file_path.split("/")[-1].split("\\")[-1]
        if filename.endswith(".css"):
            filename = filename[:-4]

        output = [f"# {filename}\n"]

        # Summary table
        output.append("## Summary\n")
        output.append("| Element Type | Count |")
        output.append("|--------------|-------|")
        output.append(f"| Rules | {len(rules)} |")
        output.append(f"| At-Rules | {len(at_rules)} |")
        output.append(f"| ID Selectors (#) | {len(id_selectors)} |")
        output.append(f"| Class Selectors (.) | {len(class_selectors)} |")
        output.append(f"| Element Selectors | {len(element_selectors)} |")
        output.append(f"| **Total** | **{len(elements)}** |")
        output.append("")

        # Sample rules
        if rules:
            output.append("## Sample Rules (Top 10)\n")
            output.append("| Selector | Properties | Line |")
            output.append("|----------|------------|------|")
            for rule in rules[:10]:
                selector = self._get_selector(rule)[:30]
                props = self._get_properties(rule)
                prop_count = len(props)
                line = self._get_start_line(rule)
                output.append(f"| `{selector}` | {prop_count} | {line} |")
            output.append("")

        return "\n".join(output)

    def _format_csv(self, analysis_result: dict[str, Any]) -> str:
        """Format CSV output for CSS files."""
        elements = analysis_result.get("elements", [])

        output = ["name,element_type,selector,property_count,start_line,end_line"]

        for e in elements:
            name = self._get_name(e).replace(",", ";")
            element_type = self._get_element_type(e)
            selector = self._get_selector(e).replace(",", ";")
            prop_count = len(self._get_properties(e))
            start = self._get_start_line(e)
            end = self._get_end_line(e)
            output.append(
                f"{name},{element_type},{selector},{prop_count},{start},{end}"
            )

        return "\n".join(output)

    def _calculate_complexity(self, rules: list, at_rules: list) -> str:
        """Calculate CSS complexity based on structure."""
        score: float = 0
        score += len(rules) * 1
        score += len(at_rules) * 3

        # Add property count
        total_props = sum(len(self._get_properties(r)) for r in rules)
        score += float(total_props) * 0.5

        if score < 50:
            return "Simple"
        elif score < 150:
            return "Moderate"
        elif score < 300:
            return "Complex"
        else:
            return "Very Complex"

    def _format_advanced_text(self, data: dict[str, Any]) -> str:
        """Format advanced analysis in text format."""
        output = ["--- Advanced Analysis Results ---"]

        output.append(f'"File: {data["file_path"]}"')
        output.append(f'"Language: {data["language"]}"')
        output.append(f'"Lines: {data["line_count"]}"')
        output.append(f'"Elements: {data["element_count"]}"')

        metrics = data["rule_metrics"]
        output.append(f'"Total Rules: {metrics["total_rules"]}"')
        output.append(f'"At-Rules: {metrics["at_rules"]}"')
        output.append(f'"Avg Selector Length: {metrics["avg_selector_length"]}"')

        content = data["content_analysis"]
        output.append(f'"Has Media Queries: {content["has_media_queries"]}"')
        output.append(f'"Has Keyframes: {content["has_keyframes"]}"')
        output.append(f'"Complexity: {content["complexity"]}"')

        return "\n".join(output)

    def _format_json_output(self, title: str, data: dict[str, Any]) -> str:
        """Format JSON output with title."""
        import json

        output = [f"--- {title} ---"]
        output.append(json.dumps(data, indent=2, ensure_ascii=False))
        return "\n".join(output)

    # Helper methods for extracting data from elements (handles both dict and object)
    def _is_rule(self, element: Any) -> bool:
        """Check if element is a CSS rule."""
        if isinstance(element, dict):
            element_type = element.get("element_type", "")
            element_class = element.get("element_class", "")
        else:
            element_type = getattr(element, "element_type", "")
            element_class = getattr(element, "element_class", "")

        return bool(element_type == "rule" or element_class != "at_rule")

    def _is_at_rule(self, element: Any) -> bool:
        """Check if element is an at-rule."""
        if isinstance(element, dict):
            element_class = element.get("element_class", "")
        else:
            element_class = getattr(element, "element_class", "")

        return bool(element_class == "at_rule")

    def _get_name(self, element: Any) -> str:
        """Extract name safely"""
        if isinstance(element, dict):
            return str(element.get("name", ""))
        return str(getattr(element, "name", ""))

    def _get_element_type(self, element: Any) -> str:
        """Extract element type safely"""
        if isinstance(element, dict):
            return str(element.get("element_type", ""))
        return str(getattr(element, "element_type", ""))

    def _get_selector(self, element: Any) -> str:
        """Extract selector safely"""
        if isinstance(element, dict):
            return str(element.get("selector", ""))
        return str(getattr(element, "selector", ""))

    def _get_properties(self, element: Any) -> dict[str, Any]:
        """Extract properties safely"""
        if isinstance(element, dict):
            props = element.get("properties", {})
        else:
            props = getattr(element, "properties", {})

        if isinstance(props, dict):
            return props
        return {}

    def _get_element_class(self, element: Any) -> str:
        """Extract element class safely"""
        if isinstance(element, dict):
            return str(element.get("element_class", ""))
        return str(getattr(element, "element_class", ""))

    def _get_start_line(self, element: Any) -> int:
        """Extract start line safely"""
        try:
            if isinstance(element, dict):
                return int(element.get("start_line", 0))
            return int(getattr(element, "start_line", 0))
        except (ValueError, TypeError):
            return 0

    def _get_end_line(self, element: Any) -> int:
        """Extract end line safely"""
        try:
            if isinstance(element, dict):
                return int(element.get("end_line", 0))
            return int(getattr(element, "end_line", 0))
        except (ValueError, TypeError):
            return 0
