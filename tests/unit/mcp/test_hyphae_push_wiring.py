"""Coverage for RFC-0001 push wiring helpers (session capture + send_update).

These exercise the small, pure-ish branches added when bringing the reactive
push path to life (PR #317): session capture outside a request context, the
session-store round trip, and the no-session early return in _send_update.
"""

from __future__ import annotations

import asyncio

import pytest

from tree_sitter_analyzer.mcp.tools import hyphae_subscribe_tool as hst
from tree_sitter_analyzer.mcp.watch_push_bridge import _send_update


def test_capture_session_obj_returns_none_outside_request_context() -> None:
    """Outside an MCP request, request_ctx is unset → capture returns None,
    never raising (the bridge degrades gracefully)."""
    assert hst._capture_session_obj() is None


def test_session_obj_store_roundtrip() -> None:
    """get_session_obj returns what was captured, and None for unknown ids."""
    sentinel = object()
    hst._SESSION_SESSIONS["sess-x"] = sentinel
    try:
        assert hst.get_session_obj("sess-x") is sentinel
        assert hst.get_session_obj("missing") is None
    finally:
        hst._SESSION_SESSIONS.pop("sess-x", None)


def test_session_loop_store_roundtrip() -> None:
    """get_session_loop mirrors the captured loop; None when absent."""
    loop = asyncio.new_event_loop()
    try:
        hst._SESSION_LOOPS["sess-y"] = loop
        assert hst.get_session_loop("sess-y") is loop
        assert hst.get_session_loop("nope") is None
    finally:
        hst._SESSION_LOOPS.pop("sess-y", None)
        loop.close()


@pytest.mark.asyncio
async def test_send_update_no_session_is_noop() -> None:
    """_send_update returns quietly when no session was captured for the id —
    a dead/unknown session must never raise into the watch loop."""
    # Ensure no session registered for this id.
    hst._SESSION_SESSIONS.pop("ghost", None)
    # Should complete without raising.
    await _send_update("ghost", "tsa://hyphae/.function")


@pytest.mark.asyncio
async def test_send_update_calls_session_when_present() -> None:
    """When a session is captured, _send_update awaits send_resource_updated
    with an AnyUrl wrapping the uri."""
    sent: list[object] = []

    class FakeSession:
        async def send_resource_updated(self, uri: object) -> None:
            sent.append(uri)

    hst._SESSION_SESSIONS["live"] = FakeSession()
    try:
        await _send_update("live", "tsa://hyphae/.function")
    finally:
        hst._SESSION_SESSIONS.pop("live", None)

    assert len(sent) == 1
    # Wrapped as AnyUrl — str round-trips back to the scheme.
    assert str(sent[0]).startswith("tsa://hyphae/")
