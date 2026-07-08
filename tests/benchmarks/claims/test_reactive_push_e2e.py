"""Claim invariant: Reactive push (RFC-0001) as a differentiator.

README claim (Key Features section):
    "Reactive push / subscription (RFC-0001, implemented). search action=subscribe
    registers a Hyphae selector and returns a tsa://hyphae/{selector} MCP resource URI.
    When the watched code changes, the server emits a resource-updated notification.
    CodeGraph has no push or subscription channel."

This invariant tests the observable contract of reactive push:
    1. subscribe returns sub_id + resource_uri (tsa://hyphae/ scheme).
    2. resource_uri encodes the selector.
    3. unsubscribe removes the subscription from the registry.
    4. SubscriptionRegistry detects deltas between snapshots (the push trigger).
    5. A second subscribe for the same selector is idempotent (no duplicate).

Full E2E (file-change → server push) requires a running MCP stdio server and is
tested in the @pytest.mark.e2e suite. This test covers the behavioral contract
of the subscribe/unsubscribe surface and the delta engine without a running server.
"""

from __future__ import annotations

import asyncio
import urllib.parse

import pytest

pytestmark = [pytest.mark.benchmark, pytest.mark.claims_benchmark]


# ─── Subscribe response contract ─────────────────────────────────────────────


def test_subscribe_returns_sub_id_and_resource_uri(tmp_path):
    """subscribe must return sub_id and resource_uri (tsa://hyphae/ scheme).

    README: 'returns a tsa://hyphae/{selector} MCP resource URI'
    """
    from tree_sitter_analyzer.mcp.tools.hyphae_subscribe_tool import HyphaeSubscribeTool
    from tree_sitter_analyzer.registry.singleton_registry import (
        reset_subscription_registry,
    )

    reset_subscription_registry()
    tool = HyphaeSubscribeTool(str(tmp_path))
    result = asyncio.run(
        tool.execute({"selector": "functions()", "output_format": "json"})
    )

    assert result.get("success") is not False, f"subscribe failed: {result}"
    assert "sub_id" in result, (
        f"subscribe response missing 'sub_id'. Keys: {list(result.keys())}. "
        f"README claims subscribe returns sub_id."
    )
    assert "resource_uri" in result, (
        f"subscribe response missing 'resource_uri'. Keys: {list(result.keys())}. "
        f"README claims subscribe returns a tsa://hyphae/ URI."
    )


def test_subscribe_resource_uri_uses_tsa_hyphae_scheme(tmp_path):
    """resource_uri must use the tsa://hyphae/ scheme and encode the selector.

    README: 'tsa://hyphae/{selector} MCP resource URI'
    """
    from tree_sitter_analyzer.mcp.tools.hyphae_subscribe_tool import HyphaeSubscribeTool
    from tree_sitter_analyzer.registry.singleton_registry import (
        reset_subscription_registry,
    )

    reset_subscription_registry()
    selector = "classes(language='python')"
    tool = HyphaeSubscribeTool(str(tmp_path))
    result = asyncio.run(tool.execute({"selector": selector, "output_format": "json"}))

    uri = result.get("resource_uri", "")
    assert uri.startswith("tsa://hyphae/"), (
        f"resource_uri '{uri}' does not start with 'tsa://hyphae/'. "
        f"README specifies the tsa://hyphae/ scheme."
    )
    decoded = urllib.parse.unquote(uri[len("tsa://hyphae/") :])
    assert decoded == selector, (
        f"Decoded URI '{decoded}' does not match selector '{selector}'. "
        f"The URI must encode the selector."
    )


