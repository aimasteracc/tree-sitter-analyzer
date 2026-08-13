"""Bound AST diff node-body response materialization."""

from __future__ import annotations

import json
from typing import Any


def apply_node_body_budget(
    response: dict[str, Any], result: Any, byte_budget: int
) -> None:
    """Replace oversized child-bearing hunks with their compact representation."""
    hunks_bytes = len(json.dumps(response.get("hunks", [])))
    if hunks_bytes <= byte_budget:
        return
    compact_dict = result.to_dict(include_children=False, with_child_count=True)
    compact_hunks_bytes = len(json.dumps(compact_dict.get("hunks", [])))
    response["hunks"] = compact_dict["hunks"]
    response["children_truncated"] = True
    response["bytes_omitted"] = hunks_bytes - compact_hunks_bytes
