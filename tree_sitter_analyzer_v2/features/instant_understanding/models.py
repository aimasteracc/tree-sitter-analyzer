"""
Data models for Instant Understanding Engine.

Contains dataclasses for the three report layers and the complete report.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class Layer1Overview:
    """5-minute quick overview layer."""
    project_name: str
    summary: str
    statistics: Dict[str, Any]
    top_files: List[Dict[str, Any]]
    tech_stack: Dict[str, Any]
    entry_points: List[str]


@dataclass
class Layer2Architecture:
    """15-minute architecture understanding layer."""
    module_structure: Dict[str, Any]
    call_graph: Dict[str, Any]
    design_patterns: List[str]
    hotspot_chart: str
    dependency_graph: str


@dataclass
class Layer3DeepInsights:
    """30-minute deep understanding layer."""
    performance_analysis: Dict[str, Any]
    tech_debt_report: Dict[str, Any]
    refactoring_suggestions: List[Dict[str, Any]]
    learning_path: List[str]
    health_score: float


@dataclass
class UnderstandingReport:
    """Complete understanding report with 3 layers."""
    layer1: Layer1Overview
    layer2: Layer2Architecture
    layer3: Layer3DeepInsights
    mermaid_diagrams: List[str]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
