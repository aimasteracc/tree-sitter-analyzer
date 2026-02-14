#!/usr/bin/env python3
"""
Data models for Code Intelligence Graph.

Provides dataclasses for representing call graphs, symbol references,
dependency edges, impact analysis results, and architecture metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallSite:
    """A function/method call site extracted from source code."""

    caller_file: str
    caller_function: str | None
    callee_name: str
    callee_object: str | None
    line: int
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller_file": self.caller_file,
            "caller_function": self.caller_function,
            "callee_name": self.callee_name,
            "callee_object": self.callee_object,
            "line": self.line,
            "raw_text": self.raw_text,
        }


@dataclass
class SymbolDefinition:
    """A symbol definition (function, class, method, variable)."""

    name: str
    file_path: str
    line: int
    end_line: int
    symbol_type: str  # "function", "class", "method", "variable"
    parameters: list[str] = field(default_factory=list)
    return_type: str | None = None
    parent_class: str | None = None
    docstring: str | None = None
    modifiers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "line": self.line,
            "end_line": self.end_line,
            "symbol_type": self.symbol_type,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "parent_class": self.parent_class,
            "docstring": self.docstring,
            "modifiers": self.modifiers,
        }


@dataclass
class SymbolReference:
    """A reference to a symbol (call, import, inheritance, type hint)."""

    symbol_name: str
    file_path: str
    line: int
    ref_type: str  # "call", "import", "inheritance", "type_hint"
    context_function: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_name": self.symbol_name,
            "file_path": self.file_path,
            "line": self.line,
            "ref_type": self.ref_type,
            "context_function": self.context_function,
        }


@dataclass
class DependencyEdge:
    """A dependency relationship between two files."""

    source_file: str
    target_file: str
    target_module: str
    imported_names: list[str] = field(default_factory=list)
    is_external: bool = False
    line: int = 0
    is_type_check_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "target_module": self.target_module,
            "imported_names": self.imported_names,
            "is_external": self.is_external,
            "line": self.line,
            "is_type_check_only": self.is_type_check_only,
        }


@dataclass
class ResolvedImport:
    """Result of resolving an import statement to an actual file."""

    module_name: str
    resolved_path: str
    imported_names: list[str] = field(default_factory=list)
    is_external: bool = False
    is_resolved: bool = True


@dataclass
class DependencyCycle:
    """A circular dependency detected in the dependency graph."""

    files: list[str] = field(default_factory=list)
    length: int = 0
    severity: str = "warning"  # "info", "warning", "error"


@dataclass
class ModuleMetrics:
    """Metrics for a module/directory."""

    path: str
    file_count: int = 0
    afferent_coupling: int = 0  # Ca: incoming dependencies
    efferent_coupling: int = 0  # Ce: outgoing dependencies
    abstractness: float = 0.0  # A: abstract types / total types

    @property
    def instability(self) -> float:
        """I = Ce / (Ca + Ce). Returns 0.0 if both are zero."""
        total = self.afferent_coupling + self.efferent_coupling
        if total == 0:
            return 0.0
        return self.efferent_coupling / total

    @property
    def distance_from_main_sequence(self) -> float:
        """D = |A + I - 1|. Distance from the ideal A + I = 1 line."""
        return abs(self.abstractness + self.instability - 1.0)


@dataclass
class ImpactItem:
    """A single item affected by a code change."""

    file_path: str
    symbol_name: str
    line: int
    impact_type: str  # "direct_caller", "transitive_caller", "importer", "test"
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "line": self.line,
            "impact_type": self.impact_type,
            "depth": self.depth,
        }


@dataclass
class ImpactResult:
    """Result of a change impact analysis."""

    target: str
    change_type: str
    direct_impacts: list[ImpactItem] = field(default_factory=list)
    transitive_impacts: list[ImpactItem] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)
    risk_level: str = "low"  # "low", "medium", "high", "critical"
    total_affected_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "change_type": self.change_type,
            "direct_impacts": [i.to_dict() for i in self.direct_impacts],
            "transitive_impacts": [i.to_dict() for i in self.transitive_impacts],
            "affected_tests": self.affected_tests,
            "risk_level": self.risk_level,
            "total_affected_files": self.total_affected_files,
        }


@dataclass
class LayerViolation:
    """A layer rule violation in the architecture."""

    source_file: str
    target_file: str
    source_layer: str
    target_layer: str
    description: str = ""


@dataclass
class GodClassInfo:
    """Information about a god class (too many responsibilities)."""

    class_name: str
    file_path: str
    method_count: int = 0
    line_count: int = 0
    fan_out: int = 0


@dataclass
class UntestedSymbol:
    """A public source-code symbol with no test references."""

    name: str
    file_path: str
    symbol_type: str  # "function", "class", "method"
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "symbol_type": self.symbol_type,
            "line": self.line,
        }


@dataclass
class OvertestedSymbol:
    """A symbol referenced by an unusually high number of test functions."""

    name: str
    file_path: str
    test_ref_count: int
    test_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "test_ref_count": self.test_ref_count,
            "test_files": self.test_files,
        }


@dataclass
class TestCoverageReport:
    """Test coverage analysis report based on symbol references."""

    untested_symbols: list[UntestedSymbol] = field(default_factory=list)
    overtested_symbols: list[OvertestedSymbol] = field(default_factory=list)
    test_only_symbols: list[str] = field(default_factory=list)
    coverage_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "untested_symbols": [s.to_dict() for s in self.untested_symbols],
            "overtested_symbols": [s.to_dict() for s in self.overtested_symbols],
            "test_only_symbols": self.test_only_symbols,
            "coverage_ratio": self.coverage_ratio,
        }


@dataclass
class ArchitectureReport:
    """Complete architecture health report."""

    path: str
    score: int = 100  # 0-100
    module_metrics: dict[str, ModuleMetrics] = field(default_factory=dict)
    cycles: list[DependencyCycle] = field(default_factory=list)
    layer_violations: list[LayerViolation] = field(default_factory=list)
    god_classes: list[GodClassInfo] = field(default_factory=list)
    dead_symbols: list[str] = field(default_factory=list)
    coupling_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    test_coverage: TestCoverageReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "score": self.score,
            "module_metrics": {
                k: {
                    "path": v.path,
                    "file_count": v.file_count,
                    "afferent_coupling": v.afferent_coupling,
                    "efferent_coupling": v.efferent_coupling,
                    "instability": v.instability,
                    "abstractness": v.abstractness,
                    "distance_from_main_sequence": v.distance_from_main_sequence,
                }
                for k, v in self.module_metrics.items()
            },
            "cycles": [
                {"files": c.files, "length": c.length, "severity": c.severity}
                for c in self.cycles
            ],
            "layer_violations": [
                {
                    "source_file": v.source_file,
                    "target_file": v.target_file,
                    "source_layer": v.source_layer,
                    "target_layer": v.target_layer,
                    "description": v.description,
                }
                for v in self.layer_violations
            ],
            "god_classes": [
                {
                    "class_name": g.class_name,
                    "file_path": g.file_path,
                    "method_count": g.method_count,
                    "line_count": g.line_count,
                    "fan_out": g.fan_out,
                }
                for g in self.god_classes
            ],
            "dead_symbols": self.dead_symbols,
            "coupling_matrix": self.coupling_matrix,
            "test_coverage": self.test_coverage.to_dict()
            if self.test_coverage
            else None,
        }
