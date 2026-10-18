"""RFC-0038: bind a persisted ``annotated_receiver`` edge in the cached graph.

The edge names the method the annotation's type resolves to
(``metadata.receiver_binding``: owner class and definition line). That method
is the certain target. Everything the call could still reach at runtime stays a
``possible`` target, so dead-code and impact over-approximation lose nothing:

* every override of the method in a transitive subclass of the declared type
  or the owner class (#1635's ``SubclassIndex``), and
* every other same-name candidate the name-based tiers would have offered
  before this RFC.

An edge whose binding cannot be matched to an indexed definition (stale index,
missing metadata) returns ``None`` and is treated as an unresolved edge.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .call_graph import FunctionRef
    from .call_graph_self_dispatch import SubclassIndex

#: ``callee_resolution`` of an edge bound through an annotation (RFC-0038).
ANNOTATED_RECEIVER = "annotated_receiver"


def parse_binding(raw: Any) -> dict[str, Any] | None:
    """The ``receiver_binding`` object of an edge row, if it is well formed."""
    if isinstance(raw, dict):
        binding = raw
    elif isinstance(raw, str) and raw:
        try:
            binding = json.loads(raw)
        except ValueError:
            return None
    else:
        return None
    return binding if isinstance(binding, dict) else None


def bound_definition(
    functions_by_file: dict[str, list[FunctionRef]],
    resolved_file: str,
    base_name: str,
    binding: dict[str, Any],
) -> FunctionRef | None:
    """The indexed definition an annotated edge is bound to, or ``None``."""
    line = binding.get("line")
    owner = binding.get("owner")
    matches = [
        ref
        for ref in functions_by_file.get(resolved_file, [])
        if ref.name == base_name
        and ref.start_line == line
        and (not owner or ref.receiver == owner)
    ]
    return matches[0] if len(matches) == 1 else None


def dispatch_alternatives(
    subclasses: SubclassIndex | None,
    functions_by_name: dict[str, list[FunctionRef]],
    base_name: str,
    binding: dict[str, Any],
    target: FunctionRef,
) -> list[FunctionRef]:
    """Overrides in subclasses of the declared type / owner that may run instead."""
    if subclasses is None:
        return []
    names: set[str] = set()
    for class_name in (binding.get("type"), binding.get("owner")):
        if class_name:
            names |= subclasses.subclasses(str(class_name))
    return [
        ref
        for ref in functions_by_name.get(base_name, [])
        if ref.receiver in names and ref != target
    ]
