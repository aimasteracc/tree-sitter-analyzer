"""RFC-0038 glue for ``nav callers``: which definitions a query is about.

An ``annotated_receiver`` edge is resolved only for the definition it is bound
to. The completeness readers therefore need the (file, line) of every
definition the query covers:

* a qualified query (``Class.method``) covers the graph's resolved targets;
* a bare query covers every definition of the name, narrowed to ``file_path``
  when one is given.

An empty set is always safe: the annotated edges then count as unresolved, as
they did before the RFC.
"""

from __future__ import annotations

from typing import Any

#: (definition file, definition line).
Coordinate = tuple[str, int]


def graph_bound_targets(
    graph: Any, func_name: str, file_path: str | None
) -> frozenset[Coordinate]:
    """Definitions a qualified graph query resolved to."""
    try:
        refs = graph.resolve_targets(func_name, file_path)
    except Exception:  # nosec B110 — no targets: annotated edges stay unresolved.
        return frozenset()
    return frozenset((ref.file_path, ref.start_line) for ref in refs)


def name_bound_targets(
    cache: Any, func_name: str, file_path: str | None
) -> frozenset[Coordinate]:
    """Definitions of a bare name, narrowed to ``file_path`` when given."""
    reader = getattr(cache, "symbol_definitions", None)
    if not callable(reader):
        return frozenset()
    try:
        found = reader(func_name) or []
    except Exception:  # nosec B110 — unreadable: annotated edges stay unresolved.
        return frozenset()
    normalized = file_path.replace("\\", "/") if file_path else None
    return frozenset(
        (str(file), int(line))
        for file, line in found
        if normalized is None or str(file).replace("\\", "/") == normalized
    )


def drop_bound_sites(
    sites: list[dict[str, Any]] | None, targets: frozenset[Coordinate]
) -> list[dict[str, Any]] | None:
    """Remove declaring-file sites that are annotated edges bound to ``targets``."""
    if sites is None or not targets:
        return sites
    kept: list[dict[str, Any]] = []
    for site in sites:
        bound = site.get("bound_to")
        if (
            isinstance(bound, dict)
            and (bound.get("file"), bound.get("line")) in targets
        ):
            continue
        kept.append(site)
    return kept


def annotated_provenance(binding: Any) -> dict[str, Any]:
    """Caller-entry fields for an edge bound through an annotation; else ``{}``."""
    if not isinstance(binding, dict) or not binding:
        return {}
    return {
        "resolution_kind": "annotated_receiver",
        "receiver_type": binding.get("type"),
        "type_source": binding.get("source"),
        "confidence": binding.get("confidence"),
    }
