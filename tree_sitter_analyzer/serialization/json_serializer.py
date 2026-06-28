"""JSONSerializer — thin wrapper around json.dumps.

Wraps the existing JSON serialization path used by the CLI.
Does NOT change any defaults; CLI continues to use json.dumps directly.
"""

from __future__ import annotations

import json


class JSONSerializer:
    """Serialize a dict to compact JSON (no indent, ensure_ascii=False).

    This is a thin wrapper for use in invariant tests.  It does NOT
    change how the CLI or MCP tools produce their output — those paths
    continue to call json.dumps directly.
    """

    def serialize(self, data: dict) -> str:
        """Return ``json.dumps(data)`` without indentation.

        Compact (no indent) to match the minimal representation baseline
        for the size invariant: ``toon_bytes <= json_bytes``.  The CLI
        uses ``indent=2`` in some paths; compact JSON is a *lower* bound
        on JSON size, so using it here is conservative (makes the
        invariant harder to satisfy, not easier).
        """
        return json.dumps(data, ensure_ascii=False)

    def byte_size(self, data: dict) -> int:
        """Return the UTF-8 byte count of the serialized output."""
        return len(self.serialize(data).encode("utf-8"))
