#!/usr/bin/env python3
"""State-diagram scanner facade and stable public data types.

``uml_state.py`` remains the public import wrapper. Node discovery, transition
scanning, and result shaping live in focused private stages behind this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._uml_state_nodes import (
    extract_enum_members as _extract_members,
)
from ._uml_state_nodes import (
    find_enum_classes as _find_classes,
)
from ._uml_state_nodes import (
    node_text as _decode_node_text,
)
from ._uml_state_results import collect_state_data, finalize_states
from ._uml_state_transitions import extract_transitions

ParseFileForState = Callable[[str, str], tuple[Any, bytes] | None]


@dataclass
class StateTransition:
    """A directed transition between two states."""

    source: str
    target: str
    label: str = ""


@dataclass
class StateResult:
    """Result of a state-machine scan."""

    states: list[str] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    truncated: bool = False
    error: str = ""


def _parse_file_for_state(
    file_path: str, language: str = "python"
) -> tuple[Any, bytes] | None:
    """Parse a file once and return its tree root plus source bytes."""
    from .core.parser import Parser

    result = Parser().parse_file(file_path, language)
    if not result.success or result.tree is None:
        return None
    raw_source = result.source_code
    source_bytes: bytes = (
        raw_source.encode("utf-8", errors="replace")
        if isinstance(raw_source, str)
        else (raw_source or b"")
    )
    return result.tree.root_node, source_bytes


def _node_text(node: Any, max_len: int = 60) -> str:
    """Preserve the historical node-text helper surface."""
    return _decode_node_text(node, max_len)


def _find_enum_classes(
    root: Any, class_name_filter: str | None
) -> list[dict[str, Any]]:
    """Preserve the historical Enum discovery helper surface."""
    return _find_classes(root, class_name_filter)


def _extract_enum_members(class_node: Any) -> list[str]:
    """Preserve the historical Enum-member helper surface."""
    return _extract_members(class_node)


def _extract_transitions(
    root: Any, class_name: str, known_members: set[str]
) -> list[StateTransition]:
    """Preserve the historical transition helper surface."""
    return extract_transitions(root, class_name, known_members, StateTransition)


def _missing_enum_error(class_name: str | None) -> str:
    return (
        "NOT_FOUND:class_missing"
        if class_name is not None
        else "NOT_FOUND:no_enum_class"
    )


def build_state_result(
    file_path: str,
    class_name: str | None,
    max_nodes: int = 50,
    language: str = "python",
    *,
    parse_file_for_state: ParseFileForState = _parse_file_for_state,
) -> StateResult:
    """Parse one file and extract deterministic FSM states and transitions."""
    if not Path(file_path).exists():
        return StateResult(error="NOT_FOUND:file_missing")

    parse_result = parse_file_for_state(file_path, language)
    if parse_result is None:
        return StateResult(error="PARSE_FAILED")
    root, _source = parse_result

    enum_classes = _find_enum_classes(root, class_name)
    if not enum_classes:
        return StateResult(error=_missing_enum_error(class_name))

    members, transitions = collect_state_data(
        root,
        enum_classes,
        class_name,
        _extract_enum_members,
        _extract_transitions,
    )
    states, truncated = finalize_states(members, max_nodes)
    return StateResult(
        states=states,
        transitions=transitions,
        truncated=truncated,
    )
