"""Path inventory accounting for frozen diff snapshots."""

from __future__ import annotations

import json
from collections.abc import Collection, Sequence

from .diff_snapshot_capture import FrozenFile
from .git_path_codec import path_from_wire, path_storage, path_to_raw
from .source_oracle import SourceOracleError, normalize_repo_path
from .source_oracle_git import GitEpoch


def path_collection_storage(paths: Collection[str]) -> int:
    """Charge retained raw paths and their wire-safe public representations."""
    return sum(path_storage(path) for path in paths)


def record_storage(files: tuple[FrozenFile, ...]) -> int:
    """Charge the deterministic serialized changed-record metadata."""
    return sum(
        len(
            json.dumps(
                item.record.to_dict(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        for item in files
    )


def epoch_inventory(epoch: GitEpoch, mode: str, limit: int) -> tuple[str, ...]:
    """Derive inventory solely from the exact first-oracle Git epoch."""
    raw_paths = set(epoch.tracked_paths)
    if mode == "diff":
        raw_paths.update(epoch.untracked_paths)
    paths = tuple(
        sorted(
            (
                normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
                for raw in raw_paths
            ),
            key=path_to_raw,
        )
    )
    if path_collection_storage(paths) > limit:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return paths


def normalize_bounded_paths(
    paths: Sequence[str], *, count_limit: int, path_limit: int, storage_limit: int
) -> tuple[str, ...]:
    """Decode, normalize, sort, and capacity-check public path collections."""
    if len(paths) > count_limit:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    if any(not isinstance(path, str) for path in paths):
        raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH")
    normalized = tuple(
        sorted({path_from_wire(path) for path in paths}, key=path_to_raw)
    )
    if any(len(path_to_raw(path)) > path_limit for path in normalized):
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    if path_collection_storage(normalized) > storage_limit:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return normalized
