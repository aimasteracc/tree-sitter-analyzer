#!/usr/bin/env python3
"""
Dependency Coupling Matrix — Quantified module coupling from cached AST data.

Computes a bidirectional coupling score between every pair of modules (files)
in the project using import edges, call edges, and symbol references from the
pre-indexed AST cache. Produces a heat-map style matrix for architecture
visualization and refactoring target identification.

Coupling score between module A and module B is computed as:
  import_weight  = (# imports A→B + # imports B→A)
  call_weight    = (# calls A→B + # calls B→A)
  total          = import_weight * IMPORT_FACTOR + call_weight * CALL_FACTOR

High coupling between modules suggests:
  - They should live in the same package
  - They are refactoring candidates (extract shared interface)
  - Changes to one likely impact the other

All data comes from the pre-indexed SQLite cache — queries are O(1) after
initial indexing.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

IMPORT_FACTOR = 2.0
CALL_FACTOR = 1.0
HIGH_COUPLING_THRESHOLD = 5.0


@dataclass
class CouplingEntry:
    file_a: str
    file_b: str
    import_count: int = 0
    call_count: int = 0
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_a": self.file_a,
            "file_b": self.file_b,
            "import_count": self.import_count,
            "call_count": self.call_count,
            "score": round(self.score, 2),
        }


@dataclass
class ModuleStats:
    file: str
    afferent_coupling: int = 0
    efferent_coupling: int = 0
    instability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "afferent_coupling": self.afferent_coupling,
            "efferent_coupling": self.efferent_coupling,
            "instability": round(self.instability, 3),
        }


@dataclass
class DependencyMatrixResult:
    modules: list[str] = field(default_factory=list)
    coupling_pairs: list[CouplingEntry] = field(default_factory=list)
    module_stats: list[ModuleStats] = field(default_factory=list)
    high_coupling_pairs: list[CouplingEntry] = field(default_factory=list)
    matrix: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_count": len(self.modules),
            "coupling_pair_count": len(self.coupling_pairs),
            "high_coupling_count": len(self.high_coupling_pairs),
            "high_coupling_pairs": [e.to_dict() for e in self.high_coupling_pairs],
            "module_stats": [s.to_dict() for s in self.module_stats],
            "modules": self.modules,
        }


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


class DependencyMatrix:
    """
    Build a dependency coupling matrix from the pre-indexed AST cache.

    Reads import edges and call edges from the cache, computes pairwise
    coupling scores, and identifies tightly-coupled module pairs that
    are refactoring targets.
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = os.path.abspath(project_root)
        self._built = False
        self._import_edges: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._call_edges: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._modules: set[str] = set()
        self._result: DependencyMatrixResult | None = None

    def build(self) -> DependencyMatrixResult:
        if self._built and self._result is not None:
            return self._result

        from .ast_cache import ASTCache

        try:
            cache = ASTCache(self.project_root)
        except Exception:
            logger.warning("Failed to open AST cache for dependency matrix")
            return DependencyMatrixResult()

        try:
            self._collect_import_edges(cache)
            self._collect_call_edges(cache)
        finally:
            cache.close()

        self._modules = set(self._import_edges.keys()) | set(self._call_edges.keys())
        for src in list(self._import_edges.keys()):
            for tgt in self._import_edges[src]:
                self._modules.add(tgt)
        for src in list(self._call_edges.keys()):
            for tgt in self._call_edges[src]:
                self._modules.add(tgt)

        self._result = self._compute_matrix()
        self._built = True
        return self._result

    def _collect_import_edges(self, cache: Any) -> None:
        imports_by_file = cache.get_imports()
        project_files = set(imports_by_file.keys())

        for source_file, imports in imports_by_file.items():
            if not isinstance(imports, list):
                continue
            for imp_text in imports:
                if not isinstance(imp_text, str):
                    continue
                resolved = self._resolve_import(imp_text, source_file, project_files)
                if resolved and resolved != source_file:
                    self._import_edges[source_file][resolved] += 1

    def _collect_call_edges(self, cache: Any) -> None:
        edges = cache.get_call_edges()
        for edge in edges:
            src_file = edge.get("source_file", "")
            tgt_file = edge.get("target_file", "")
            if not src_file or not tgt_file:
                continue
            if src_file == tgt_file:
                continue
            self._call_edges[src_file][tgt_file] += 1

    def _resolve_import(
        self,
        import_text: str,
        source_file: str,
        project_files: set[str],
    ) -> str | None:
        if import_text.startswith("from ") or import_text.startswith("import "):
            return self._resolve_python_import(import_text, source_file, project_files)
        return None

    def _resolve_python_import(
        self,
        import_text: str,
        source_file: str,
        project_files: set[str],
    ) -> str | None:
        parts = import_text.split()
        if len(parts) < 2:
            return None

        if parts[0] == "from":
            if len(parts) < 3:
                return None
            module_path = parts[1]
        else:
            module_path = parts[1].split(",")[0].split(" as ")[0].strip()

        module_path = module_path.lstrip(".")

        candidates = [
            module_path.replace(".", "/") + ".py",
            os.path.join(module_path.replace(".", "/"), "__init__.py"),
        ]

        for candidate in candidates:
            if candidate in project_files:
                return candidate

        return None

    def _compute_matrix(self) -> DependencyMatrixResult:
        result = DependencyMatrixResult()
        modules = sorted(self._modules)
        result.modules = modules

        coupling_map: dict[tuple[str, str], CouplingEntry] = {}

        for src, targets in self._import_edges.items():
            for tgt, count in targets.items():
                key = _pair_key(src, tgt)
                entry = coupling_map.setdefault(
                    key,
                    CouplingEntry(file_a=key[0], file_b=key[1]),
                )
                entry.import_count += count

        for src, targets in self._call_edges.items():
            for tgt, count in targets.items():
                key = _pair_key(src, tgt)
                entry = coupling_map.setdefault(
                    key,
                    CouplingEntry(file_a=key[0], file_b=key[1]),
                )
                entry.call_count += count

        for entry in coupling_map.values():
            entry.score = (
                entry.import_count * IMPORT_FACTOR + entry.call_count * CALL_FACTOR
            )

        result.coupling_pairs = sorted(
            coupling_map.values(), key=lambda e: e.score, reverse=True
        )

        result.high_coupling_pairs = [
            e for e in result.coupling_pairs if e.score >= HIGH_COUPLING_THRESHOLD
        ]

        matrix: dict[str, dict[str, float]] = {}
        for m in modules:
            matrix[m] = {}
        for entry in result.coupling_pairs:
            matrix.setdefault(entry.file_a, {})[entry.file_b] = entry.score
            matrix.setdefault(entry.file_b, {})[entry.file_a] = entry.score
        result.matrix = matrix

        result.module_stats = self._compute_module_stats(modules)

        return result

    def _compute_module_stats(self, modules: list[str]) -> list[ModuleStats]:
        stats = []
        for mod in modules:
            afferent = sum(
                1 for src in self._import_edges if mod in self._import_edges[src]
            )
            efferent = len(self._import_edges.get(mod, {}))
            total = afferent + efferent
            instability = efferent / total if total > 0 else 0.0
            stats.append(
                ModuleStats(
                    file=mod,
                    afferent_coupling=afferent,
                    efferent_coupling=efferent,
                    instability=instability,
                )
            )
        stats.sort(key=lambda s: s.instability, reverse=True)
        return stats

    def coupling_between(self, file_a: str, file_b: str) -> CouplingEntry | None:
        if not self._built:
            self.build()
        assert self._result is not None
        for entry in self._result.coupling_pairs:
            if (entry.file_a == file_a and entry.file_b == file_b) or (
                entry.file_a == file_b and entry.file_b == file_a
            ):
                return entry
        return None

    def most_coupled(self, top_k: int = 10) -> list[CouplingEntry]:
        if not self._built:
            self.build()
        assert self._result is not None
        return self._result.coupling_pairs[:top_k]

    def unstable_modules(self, threshold: float = 0.7) -> list[ModuleStats]:
        if not self._built:
            self.build()
        assert self._result is not None
        return [s for s in self._result.module_stats if s.instability >= threshold]

    def summary(self) -> dict[str, Any]:
        if not self._built:
            self.build()
        assert self._result is not None
        scores = [e.score for e in self._result.coupling_pairs]
        return {
            "module_count": len(self._result.modules),
            "coupling_pair_count": len(self._result.coupling_pairs),
            "high_coupling_count": len(self._result.high_coupling_pairs),
            "avg_coupling": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "max_coupling": round(max(scores), 2) if scores else 0.0,
            "unstable_module_count": len(self.unstable_modules()),
        }
