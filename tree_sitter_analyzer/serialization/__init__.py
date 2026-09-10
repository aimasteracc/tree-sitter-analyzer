"""Serialization subpackage — thin wrappers for cost invariant tests."""

from .interface import Serializer
from .json_serializer import JSONSerializer

__all__ = ["Serializer", "JSONSerializer"]
