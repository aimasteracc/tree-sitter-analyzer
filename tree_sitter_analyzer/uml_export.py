#!/usr/bin/env python3
"""UML-oriented Mermaid exports built from cached project intelligence."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .call_path import CallPathFinder
from .class_hierarchy import ClassHierarchy
from .import_graph import ImportGraph
from .utils.test_detection import is_test_file

_EXTERNAL_BASES = frozenset(
    {
        "ABC",
        "Enum",
        "Exception",
        "Protocol",
        "RuntimeError",
        "ValueError",
        "object",
        "str",
    }
)

# P1-C (RFC-0015): path segments that identify test/fixture content.
# is_test_file() already covers these and more; we use it for filtering.
# This constant documents the intent rather than providing a second filter.

_TRUNCATION_NOTE = (
    "%% NOTE: diagram truncated — only the top N edges shown.\n"
    "%% Pass a higher max_edges value to see more, or use file_path / class_name to scope."
)


@dataclass(frozen=True)
class UMLEdge:
    source: str
    target: str
    label: str = ""
    weight: int = 1

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "weight": self.weight,
        }
        if self.label:
            data["label"] = self.label
        return data


@dataclass(frozen=True)
class UMLDiagram:
    diagram_type: str
    mermaid_type: str
    mermaid: str
    nodes: list[str]
    edges: list[UMLEdge]
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagram_type": self.diagram_type,
            "mermaid_type": self.mermaid_type,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "truncated": self.truncated,
            "nodes": self.nodes,
            "edges": [edge.to_dict() for edge in self.edges],
            "mermaid": self.mermaid,
            "metadata": self.metadata,
        }


def _safe_id(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not safe or safe[0].isdigit():
        safe = f"N_{safe}"
    return safe


def _escape_label(label: str) -> str:
    """Sanitise a Mermaid node/edge label.

    Replaces characters that would break the ``["..."]`` syntax:
    - ``"`` → ``'``  (keeps text inside double-quoted Mermaid labels valid)
    - ``\\n`` / ``\\r`` → space  (raw newlines inside ["..."] are illegal in Mermaid)
    """
    return (
        label.replace('"', "'")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _package_name(file_path: str, max_depth: int = 2) -> str:
    parts = [part for part in Path(file_path).parts if part and part != "."]
    if not parts:
        return "root"
    if len(parts) == 1:
        return "root"
    package_parts = parts[:-1][:max_depth]
    return ".".join(package_parts) if package_parts else "root"


def _component_name(file_path: str) -> str:
    parts = [part for part in Path(file_path).parts if part and part != "."]
    if not parts:
        return "root"
    if len(parts) == 1 and Path(parts[0]).suffix:
        return "root"
    if parts[0] == "tree_sitter_analyzer" and len(parts) > 1:
        if len(parts) == 2 and parts[1].endswith(".py"):
            return "tree_sitter_analyzer.root"
        return parts[1]
    return parts[0]


def _clamp_edges(
    edges: Iterable[UMLEdge], max_edges: int
) -> tuple[list[UMLEdge], bool]:
    unique: dict[tuple[str, str, str], UMLEdge] = {}
    for edge in edges:
        key = (edge.source, edge.target, edge.label)
        existing = unique.get(key)
        if existing is None:
            unique[key] = edge
        else:
            unique[key] = UMLEdge(
                source=edge.source,
                target=edge.target,
                label=edge.label,
                weight=existing.weight + edge.weight,
            )
    sorted_edges = sorted(
        unique.values(), key=lambda edge: (-edge.weight, edge.source, edge.target)
    )
    return sorted_edges[:max_edges], len(sorted_edges) > max_edges


def render_class_mermaid(
    nodes: Iterable[str],
    edges: Iterable[UMLEdge],
    truncated: bool = False,
) -> str:
    lines = ["classDiagram"]
    node_list = sorted(set(nodes))
    edge_list = sorted(edges, key=lambda edge: (edge.source, edge.target))
    if not node_list and not edge_list:
        lines.append("  class EmptyProject")
        return "\n".join(lines)
    for node in node_list:
        lines.append(f"  class {_safe_id(node)}")
    for edge in edge_list:
        lines.append(f"  {_safe_id(edge.source)} <|-- {_safe_id(edge.target)}")
    # P1-D: honest truncation note so consumers know the diagram is incomplete
    if truncated:
        lines.append(_TRUNCATION_NOTE)
    return "\n".join(lines)


def render_flowchart_mermaid(
    nodes: Iterable[str],
    edges: Iterable[UMLEdge],
    direction: str = "LR",
) -> str:
    lines = [f"flowchart {direction}"]
    node_list = sorted(set(nodes))
    edge_list = sorted(edges, key=lambda edge: (edge.source, edge.target, edge.label))
    if not node_list and not edge_list:
        lines.append('  empty["No edges found"]')
        return "\n".join(lines)
    for node in node_list:
        lines.append(f'  {_safe_id(node)}["{_escape_label(node)}"]')
    for edge in edge_list:
        if edge.label:
            lines.append(
                f"  {_safe_id(edge.source)} -->|{_escape_label(edge.label)}| "
                f"{_safe_id(edge.target)}"
            )
        else:
            lines.append(f"  {_safe_id(edge.source)} --> {_safe_id(edge.target)}")
    return "\n".join(lines)


def render_state_mermaid(
    states: list[str],
    transitions: list[Any],  # list[StateTransition] — avoid circular at module level
    truncated: bool = False,
) -> str:
    """Render a Mermaid stateDiagram-v2 from states and transitions.

    Each state gets a [*] --> StateName initial-state edge.
    Transitions appear as StateA --> StateB (with optional label).
    The RFC-0015 §P2-B honesty comment is always prepended.
    """
    lines = ["stateDiagram-v2"]
    lines.append("%% NOTE: state diagram is a static approximation.")
    lines.append(
        "%% Guard conditions, timers, and exception-driven transitions are not captured."
    )
    if not states:
        lines.append("    [*] --> EmptyEnum")
        return "\n".join(lines)
    for state in sorted(states):
        lines.append(f"    [*] --> {_safe_id(state)}")
    for t in transitions:
        src = _safe_id(t.source)
        tgt = _safe_id(t.target)
        if t.label:
            lines.append(f"    {src} --> {tgt} : {_escape_label(t.label)}")
        else:
            lines.append(f"    {src} --> {tgt}")
    if truncated:
        lines.append(_TRUNCATION_NOTE)
    return "\n".join(lines)


def render_sequence_mermaid(paths: list[dict[str, Any]], max_hops: int) -> str:
    lines = ["sequenceDiagram"]
    if not paths:
        lines.append("  participant NoPath")
        lines.append("  Note over NoPath: No call path found")
        return "\n".join(lines)

    first_path = paths[0].get("hops", [])[:max_hops]
    participants: list[str] = []
    for hop in first_path:
        for key in ("caller", "callee"):
            name = hop.get(key, "")
            if name and name not in participants:
                participants.append(name)
    if not participants:
        lines.append("  participant EmptyPath")
        return "\n".join(lines)
    for name in participants:
        lines.append(f'  participant {_safe_id(name)} as "{_escape_label(name)}"')
    for hop in first_path:
        caller = hop.get("caller", "")
        callee = hop.get("callee", "")
        if caller and callee:
            lines.append(f"  {_safe_id(caller)}->>+{_safe_id(callee)}: call")
            lines.append(f"  {_safe_id(callee)}-->>-{_safe_id(caller)}: return")
    return "\n".join(lines)


def _file_matches(cls_file: str, filter_path: str | None) -> bool:
    """Return True when *cls_file* matches *filter_path*.

    Accepts both exact-match and suffix-match so callers can pass either
    a repo-relative path ("src/a.py") or a basename ("a.py").
    """
    if not cls_file or not filter_path:
        return False
    norm_cls = cls_file.replace("\\", "/").lstrip("/")
    norm_filter = filter_path.replace("\\", "/").lstrip("/")
    return norm_cls == norm_filter or norm_cls.endswith("/" + norm_filter)


def _is_neighbourhood(
    child: str,
    cls: dict[str, Any],
    center: str | None,
    all_classes: list[dict[str, Any]],
) -> bool:
    """Return True when *child* is in the neighbourhood of *center*.

    The neighbourhood is: center itself + direct parents of center + direct
    subclasses of center (classes that list center as a parent).
    """
    if center is None:
        return False
    if child == center:
        return True
    # child is a direct parent of center
    center_cls = next((c for c in all_classes if c.get("name") == center), None)
    if center_cls is not None:
        parents = [str(p).rsplit(".", 1)[-1] for p in (center_cls.get("parents") or [])]
        if child in parents:
            return True
    # child is a direct subclass of center (center is in child's parents)
    child_parents = [str(p).rsplit(".", 1)[-1] for p in (cls.get("parents") or [])]
    return center in child_parents


class UMLExporter:
    """Build Mermaid UML-style diagrams from existing CodeGraph indexes."""

    def __init__(self, project_root: str, cache: Any | None = None) -> None:
        self.project_root = project_root
        self._cache = cache

    def _open_cache(self) -> tuple[Any, bool]:
        if self._cache is not None:
            return self._cache, False
        from .ast_cache import ASTCache

        return ASTCache(self.project_root), True

    def _resolve_function_file(self, function_name: str) -> str | None:
        """Look up *function_name* in the AST index and return a unique file path.

        Returns:
            Absolute path string if exactly one match; ``None`` otherwise
            (not found OR ambiguous — caller handles both via
            ``_activity_not_found_no_file``).

        Stores the search results on ``self._last_activity_index_hits`` so that
        ``_activity_not_found_no_file`` can compose a richer message without a
        second query.
        """
        cache, should_close = self._open_cache()
        try:
            hits = cache.search_symbols(function_name)
        finally:
            if should_close:
                cache.close()
        # Filter to exact name matches with a file (avoid partial BM25 hits).
        # Python-only (Codex P2 on #498): the CFG builder is Python-only, so a
        # same-name JS/Go symbol must not make the lookup "ambiguous" — and a
        # JS-only hit must not be offered as a CFG target. Also restrict to
        # function-like kinds so a same-name class/variable doesn't collide.
        _FUNC_KINDS = {"function", "method", None, ""}
        exact = [
            h
            for h in hits
            if h.get("name") == function_name
            and h.get("file")
            and (h.get("language") or "python") == "python"
            and (h.get("kind") in _FUNC_KINDS)
        ]
        self._last_activity_index_hits: list[dict[str, Any]] = exact
        if len(exact) == 1:
            raw = exact[0]["file"]
            p = Path(raw)
            return str(p) if p.is_absolute() else str(Path(self.project_root) / raw)
        return None

    def _activity_not_found_no_file(self, function_name: str) -> UMLDiagram:
        """Return a descriptive NOT_FOUND when index lookup for *function_name* fails.

        Distinguishes three cases:
        - not in index at all
        - ambiguous (multiple files) — lists candidate files
        """
        hits: list[dict[str, Any]] = getattr(self, "_last_activity_index_hits", [])
        if not hits:
            next_step = (
                f"activity diagram: '{function_name}' not found in the index; "
                "verify the project is indexed and the function name is correct, "
                "or supply --uml-file-path / file_path directly"
            )
        else:
            # Ambiguous: list candidate files (max 5 for brevity)
            candidates = [h.get("file", "") for h in hits[:5]]
            cand_list = ", ".join(f"'{c}'" for c in candidates)
            next_step = (
                f"activity diagram: '{function_name}' found in multiple files "
                f"({cand_list}{'...' if len(hits) > 5 else ''}); "
                "pass file_path to select the correct one"
            )
        return UMLDiagram(
            diagram_type="activity",
            mermaid_type="flowchart",
            mermaid="flowchart TD\n",
            nodes=[],
            edges=[],
            metadata={
                "diagram_type": "activity",
                "verdict": "NOT_FOUND",
                "next_step": next_step,
            },
        )

    def class_diagram(
        self,
        max_edges: int = 80,
        include_external_bases: bool = True,
        *,
        file_path: str | None = None,
        class_name: str | None = None,
        include_tests: bool = False,
    ) -> UMLDiagram:
        """Build a class inheritance diagram.

        Scoping (P1-A, RFC-0015): applied in priority order, first match wins.
        1. class_name given — neighbourhood subgraph (named class + direct bases
           + direct subclasses).
        2. file_path given — classes defined in that file plus their direct
           bases (so inheritance arrows remain correct).
        3. Neither given — whole-project view, subject to include_tests.

        include_tests=False (P1-C) strips classes whose source file is a
        test/fixture path (detected via is_test_file()).
        """
        cache, should_close = self._open_cache()
        try:
            hierarchy = ClassHierarchy(cache)
            hierarchy.build()
            classes = hierarchy.all_classes()
        finally:
            if should_close:
                cache.close()

        # P1-C: strip test-corpus classes from whole-project view by default
        if not include_tests:
            classes = [c for c in classes if not is_test_file(c.get("file"))]

        internal_names = {c.get("name", "") for c in classes if c.get("name")}
        raw_edges: list[UMLEdge] = []
        nodes: set[str] = set()

        # Determine scope label for metadata
        if class_name is not None:
            scope = "class_neighbourhood"
        elif file_path is not None:
            scope = "file"
        else:
            scope = "whole_project"

        # P2-1: an unknown class_name must be distinguishable from a known
        # class with an empty neighbourhood — agents can't tell them apart
        # from an empty diagram alone.
        not_found = class_name is not None and class_name not in internal_names

        for cls in classes:
            child = cls.get("name", "")
            if not child:
                continue

            # P1-A scoping: apply file_path / class_name filter
            if scope == "file":
                cls_file = cls.get("file", "")
                if not _file_matches(cls_file, file_path):
                    continue
            elif scope == "class_neighbourhood":
                # Include: the named class itself, its direct parents, and
                # classes that list it as a direct parent (subclasses one hop)
                if not _is_neighbourhood(child, cls, class_name, classes):
                    continue

            nodes.add(child)
            for parent_text in cls.get("parents") or []:
                parent = str(parent_text).rsplit(".", 1)[-1]
                if parent in internal_names or (
                    include_external_bases and parent in _EXTERNAL_BASES
                ):
                    nodes.add(parent)
                    raw_edges.append(UMLEdge(parent, child, "inherits"))

        edges, truncated = _clamp_edges(raw_edges, max_edges)
        rendered_nodes = sorted(
            {n for edge in edges for n in (edge.source, edge.target)}
        )
        if not rendered_nodes:
            rendered_nodes = sorted(nodes)[:max_edges]
        return UMLDiagram(
            diagram_type="class",
            mermaid_type="classDiagram",
            mermaid=render_class_mermaid(rendered_nodes, edges, truncated=truncated),
            nodes=rendered_nodes,
            edges=edges,
            truncated=truncated,
            metadata={
                "source": "class_hierarchy",
                "scope": scope,
                **({"not_found": True} if not_found else {}),
            },
        )

    def package_diagram(
        self, max_edges: int = 200, package_depth: int = 2
    ) -> UMLDiagram:
        graph = ImportGraph(self.project_root)
        result = graph.build()
        edge_weights: dict[tuple[str, str], int] = defaultdict(int)
        nodes: set[str] = set()
        for edge in result.edges:
            source = _package_name(edge.source_file, package_depth)
            target = _package_name(edge.target_file, package_depth)
            if source == target:
                continue
            edge_weights[(source, target)] += 1
            nodes.update((source, target))
        edges, truncated = _clamp_edges(
            (
                UMLEdge(source, target, str(weight), weight)
                for (source, target), weight in edge_weights.items()
            ),
            max_edges,
        )
        return UMLDiagram(
            diagram_type="package",
            mermaid_type="flowchart",
            mermaid=render_flowchart_mermaid(nodes, edges, "LR"),
            nodes=sorted(nodes),
            edges=edges,
            truncated=truncated,
            metadata={"source": "import_graph", "package_depth": package_depth},
        )

    def component_diagram(self, max_edges: int = 120) -> UMLDiagram:
        graph = ImportGraph(self.project_root)
        result = graph.build()
        edge_weights: dict[tuple[str, str], int] = defaultdict(int)
        nodes: set[str] = set()
        for edge in result.edges:
            source = _component_name(edge.source_file)
            target = _component_name(edge.target_file)
            if source == target:
                continue
            edge_weights[(source, target)] += 1
            nodes.update((source, target))
        edges, truncated = _clamp_edges(
            (
                UMLEdge(source, target, str(weight), weight)
                for (source, target), weight in edge_weights.items()
            ),
            max_edges,
        )
        return UMLDiagram(
            diagram_type="component",
            mermaid_type="flowchart",
            mermaid=render_flowchart_mermaid(nodes, edges, "LR"),
            nodes=sorted(nodes),
            edges=edges,
            truncated=truncated,
            metadata={"source": "import_graph", "group_by": "top_level_component"},
        )

    def sequence_diagram(
        self,
        source: str,
        target: str,
        max_depth: int = 8,
        max_paths: int = 3,
        max_hops: int = 12,
    ) -> UMLDiagram:
        finder = CallPathFinder(self.project_root, self._cache)
        result = finder.find_path(
            source_function=source,
            target_function=target,
            max_depth=max_depth,
            max_paths=max_paths,
        )
        result_dict = result.to_dict()
        paths = result_dict.get("paths", [])
        first_hops = paths[0].get("hops", []) if paths else []
        nodes = sorted(
            {
                hop.get(key, "")
                for hop in first_hops[:max_hops]
                for key in ("caller", "callee")
                if hop.get(key)
            }
        )
        edges = [
            UMLEdge(hop.get("caller", ""), hop.get("callee", ""), "call")
            for hop in first_hops[:max_hops]
            if hop.get("caller") and hop.get("callee")
        ]
        # P1-E (RFC-0015): observability label — "call_path+synapse_resolved"
        # when at least one hop has callee_file populated (synapse resolution
        # contributed to BFS traversal); "call_path" otherwise.
        has_resolved = any(
            hop.get("callee_file") for path in paths for hop in path.get("hops", [])
        )
        source_label = "call_path+synapse_resolved" if has_resolved else "call_path"
        return UMLDiagram(
            diagram_type="sequence",
            mermaid_type="sequenceDiagram",
            mermaid=render_sequence_mermaid(paths, max_hops),
            nodes=nodes,
            edges=edges,
            truncated=result.truncated or len(first_hops) > max_hops,
            metadata={
                "source": source_label,
                "analysis_kind": "static_approximation",
                "path_count": len(paths),
            },
        )

    def activity_diagram(
        self,
        function_name: str,
        file_path: str | None = None,
        max_nodes: int = 50,
    ) -> UMLDiagram:
        """Build a structural control-flow graph for *function_name*.

        P2-A (RFC-0015): requires a disk read + tree-sitter parse at query
        time (AST bodies are NOT cache-resident). Cost: typically < 50 ms.

        Stale file (changed since indexing): parsed from current disk content;
        metadata["note"] records the staleness. Missing file/function:
        verdict="NOT_FOUND".

        Language support: Python only in this phase. The node-type map in
        uml_activity._CFG_NODE_TYPES is language-keyed; future languages
        register there without touching this method.
        """
        from .uml_activity import build_activity_cfg

        # Resolve file_path: use as-is if absolute, otherwise interpret as
        # relative to project_root.
        resolved_path: str | None = None
        if file_path is not None:
            p = Path(file_path)
            if p.is_absolute():
                resolved_path = str(p)
            else:
                resolved_path = str(Path(self.project_root) / p)

        if resolved_path is None:
            # No file_path given: attempt to resolve via the AST index (#477 STRONG).
            # Look up function_name in the index to distinguish:
            #   a) unique hit  → resolve file and proceed
            #   b) ambiguous   → NOT_FOUND with candidate file list
            #   c) not in index → NOT_FOUND with "not found in index" message
            resolved_path = self._resolve_function_file(function_name)
            if resolved_path is None:
                # Index lookup failed — return descriptive NOT_FOUND
                return self._activity_not_found_no_file(function_name)

        cfg = build_activity_cfg(function_name, resolved_path, max_nodes)

        if cfg.error:
            if "file_missing" in cfg.error:
                return UMLDiagram(
                    diagram_type="activity",
                    mermaid_type="flowchart",
                    mermaid="flowchart TD\n",
                    nodes=[],
                    edges=[],
                    metadata={
                        "diagram_type": "activity",
                        "verdict": "NOT_FOUND",
                        "next_step": (
                            f"activity diagram: source file '{resolved_path}' does "
                            "not exist; the indexed symbol's source file may have "
                            "been deleted or moved"
                        ),
                    },
                )
            if "function_missing" in cfg.error:
                return UMLDiagram(
                    diagram_type="activity",
                    mermaid_type="flowchart",
                    mermaid="flowchart TD\n",
                    nodes=[],
                    edges=[],
                    metadata={
                        "diagram_type": "activity",
                        "verdict": "NOT_FOUND",
                        "next_step": (
                            f"activity diagram: function '{function_name}' not found "
                            f"in '{resolved_path}'"
                        ),
                    },
                )
            if "empty_body" in cfg.error:
                return UMLDiagram(
                    diagram_type="activity",
                    mermaid_type="flowchart",
                    mermaid="flowchart TD\n",
                    nodes=[],
                    edges=[],
                    metadata={
                        "diagram_type": "activity",
                        "verdict": "NOT_FOUND",
                        "next_step": (
                            f"activity diagram found no control-flow nodes in "
                            f"'{function_name}'; the function may be a stub or use "
                            "a pattern not yet supported"
                        ),
                    },
                )
            # PARSE_FAILED or unknown error
            return UMLDiagram(
                diagram_type="activity",
                mermaid_type="flowchart",
                mermaid="flowchart TD\n",
                nodes=[],
                edges=[],
                metadata={
                    "diagram_type": "activity",
                    "verdict": "NOT_FOUND",
                    "error": cfg.error,
                    "next_step": "activity diagram: parse failed; check the file is valid Python",
                },
            )

        # Build Mermaid from CFG
        uml_nodes = [n.node_id for n in cfg.nodes]
        uml_edges = [UMLEdge(e.source_id, e.target_id, e.label) for e in cfg.edges]

        # Build Mermaid flowchart TD (not via render_flowchart_mermaid — we
        # want actual node labels, not sorted IDs)
        lines = ["flowchart TD"]
        lines.append("%% NOTE: activity diagram is a structural AST approximation.")
        lines.append(
            "%% Exception edges, async suspension, and dynamic dispatch are not modelled."
        )
        for n in cfg.nodes:
            safe = _safe_id(n.node_id)
            label = _escape_label(n.label)
            lines.append(f'  {safe}["{label}"]')
        for e in cfg.edges:
            src = _safe_id(e.source_id)
            tgt = _safe_id(e.target_id)
            if e.label:
                lines.append(f"  {src} -->|{_escape_label(e.label)}| {tgt}")
            else:
                lines.append(f"  {src} --> {tgt}")
        if cfg.truncated:
            lines.append(_TRUNCATION_NOTE)

        mermaid = "\n".join(lines)

        return UMLDiagram(
            diagram_type="activity",
            mermaid_type="flowchart",
            mermaid=mermaid,
            nodes=uml_nodes,
            edges=uml_edges,
            truncated=cfg.truncated,
            metadata={
                "diagram_type": "activity",
                "analysis_kind": "structural_approximation",
                "function_name": function_name,
                "file_path": resolved_path,
                # RFC-0015 §P2-A stale-file contract: activity ALWAYS re-parses
                # the current file from disk (AST bodies are not cache-resident),
                # so the diagram reflects the current file content, not the index.
                "note": "parsed from current file content; may differ from indexed symbols",
            },
        )

    def state_diagram(
        self,
        *,
        class_name: str | None = None,
        file_path: str | None = None,
        max_nodes: int = 50,
    ) -> UMLDiagram:
        """Build a stateDiagram-v2 from an enum/match-driven FSM (P2-B, RFC-0015).

        Static approximation: enum members become states; match/case patterns
        with return <Enum>.<Member> become transitions.

        Honesty rules (#480 update):
        - metadata["analysis_kind"] == "static_approximation" always.
        - metadata["note"] records that parsing is done from current file content.
        - states found, zero transitions → verdict="INFO" with next_step note
          (partial result — enum members extracted but FSM pattern not recognised).
        - zero states (class missing / no enum found / file absent) → verdict="NOT_FOUND".
        - Language coverage: Python-only; non-Python files emit a language note.

        Cost: ONE disk read + ONE tree-sitter parse (rule-11 invariant).
        """
        from .uml_state import build_state_result

        # Resolve file_path: use as-is if absolute, otherwise interpret as
        # relative to project_root (mirrors activity_diagram path logic).
        resolved_path = ""
        if file_path:
            p = Path(file_path)
            if p.is_absolute():
                resolved_path = str(p)
            else:
                resolved_path = str(Path(self.project_root) / p)

        if not resolved_path:
            # No file given — try to find via class_hierarchy if class_name provided
            # (best-effort: use ClassHierarchy to find the file for the named class)
            if class_name is not None:
                cache, should_close = self._open_cache()
                try:
                    from .class_hierarchy import ClassHierarchy

                    hierarchy = ClassHierarchy(cache)
                    hierarchy.build()
                    all_cls = hierarchy.all_classes()
                    for cls_info in all_cls:
                        if cls_info.get("name") == class_name:
                            cf = cls_info.get("file", "") or ""
                            if cf:
                                cp = Path(cf)
                                resolved_path = (
                                    str(cp)
                                    if cp.is_absolute()
                                    else str(Path(self.project_root) / cp)
                                )
                            if resolved_path:
                                break
                finally:
                    if should_close:
                        cache.close()

        if not resolved_path:
            return UMLDiagram(
                diagram_type="state",
                mermaid_type="stateDiagram-v2",
                mermaid="stateDiagram-v2\n",
                nodes=[],
                edges=[],
                metadata={
                    "analysis_kind": "static_approximation",
                    "verdict": "NOT_FOUND",
                    "next_step": (
                        "state diagram: supply file_path or class_name with an indexed "
                        "Enum class so the scanner can locate the source file"
                    ),
                },
            )

        # Language coverage: state extraction is Python-only (#480).
        # Non-Python files (e.g. .ts, .java) will fail the no-enum check below,
        # but the message should explain the scope limit, not just say "check
        # for an Enum subclass" (which is meaningless for TypeScript).
        _py_extensions = {".py", ".pyw"}
        _file_is_python = Path(resolved_path).suffix.lower() in _py_extensions

        result = build_state_result(
            file_path=resolved_path,
            class_name=class_name,
            max_nodes=max_nodes,
        )

        base_metadata: dict[str, Any] = {
            "analysis_kind": "static_approximation",
            "note": "parsed from current file content; may differ from indexed symbols",
        }
        if class_name:
            base_metadata["class_name"] = class_name
        base_metadata["file_path"] = resolved_path

        if result.error:
            if not _file_is_python:
                next_step_msg = (
                    f"state diagram: state extraction supports Python only; "
                    f"'{Path(resolved_path).name}' is not a Python file. "
                    "Pass a .py file that contains an Enum subclass."
                )
            else:
                next_step_msg = (
                    f"state diagram: {result.error}; "
                    "check that the file exists and contains an Enum subclass"
                )
            return UMLDiagram(
                diagram_type="state",
                mermaid_type="stateDiagram-v2",
                mermaid="stateDiagram-v2\n",
                nodes=[],
                edges=[],
                metadata={
                    **base_metadata,
                    "verdict": "NOT_FOUND",
                    "next_step": next_step_msg,
                },
            )

        # Zero transitions but states found → INFO (#480 fix).
        # A partial result (states extracted, FSM pattern not recognised) is not
        # "not found". Use INFO so agents can consume the extracted enum members.
        # The mermaid [*]--> lines are still suppressed (mermaid honesty rule):
        # an agent reading only `mermaid` would see a structurally-valid diagram;
        # emitting only the header + NOTE guard keeps the mermaid honest.
        if not result.transitions:
            info_mermaid = (
                "stateDiagram-v2\n"
                "%% NOTE: state diagram is a static approximation.\n"
                "%% Guard conditions, timers, and exception-driven transitions are not captured.\n"
                "%% NOTE: no transitions detected — FSM pattern not recognised by this heuristic."
            )
            return UMLDiagram(
                diagram_type="state",
                mermaid_type="stateDiagram-v2",
                mermaid=info_mermaid,
                nodes=result.states,
                edges=[],
                metadata={
                    **base_metadata,
                    "verdict": "INFO",
                    "next_step": (
                        f"state diagram: {len(result.states)} enum member(s) extracted "
                        "as states but no match-pattern transitions were found; "
                        "the class may not encode a finite-state machine in a pattern "
                        "this heuristic recognises"
                    ),
                },
            )

        uml_edges = [UMLEdge(t.source, t.target, t.label) for t in result.transitions]
        mermaid = render_state_mermaid(
            result.states, result.transitions, truncated=result.truncated
        )
        return UMLDiagram(
            diagram_type="state",
            mermaid_type="stateDiagram-v2",
            mermaid=mermaid,
            nodes=result.states,
            edges=uml_edges,
            truncated=result.truncated,
            metadata=base_metadata,
        )
