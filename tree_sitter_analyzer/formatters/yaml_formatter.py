#!/usr/bin/env python3
"""
YAML Formatter

Provides specialized formatting for YAML files, focusing on configuration structure
including mappings, sequences, anchors, aliases, and multi-document support.
"""

from typing import Any

from .base_formatter import BaseFormatter


class YAMLFormatter(BaseFormatter):
    """Formatter specialized for YAML documents."""

    def __init__(self) -> None:
        """Initialize the YAML formatter."""
        self.language = "yaml"

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary for YAML files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])

        # Count different types of YAML elements
        documents = [e for e in elements if e.get("element_type") == "document"]
        mappings = [e for e in elements if e.get("element_type") == "mapping"]
        sequences = [e for e in elements if e.get("element_type") == "sequence"]
        anchors = [e for e in elements if e.get("element_type") == "anchor"]
        aliases = [e for e in elements if e.get("element_type") == "alias"]
        comments = [e for e in elements if e.get("element_type") == "comment"]

        summary = {
            "documents": len(documents),
            "mappings": len(mappings),
            "sequences": len(sequences),
            "anchors": [{"name": a.get("anchor_name", "")} for a in anchors],
            "aliases": [{"target": a.get("alias_target", "")} for a in aliases],
            "comments": len(comments),
        }

        result = {"file_path": file_path, "language": "yaml", "summary": summary}

        return self._format_json_output("Summary Results", result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis for YAML files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        line_count = analysis_result.get("line_count", 0)

        # Organize elements by type
        documents = [e for e in elements if e.get("element_type") == "document"]
        mappings = [e for e in elements if e.get("element_type") == "mapping"]
        sequences = [e for e in elements if e.get("element_type") == "sequence"]
        anchors = [e for e in elements if e.get("element_type") == "anchor"]
        aliases = [e for e in elements if e.get("element_type") == "alias"]
        comments = [e for e in elements if e.get("element_type") == "comment"]

        structure = {
            "file_path": file_path,
            "language": "yaml",
            "documents": [
                {
                    "index": d.get("document_index", 0),
                    "line_range": {
                        "start": d.get("start_line", 0),
                        "end": d.get("end_line", 0),
                    },
                    "child_count": d.get("child_count", 0),
                }
                for d in documents
            ],
            "mappings": [
                {
                    "key": m.get("key", ""),
                    "value_type": m.get("value_type", ""),
                    "nesting_level": m.get("nesting_level", 0),
                    "line_range": {
                        "start": m.get("start_line", 0),
                        "end": m.get("end_line", 0),
                    },
                }
                for m in mappings
            ],
            "sequences": [
                {
                    "child_count": s.get("child_count", 0),
                    "nesting_level": s.get("nesting_level", 0),
                    "line_range": {
                        "start": s.get("start_line", 0),
                        "end": s.get("end_line", 0),
                    },
                }
                for s in sequences
            ],
            "anchors": [
                {
                    "name": a.get("anchor_name", ""),
                    "line": a.get("start_line", 0),
                }
                for a in anchors
            ],
            "aliases": [
                {
                    "target": a.get("alias_target", ""),
                    "line": a.get("start_line", 0),
                }
                for a in aliases
            ],
            "statistics": {
                "document_count": len(documents),
                "mapping_count": len(mappings),
                "sequence_count": len(sequences),
                "anchor_count": len(anchors),
                "alias_count": len(aliases),
                "comment_count": len(comments),
                "total_lines": line_count,
            },
            "analysis_metadata": analysis_result.get("analysis_metadata", {}),
        }

        return self._format_json_output("Structure Analysis Results", structure)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis for YAML files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        line_count = analysis_result.get("line_count", 0)
        element_count = len(elements)

        # Calculate YAML-specific metrics
        documents = [e for e in elements if e.get("element_type") == "document"]
        mappings = [e for e in elements if e.get("element_type") == "mapping"]
        sequences = [e for e in elements if e.get("element_type") == "sequence"]
        anchors = [e for e in elements if e.get("element_type") == "anchor"]
        aliases = [e for e in elements if e.get("element_type") == "alias"]
        comments = [e for e in elements if e.get("element_type") == "comment"]

        # Calculate nesting metrics
        nesting_levels = [m.get("nesting_level", 0) for m in mappings + sequences]
        max_nesting = max(nesting_levels) if nesting_levels else 0
        avg_nesting = sum(nesting_levels) / len(nesting_levels) if nesting_levels else 0

        # Value type distribution
        value_types: dict[str, int] = {}
        for m in mappings:
            vt = m.get("value_type", "unknown")
            value_types[vt] = value_types.get(vt, 0) + 1

        advanced_data = {
            "file_path": file_path,
            "language": "yaml",
            "line_count": line_count,
            "element_count": element_count,
            "success": True,
            "elements": elements,
            "document_metrics": {
                "document_count": len(documents),
                "mapping_count": len(mappings),
                "sequence_count": len(sequences),
                "anchor_count": len(anchors),
                "alias_count": len(aliases),
                "comment_count": len(comments),
                "max_nesting_level": max_nesting,
                "avg_nesting_level": round(avg_nesting, 2),
            },
            "value_type_distribution": value_types,
            "content_analysis": {
                "is_multi_document": len(documents) > 1,
                "has_anchors": len(anchors) > 0,
                "has_aliases": len(aliases) > 0,
                "has_comments": len(comments) > 0,
                "complexity": self._calculate_complexity(
                    mappings, sequences, max_nesting
                ),
            },
        }

        if output_format == "text":
            return self._format_advanced_text(advanced_data)
        else:
            return self._format_json_output("Advanced Analysis Results", advanced_data)

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for YAML files."""
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
                    "key": getattr(element, "key", ""),
                    "value": getattr(element, "value", ""),
                    "value_type": getattr(element, "value_type", ""),
                    "anchor_name": getattr(element, "anchor_name", ""),
                    "alias_target": getattr(element, "alias_target", ""),
                    "nesting_level": getattr(element, "nesting_level", 0),
                    "document_index": getattr(element, "document_index", 0),
                    "child_count": getattr(element, "child_count", None),
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
        """Format table output for YAML files."""
        if table_type == "compact":
            return self._format_compact(analysis_result)
        elif table_type == "csv":
            return self._format_csv(analysis_result)
        return self._format_full(analysis_result)

    def _format_full(self, analysis_result: dict[str, Any]) -> str:
        """Format full table output for YAML files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])

        # Extract filename from path
        filename = file_path.split("/")[-1].split("\\")[-1]
        if filename.endswith((".yaml", ".yml")):
            filename = filename.rsplit(".", 1)[0]

        output = [f"# {filename}\n"]

        # Document Overview
        output.append("## Document Overview\n")
        output.append("| Property | Value |")
        output.append("|----------|-------|")
        output.append(f"| File | {file_path} |")
        output.append("| Language | yaml |")
        output.append(f"| Total Lines | {analysis_result.get('line_count', 0)} |")
        output.append(f"| Total Elements | {len(elements)} |")
        output.append("")

        # Documents Section
        documents = [e for e in elements if e.get("element_type") == "document"]
        if documents:
            output.append("## Documents\n")
            output.append("| Index | Lines | Children |")
            output.append("|-------|-------|----------|")
            for doc in documents:
                idx = doc.get("document_index", 0)
                start = doc.get("start_line", 0)
                end = doc.get("end_line", 0)
                children = doc.get("child_count", 0)
                output.append(f"| {idx} | {start}-{end} | {children} |")
            output.append("")

        # Mappings Section
        mappings = [e for e in elements if e.get("element_type") == "mapping"]
        if mappings:
            output.append("## Mappings\n")
            output.append("| Key | Value Type | Nesting | Line |")
            output.append("|-----|------------|---------|------|")
            for m in mappings[:50]:  # Limit to 50 for readability
                key = m.get("key", "")[:30]
                vtype = m.get("value_type", "")
                nesting = m.get("nesting_level", 0)
                line = m.get("start_line", 0)
                output.append(f"| {key} | {vtype} | {nesting} | {line} |")
            if len(mappings) > 50:
                output.append(f"| ... | ({len(mappings) - 50} more) | | |")
            output.append("")

        # Sequences Section
        sequences = [e for e in elements if e.get("element_type") == "sequence"]
        if sequences:
            output.append("## Sequences\n")
            output.append("| Items | Nesting | Line |")
            output.append("|-------|---------|------|")
            for s in sequences:
                items = s.get("child_count", 0)
                nesting = s.get("nesting_level", 0)
                line = s.get("start_line", 0)
                output.append(f"| {items} | {nesting} | {line} |")
            output.append("")

        # Anchors Section
        anchors = [e for e in elements if e.get("element_type") == "anchor"]
        if anchors:
            output.append("## Anchors\n")
            output.append("| Name | Line |")
            output.append("|------|------|")
            for a in anchors:
                name = a.get("anchor_name", "")
                line = a.get("start_line", 0)
                output.append(f"| &{name} | {line} |")
            output.append("")

        # Aliases Section
        aliases = [e for e in elements if e.get("element_type") == "alias"]
        if aliases:
            output.append("## Aliases\n")
            output.append("| Target | Line |")
            output.append("|--------|------|")
            for a in aliases:
                target = a.get("alias_target", "")
                line = a.get("start_line", 0)
                output.append(f"| *{target} | {line} |")
            output.append("")

        # Comments Section
        comments = [e for e in elements if e.get("element_type") == "comment"]
        if comments:
            output.append("## Comments\n")
            output.append("| Content | Line |")
            output.append("|---------|------|")
            for c in comments:
                content = c.get("value", "")[:50]
                if len(c.get("value", "")) > 50:
                    content += "..."
                line = c.get("start_line", 0)
                output.append(f"| {content} | {line} |")
            output.append("")

        return "\n".join(output)

    def _format_compact(self, analysis_result: dict[str, Any]) -> str:
        """Format compact table output for YAML files."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])

        # Count elements by type
        documents = [e for e in elements if e.get("element_type") == "document"]
        mappings = [e for e in elements if e.get("element_type") == "mapping"]
        sequences = [e for e in elements if e.get("element_type") == "sequence"]
        anchors = [e for e in elements if e.get("element_type") == "anchor"]
        aliases = [e for e in elements if e.get("element_type") == "alias"]
        comments = [e for e in elements if e.get("element_type") == "comment"]

        # Extract filename from path
        filename = file_path.split("/")[-1].split("\\")[-1]
        if filename.endswith((".yaml", ".yml")):
            filename = filename.rsplit(".", 1)[0]

        output = [f"# {filename}\n"]

        # Summary table
        output.append("## Summary\n")
        output.append("| Element Type | Count |")
        output.append("|--------------|-------|")
        output.append(f"| Documents | {len(documents)} |")
        output.append(f"| Mappings | {len(mappings)} |")
        output.append(f"| Sequences | {len(sequences)} |")
        output.append(f"| Anchors | {len(anchors)} |")
        output.append(f"| Aliases | {len(aliases)} |")
        output.append(f"| Comments | {len(comments)} |")
        output.append(f"| **Total** | **{len(elements)}** |")
        output.append("")

        # Top-level mappings only
        top_level_mappings = [m for m in mappings if m.get("nesting_level", 0) == 1]
        if top_level_mappings:
            output.append("## Top-Level Keys\n")
            output.append("| Key | Value Type | Line |")
            output.append("|-----|------------|------|")
            for m in top_level_mappings:
                key = m.get("key", "")[:30]
                vtype = m.get("value_type", "")
                line = m.get("start_line", 0)
                output.append(f"| {key} | {vtype} | {line} |")
            output.append("")

        # Anchors and Aliases
        if anchors or aliases:
            output.append("## References\n")
            output.append("| Type | Name/Target | Line |")
            output.append("|------|-------------|------|")
            for a in anchors:
                output.append(
                    f"| Anchor | &{a.get('anchor_name', '')} | {a.get('start_line', 0)} |"
                )
            for a in aliases:
                output.append(
                    f"| Alias | *{a.get('alias_target', '')} | {a.get('start_line', 0)} |"
                )
            output.append("")

        return "\n".join(output)

    def _format_csv(self, analysis_result: dict[str, Any]) -> str:
        """Format CSV output for YAML files."""
        elements = analysis_result.get("elements", [])

        output = ["name,element_type,value_type,nesting_level,start_line,end_line"]

        for e in elements:
            name = e.get("name", "").replace(",", ";")
            element_type = e.get("element_type", "")
            value_type = e.get("value_type", "") or ""
            nesting = e.get("nesting_level", 0)
            start = e.get("start_line", 0)
            end = e.get("end_line", 0)
            output.append(f"{name},{element_type},{value_type},{nesting},{start},{end}")

        return "\n".join(output)

    def _calculate_complexity(
        self, mappings: list[dict], sequences: list[dict], max_nesting: int
    ) -> str:
        """Calculate document complexity based on structure."""
        score = 0
        score += len(mappings) * 1
        score += len(sequences) * 2
        score += max_nesting * 5

        if score < 20:
            return "Simple"
        elif score < 50:
            return "Moderate"
        elif score < 100:
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

        metrics = data["document_metrics"]
        output.append(f'"Documents: {metrics["document_count"]}"')
        output.append(f'"Mappings: {metrics["mapping_count"]}"')
        output.append(f'"Sequences: {metrics["sequence_count"]}"')
        output.append(f'"Anchors: {metrics["anchor_count"]}"')
        output.append(f'"Aliases: {metrics["alias_count"]}"')
        output.append(f'"Comments: {metrics["comment_count"]}"')
        output.append(f'"Max Nesting: {metrics["max_nesting_level"]}"')

        content = data["content_analysis"]
        output.append(f'"Multi-Document: {content["is_multi_document"]}"')
        output.append(f'"Has Anchors: {content["has_anchors"]}"')
        output.append(f'"Complexity: {content["complexity"]}"')

        return "\n".join(output)

    def _format_json_output(self, title: str, data: dict[str, Any]) -> str:
        """Format JSON output with title."""
        import json

        output = [f"--- {title} ---"]
        output.append(json.dumps(data, indent=2, ensure_ascii=False))
        return "\n".join(output)
