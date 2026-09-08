"""TOONSerializer — thin wrapper around the ToonFormatter path.

Calls :class:`~tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter`
directly, which is the formatter the MCP path also reaches through
``format_as_toon()``. Going to ``formatters/`` rather than to
``mcp/utils/format_helper`` keeps this low-level package from importing the
MCP layer: ``serialization`` sits below ``mcp``, and the previous import
inverted that. The JSON fallback mirrors ``format_as_toon`` so byte counts
measured here stay representative of real MCP output.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _format_as_toon(data: dict[str, Any]) -> str:
    """Format ``data`` as TOON, falling back to JSON on any failure.

    Mirrors ``mcp.utils.format_helper.format_as_toon`` including its
    fallback, so the two paths cannot drift in what they produce.
    """
    try:
        from ..formatters.toon_formatter import ToonFormatter

        return ToonFormatter().format(data)
    except ImportError as exc:
        logger.warning("ToonFormatter not available, falling back to JSON: %s", exc)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("TOON formatting failed, falling back to JSON: %s", exc)
        return json.dumps(data, indent=2, ensure_ascii=False)


class TOONSerializer:
    """Serialize a dict to TOON format.

    A thin wrapper for use in invariant tests. It drives the same
    ``ToonFormatter`` the live MCP path uses, so the byte counts measured
    in tests are representative of real MCP output.
    """

    def serialize(self, data: dict) -> str:
        """Return the TOON-formatted string for *data*."""
        return _format_as_toon(data)

    def byte_size(self, data: dict) -> int:
        """Return the UTF-8 byte count of the serialized output."""
        return len(self.serialize(data).encode("utf-8"))
