#!/usr/bin/env python3
"""
Project Overview Reporter - Generates reports in multiple formats.

Supports Markdown, JSON, and TOON (Token-Oriented Object Notation) output formats.
Reports include health metrics, dependencies, patterns, security issues, and recommendations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from tree_sitter_analyzer.mcp.utils.format_helper import format_as_toon
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


class OutputFormat(Enum):
    """Supported output formats."""

    MARKDOWN = "markdown"
    JSON = "json"
    TOON = "toon"


@dataclass(frozen=True)
class ReportSection:
    """A section of the overview report."""

    title: str
    content: str
    priority: int = 0  # Lower = higher priority (appears first)
    visual_element: str | None = None  # Optional visual (badge, bar, heatmap)


@dataclass(frozen=True)
class VisualizationElement:
    """Visual elements for report rendering."""

    type: str  # badge, progress_bar, heatmap, table
    data: dict[str, Any]
    label: str | None = None


class OverviewReporter:
    """Generates formatted project overview reports."""

    def __init__(self, report: Any) -> None:
        """Initialize reporter with an OverviewReport.

        Args:
            report: OverviewReport from OverviewAggregator.
        """
        self.report = report

    def generate_markdown(self) -> str:
        """Generate Markdown format report.

        Returns:
            Markdown formatted report string.
        """
        sections = self._build_sections()
        lines = ["# Project Overview Report\n"]

        # Header with project path and summary
        lines.append(f"**Project**: `{self.report.project_path}`\n")
        lines.append("---\n")

        # Add sections in priority order
        for section in sorted(sections, key=lambda s: s.priority):
            lines.append(f"## {section.title}\n")
            lines.append(section.content)
            lines.append("")

        # Add errors if any
        if self.report.errors:
            lines.append("## Errors\n")
            for name, error in self.report.errors.items():
                lines.append(f"- **{name}**: {error}")
            lines.append("")

        return "\n".join(lines)

    def generate_json(self) -> str:
        """Generate JSON format report.

        Returns:
            JSON formatted report string.
        """
        data = self.report.to_dict()
        return json.dumps(data, indent=2, ensure_ascii=False)

    def generate_toon(self) -> str:
        """Generate TOON (Token-Oriented Object Notation) format report.

        Returns:
            TOON formatted report string.
        """
        data = self.report.to_dict()
        return format_as_toon(data)

    def _build_sections(self) -> list[ReportSection]:
        """Build report sections from analysis results.

        Returns:
            List of ReportSection objects ordered by display priority.
        """
        sections: list[ReportSection] = []

        # Summary section (highest priority)
        sections.append(self._build_summary_section())

        # Health Analysis
        if self.report.health_scores:
            sections.append(self._build_health_section())

        # Dependency Analysis
        if self.report.dependency_graph:
            sections.append(self._build_dependency_section())

        # Security Issues
        if self.report.security_issues:
            sections.append(self._build_security_section())

        # Design Patterns
        if self.report.design_patterns:
            sections.append(self._build_patterns_section())

        # Dead Code
        if self.report.dead_code:
            sections.append(self._build_dead_code_section())

        # Ownership
        if self.report.ownership:
            sections.append(self._build_ownership_section())

        # Blast Radius
        if self.report.blast_radius:
            sections.append(self._build_blast_section())

        return sections

    def _build_summary_section(self) -> ReportSection:
        """Build executive summary section."""
        # Count how many analyses have data
        analyses = [
            self.report.dependency_graph,
            self.report.health_scores,
            self.report.design_patterns,
            self.report.security_issues,
            self.report.dead_code,
            self.report.ownership,
            self.report.blast_radius,
        ]
        total_analyses = len([a for a in analyses if a is not None])
        error_count = len(self.report.errors) if self.report.errors else 0

        content = f"""**Analyses Completed**: {total_analyses}

| Metric | Value |
|--------|-------|
| Project Path | `{self.report.project_path}` |
| Analyses Run | {total_analyses} |
| Errors | {error_count} |
"""
        return ReportSection(title="Summary", content=content, priority=0)

    def _build_health_section(self) -> ReportSection:
        """Build health score analysis section."""
        data = self.report.health_scores or {}

        if not data:
            return ReportSection(title="Health Analysis", content="No data available.", priority=10)

        file_count = data.get("file_count", 0)
        avg_score = data.get("avg_score", 0)
        grade_dist = data.get("grade_distribution", {})

        # Build grade distribution table
        grade_lines = ["| Grade | Count |", "|-------|-------|"]
        for grade in ["A", "B", "C", "D", "F"]:
            count = grade_dist.get(grade, 0)
            bar = "█" * min(count // 5 + 1, 20) if count else ""
            grade_lines.append(f"| {grade} | {count} {bar} |")

        content = f"""**Average Score**: {avg_score:.1f}/100
**Files Analyzed**: {file_count}

### Grade Distribution
{chr(10).join(grade_lines)}

### Top Risk Files
"""

        top_risks = data.get("top_risk_files", [])
        if top_risks:
            for item in top_risks[:5]:
                path = item.get("path", "unknown")
                score = item.get("score", 0)
                grade = item.get("grade", "N/A")
                content += f"- `{path}` - Score: {score}, Grade: {grade}\n"
        else:
            content += "No high-risk files detected.\n"

        return ReportSection(
            title="Health Analysis",
            content=content,
            priority=10,
            visual_element="bar",
        )

    def _build_dependency_section(self) -> ReportSection:
        """Build dependency graph section."""
        data = self.report.dependency_graph or {}

        if not data:
            return ReportSection(title="Dependency Analysis", content="No data available.", priority=20)

        node_count = data.get("node_count", 0)
        edge_count = data.get("edge_count", 0)
        has_cycles = data.get("has_cycles", False)

        status = "⚠️ **Cycles Detected**" if has_cycles else "✅ **No Cycles**"

        avg_deps = edge_count / node_count if node_count > 0 else 0
        complexity = edge_count / node_count + 1 if node_count > 0 else 1
        content = f"""**Files**: {node_count}
