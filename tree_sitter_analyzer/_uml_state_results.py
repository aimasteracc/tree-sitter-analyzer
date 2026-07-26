"""State selection and deterministic result shaping."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar


class TransitionLike(Protocol):
    """Structural transition surface used for cross-Enum deduplication."""

    source: str
    target: str


TransitionT = TypeVar("TransitionT", bound=TransitionLike)
TransitionExtractor = Callable[[Any, str, set[str]], list[TransitionT]]
MemberExtractor = Callable[[Any], list[str]]
EnumScan = tuple[str, list[str], list[TransitionT]]


def _scan_enums(
    root: Any,
    enum_classes: list[dict[str, Any]],
    member_extractor: MemberExtractor,
    transition_extractor: TransitionExtractor[TransitionT],
) -> list[EnumScan[TransitionT]]:
    """Extract members and transitions independently for every Enum."""
    scans: list[EnumScan[TransitionT]] = []
    for enum_class in enum_classes:
        name = str(enum_class["name"])
        members = member_extractor(enum_class["node"])
        transitions = transition_extractor(root, name, set(members))
        scans.append((name, members, transitions))
    return scans


def _selected_scans(
    scans: list[EnumScan[TransitionT]], class_name: str | None
) -> list[EnumScan[TransitionT]]:
    """Choose the requested Enum or every transition-bearing Enum."""
    if class_name is not None:
        return scans[:1]
    transition_bearing = [scan for scan in scans if scan[2]]
    return transition_bearing or scans


def _dedupe_transitions(scans: list[EnumScan[TransitionT]]) -> list[TransitionT]:
    """Deduplicate transitions across selected Enums in discovery order."""
    transitions: list[TransitionT] = []
    seen: set[tuple[str, str]] = set()
    for _, _, scan_transitions in scans:
        for transition in scan_transitions:
            key = (transition.source, transition.target)
            if key in seen:
                continue
            seen.add(key)
            transitions.append(transition)
    return transitions


def collect_state_data(
    root: Any,
    enum_classes: list[dict[str, Any]],
    class_name: str | None,
    member_extractor: MemberExtractor,
    transition_extractor: TransitionExtractor[TransitionT],
) -> tuple[list[str], list[TransitionT]]:
    """Return selected member names and deduplicated transitions."""
    classes_to_scan = enum_classes[:1] if class_name is not None else enum_classes
    scans = _scan_enums(
        root,
        classes_to_scan,
        member_extractor,
        transition_extractor,
    )
    selected = _selected_scans(scans, class_name)
    members = [member for _, names, _ in selected for member in names]
    return members, _dedupe_transitions(selected)


def finalize_states(members: list[str], max_nodes: int) -> tuple[list[str], bool]:
    """Deduplicate, cap, and sort states with the historical ordering rules."""
    unique_members = list(dict.fromkeys(members))
    truncated = len(unique_members) > max_nodes
    if truncated:
        unique_members = unique_members[:max_nodes]
    return sorted(unique_members), truncated
