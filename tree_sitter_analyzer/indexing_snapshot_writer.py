"""Writer-side validation boundary for frozen index candidates."""

from .indexing_snapshot import changed_since_snapshot, validate_index_candidate_snapshot

__all__ = ["changed_since_snapshot", "validate_index_candidate_snapshot"]
