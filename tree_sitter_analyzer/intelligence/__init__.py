#!/usr/bin/env python3
"""
Code Intelligence Graph Module

Provides advanced code analysis capabilities including:
- Symbol tracing (definitions, usages, call chains)
- Change impact analysis (blast radius prediction)
- Architecture health assessment (coupling, cycles, metrics)
"""

from .call_graph import CallGraphBuilder
from .dependency_graph import DependencyGraphBuilder
from .impact_analyzer import ImpactAnalyzer
from .architecture_metrics import ArchitectureMetrics
from .cycle_detector import CycleDetector
from .formatters import (
    format_trace_result,
    format_impact_result,
    format_architecture_report,
)
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
from .symbol_index import SymbolIndex

__all__ = [
    "CallGraphBuilder",
    "DependencyGraphBuilder",
    "ImpactAnalyzer",
    "ArchitectureMetrics",
    "CycleDetector",
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
