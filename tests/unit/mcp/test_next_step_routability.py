#!/usr/bin/env python3
"""RFC-0028 §3.1 — a ``next_step`` that names a route must name a *resolvable* one.

§3.1 states the invariant, and states it carefully, because the obvious
formulation is false:

    Any ``next_step`` containing a token matching a known tool / facade / action
    name must resolve to a **registered** route.

The obvious formulation — "every ``next_step`` names a route" — fails on correct
behaviour, because real emitted strings are English prose ("Pass roots within the
project boundary."). This gate only constrains tokens that *are* route names.

It harvests the string constants assigned to ``next_step`` across the tool
package and checks every token that collides with the published vocabulary.
Tokens are matched against legacy tool names (``facade_map.LEGACY_TOOL_MAP``) and
registered facade names, so a name that used to resolve and no longer does — or a
name that never did, which is exactly the defect §3.1 records — fails here rather
than in an agent's next call.

**Limit:** this reads literals, so a ``next_step`` assembled entirely from
runtime data is not seen. The harvest is asserted non-trivial and asserted to
match vocabulary tokens, so a broken harvest fails instead of passing quietly.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tree_sitter_analyzer.mcp.facade_map import LEGACY_TOOL_MAP, REMOVED_TOOL_NAMES

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools"

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _next_step_strings() -> list[tuple[str, str]]:
    """Every string constant assigned into a ``next_step``, with its module."""
    harvested: list[tuple[str, str]] = []
    for path in sorted(TOOLS_DIR.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - a broken module fails elsewhere
            raise AssertionError(f"{path.name} does not parse: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            else:
                continue
            if value is None or not any(
                isinstance(target, ast.Name) and target.id == "next_step"
                for target in targets
            ):
                continue
            for inner in ast.walk(value):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    harvested.append((path.name, inner.value))
    return harvested


def _registered_facades() -> dict[str, set[str]]:
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _lookup = create_tool_registry(".")
    return {
        name: set(getattr(facade, "action_map", {}))
        | set(getattr(facade, "bespoke_map", {}))
        for name, facade in tools
    }


def _vocabulary_tokens(harvest: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Map each route-name token found in a ``next_step`` to its modules."""
    vocabulary = set(LEGACY_TOOL_MAP) | set(_registered_facades()) | set(REMOVED_TOOL_NAMES)
    found: dict[str, set[str]] = {}
    for module, text in harvest:
        for token in _TOKEN.findall(text):
            if token in vocabulary:
                found.setdefault(token, set()).add(module)
    return found


def test_no_next_step_names_a_removed_tool() -> None:
    """A ``next_step`` naming a removed capability is a dead route.

    This is the class §3.1 records, and the reason the vocabulary cannot be
    "names that currently resolve": a removed name resolves nowhere by
    construction, so checking only live names cannot see it. ``REMOVED_TOOL_NAMES``
    is what makes "removed" machine-checkable instead of prose.
    """
    tokens = _vocabulary_tokens(_next_step_strings())
    named = {token: sorted(where) for token, where in tokens.items() if token in REMOVED_TOOL_NAMES}
    assert named == {}, (
        "a next_step names a capability a released breaking change removed, so "
        "an agent following it calls something that no longer exists:\n  "
        + "\n  ".join(f"{token} (in {', '.join(where)})" for token, where in sorted(named.items()))
    )


def test_the_harvest_is_not_vacuous() -> None:
    """A harvest that found nothing would make the invariant below meaningless."""
    harvest = _next_step_strings()
    assert len(harvest) > 50, (
        f"only {len(harvest)} next_step string constants harvested; the AST walk "
        "is probably no longer matching how next_step is assigned"
    )
    tokens = _vocabulary_tokens(harvest)
    assert len(tokens) >= 5, (
        f"only {len(tokens)} route-name tokens found across {len(harvest)} "
        "strings; the vocabulary or the tokenizer has drifted and the invariant "
        "below no longer constrains anything"
    )


def test_every_route_token_in_a_next_step_resolves() -> None:
    facades = _registered_facades()
    tokens = _vocabulary_tokens(_next_step_strings())

    unresolved: list[str] = []
    for token in sorted(tokens):
        where = ", ".join(sorted(tokens[token]))
        legacy = LEGACY_TOOL_MAP.get(token)
        if legacy is not None:
            facade, action = legacy
            if facade not in facades or action not in facades[facade]:
                unresolved.append(
                    f"{token} (in {where}): legacy name maps to "
                    f"{facade}.{action}, which is not a registered route"
                )
        elif token not in facades:
            unresolved.append(
                f"{token} (in {where}): matches no legacy name and no "
                "registered facade"
            )

    assert unresolved == [], (
        "RFC-0028 §3.1 next_step routability is red. A next_step that names a "
        "route must name one that resolves; an agent follows these literally:\n  "
        + "\n  ".join(unresolved)
    )


def test_the_prose_case_is_not_constrained() -> None:
    """The invariant must not require every ``next_step`` to be a route.

    Real emitted strings are English ("Pass roots within the project
    boundary."), and a gate that fails them would be wrong rather than strict.
    """
    harvest = _next_step_strings()
    prose = [text for _module, text in harvest if " " in text.strip()]
    assert prose, "no prose next_step found; the corpus changed shape"
    vocabulary = set(LEGACY_TOOL_MAP) | set(_registered_facades()) | set(REMOVED_TOOL_NAMES)
    prose_without_route = [
        text for text in prose if not (set(_TOKEN.findall(text)) & vocabulary)
    ]
    assert prose_without_route, (
        "every harvested next_step now names a route token, so the prose case "
        "this test protects is no longer represented"
    )
