"""Cost must be readable before the call, on the surface the client sees.

An MCP client reads a facade's ``description`` and never its inners'. The inner
tools are not separately registered, so prose that lives only on an inner tool
is unreachable: the budget table for ``health action=project`` sat on
``check_project_health`` while the route measured 202 s on a 268-package
monorepo and callers failed at a default 60 s timeout.

These tests derive the expectation from :data:`EXPENSIVE_ROUTES`, so a route
added to that registry is covered here without editing this file.
"""

from __future__ import annotations

from tree_sitter_analyzer.cache.query_cost import EXPENSIVE_ROUTES
from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

_FACADES = dict(create_tool_registry(".")[0])


def _expensive_actions_for(facade: str) -> dict[str, object]:
    return {
        action: route
        for (tool, action), route in EXPENSIVE_ROUTES.items()
        if tool == facade
    }


def test_the_registry_is_not_empty() -> None:
    """The walk below is vacuous if the cost registry declares nothing."""
    assert len(EXPENSIVE_ROUTES) == 3, (
        f"expected 3 declared expensive routes, found {len(EXPENSIVE_ROUTES)}; "
        "update this constant if the route set legitimately changed, otherwise "
        "the cost-surface checks below constrain nothing"
    )


def test_every_expensive_action_is_named_on_the_always_sent_surface() -> None:
    """The client reads this description before choosing an action."""
    missing: list[str] = []
    for (facade, action), route in sorted(EXPENSIVE_ROUTES.items()):
        tool = _FACADES.get(facade)
        if tool is None:
            missing.append(f"{facade}: facade is not registered")
            continue
        description = tool.get_tool_definition()["description"]
        if f"action={action}" not in description:
            missing.append(f"{facade} action={action}: not named in the description")
        if "slow" not in description:
            missing.append(
                f"{facade} action={action}: the description says nothing slow"
            )
        if route.cheaper_alternative and route.cheaper_alternative not in description:
            missing.append(
                f"{facade} action={action}: cheaper route "
                f"{route.cheaper_alternative!r} is not named"
            )
    assert missing == [], (
        "a caller cannot discover these costs before the call, which is the only "
        "moment the warning is useful:\n  " + "\n  ".join(missing)
    )


def test_facades_without_expensive_routes_gain_nothing() -> None:
    """The note is derived, so a cheap facade must stay unchanged."""
    offenders = [
        name
        for name, tool in sorted(_FACADES.items())
        if not _expensive_actions_for(name)
        and "Cost:" in tool.get_tool_definition()["description"]
    ]
    assert offenders == [], (
        f"these facades declare no expensive route but carry a cost note: {offenders}"
    )


def test_action_help_documents_every_expensive_action() -> None:
    """Help must stay the deeper surface for a route the description flags."""
    undocumented = [
        f"{facade} action={action}"
        for facade, action in sorted(EXPENSIVE_ROUTES)
        if f"action={action}" not in _FACADES[facade].full_description()
    ]
    assert undocumented == [], (
        "the always-sent description flags these routes, but action=help says "
        "nothing further about them:\n  " + "\n  ".join(undocumented)
    )


def test_help_carries_the_prose_of_an_inner_that_owns_the_route() -> None:
    """Where an inner tool owns a route, its prose must be reachable.

    Bespoke routes have no inner tool — ``nav action=callers`` is a closure —
    and are documented by the facade's own prose, which the check above covers.
    An ``action_map`` route does have one, and the facade replaces it in the
    tool definition: the inner is not separately registered, so its prose was
    reachable from nowhere. The budget table for ``health action=project`` sat
    in exactly that position.
    """
    unreachable: list[str] = []
    for facade, action in sorted(EXPENSIVE_ROUTES):
        tool = _FACADES[facade]
        inner = tool.action_map.get(action)
        if inner is None:
            continue
        prose = inner.get_tool_definition()["description"].strip()
        if prose and prose not in tool.full_description():
            unreachable.append(f"{facade} action={action}: owner prose is unreachable")
    assert unreachable == [], "\n  ".join(["help drops:"] + unreachable)


def test_every_facade_description_stays_within_the_wave_e_budget() -> None:
    """The cost note must not undo the tool-definition diet."""
    over = [
        (name, len(tool.get_tool_definition()["description"]))
        for name, tool in sorted(_FACADES.items())
        if len(tool.get_tool_definition()["description"]) >= 400
    ]
    assert over == [], f"descriptions over the 400-char budget: {over}"
