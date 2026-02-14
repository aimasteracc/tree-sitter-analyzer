#!/usr/bin/env python3
"""
Code Intelligence Graph Module

Provides advanced code analysis capabilities including:
- Symbol tracing (definitions, usages, call chains)
- Change impact analysis (blast radius prediction)
- Architecture health assessment (coupling, cycles, metrics)
"""

from .architecture_metrics import ArchitectureMetrics
from .call_graph import CallGraphBuilder
from .cycle_detector import CycleDetector
from .dependency_graph import DependencyGraphBuilder
from .formatters import (
    format_architecture_report,
    format_impact_result,
    format_trace_result,
)
from .impact_analyzer import ImpactAnalyzer
from .models import (
    ArchitectureReport,
    CallSite,
    DependencyCycle,
    DependencyEdge,
    GodClassInfo,
    ImpactItem,
    ImpactResult,
    LayerViolation,
    ModuleMetrics,
    ResolvedImport,
    SymbolDefinition,
    SymbolReference,
)
from .project_indexer import ProjectIndexer
from .symbol_index import SymbolIndex

__all__ = [
    "CallGraphBuilder",
    "DependencyGraphBuilder",
    "ImpactAnalyzer",
    "ArchitectureMetrics",
    "CycleDetector",
    "ProjectIndexer",
    "format_trace_result",
    "format_impact_result",
    "format_architecture_report",
    "CallSite",
    "SymbolDefinition",
    "SymbolReference",
    "SymbolIndex",
    "DependencyEdge",
    "ResolvedImport",
    "DependencyCycle",
    "ModuleMetrics",
    "ImpactItem",
    "ImpactResult",
    "LayerViolation",
    "GodClassInfo",
    "ArchitectureReport",
]
