"""Schema-validation boundary for authoritative snapshot databases."""

from .index_snapshot_schema import validate_snapshot_schema

__all__ = ["validate_snapshot_schema"]
