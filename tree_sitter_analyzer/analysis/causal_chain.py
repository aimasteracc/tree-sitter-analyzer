"""Causal Chain Analysis — find the thread that unravels the tangle.

Like the worker who can instantly pull the right cable from a tangled mess,
this module identifies root causes: fixing which cascades to fix the most
downstream problems.

Three causal mechanisms:
1. INHERITANCE: sql_plugin inherits from base_plugin → fix base, fix all plugins
2. IMPORT: server.py imports analysis_engine → engine bugs propagate to server
3. PATTERN: same empty_block issue in 15 files → fix the shared template, fix all

Impact prediction: change any file → instantly see which code, tests, and
interfaces are affected. Like touching one cable and seeing every connected
cable light up.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
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
    cascade: str


@dataclass(frozen=True)
class CausalLink:
    """A dependency edge: parent → child."""
    parent: str
    child: str
    kind: str
    evidence: str


@dataclass(frozen=True)
class ImpactNode:
    """One file affected by a change."""
    file: str
    kind: str  # "direct_import", "transitive", "inheritance", "test"
    distance: int  # 0=changed file, 1=direct dep, 2=transitive
    health: float
    findings: int
    imported_symbols: tuple[str, ...]


@dataclass(frozen=True)
class ImpactResult:
    """Full impact prediction for a file change."""
    changed_file: str
    changed_line: int | None
    code_impact: tuple[ImpactNode, ...]
    test_impact: tuple[ImpactNode, ...]
    interface_impact: tuple[str, ...]
    total_affected_files: int
    total_affected_tests: int
    risk: str  # "low", "medium", "high", "critical"
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_file": self.changed_file,
            "changed_line": self.changed_line,
            "risk": self.risk,
            "summary": self.summary,
            "total_affected_files": self.total_affected_files,
            "total_affected_tests": self.total_affected_tests,
            "code_impact": [
                {
                    "file": n.file,
                    "kind": n.kind,
                    "distance": n.distance,
                    "health": n.health,
                    "findings": n.findings,
                    "imports": list(n.imported_symbols),
                }
                for n in self.code_impact
            ],
            "test_impact": [
                {"file": n.file, "kind": n.kind, "distance": n.distance}
                for n in self.test_impact
            ],
            "interface_impact": list(self.interface_impact),
        }


@dataclass
class CausalResult:
    """Full causal analysis result."""
    leverage_points: list[LeveragePoint] = field(default_factory=list)
    causal_links: list[CausalLink] = field(default_factory=list)
    the_one_thread: LeveragePoint | None = None
    total_hotspots_addressable: int = 0

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
    """Traces root causes and predicts change impact."""

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self._import_graph: dict[str, set[str]] = defaultdict(set)
        self._reverse_imports: dict[str, set[str]] = defaultdict(set)
        self._inheritance_graph: dict[str, set[str]] = defaultdict(set)
        self._imported_symbols: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._file_health: dict[str, tuple[float, int]] = {}

    def build_causal_model(
        self,
        file_maps: dict[str, Any],
        hotspots: list[dict[str, Any]],
    ) -> CausalResult:
        self._build_import_graph(file_maps)
        self._build_inheritance_graph(file_maps)
        self._build_file_health(file_maps, hotspots)
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

    def predict_impact(
        self,
        file_path: str,
        line: int | None = None,
    ) -> ImpactResult:
        """Change this file → instantly see every ripple."""
        short = self._short(file_path)

        # 1. Direct dependents (import this file)
        direct = self._reverse_imports.get(short, set())

        # 2. Transitive dependents (import files that import this file)
        transitive: set[str] = set()
        for dep in direct:
            transitive |= self._reverse_imports.get(dep, set())
        transitive -= direct
        transitive.discard(short)

        # 3. Inheritance children
        children: set[str] = set()
        for child_file, parents in self._inheritance_graph.items():
            if any(short.split("/")[-1].replace(".py", "") in p.lower()
                   for p in parents):
                children.add(child_file)

        # 4. Test files that test this code
        all_code = {short} | direct | transitive | children
        test_files = self._find_test_coverage(all_code)

        # 5. MCP tool interface impact
        interfaces = self._find_interface_impact(short, direct)

        # Build impact nodes
        code_nodes: list[ImpactNode] = []
        for f in sorted(direct):
            code_nodes.append(self._make_node(f, "direct_import", 1))
        for f in sorted(transitive):
            code_nodes.append(self._make_node(f, "transitive", 2))
        for f in sorted(children):
            code_nodes.append(self._make_node(f, "inheritance", 1))

        test_nodes: list[ImpactNode] = []
        for f in sorted(test_files):
            test_nodes.append(self._make_node(f, "test", 0))

        # Risk assessment
        total_affected = len(direct) + len(transitive) + len(children)
        total_tests = len(test_files)
        if total_affected >= 20 or total_tests >= 30:
            risk = "critical"
        elif total_affected >= 10 or total_tests >= 15:
            risk = "high"
        elif total_affected >= 5 or total_tests >= 5:
            risk = "medium"
        else:
            risk = "low"

        health, findings = self._file_health.get(short, (100.0, 0))
        summary = (
            f"Change {short}: {total_affected} code files affected, "
            f"{total_tests} tests at risk, {len(interfaces)} MCP tools impacted. "
            f"Risk={risk}. Current health={health:.1f}h with {findings} findings."
        )

        return ImpactResult(
            changed_file=short,
            changed_line=line,
            code_impact=tuple(code_nodes),
            test_impact=tuple(test_nodes),
            interface_impact=tuple(sorted(interfaces)),
            total_affected_files=total_affected,
            total_affected_tests=total_tests,
            risk=risk,
            summary=summary,
        )

    def _build_import_graph(self, file_maps: dict[str, Any]) -> None:
        for fpath in file_maps:
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue
            short = self._short(fpath)
            for match in re.finditer(
                r"from\s+([\w.]+)\s+import\s+([\w,\s]+)|"
                r"import\s+([\w.]+)",
                content,
            ):
                module = match.group(1) or match.group(3) or ""
                symbols_str = match.group(2) or ""
                if module.startswith("tree_sitter_analyzer"):
                    target = module.replace(".", "/") + ".py"
                    self._import_graph[short].add(target)
                    self._reverse_imports[target].add(short)
                    if symbols_str:
                        for sym in symbols_str.split(","):
                            sym = sym.strip()
                            if sym:
                                self._imported_symbols[short][target].add(sym)

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

    def _build_file_health(
        self,
        file_maps: dict[str, Any],
        hotspots: list[dict[str, Any]],
    ) -> None:
        for fpath, knowledge in file_maps.items():
            short = self._short(fpath)
            self._file_health[short] = (
                knowledge.health_score,
                knowledge.total_findings,
            )

    def _find_test_coverage(self, code_files: set[str]) -> set[str]:
        """Find test files that correspond to given code files."""
        test_files: set[str] = set()
        for code_file in code_files:
            base = code_file.replace(".py", "").split("/")[-1]
            for short in self._reverse_imports:
                if short.startswith("test_") or "/test_" in short:
                    if base in short.lower():
                        test_files.add(short)
        for short in self._reverse_imports:
            if short.startswith("test_") or "/test_" in short:
                for dep in self._import_graph.get(short, set()):
                    for code_file in code_files:
                        if code_file in dep or dep.startswith(code_file.replace(".py", "")):
                            test_files.add(short)
        return test_files

    def _find_interface_impact(
        self, short: str, direct: set[str]
    ) -> set[str]:
        """Find MCP tool interfaces affected by this change."""
        interfaces: set[str] = set()
        for dep in direct | {short}:
            if "mcp/tools/" in dep:
                tool_name = dep.split("/")[-1].replace("_tool.py", "")
                if tool_name:
                    interfaces.add(tool_name)
            if "mcp/server" in dep:
                interfaces.add("mcp_server")
            if "mcp/registry" in dep or "mcp/tool_registration" in dep:
                interfaces.add("all_mcp_tools")
        return interfaces

    def _make_node(
        self, short: str, kind: str, distance: int
    ) -> ImpactNode:
        health, findings = self._file_health.get(short, (100.0, 0))
        return ImpactNode(
            file=short,
            kind=kind,
            distance=distance,
            health=health,
            findings=findings,
            imported_symbols=(),
        )

    def _find_leverage_points(
        self, hotspots: list[dict[str, Any]]
    ) -> list[LeveragePoint]:
        points: list[LeveragePoint] = []

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
