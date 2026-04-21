"""Causal Chain Analysis — find the thread that unravels the tangle.

Like the worker who can instantly pull the right cable from a tangled mess,
this module identifies root causes: fixing which cascades to fix the most
downstream problems.

Three causal mechanisms:
1. INHERITANCE: sql_plugin inherits from base_plugin → fix base, fix all plugins
2. IMPORT: server.py imports analysis_engine → engine bugs propagate to server
3. PATTERN: same empty_block issue in 15 files → fix the shared template, fix all

The output is a ranked list of LEVERAGE POINTS — ordered by cascade impact.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class LeveragePoint:
    """A single root-cause fix and its cascade effect."""
    action: str
    kind: str  # "inheritance", "import", "pattern", "god_file"
    hotspot_count: int
    file_count: int
    affected_files: tuple[str, ...]
    cascade: str  # human-readable cascade description


@dataclass(frozen=True)
class CausalLink:
    """A dependency edge: parent → child."""
    parent: str
    child: str
    kind: str  # "inheritance", "import"
    evidence: str


@dataclass
class CausalResult:
    """Full causal analysis result."""
    leverage_points: list[LeveragePoint]
    causal_links: list[CausalLink]
    the_one_thread: LeveragePoint | None
    total_hotspots_addressable: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "the_one_thread": (
                {
                    "action": self.the_one_thread.action,
                    "kind": self.the_one_thread.kind,
                    "hotspots_killed": self.the_one_thread.hotspot_count,
                    "files_fixed": self.the_one_thread.file_count,
                    "cascade": self.the_one_thread.cascade,
                }
                if self.the_one_thread
                else None
            ),
            "leverage_points": [
                {
                    "action": lp.action,
                    "kind": lp.kind,
                    "hotspots_killed": lp.hotspot_count,
                    "files_fixed": lp.file_count,
                    "cascade": lp.cascade,
                }
                for lp in self.leverage_points
            ],
            "total_addressable": self.total_hotspots_addressable,
        }


class CausalChain:
    """Traces root causes through dependency and pattern analysis."""

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self._import_graph: dict[str, set[str]] = defaultdict(set)
        self._inheritance_graph: dict[str, set[str]] = defaultdict(set)

    def analyze(
        self,
        file_maps: dict[str, Any],
        hotspots: list[dict[str, Any]],
    ) -> CausalResult:
        self._build_import_graph(file_maps)
        self._build_inheritance_graph(file_maps)
        leverage = self._find_leverage_points(hotspots)
        leverage.sort(key=lambda lp: lp.hotspot_count, reverse=True)
        total = sum(lp.hotspot_count for lp in leverage)

        the_one = leverage[0] if leverage else None
        links = self._collect_links()

        return CausalResult(
            leverage_points=leverage,
            causal_links=links,
            the_one_thread=the_one,
            total_hotspots_addressable=total,
        )

    def _build_import_graph(self, file_maps: dict[str, Any]) -> None:
        for fpath in file_maps:
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue
            short = self._short(fpath)
            for match in re.finditer(
                r"from\s+([\w.]+)\s+import|import\s+([\w.]+)", content
            ):
                module = match.group(1) or match.group(2) or ""
                if module.startswith("tree_sitter_analyzer"):
                    target = module.replace(".", "/") + ".py"
                    self._import_graph[short].add(target)

    def _build_inheritance_graph(self, file_maps: dict[str, Any]) -> None:
        for fpath in file_maps:
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue
            short = self._short(fpath)
            for match in re.finditer(r"class\s+\w+\((\w+)\)", content):
                parent_class = match.group(1)
                if parent_class not in ("ABC", "object", "Enum", "Exception"):
                    self._inheritance_graph[short].add(parent_class)

    def _find_leverage_points(
        self, hotspots: list[dict[str, Any]]
    ) -> list[LeveragePoint]:
        points: list[LeveragePoint] = []

        # 1. PATTERN leverage: fix one pattern type across all files
        pattern_hotspots: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for h in hotspots:
            for name in h["analyzer_names"]:
                pattern_hotspots[name].append(h)

        for pattern, hs_list in pattern_hotspots.items():
            affected = tuple(
                sorted({self._short(h["file"]) for h in hs_list})
            )
            points.append(LeveragePoint(
                action=f"Fix all {pattern} issues",
                kind="pattern",
                hotspot_count=len(hs_list),
                file_count=len(affected),
                affected_files=affected,
                cascade=(
                    f"Fix {pattern} in {len(affected)} files → "
                    f"{len(hs_list)} hotspots disappear"
                ),
            ))

        # 2. FILE leverage: fix one god-file, cascade to dependents
        file_hotspots: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for h in hotspots:
            file_hotspots[self._short(h["file"])].append(h)

        for fpath, hs_list in file_hotspots.items():
            dependents = self._get_downstream(fpath)
            if not dependents:
                continue
            dependent_hotspots = sum(
                len(file_hotspots.get(d, [])) for d in dependents
            )
            total_killed = len(hs_list) + dependent_hotspots
            if total_killed < 3:
                continue
            points.append(LeveragePoint(
                action=f"Fix god-file {fpath}",
                kind="god_file",
                hotspot_count=total_killed,
                file_count=1 + len(dependents),
                affected_files=tuple(sorted({fpath} | dependents)),
                cascade=(
                    f"Fix {fpath} ({len(hs_list)} hotspots) → "
                    f"cascades to {len(dependents)} dependents "
                    f"(+{dependent_hotspots} more hotspots)"
                ),
            ))

        # 3. INHERITANCE leverage: fix base class, fix all children
        for parent_class, children_files in self._inheritance_graph.items():
            if len(children_files) < 3:
                continue
            child_hotspots = sum(
                len(file_hotspots.get(f, [])) for f in children_files
            )
            if child_hotspots < 3:
                continue
            points.append(LeveragePoint(
                action=f"Fix base class {parent_class}",
                kind="inheritance",
                hotspot_count=child_hotspots,
                file_count=len(children_files),
                affected_files=tuple(sorted(children_files)),
                cascade=(
                    f"Fix {parent_class} → {len(children_files)} "
                    f"child classes improved ({child_hotspots} hotspots)"
                ),
            ))

        return points

    def _get_downstream(self, file_short: str) -> set[str]:
        """Files that import or depend on this file."""
        downstream: set[str] = set()
        for other, deps in self._import_graph.items():
            if any(file_short in d for d in deps):
                downstream.add(other)
        return downstream

    def _collect_links(self) -> list[CausalLink]:
        links: list[CausalLink] = []
        for child, parents in self._inheritance_graph.items():
            for parent in parents:
                links.append(CausalLink(
                    parent=parent, child=child,
                    kind="inheritance",
                    evidence=f"{child} extends {parent}",
                ))
        return links

    def _short(self, fpath: str) -> str:
        return fpath.split("tree_sitter_analyzer/")[-1]