**Dependencies**: {edge_count}
**Status**: {status}

### Architecture Health
- Average dependencies per file: {avg_deps:.1f}
- Graph complexity: {complexity:.1f}
"""
        return ReportSection(
            title="Dependency Analysis",
            content=content,
            priority=20,
            visual_element="badge",
        )

    def _build_security_section(self) -> ReportSection:
        """Build security analysis section."""
        data = self.report.security_issues or {}

        if not data:
            return ReportSection(title="Security Analysis", content="No data available.", priority=30)

        issue_count = data.get("issue_count", 0)
        severity_dist = data.get("severity_distribution", {})

        content = f"**Issues Found**: {issue_count}\n\n### Severity Distribution\n"

        if severity_dist:
            for severity in ["critical", "high", "medium", "low"]:
                count = severity_dist.get(severity, 0)
                if count > 0:
                    emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "")
                    content += f"- {emoji} **{severity.title()}**: {count}\n"
        else:
            content += "No security issues detected.\n"

        return ReportSection(
            title="Security Analysis",
            content=content,
            priority=30,
            visual_element="badge",
        )

    def _build_patterns_section(self) -> ReportSection:
        """Build design patterns section."""
        data = self.report.design_patterns or {}

        if not data:
            return ReportSection(title="Design Patterns", content="No data available.", priority=40)

        pattern_count = data.get("pattern_count", 0)
        pattern_dist = data.get("pattern_distribution", {})

        content = f"**Patterns Detected**: {pattern_count}\n\n### Pattern Types\n"

        if pattern_dist:
            for pattern, count in sorted(pattern_dist.items(), key=lambda x: -x[1])[:10]:
                content += f"- **{pattern}**: {count}\n"
        else:
            content += "No design patterns detected.\n"

        return ReportSection(title="Design Patterns", content=content, priority=40)

    def _build_dead_code_section(self) -> ReportSection:
        """Build dead code analysis section."""
        data = self.report.dead_code or {}

        if not data:
            return ReportSection(title="Dead Code", content="No data available.", priority=50)

        unused_classes = data.get("unused_class_count", 0)
        unused_functions = data.get("unused_function_count", 0)
        unused_imports = data.get("unused_import_count", 0)

        content = f"""**Unused Classes**: {unused_classes}
**Unused Functions**: {unused_functions}
**Unused Imports**: {unused_imports}

**Total Dead Code Items**: {unused_classes + unused_functions + unused_imports}
"""
        return ReportSection(title="Dead Code Analysis", content=content, priority=50)

    def _build_ownership_section(self) -> ReportSection:
        """Build code ownership section."""
        data = self.report.ownership or {}

        if not data:
            return ReportSection(title="Code Ownership", content="No data available.", priority=60)

        file_count = data.get("file_count", 0)
        top_owned = data.get("top_owned_files", [])
        high_churn = data.get("high_churn_files", [])

        content = f"**Files Tracked**: {file_count}\n\n### Top Contributors\n"

        for item in top_owned[:5]:
            path = item.get("path", "unknown")
            owner = item.get("owner", "unknown")
            pct = item.get("ownership_percentage", 0)
            content += f"- `{path}` - {owner}: {pct:.1f}%\n"

        content += "\n### High Churn Files\n"

        for item in high_churn[:5]:
            path = item.get("path", "unknown")
            commits = item.get("commit_count", 0)
            content += f"- `{path}` - {commits} commits\n"

        return ReportSection(title="Code Ownership", content=content, priority=60)

    def _build_blast_section(self) -> ReportSection:
        """Build blast radius/impact analysis section."""
        data = self.report.blast_radius or {}

        if not data:
            return ReportSection(title="Impact Analysis", content="No data available.", priority=70)

        high_impact = data.get("high_impact_symbols", [])

        content = f"**High Impact Symbols**: {len(high_impact)}\n\n"

        for item in high_impact[:10]:
            name = item.get("name", "unknown")
            file = item.get("file", "unknown")
            complexity = item.get("complexity", 0)
            risk = item.get("risk_level", "unknown")
            content += f"- **{name}** ({file}) - Complexity: {complexity}, Risk: {risk}\n"

        return ReportSection(title="Impact Analysis", content=content, priority=70)


def format_score_bar(score: int, max_score: int = 100) -> str:
    """Generate a visual progress bar for scores.

    Args:
        score: Current score value.
        max_score: Maximum possible score.

    Returns:
        String representation of progress bar.
    """
    filled = int(score / max_score * 20)
    empty = 20 - filled
    return "█" * filled + "░" * empty


def generate_health_badge(grade: str) -> str:
    """Generate a color-coded badge for health grades.

    Args:
        grade: Letter grade (A-F).

    Returns:
        Colored badge string.
    """
    colors = {
        "A": "🟢",
        "B": "🟢",
        "C": "🟡",
        "D": "🟠",
        "F": "🔴",
    }
    return colors.get(grade, "⚪") + f" {grade}"
