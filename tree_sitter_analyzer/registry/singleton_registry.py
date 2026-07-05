"""Process-wide singleton for the SubscriptionRegistry (RFC-0001).

A single ``SubscriptionRegistry`` instance is shared across the MCP server,
the FileWatcherDaemon callback, and the tsa:// resource handler. This module
provides the accessor so callers don't need to pass the registry explicitly.
"""

from __future__ import annotations

from ..mcp.subscription_registry import SubscriptionRegistry

_registry: SubscriptionRegistry | None = None


def get_subscription_registry() -> SubscriptionRegistry:
    """Return the process-wide ``SubscriptionRegistry``, creating it on first call."""
    global _registry
    if _registry is None:
        _registry = SubscriptionRegistry(min_interval_s=2.0)
    return _registry


def reset_subscription_registry() -> None:
    """Replace the singleton with a fresh instance (for testing only)."""
    global _registry
    _registry = None
