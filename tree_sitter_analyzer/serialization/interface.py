"""Serializer Protocol for MCP tool responses.

Phase 4: Serialization Unification — thin wrapper around existing
JSON and TOON code paths. The Protocol defines only what the
invariant tests need: serialize() → str and byte_size() → int.
"""

from __future__ import annotations

from typing import Protocol


class Serializer(Protocol):
    """Minimal serialization protocol for MCP tool response dicts.

    Implementations must be thin wrappers — they must NOT change what
    serializer is selected by default in MCP tools or CLI tools.
    """

    def serialize(self, data: dict) -> str:
        """Serialize a dict to a string in this format."""
        ...

    def byte_size(self, data: dict) -> int:
        """Return the UTF-8 byte length of the serialized output."""
        ...
