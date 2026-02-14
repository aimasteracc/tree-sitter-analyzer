#!/usr/bin/env python3
"""Dependency Graph Builder for Code Intelligence Graph."""
from __future__ import annotations

from .models import DependencyEdge


class DependencyGraphBuilder:
    """Builds file-level dependency graphs from import analysis."""

    def __init__(self) -> None:
        self._edges: list[DependencyEdge] = []
        self._adjacency: dict[str, list[str]] = {}  # file -> [dependencies]
        self._reverse_adjacency: dict[str, list[str]] = {}  # file -> [dependents]

    def add_edge(self, edge: DependencyEdge) -> None:
        self._edges.append(edge)
        if edge.source_file not in self._adjacency:
            self._adjacency[edge.source_file] = []
        if edge.target_file and edge.target_file not in self._adjacency[edge.source_file]:
            self._adjacency[edge.source_file].append(edge.target_file)
        if edge.target_file:
            if edge.target_file not in self._reverse_adjacency:
                self._reverse_adjacency[edge.target_file] = []
            if edge.source_file not in self._reverse_adjacency[edge.target_file]:
                self._reverse_adjacency[edge.target_file].append(edge.source_file)

    def get_dependencies(self, file_path: str) -> list[str]:
        return self._adjacency.get(file_path, [])

    def get_dependents(self, file_path: str) -> list[str]:
        return self._reverse_adjacency.get(file_path, [])

    def get_all_files(self) -> set[str]:
        files = set(self._adjacency.keys())
        files.update(self._reverse_adjacency.keys())
        return files

    def get_edges(self) -> list[DependencyEdge]:
        return list(self._edges)

    def get_edges_for_file(self, file_path: str) -> list[DependencyEdge]:
        return [e for e in self._edges if e.source_file == file_path]

    def clear(self) -> None:
        self._edges.clear()
        self._adjacency.clear()
        self._reverse_adjacency.clear()
