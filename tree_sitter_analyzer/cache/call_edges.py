"""Call-edge derivation from parsed source trees."""

from __future__ import annotations

from typing import Any

_DefinitionSpan = tuple[str, int, int, int, int, int]


def extract_call_edges(
    tree: Any,
    source_code: str,
    language: str,
) -> list[dict[str, Any]]:
    """Return ordered call edges with innermost-function attribution."""
    if tree is None:
        return []
    from ..function_extraction import walk_tree

    definitions, calls = walk_tree(tree.root_node, source_code, language)
    spans = _definition_spans(definitions)
    return [_edge_for_call(call, spans) for call in calls]


def _definition_spans(definitions: list[dict[str, Any]]) -> list[_DefinitionSpan]:
    """Preserve every definition span, including duplicate method names."""
    # Keep every span: same-named methods in different classes must not collide.
    spans: list[_DefinitionSpan] = []
    for definition in definitions:
        start_line = definition["start_line"]
        start_col = definition.get("start_col", 0)
        end_line = definition.get("end_line", start_line)
        end_col = definition.get("end_col", 0)
        spans.append(
            (
                definition["name"],
                start_line,
                start_col,
                end_line,
                end_col,
                start_line,
            )
        )
    return spans


def _edge_for_call(
    call: dict[str, Any],
    spans: list[_DefinitionSpan],
) -> dict[str, Any]:
    """Build one edge using the smallest enclosing definition span."""
    call_line = call["line"]
    call_col = call.get("col", 0)
    caller_name = ""
    caller_line = 0
    best_span: tuple[int, int] | None = None
    for name, start_line, start_col, end_line, end_col, raw_start in spans:
        after_start = (call_line, call_col) >= (start_line, start_col)
        before_end = (call_line, call_col) <= (end_line, end_col)
        if not (after_start and before_end):
            continue
        line_span = end_line - start_line
        col_span = end_col - start_col if end_line == start_line else 0
        candidate_span = (line_span, col_span)
        if best_span is None or candidate_span < best_span:
            best_span = candidate_span
            caller_name = name
            caller_line = raw_start
    callee_name = call.get("name", "")
    return {
        "caller_name": caller_name,
        "caller_line": caller_line,
        "callee_name": callee_name,
        "callee_full": call.get("full_name", callee_name),
        "callee_line": call_line,
    }
