"""RFC-0001 criterion 3: ``tsa://hyphae/{selector}`` resource read.

When the MCP server lists or reads this resource, it runs the Hyphae selector
against the current index and returns the result set.  The URI is produced by
``HyphaeSubscribeTool`` so the agent knows which URI to re-read after a push.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

_RESOURCE_SCHEME = "tsa://hyphae/"


def is_hyphae_resource_uri(uri: str) -> bool:
    """True when *uri* matches the ``tsa://hyphae/`` scheme."""
    return uri.startswith(_RESOURCE_SCHEME)


def selector_from_uri(uri: str) -> str:
    """Extract and URL-decode the selector from a ``tsa://hyphae/`` URI."""
    return urllib.parse.unquote(uri[len(_RESOURCE_SCHEME) :])


def uri_from_selector(selector: str) -> str:
    """Build a ``tsa://hyphae/`` URI for *selector*."""
    return _RESOURCE_SCHEME + urllib.parse.quote(selector, safe="")


async def read_hyphae_resource(
    uri: str,
    project_root: str | None,
) -> dict[str, Any]:
    """Execute the Hyphae selector encoded in *uri* and return the result.

    This is called by the MCP server's ``read_resource`` handler when the URI
    matches ``tsa://hyphae/``.  Returns a dict with ``items`` (the matching
    symbol list) and ``selector`` for agent transparency.
    """
    selector = selector_from_uri(uri)
    if not project_root:
        return {"selector": selector, "items": [], "error": "project_root not set"}

    try:
        from ...ast_cache import ASTCache
        from ...hyphae import Evaluator, parse

        selector_ast = parse(selector)
        cache = ASTCache(project_root)
        evaluator = Evaluator(cache)
        items = evaluator.eval(selector_ast)
        return {
            "selector": selector,
            "items": [_item_to_dict(item) for item in items],
            "count": len(items),
        }
    except Exception as exc:
        return {"selector": selector, "items": [], "error": str(exc)}


def _item_to_dict(item: Any) -> dict[str, Any]:
    """Convert a Hyphae result item to a serialisable dict."""
    if isinstance(item, dict):
        return item
    try:
        return {
            "name": getattr(item, "name", str(item)),
            "file": getattr(item, "file", ""),
            "line": getattr(item, "line", 0),
            "kind": getattr(item, "kind", ""),
        }
    except Exception:
        return {"value": str(item)}
