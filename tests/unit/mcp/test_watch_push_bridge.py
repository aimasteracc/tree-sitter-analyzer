"""RFC-0001 watch→push bridge: push only on real delta (Codex P2 on #317)."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.subscription_registry import SubscriptionRegistry
from tree_sitter_analyzer.mcp.watch_push_bridge import collect_changed_pairs


def _seed(registry: SubscriptionRegistry, session: str, selector: str, snap: list):
    """Subscribe and prime the stored snapshot so later diffs are meaningful."""
    registry.subscribe(session, selector)
    # First compute_delta stores the baseline snapshot (added == snap).
    registry.compute_delta(session, selector, snap)


def test_unchanged_selector_is_not_pushed() -> None:
    """A sync event that does not move the result pushes nothing."""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    snap = [{"name": "foo", "file": "a.py", "line": 1}]
    _seed(reg, "s1", ".function", snap)

    # Re-evaluate returns the IDENTICAL snapshot — no delta.
    changed = collect_changed_pairs(reg, lambda sid, sel: list(snap))
    assert changed == []


def test_changed_selector_is_pushed() -> None:
    """When the selector result moves, exactly that pair is returned."""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    _seed(reg, "s1", ".function", [{"name": "foo", "file": "a.py", "line": 1}])

    new_snap = [
        {"name": "foo", "file": "a.py", "line": 1},
        {"name": "bar", "file": "b.py", "line": 2},
    ]
    changed = collect_changed_pairs(reg, lambda sid, sel: list(new_snap))
    assert changed == [("s1", ".function")]


def test_only_the_moved_selector_among_many_is_pushed() -> None:
    """An unrelated subscription is not woken when another selector changes."""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    stable = [{"name": "foo", "file": "a.py", "line": 1}]
    moving = [{"name": "baz", "file": "c.py", "line": 3}]
    _seed(reg, "s1", ".stable", stable)
    _seed(reg, "s1", ".moving", moving)

    def evaluate(_sid: str, selector: str) -> list:
        if selector == ".moving":
            return [*moving, {"name": "new", "file": "d.py", "line": 4}]
        return list(stable)

    changed = collect_changed_pairs(reg, evaluate)
    assert changed == [("s1", ".moving")]
