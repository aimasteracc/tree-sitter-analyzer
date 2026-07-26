"""Transition extraction for Enum-backed Python state machines."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from ._uml_state_nodes import node_text, walk_nodes


class TransitionLike(Protocol):
    """Structural surface required from a state transition."""

    source: str
    target: str


TransitionT = TypeVar("TransitionT", bound=TransitionLike)
TransitionFactory = Callable[..., TransitionT]


@dataclass
class _TransitionScanner(Generic[TransitionT]):
    """Scan one Enum class for match/case state transitions."""

    class_name: str
    known_members: set[str]
    transition_factory: TransitionFactory[TransitionT]

    def scan(self, root: Any) -> list[TransitionT]:
        """Return unique, source-ordered transitions below ``root``."""
        transitions: list[TransitionT] = []
        seen: set[tuple[str, str]] = set()
        for transition in self._candidate_transitions(root):
            if transition in seen:
                continue
            seen.add(transition)
            source, target = transition
            transitions.append(self.transition_factory(source=source, target=target))
        return transitions

    def _candidate_transitions(self, root: Any) -> Iterator[tuple[str, str]]:
        matches = (node for node in walk_nodes(root) if node.type == "match_statement")
        for match_statement in matches:
            candidates = (
                self._transition_from_case(case_clause)
                for case_clause in self._case_clauses(match_statement)
            )
            yield from (candidate for candidate in candidates if candidate is not None)

    def _enum_ref(self, node: Any) -> str | None:
        """Return a known member referenced as ``ClassName.member``."""
        text = node_text(node, 80)
        prefix = self.class_name + "."
        if not text.startswith(prefix):
            return None
        member = text[len(prefix) :]
        return member if member in self.known_members else None

    def _first_enum_ref(self, nodes: list[Any]) -> str | None:
        for node in nodes:
            member = self._enum_ref(node)
            if member is not None:
                return member
        return None

    def _direct_target(self, node: Any) -> str | None:
        """Return a transition target directly owned by one syntax node."""
        children = list(node.children)
        if node.type == "return_statement":
            return self._first_enum_ref(children)
        if node.type != "assignment":
            return None
        for child in reversed(children):
            if child.type == "=" or node_text(child, 2) == "=":
                continue
            return self._enum_ref(child)
        return None

    def _target_below(self, node: Any) -> str | None:
        """Find the first return or assignment target in source order."""
        direct = self._direct_target(node)
        if direct is not None:
            return direct
        for child in node.children:
            target = self._target_below(child)
            if target is not None:
                return target
        return None

    def _case_source(self, case_clause: Any) -> str | None:
        """Extract the Enum member named by a case pattern."""
        for child in case_clause.children:
            source = self._source_from_child(child)
            if source is not None:
                return source
        return None

    def _source_from_child(self, child: Any) -> str | None:
        if child.type == "case_pattern":
            source = self._first_enum_ref(list(child.children))
            return source if source is not None else self._enum_ref(child)
        if child.type in ("dotted_name", "attribute"):
            return self._enum_ref(child)
        return None

    def _transition_from_case(self, case_clause: Any) -> tuple[str, str] | None:
        source = self._case_source(case_clause)
        blocks = (child for child in case_clause.children if child.type == "block")
        target = next(
            (
                candidate
                for candidate in (self._target_below(block) for block in blocks)
                if candidate is not None
            ),
            None,
        )
        if source is None or target is None or source == target:
            return None
        return source, target

    @staticmethod
    def _case_clauses(match_statement: Any) -> list[Any]:
        """Return direct or block-owned case clauses in grammar order."""
        clauses: list[Any] = []
        for child in match_statement.children:
            clauses.extend(_TransitionScanner._clauses_from_child(child))
        return clauses

    @staticmethod
    def _clauses_from_child(child: Any) -> list[Any]:
        if child.type == "case_clause":
            return [child]
        if child.type == "block":
            return [node for node in child.children if node.type == "case_clause"]
        return []


def extract_transitions(
    root: Any,
    class_name: str,
    known_members: set[str],
    transition_factory: TransitionFactory[TransitionT],
) -> list[TransitionT]:
    """Extract transitions for one Enum class from every match statement."""
    return _TransitionScanner(
        class_name=class_name,
        known_members=known_members,
        transition_factory=transition_factory,
    ).scan(root)
