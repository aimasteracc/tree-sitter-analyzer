"""Worker-facing immutable types for frozen index candidates."""

from .indexing_snapshot import IndexFileFingerprint, IndexSnapshotEntry

__all__ = ["IndexFileFingerprint", "IndexSnapshotEntry"]
