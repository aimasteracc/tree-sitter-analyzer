"""Serializer Protocol for MCP tool responses.

Serialization interface for the canonical JSON response path. The Protocol
keeps serialization and byte-size measurement explicit for contract tests.
"""

from __future__ import annotations

from typing import Protocol


class Serializer(Protocol):
    """Minimal serialization protocol for MCP tool response dicts.

    Implementations must preserve the canonical JSON response contract.
    """

    def serialize(self, data: dict) -> str:
        """Serialize a dict to a string in this format."""
        ...

    def byte_size(self, data: dict) -> int:
        """Return the UTF-8 byte length of the serialized output."""
        ...
