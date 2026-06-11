#!/usr/bin/env python3
"""State diagram (stateDiagram-v2) scanner for P2-B of RFC-0015.

Builds a static approximation of enum/match-driven state machines using
tree-sitter AST parsing. One public entry point:
  build_state_result(file_path, class_name, max_nodes) -> StateResult

Design decisions:
- Python only for this phase.
- Requires ONE disk read + ONE tree-sitter parse per call (rule-11 invariant).
- Empty/no-transition result is returned as StateResult with error="" and
  zero transitions — the NOT_FOUND verdict is applied by UMLExporter.state_diagram,
  not here, so tests can inspect the raw scanner output separately.
- Enum members are identified by walking class body children for assignments
  with an UPPERCASE name, which matches typical Enum member patterns.
- Transitions are identified by walking match_statement nodes: a case whose
  pattern references <ClassName>.<MemberName> and whose body contains a
  return_statement of <ClassName>.<OtherMemberName> becomes a transition.
  Also detected: assignment statements of the form ``<anything> = <ClassName>.<MemberName>``
  inside match arms (OOP FSM style, e.g. ``self.state = Door.OPEN``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Parser helper (one parse per call — rule-11 invariant)
# ---------------------------------------------------------------------------


def _parse_file_for_state(
    file_path: str, language: str = "python"
) -> tuple[Any, bytes] | None:
    """Parse *file_path* with tree-sitter and return (tree_root, source_bytes).

    Returns None when the file does not exist, the language is unsupported,
    or the parser fails. ONE parse per call — callers MUST NOT call this in
    a loop for the same file (rule-11 invariant).
    """
    from .core.parser import Parser

    parser = Parser()
    result = parser.parse_file(file_path, language)
    if not result.success or result.tree is None:
        return None
    raw_source = result.source_code
    source_bytes: bytes = (
        raw_source.encode("utf-8", errors="replace")
        if isinstance(raw_source, str)
        else (raw_source or b"")
    )
    return result.tree.root_node, source_bytes


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _node_text(node: Any, max_len: int = 60) -> str:
    """Decode a tree-sitter node's text, capped at max_len chars."""
    try:
        raw = node.text
        if raw is None:
            return ""
        text: str = raw.decode("utf-8", errors="replace").strip()
        return text[:max_len] if len(text) > max_len else text
    except Exception:
        return ""


def _find_enum_classes(
    root: Any, class_name_filter: str | None
) -> list[dict[str, Any]]:
    """Walk the root node to find class definitions that inherit from Enum.

    Returns a list of dicts: {"name": str, "node": ts_node}.
    Looks for class_definition nodes whose argument_list or base_class
    contains "Enum".
    """
    results: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if node.type == "class_definition":
            name = ""
            has_enum_base = False
            for child in node.children:
                if child.type == "identifier":
                    name = _node_text(child)
                elif child.type == "argument_list":
                    # Python class bases are in argument_list
                    for base in child.children:
                        base_text = _node_text(base)
                        if base_text in (
                            "Enum",
                            "IntEnum",
                            "StrEnum",
                            "Flag",
                            "IntFlag",
                        ):
                            has_enum_base = True
            if name and has_enum_base:
                if class_name_filter is None or name == class_name_filter:
                    results.append({"name": name, "node": node})
        for child in node.children:
            _walk(child)

    _walk(root)
    return results


def _extract_enum_members(class_node: Any) -> list[str]:
    """Extract Enum member names from a class_definition body.

    Returns member names in the order they appear (for stable ordering).
    All assignment targets that are not underscore-prefixed are treated as
    members (avoiding __doc__, __module__, _ignore_, etc.). This includes
    UPPERCASE_NAMES, MixedCase, and lowercase names alike.
    """
    members: list[str] = []
    for child in class_node.children:
        if child.type == "block":
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    for sub in stmt.children:
                        if sub.type == "assignment":
                            lhs_children = list(sub.children)
                            if lhs_children:
                                lhs = lhs_children[0]
                                if lhs.type == "identifier":
                                    name = _node_text(lhs)
                                    if name and not name.startswith("_"):
                                        members.append(name)
    return members


