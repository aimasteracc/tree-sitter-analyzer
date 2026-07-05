"""TOONSerializer — thin wrapper around the existing ToonFormatter path.

Wraps ``format_as_toon()`` from ``mcp.utils.format_helper``, which is the
same function MCP tools use when ``output_format="toon"`` is requested.
Does NOT change any defaults; MCP tools continue to call format_as_toon
directly via apply_toon_format_to_response.
"""

from __future__ import annotations

from ..mcp.utils.format_helper import format_as_toon


class TOONSerializer:
    """Serialize a dict to TOON format.

    This is a thin wrapper for use in invariant tests.  It calls the same
    ``format_as_toon()`` function used by the MCP tool path, so the
    byte counts measured in tests are representative of real MCP output.
    """

    def serialize(self, data: dict) -> str:
        """Return the TOON-formatted string for *data*.

        Delegates to ``format_as_toon()`` — the same function used by
        ``apply_toon_format_to_response()`` on the live MCP path.
        """
        return format_as_toon(data)

    def byte_size(self, data: dict) -> int:
        """Return the UTF-8 byte count of the serialized output."""
        return len(self.serialize(data).encode("utf-8"))
