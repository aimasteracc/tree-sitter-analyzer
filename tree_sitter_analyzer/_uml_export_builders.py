"""Focused sequence- and state-diagram builders for :mod:`uml_export`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .uml_state import StateResult, build_state_result

if TYPE_CHECKING:
    from .uml_export import UMLDiagram, UMLEdge


def build_class_diagram(
    classes: list[dict[str, Any]],
    *,
    max_edges: int,
    include_external_bases: bool,
    file_path: str | None,
    class_name: str | None,
    include_tests: bool,
) -> UMLDiagram:
    """Build the class-diagram payload from an already-loaded hierarchy."""
    from . import uml_export as api
    from .utils.test_detection import is_test_file

    if not include_tests:
        classes = [item for item in classes if not is_test_file(item.get("file"))]
    internal_names = {item.get("name", "") for item in classes if item.get("name")}
    scope = (
        "class_neighbourhood"
        if class_name is not None
        else "file"
        if file_path is not None
        else "whole_project"
    )
    nodes: set[str] = set()
    production_edges: list[api.UMLEdge] = []
    test_edges: list[api.UMLEdge] = []
    for item in classes:
        child = item.get("name", "")
        if not child or (
            scope == "file" and not api._file_matches(item.get("file", ""), file_path)
        ):
            continue
        if scope == "class_neighbourhood" and not api._is_neighbourhood(
            child, item, class_name, classes
        ):
            continue
        nodes.add(child)
        for parent_text in item.get("parents") or []:
            parent = str(parent_text).rsplit(".", 1)[-1]
            if parent not in internal_names and not (
                include_external_bases and parent in api._EXTERNAL_BASES
            ):
                continue
            nodes.add(parent)
            edge = api.UMLEdge(parent, child, "inherits")
            target = (
                test_edges
                if include_tests
                and scope == "whole_project"
                and is_test_file(item.get("file"))
                else production_edges
            )
            target.append(edge)

    edges, truncated = _prioritized_class_edges(production_edges, test_edges, max_edges)
    rendered_nodes = (
        sorted({name for edge in edges for name in (edge.source, edge.target)})
        or sorted(nodes)[:max_edges]
    )
    return api.UMLDiagram(
        diagram_type="class",
        mermaid_type="classDiagram",
        mermaid=api.render_class_mermaid(rendered_nodes, edges, truncated=truncated),
        nodes=rendered_nodes,
        edges=edges,
        truncated=truncated,
        metadata={
            "source": "class_hierarchy",
            "scope": scope,
            **(
                {"not_found": True}
                if class_name is not None and class_name not in internal_names
                else {}
            ),
        },
    )


def _prioritized_class_edges(
    production_edges: list[UMLEdge], test_edges: list[UMLEdge], max_edges: int
) -> tuple[list[UMLEdge], bool]:
    from . import uml_export as api

    if not test_edges:
        edges, truncated = api._clamp_edges(production_edges, max_edges)
        return api._dedupe_edges_by_signature(edges), truncated
    edges, production_truncated = api._clamp_edges(production_edges, max_edges)
    remaining = max_edges - len(edges)
    if remaining <= 0:
        return api._dedupe_edges_by_signature(edges), (
            production_truncated or bool(test_edges)
        )
    selected_tests, tests_truncated = api._clamp_edges(test_edges, remaining)
    return api._dedupe_edges_by_signature(edges + selected_tests), (
        production_truncated or tests_truncated
    )


def build_sequence_diagram(
    exporter: Any,
    source: str,
    target: str,
    max_depth: int,
    max_paths: int,
    max_hops: int,
) -> UMLDiagram:
    """Build a sequence diagram while preserving the public patch seams."""
    from . import uml_export as api

    finder = api.CallPathFinder(exporter.project_root, exporter._cache)
    result = finder.find_path(
        source_function=source,
        target_function=target,
        max_depth=max_depth,
        max_paths=max_paths,
    )
    paths = result.to_dict().get("paths", [])
    first_hops = paths[0].get("hops", []) if paths else []
    path_search_truncated = bool(
        getattr(result, "truncated", False) and len(paths) >= max_paths
    )
    return api.UMLDiagram(
        diagram_type="sequence",
        mermaid_type="sequenceDiagram",
        mermaid=api.render_sequence_mermaid(paths, max_hops),
        nodes=_sequence_nodes(first_hops, max_hops),
        edges=_sequence_edges(first_hops, max_hops),
        truncated=path_search_truncated or len(first_hops) > max_hops,
        metadata={
            "source": (
                "call_path+synapse_resolved"
                if _has_resolved_hop(paths)
                else "call_path"
            ),
            "analysis_kind": "static_approximation",
            "path_count": len(paths),
        },
    )


def _sequence_nodes(hops: list[dict[str, Any]], max_hops: int) -> list[str]:
    return sorted(
        {
            hop.get(key, "")
            for hop in hops[:max_hops]
            for key in ("caller", "callee")
            if hop.get(key)
        }
    )


def _sequence_edges(hops: list[dict[str, Any]], max_hops: int) -> list[UMLEdge]:
    from .uml_export import UMLEdge

    return [
        UMLEdge(hop.get("caller", ""), hop.get("callee", ""), "call")
        for hop in hops[:max_hops]
        if hop.get("caller") and hop.get("callee")
    ]


def _has_resolved_hop(paths: list[dict[str, Any]]) -> bool:
    return any(hop.get("callee_file") for path in paths for hop in path.get("hops", []))


def build_state_diagram(
    exporter: Any,
    *,
    class_name: str | None,
    file_path: str | None,
    max_nodes: int,
) -> UMLDiagram:
    """Build an enum/match-driven state diagram from one current source file."""
    resolved_path = _state_source_path(exporter, class_name, file_path)
    if not resolved_path:
        return _missing_state_source_diagram()

    result = build_state_result(
        file_path=resolved_path,
        class_name=class_name,
        max_nodes=max_nodes,
    )
    metadata = _state_metadata(class_name, resolved_path)
    if result.error:
        return _state_error_diagram(result, resolved_path, metadata)
    if not result.transitions:
        return _state_info_diagram(result, metadata)
    return _complete_state_diagram(result, metadata)


def _state_source_path(
    exporter: Any,
    class_name: str | None,
    file_path: str | None,
) -> str:
    if file_path:
        return _project_path(exporter.project_root, file_path)
    if class_name is None:
        return ""
    return _indexed_class_path(exporter, class_name)


def _indexed_class_path(exporter: Any, class_name: str) -> str:
    from .class_hierarchy import ClassHierarchy

    cache, should_close = exporter._open_cache()
    try:
        hierarchy = ClassHierarchy(cache)
        hierarchy.build()
        match = next(
            (
                item
                for item in hierarchy.all_classes()
                if item.get("name") == class_name and item.get("file")
            ),
            None,
        )
        return _project_path(exporter.project_root, match["file"]) if match else ""
    finally:
        if should_close:
            cache.close()


def _project_path(project_root: str, file_path: Any) -> str:
    path = Path(str(file_path))
    return str(path) if path.is_absolute() else str(Path(project_root) / path)


def _state_metadata(class_name: str | None, resolved_path: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "analysis_kind": "static_approximation",
        "note": "parsed from current file content; may differ from indexed symbols",
        "file_path": resolved_path,
    }
    if class_name:
        metadata["class_name"] = class_name
    return metadata


def _missing_state_source_diagram() -> UMLDiagram:
    from .uml_export import UMLDiagram

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


def _state_error_diagram(
    result: StateResult,
    resolved_path: str,
    metadata: dict[str, Any],
) -> UMLDiagram:
    from .uml_export import UMLDiagram

    if Path(resolved_path).suffix.lower() not in {".py", ".pyw"}:
        next_step = (
            "state diagram: state extraction supports Python only; "
            f"'{Path(resolved_path).name}' is not a Python file. "
            "Pass a .py file that contains an Enum subclass."
        )
    else:
        next_step = (
            f"state diagram: {result.error}; "
            "check that the file exists and contains an Enum subclass"
        )
    return UMLDiagram(
        diagram_type="state",
        mermaid_type="stateDiagram-v2",
        mermaid="stateDiagram-v2\n",
        nodes=[],
        edges=[],
        metadata={**metadata, "verdict": "NOT_FOUND", "next_step": next_step},
    )


def _state_info_diagram(
    result: StateResult,
    metadata: dict[str, Any],
) -> UMLDiagram:
    from .uml_export import UMLDiagram

    mermaid = (
        "stateDiagram-v2\n"
        "%% NOTE: state diagram is a static approximation.\n"
        "%% Guard conditions, timers, and exception-driven transitions are not captured.\n"
        "%% NOTE: no transitions detected — FSM pattern not recognised by this heuristic."
    )
    return UMLDiagram(
        diagram_type="state",
        mermaid_type="stateDiagram-v2",
        mermaid=mermaid,
        nodes=result.states,
        edges=[],
        metadata={
            **metadata,
            "verdict": "INFO",
            "next_step": (
                f"state diagram: {len(result.states)} enum member(s) extracted "
                "as states but no match-pattern transitions were found; "
                "the class may not encode a finite-state machine in a pattern "
                "this heuristic recognises"
            ),
        },
    )


def _complete_state_diagram(
    result: StateResult,
    metadata: dict[str, Any],
) -> UMLDiagram:
    from .uml_export import UMLDiagram, UMLEdge, render_state_mermaid

    edges = [
        UMLEdge(item.source, item.target, item.label) for item in result.transitions
    ]
    return UMLDiagram(
        diagram_type="state",
        mermaid_type="stateDiagram-v2",
        mermaid=render_state_mermaid(
            result.states,
            result.transitions,
            truncated=result.truncated,
        ),
        nodes=result.states,
        edges=edges,
        truncated=result.truncated,
        metadata=metadata,
    )
