#!/usr/bin/env python3
"""Cycle detector using Tarjan's algorithm."""
from __future__ import annotations
from typing import Any
from .models import DependencyCycle


class CycleDetector:
    """Detects circular dependencies using Tarjan's SCC algorithm."""

    def detect_cycles(self, adjacency: dict[str, list[str]]) -> list[DependencyCycle]:
        sccs = self._tarjan_scc(adjacency)
        cycles = []
        for scc in sccs:
            if len(scc) > 1:
                cycle_files = list(scc) + [scc[0]]  # close the loop
                severity = "error" if len(scc) > 3 else "warning"
                cycles.append(DependencyCycle(files=cycle_files, length=len(scc), severity=severity))
            elif len(scc) == 1:
                node = scc[0]
                if node in adjacency and node in adjacency.get(node, []):
                    cycles.append(DependencyCycle(files=[node, node], length=1, severity="warning"))
        return cycles

    def _tarjan_scc(self, graph: dict[str, list[str]]) -> list[list[str]]:
        index_counter = [0]
        stack: list[str] = []
        lowlink: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        result: list[list[str]] = []

        all_nodes = set(graph.keys())
        for deps in graph.values():
            all_nodes.update(deps)

        def strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack[v] = True

            for w in graph.get(v, []):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif on_stack.get(w, False):
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == v:
                        break
                result.append(component)

        for v in all_nodes:
            if v not in index:
                strongconnect(v)

        return result
