#!/usr/bin/env python3
"""Public re-export wrapper for the state-diagram scanner."""

from __future__ import annotations

from . import _uml_state_helpers as _helpers

StateResult = _helpers.StateResult
StateTransition = _helpers.StateTransition
_extract_enum_members = _helpers._extract_enum_members
_extract_transitions = _helpers._extract_transitions
_find_enum_classes = _helpers._find_enum_classes
_node_text = _helpers._node_text


def _parse_file_for_state(
    file_path: str, language: str = "python"
) -> tuple[object, bytes] | None:
    return _helpers._parse_file_for_state(file_path, language)


def build_state_result(
    file_path: str,
    class_name: str | None,
    max_nodes: int = 50,
    language: str = "python",
) -> _helpers.StateResult:
    return _helpers.build_state_result(
        file_path,
        class_name,
        max_nodes=max_nodes,
        language=language,
        parse_file_for_state=_parse_file_for_state,
    )


__all__ = [
    "StateResult",
    "StateTransition",
    "_parse_file_for_state",
    "_node_text",
    "_find_enum_classes",
    "_extract_enum_members",
    "_extract_transitions",
    "build_state_result",
]
