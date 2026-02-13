#!/usr/bin/env python3
"""Impact Analyzer for Code Intelligence Graph."""
from __future__ import annotations
import os
from typing import Any
from .models import ImpactItem, ImpactResult
from .call_graph import CallGraphBuilder
from .dependency_graph import DependencyGraphBuilder
from .symbol_index import SymbolIndex


class ImpactAnalyzer:
    """Analyzes the blast radius of code changes."""

    def __init__(
        self,
        call_graph: CallGraphBuilder,
        dependency_graph: DependencyGraphBuilder,
        symbol_index: SymbolIndex,
    ) -> None:
        self._call_graph = call_graph
        self._dep_graph = dependency_graph
        self._symbol_index = symbol_index

    def assess(
        self,
        target: str,
        change_type: str = "behavior_change",
        depth: int = 3,
        include_tests: bool = True,
    ) -> ImpactResult:
        direct_impacts: list[ImpactItem] = []
        transitive_impacts: list[ImpactItem] = []
        affected_tests: list[str] = []

        # Find direct callers via call graph
        callers = self._call_graph.find_callers(target, depth=1)
        for caller in callers:
            direct_impacts.append(ImpactItem(
                file_path=caller.caller_file,
                symbol_name=caller.caller_function or "",
                line=caller.line,
                impact_type="direct_caller",
                depth=1,
            ))

        # Find direct importers
        defs = self._symbol_index.lookup_definition(target)
        for d in defs:
            dependents = self._dep_graph.get_dependents(d.file_path)
            for dep_file in dependents:
                if not any(i.file_path == dep_file for i in direct_impacts):
                    direct_impacts.append(ImpactItem(
                        file_path=dep_file,
                        symbol_name="",
                        line=0,
                        impact_type="importer",
                        depth=1,
                    ))

        # Find transitive impacts (depth > 1)
        seen_files: set[str] = {i.file_path for i in direct_impacts}
        frontier = list(seen_files)
        for current_depth in range(2, depth + 1):
            next_frontier: list[str] = []
            for f in frontier:
                trans_dependents = self._dep_graph.get_dependents(f)
                for td in trans_dependents:
                    if td not in seen_files:
                        seen_files.add(td)
                        next_frontier.append(td)
                        transitive_impacts.append(ImpactItem(
                            file_path=td,
                            symbol_name="",
                            line=0,
                            impact_type="transitive_caller",
                            depth=current_depth,
                        ))
            frontier = next_frontier

        # Identify affected tests
        if include_tests:
            all_affected = {i.file_path for i in direct_impacts + transitive_impacts}
            for f in list(all_affected) + [d.file_path for d in defs]:
                base = os.path.basename(f)
                if base.startswith("test_") or base.endswith("_test.py"):
                    if f not in affected_tests:
                        affected_tests.append(f)
            # Also check test files that import affected modules
            for f in all_affected:
                dependents = self._dep_graph.get_dependents(f)
                for dep in dependents:
                    base = os.path.basename(dep)
                    if base.startswith("test_") or base.endswith("_test.py"):
                        if dep not in affected_tests:
                            affected_tests.append(dep)

        # Calculate risk level
        total = len(set(i.file_path for i in direct_impacts + transitive_impacts))
        risk_level = self._compute_risk(total, change_type)

        return ImpactResult(
            target=target,
            change_type=change_type,
            direct_impacts=direct_impacts,
            transitive_impacts=transitive_impacts,
            affected_tests=affected_tests,
            risk_level=risk_level,
            total_affected_files=total,
        )

    def _compute_risk(self, affected_count: int, change_type: str) -> str:
        if change_type in ("delete", "signature_change"):
            if affected_count > 10:
                return "critical"
            if affected_count > 5:
                return "high"
            if affected_count > 1:
                return "medium"
            return "low"
        # behavior_change, rename
        if affected_count > 15:
            return "high"
        if affected_count > 5:
            return "medium"
        return "low"
