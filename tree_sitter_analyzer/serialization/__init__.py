"""Serialization subpackage — thin wrappers for cost invariant tests.

Phase 4: Serialization Unification.

Exports:
    Serializer   — Protocol (interface.py)
    JSONSerializer — wraps json.dumps (json_serializer.py)
    TOONSerializer — wraps format_as_toon (toon_serializer.py)

Design contract: these classes wrap existing serialization paths.
They do NOT change what serializer is selected by default in any
MCP tool or CLI command.
"""

from .interface import Serializer
from .json_serializer import JSONSerializer
from .toon_serializer import TOONSerializer

__all__ = ["Serializer", "JSONSerializer", "TOONSerializer"]
