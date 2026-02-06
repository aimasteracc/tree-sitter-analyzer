"""
Instant Project Understanding Engine

A pure MCP/data-driven system that combines existing analyzers
to generate layered understanding reports without requiring AI.

Core Features:
- Layer 1 (5min): Quick overview with statistics
- Layer 2 (15min): Architecture understanding with Mermaid diagrams
- Layer 3 (30min): Deep insights with recommendations

No AI required - pure data aggregation and visualization.
"""

from pathlib import Path
from typing import Optional

from tree_sitter_analyzer_v2.features.instant_understanding.models import (
    Layer1Overview,
    Layer2Architecture,
    Layer3DeepInsights,
    UnderstandingReport,
)
from tree_sitter_analyzer_v2.features.instant_understanding.engine import (
    InstantUnderstandingEngine,
)
from tree_sitter_analyzer_v2.features.instant_understanding.output import (
    ReportFormatter,
    save_report,
)

__all__ = [
    "Layer1Overview",
    "Layer2Architecture",
    "Layer3DeepInsights",
    "UnderstandingReport",
    "InstantUnderstandingEngine",
    "ReportFormatter",
    "save_report",
    "instant_understand",
]


def instant_understand(
    project_path: Path,
    output_path: Optional[Path] = None,
    force_rebuild: bool = False,
) -> UnderstandingReport:
    """
    Convenience function for instant project understanding.

    Args:
        project_path: Path to project
        output_path: Optional output file path (.md or .html)
        force_rebuild: Force rebuild caches

    Returns:
        UnderstandingReport

    Example:
        >>> report = instant_understand(Path("."), Path("understanding.md"))
        >>> print(f"Health score: {report.layer3.health_score}")
    """
    engine = InstantUnderstandingEngine(project_path)
    report = engine.analyze(force_rebuild=force_rebuild)

    if output_path:
        engine.save_report(report, output_path)

    return report