def _extract_transitions(
    root: Any, class_name: str, known_members: set[str]
) -> list[StateTransition]:
    """Walk root for match_statement nodes and extract FSM transitions.

    Heuristic: a match_statement with a subject, where each case_clause
    whose pattern references <class_name>.<MemberA> and whose body
    contains a transition target becomes a transition A → B.

    Two transition-target patterns are detected:
    1. ``return <class_name>.<MemberB>``  — pure functional FSM style.
    2. ``<target> = <class_name>.<MemberB>``  — OOP style (e.g.
       ``self.state = Door.OPEN``), detected by scanning assignment
       statements whose right-hand side is an enum member reference.
    """
    transitions: list[StateTransition] = []
    seen: set[tuple[str, str]] = set()

    def _find_match_statements(node: Any) -> list[Any]:
        results: list[Any] = []
        if node.type == "match_statement":
            results.append(node)
        for child in node.children:
            results.extend(_find_match_statements(child))
        return results

    def _parse_enum_ref(node: Any) -> str | None:
        """Return the member name if node is <class_name>.<member>."""
        text = _node_text(node, 80)
        prefix = class_name + "."
        if text.startswith(prefix):
            member = text[len(prefix) :]
            if member in known_members:
                return member
        return None

    def _find_return_enum_ref(node: Any) -> str | None:
        """Recursively search for a return_statement or assignment whose RHS is
        <class_name>.<member>.

        Patterns detected:
        - ``return <class_name>.<member>``  (return_statement)
        - ``<anything> = <class_name>.<member>``  (assignment, e.g. self.state = Door.OPEN)
        """
        if node.type == "return_statement":
            for child in node.children:
                ref = _parse_enum_ref(child)
                if ref is not None:
                    return ref
        elif node.type == "assignment":
            # assignment children: [lhs, "=", rhs]
            # We look for the RHS (last child that is not "=")
            children = list(node.children)
            for child in reversed(children):
                if child.type != "=" and _node_text(child, 2) != "=":
                    ref = _parse_enum_ref(child)
                    if ref is not None:
                        return ref
                    break
        for child in node.children:
            result = _find_return_enum_ref(child)
            if result is not None:
                return result
        return None

    def _find_case_pattern_member(node: Any) -> str | None:
        """Extract the enum member from a case pattern like TrafficLight.RED."""
        # case_clause children include "case", the pattern, and ":"
        for child in node.children:
            if child.type in (
                "dotted_name",
                "attribute",
                "identifier",
                "case_pattern",
            ):
                ref = _parse_enum_ref(child)
                if ref is not None:
                    return ref
                # attribute node: value.attribute
                val = getattr(child, "children", [])
                for sub in val:
                    ref2 = _parse_enum_ref(sub)
                    if ref2 is not None:
                        return ref2
        return None

    def _iter_case_clauses(match_stmt: Any) -> list[Any]:
        """Return all case_clause nodes from a match_statement.

        Tree-sitter places case_clauses inside a 'block' child of
        match_statement (not as direct children).
        """
        clauses: list[Any] = []
        for child in match_stmt.children:
            if child.type == "block":
                for sub in child.children:
                    if sub.type == "case_clause":
                        clauses.append(sub)
            elif child.type == "case_clause":
                # Direct child fallback (some grammar versions)
                clauses.append(child)
        return clauses

    match_stmts = _find_match_statements(root)
    for match_stmt in match_stmts:
        for case_clause in _iter_case_clauses(match_stmt):
            source_member = None
            target_member = None

            for cc in case_clause.children:
                if cc.type == "case_pattern":
                    # case_pattern > dotted_name: "ClassName.MEMBER"
                    for sub in cc.children:
                        m = _parse_enum_ref(sub)
                        if m is not None:
                            source_member = m
                            break
                    if source_member is None:
                        # fallback: try the case_pattern node text itself
                        m = _parse_enum_ref(cc)
                        if m is not None:
                            source_member = m
                elif cc.type in ("dotted_name", "attribute"):
                    m = _parse_enum_ref(cc)
                    if m is not None:
                        source_member = m
                elif cc.type == "block":
                    target_member = _find_return_enum_ref(cc)

            if source_member and target_member and source_member != target_member:
                key = (source_member, target_member)
                if key not in seen:
                    seen.add(key)
                    transitions.append(
                        StateTransition(source=source_member, target=target_member)
                    )

    return transitions


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_state_result(
    file_path: str,
    class_name: str | None,
    max_nodes: int = 50,
    language: str = "python",
) -> StateResult:
    """Parse *file_path* and extract FSM states and transitions.

    Cost: ONE disk read + ONE tree-sitter parse (rule-11 invariant).

    Returns StateResult with error="" on success (even if transitions is empty —
    the NOT_FOUND verdict for empty transitions is applied at the UMLExporter
    level, not here).

    Errors:
      error="NOT_FOUND:file_missing"  — file does not exist
      error="NOT_FOUND:no_enum_class" — no Enum subclass found in file
      error="NOT_FOUND:class_missing" — class_name given but not found
      error="PARSE_FAILED"            — tree-sitter parse failure
    """
    if not Path(file_path).exists():
        return StateResult(error="NOT_FOUND:file_missing")

    parse_result = _parse_file_for_state(file_path, language)
    if parse_result is None:
        return StateResult(error="PARSE_FAILED")

    root, _source = parse_result

    enum_classes = _find_enum_classes(root, class_name)

    if not enum_classes:
        if class_name is not None:
            # class_name was provided but not found as an Enum subclass
            return StateResult(error="NOT_FOUND:class_missing")
        return StateResult(error="NOT_FOUND:no_enum_class")

    # Collect members from all matched Enum classes (usually 1 after filter)
    all_members: list[str] = []
    for ec in enum_classes:
        members = _extract_enum_members(ec["node"])
        all_members.extend(members)

    # Deduplicate while preserving order
    seen_members: set[str] = set()
    unique_members: list[str] = []
    for m in all_members:
        if m not in seen_members:
            seen_members.add(m)
            unique_members.append(m)

    truncated = False
    if len(unique_members) > max_nodes:
        unique_members = unique_members[:max_nodes]
        truncated = True

    # Sort for deterministic output
    states = sorted(unique_members)

    # Extract transitions using all enum member names from the file as context
    known_members = set(unique_members)
    # Use the first class name found (or the filtered class_name) as the prefix
    primary_class = class_name if class_name else enum_classes[0]["name"]
    transitions = _extract_transitions(root, primary_class, known_members)

    return StateResult(
        states=states,
        transitions=transitions,
        truncated=truncated,
    )
