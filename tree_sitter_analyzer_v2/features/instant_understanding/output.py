"""
Output formatters for Instant Understanding Engine.

Contains functions for generating Markdown and HTML reports.
"""

import logging
from pathlib import Path
from typing import List

from tree_sitter_analyzer_v2.features.instant_understanding.models import (
    UnderstandingReport,
)

logger = logging.getLogger(__name__)


class ReportFormatter:
    """Formats UnderstandingReport into various output formats."""

    def to_markdown(self, report: UnderstandingReport) -> str:
        """Convert report to Markdown format."""
        lines: List[str] = []

        # Header
        lines.append(f"# {report.layer1.project_name} - Understanding Report")
        lines.append(f"\nGenerated: {report.generated_at}\n")
        lines.append("---\n")

        # Layer 1: 5-minute overview
        self._add_layer1_section(lines, report)

        # Layer 2: 15-minute architecture
        self._add_layer2_section(lines, report)

        # Layer 3: 30-minute deep insights
        self._add_layer3_section(lines, report)

        # Additional diagrams
        self._add_additional_diagrams(lines, report)

        return "\n".join(lines)

    def _add_layer1_section(self, lines: List[str], report: UnderstandingReport) -> None:
        """Add Layer 1 section to markdown."""
        lines.append("## [5 Minutes] Quick Overview\n")
        lines.append(f"**Summary**: {report.layer1.summary}\n")
        lines.append("### Statistics")
        for key, value in report.layer1.statistics.items():
            lines.append(f"- {key}: {value}")

        lines.append("\n### Top 5 Core Files")
        for i, file_info in enumerate(report.layer1.top_files[:5], 1):
            lines.append(f"{i}. `{file_info['file']}` - Impact: {file_info['impact']}")

        lines.append("\n### Tech Stack")
        lines.append(f"- Framework: {report.layer1.tech_stack.get('framework', 'Unknown')}")
        lines.append(f"- Tools: {', '.join(report.layer1.tech_stack.get('tools', []))}")

        lines.append("\n### Entry Points")
        for ep in report.layer1.entry_points:
            lines.append(f"- `{ep}`")

        lines.append("\n---\n")

    def _add_layer2_section(self, lines: List[str], report: UnderstandingReport) -> None:
        """Add Layer 2 section to markdown."""
        lines.append("## [15 Minutes] Architecture Understanding\n")

        if report.mermaid_diagrams:
            lines.append("### Architecture Overview\n")
            lines.append("```mermaid")
            lines.append(report.mermaid_diagrams[0])
            lines.append("```\n")

        lines.append("### Call Graph Summary")
        cg = report.layer2.call_graph
        lines.append(f"- Total functions: {cg.get('total_functions', 0)}")
        lines.append(f"- High impact: {cg.get('high_impact', 0)}")
        lines.append(f"- Medium impact: {cg.get('medium_impact', 0)}")
        lines.append(f"- Low impact: {cg.get('low_impact', 0)}")

        lines.append("\n### Design Patterns Detected")
        for pattern in report.layer2.design_patterns:
            lines.append(f"- {pattern}")

        lines.append("\n### Hotspot Chart (Top 10)\n")
        lines.append("```")
        lines.append(report.layer2.hotspot_chart)
        lines.append("```\n")

        lines.append("\n---\n")

    def _add_layer3_section(self, lines: List[str], report: UnderstandingReport) -> None:
        """Add Layer 3 section to markdown."""
        lines.append("## [30 Minutes] Deep Insights\n")

        lines.append("### Performance Analysis")
        perf = report.layer3.performance_analysis
        lines.append(f"\nTotal hotspots detected: {perf.get('total_hotspots', 0)}\n")
        lines.append("**Top 5 Performance Hotspots:**")
        for i, h in enumerate(perf.get("top_5", [])[:5], 1):
            lines.append(f"{i}. `{h['function']}` in `{h['file']}`")
            lines.append(f"   - Complexity: {h['complexity']}, Score: {h['score']:.1f}")
            lines.append(f"   - Recommendation: {h['recommendation']}")

        lines.append("\n### Tech Debt Report")
        debt = report.layer3.tech_debt_report
        lines.append(f"\nTotal debt items: {debt.get('total_count', 0)}")
        lines.append(f"Estimated fix time: {debt.get('estimated_fix_hours', 0):.1f} hours\n")
        lines.append("**By Severity:**")
        for severity, count in debt.get("by_severity", {}).items():
            lines.append(f"- {severity.upper()}: {count}")

        if debt.get("by_type"):
            lines.append("\n**By Type:**")
            for debt_type, count in debt.get("by_type", {}).items():
                lines.append(f"- {debt_type}: {count}")

        lines.append("\n### Refactoring Suggestions")
        for i, suggestion in enumerate(report.layer3.refactoring_suggestions[:5], 1):
            lines.append(f"{i}. `{suggestion['function']}` in `{suggestion['file']}`")
            lines.append(f"   - Reason: {suggestion['reason']}")
            lines.append(f"   - Priority: {suggestion['priority']}")

        lines.append("\n### Recommended Learning Path")
        for i, step in enumerate(report.layer3.learning_path, 1):
            lines.append(f"{i}. {step}")

        lines.append(f"\n### Project Health Score: {report.layer3.health_score:.1f}/100\n")

    def _add_additional_diagrams(self, lines: List[str], report: UnderstandingReport) -> None:
        """Add additional Mermaid diagrams section."""
        if len(report.mermaid_diagrams) > 1:
            lines.append("\n---\n")
            lines.append("## Additional Diagrams\n")

            if len(report.mermaid_diagrams) > 1:
                lines.append("### Call Graph\n")
                lines.append("```mermaid")
                lines.append(report.mermaid_diagrams[1])
                lines.append("```\n")

            if len(report.mermaid_diagrams) > 2:
                lines.append("### Performance Heatmap\n")
                lines.append("```mermaid")
                lines.append(report.mermaid_diagrams[2])
                lines.append("```\n")

    def to_html(self, markdown: str) -> str:
        """Convert Markdown to collapsible HTML."""
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "    <meta charset='utf-8'>",
            "    <title>Project Understanding Report</title>",
            "    <style>",
            "        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 40px auto; padding: 0 20px; }",
            "        details { margin: 20px 0; border: 1px solid #ddd; padding: 10px; border-radius: 5px; }",
            "        summary { cursor: pointer; font-weight: bold; font-size: 1.2em; }",
            "        pre { background: #f5f5f5; padding: 10px; overflow-x: auto; }",
            "        code { background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }",
            "    </style>",
            "    <script src='https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js'></script>",
            "    <script>mermaid.initialize({ startOnLoad: true });</script>",
            "</head>",
            "<body>",
        ]

        sections = markdown.split("## ")
        html_parts.append(f"<h1>{sections[0].strip()}</h1>")

        for section in sections[1:]:
            if not section.strip():
                continue

            section_lines = section.split("\n", 1)
            title = section_lines[0].strip()
            content = section_lines[1] if len(section_lines) > 1 else ""

            content = content.replace("```mermaid", "<div class='mermaid'>")
            content = content.replace("```", "</div>")
            content = content.replace("**", "<strong>").replace("**", "</strong>")
            content = content.replace("`", "<code>").replace("`", "</code>")

            html_parts.append("<details open>")
            html_parts.append(f"    <summary>{title}</summary>")
            html_parts.append(f"    <div>{content}</div>")
            html_parts.append("</details>")

        html_parts.extend(["</body>", "</html>"])

        return "\n".join(html_parts)


def save_report(report: UnderstandingReport, output_path: Path) -> None:
    """
    Save understanding report to file.

    Args:
        report: Understanding report
        output_path: Output file path (.md or .html)
    """
    formatter = ReportFormatter()
    markdown = formatter.to_markdown(report)

    if output_path.suffix == ".md":
        output_path.write_text(markdown, encoding="utf-8")
        logger.info(f"Report saved to {output_path}")
    elif output_path.suffix == ".html":
        html = formatter.to_html(markdown)
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"HTML report saved to {output_path}")
    else:
        raise ValueError(f"Unsupported output format: {output_path.suffix}")
