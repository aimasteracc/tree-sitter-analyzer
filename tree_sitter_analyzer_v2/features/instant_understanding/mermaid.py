"""
Mermaid diagram generators for Instant Understanding Engine.

Contains functions for generating various Mermaid diagrams.
"""

from pathlib import Path
from typing import Any, Dict, List


class MermaidGenerator:
    """Generates Mermaid diagrams for project understanding reports."""

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def generate_all(self, results: Dict[str, Any]) -> List[str]:
        """Generate all Mermaid diagrams."""
        diagrams = []

        arch_diagram = self.generate_architecture()
        diagrams.append(arch_diagram)

        knowledge = results.get("knowledge", {})
        hotspots = knowledge.get("hotspots", []) if knowledge else []
        if hotspots:
            call_diagram = self.generate_call_graph(hotspots[:10])
            diagrams.append(call_diagram)

        perf_hotspots = results.get("performance", [])
        if perf_hotspots:
            heatmap = self.generate_performance_heatmap(perf_hotspots[:10])
            diagrams.append(heatmap)

        return diagrams

    def generate_architecture(self) -> str:
        """Generate architecture overview Mermaid diagram."""
        has_cli = (self.project_path / "cli").exists()
        has_api = (self.project_path / "api").exists()
        has_mcp = (self.project_path / "mcp").exists()
        has_core = (self.project_path / "core").exists()
        has_features = (self.project_path / "features").exists()

        lines = ["graph TD"]

        if has_cli:
            lines.append("    CLI[CLI Entry] --> API[API Layer]")
        if has_mcp:
            lines.append("    MCP[MCP Server] --> Tools[Analysis Tools]")
        if has_api and has_core:
            lines.append("    API --> Core[Core Parser]")
        if has_mcp and has_core:
            lines.append("    Tools --> Core")
        if has_core and has_features:
            lines.append("    Core --> Features[Feature Modules]")

        return "\n".join(lines)

    def generate_call_graph(self, hotspots: List[Dict[str, Any]]) -> str:
        """Generate call graph Mermaid diagram for top hotspots."""
        lines = ["graph LR"]

        for i, hotspot in enumerate(hotspots[:10]):
            func = hotspot.get("function", "unknown")
            callers = hotspot.get("called_by_count", 0)

            node_id = f"F{i}"
            node_label = f"{func}"

            lines.append(f'    {node_id}["{node_label}"]')

            if callers > 0:
                lines.append(f"    Callers{i}[{callers} callers] --> {node_id}")

        return "\n".join(lines)

    def generate_performance_heatmap(self, hotspots: List[Any]) -> str:
        """Generate performance heatmap as Mermaid diagram."""
        lines = ["graph TD"]
        lines.append("    subgraph PerformanceHotspots")

        for i, hotspot in enumerate(hotspots[:8]):
            func_name = hotspot.function.replace(".", "_").replace(":", "_")
            complexity = hotspot.complexity
            lines.append(f'        H{i}["{hotspot.function}\\nComplexity: {complexity}"]')

        lines.append("    end")

        return "\n".join(lines)