def test_unsubscribe_removes_subscription(tmp_path):
    """unsubscribe must remove the subscription from the registry.

    README: 'search action=unsubscribe cancels it.'
    """
    from tree_sitter_analyzer.mcp.tools.hyphae_subscribe_tool import (
        HyphaeSubscribeTool,
        HyphaeUnsubscribeTool,
    )
    from tree_sitter_analyzer.registry.singleton_registry import (
        get_subscription_registry,
        reset_subscription_registry,
    )

    reset_subscription_registry()
    selector = "functions()"
    sub_tool = HyphaeSubscribeTool(str(tmp_path))
    sub_result = asyncio.run(
        sub_tool.execute({"selector": selector, "output_format": "json"})
    )
    sub_id = sub_result["sub_id"]

    reg = get_subscription_registry()
    assert selector in reg.subscriptions_for(sub_id), (
        "Subscription not registered after subscribe"
    )

    unsub_tool = HyphaeUnsubscribeTool(str(tmp_path))
    asyncio.run(
        unsub_tool.execute(
            {"sub_id": sub_id, "selector": selector, "output_format": "json"}
        )
    )

    assert selector not in reg.subscriptions_for(sub_id), (
        "Subscription still active after unsubscribe. "
        "README claims 'unsubscribe cancels it'."
    )


# ─── SubscriptionRegistry delta engine (the push trigger) ────────────────────


def test_subscription_registry_detects_added_items():
    """Registry must detect when new items appear in a snapshot.

    This is the delta engine that triggers resource-updated notifications.
    """
    from tree_sitter_analyzer.mcp.subscription_registry import SubscriptionRegistry

    reg = SubscriptionRegistry(min_interval_s=0)  # no throttle in tests
    reg.subscribe("session-1", "functions()")
    reg.compute_delta("session-1", "functions()", ["f1", "f2"])  # set initial snapshot

    added, removed = reg.compute_delta("session-1", "functions()", ["f1", "f2", "f3"])
    assert "f3" in added, f"New item 'f3' not detected as added: added={added}"
    assert removed == [], f"No items should be removed: removed={removed}"


def test_subscription_registry_detects_removed_items():
    """Registry must detect when items disappear from a snapshot."""
    from tree_sitter_analyzer.mcp.subscription_registry import SubscriptionRegistry

    reg = SubscriptionRegistry(min_interval_s=0)
    reg.subscribe("session-2", "classes()")
    reg.compute_delta("session-2", "classes()", ["ClassA", "ClassB"])

    added, removed = reg.compute_delta("session-2", "classes()", ["ClassA"])
    assert "ClassB" in removed, f"Removed item 'ClassB' not detected: removed={removed}"
    assert added == [], f"No items should be added: added={added}"


def test_subscription_registry_no_delta_when_unchanged():
    """Registry must not fire delta when snapshot is unchanged (prevents noise)."""
    from tree_sitter_analyzer.mcp.subscription_registry import SubscriptionRegistry

    reg = SubscriptionRegistry(min_interval_s=0)
    reg.subscribe("session-3", "imports()")
    reg.compute_delta("session-3", "imports()", ["os", "sys"])

    added, removed = reg.compute_delta("session-3", "imports()", ["os", "sys"])
    assert added == [], f"Spurious added items: {added}"
    assert removed == [], f"Spurious removed items: {removed}"


def test_subscribe_is_idempotent(tmp_path):
    """Subscribing twice to the same selector must not create duplicate entries."""
    from tree_sitter_analyzer.mcp.tools.hyphae_subscribe_tool import HyphaeSubscribeTool
    from tree_sitter_analyzer.registry.singleton_registry import (
        get_subscription_registry,
        reset_subscription_registry,
    )

    reset_subscription_registry()
    selector = "functions()"
    tool = HyphaeSubscribeTool(str(tmp_path))
    r1 = asyncio.run(tool.execute({"selector": selector, "output_format": "json"}))
    asyncio.run(tool.execute({"selector": selector, "output_format": "json"}))

    reg = get_subscription_registry()
    subs = reg.subscriptions_for(r1["sub_id"])
    assert subs.count(selector) == 1, (
        f"Duplicate subscription detected: {subs}. Subscribe must be idempotent."
    )
