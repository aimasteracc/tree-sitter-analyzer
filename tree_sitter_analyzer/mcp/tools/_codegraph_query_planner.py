"""Intent planner for codegraph_query chains."""

from __future__ import annotations

from typing import Any

from ._codegraph_query_dsl import _ChainStep, step_to_dict


def build_query_planner(
    *,
    query: str,
    steps: list[_ChainStep],
    state: Any,
    warnings: list[str],
) -> dict[str, Any]:
    """Explain the chain strategy and the remaining exploration budget."""
    intent = state.intent or first_intent_step(steps) or "custom"
    relationship_hops = max_relationship_depth(steps)
    has_evidence = bool(state.files or state.symbols)
    has_relationships = state.counts()["caller_edges"] + state.counts()["callee_edges"]
    answer_requested = state.answer_requested
    should_stop = bool(answer_requested and has_evidence and not warnings)

    return {
        "version": 1,
        "intent": intent,
        "query": query,
        "strategy": strategy_for(intent),
        "default_chain": default_chain_for(intent),
        "budget": {
            "max_cli_calls": 1 if answer_requested else 2,
            "max_followups": 0 if should_stop else 1,
            "should_stop": should_stop,
        },
        "signals": {
            "answer_requested": answer_requested,
            "raw_reads_allowed": not should_stop,
            "exclude_tests_recommended": not chain_has_step(steps, "exclude_tests"),
            "exclude_tests_applied": chain_has_step(steps, "exclude_tests")
            or prefer_excludes_tests(steps),
            "relationship_hops": relationship_hops,
            "has_relationships": bool(has_relationships),
            "has_code": any(file_has_code(entry) for entry in state.files),
        },
        "execution_steps": state.query_plan,
        "warnings": list(warnings),
        "next_step": next_step_for(should_stop=should_stop, has_evidence=has_evidence),
        "normalized_chain": [step_to_dict(step) for step in steps],
    }


def first_intent_step(steps: list[_ChainStep]) -> str:
    for step in steps:
        if step.name in {"flow", "impact", "ownership"}:
            return step.name
    return ""


def strategy_for(intent: str) -> str:
    if intent == "flow":
        return "Resolve entry-point symbols, fetch snippets, then follow callees."
    if intent == "impact":
        return "Resolve the target symbol, fetch snippets, then collect callers and callees."
    if intent == "ownership":
        return "Resolve named owners first, then fall back to concept file matches."
    return "Build a focused selection, explore source evidence, then add nearby graph edges."


def default_chain_for(intent: str) -> str:
    if intent == "flow":
        return "flow('<request flow>').prefer(exclude_tests=True).callees(depth=1).answer()"
    if intent == "impact":
        return "impact('<symbol>').prefer(exclude_tests=True).answer()"
    if intent == "ownership":
        return "ownership('<concept>').prefer(exclude_tests=True).answer()"
    return "search('<symbol or concept>').explore().related(depth=1).answer()"


def max_relationship_depth(steps: list[_ChainStep]) -> int:
    depth = 0
    for step in steps:
        if step.name in {"callers", "callees", "related", "impact"}:
            value = step.kwargs.get("depth", 1)
            try:
                depth = max(depth, int(value))
            except (TypeError, ValueError):
                depth = max(depth, 1)
    return depth


def chain_has_step(steps: list[_ChainStep], name: str) -> bool:
    return any(step.name == name for step in steps)


def prefer_excludes_tests(steps: list[_ChainStep]) -> bool:
    return any(
        step.name == "prefer" and bool(step.kwargs.get("exclude_tests"))
        for step in steps
    )


def file_has_code(entry: dict[str, Any]) -> bool:
    return any(bool(symbol.get("code")) for symbol in entry.get("symbols", []))


def next_step_for(*, should_stop: bool, has_evidence: bool) -> str:
    if should_stop:
        return "Stop querying and answer from the cited evidence."
    if has_evidence:
        return "Use one targeted follow-up only if a required named detail is missing."
    return "Run one narrower query with a concrete symbol, path, or owner term."


__all__ = ["build_query_planner"]
