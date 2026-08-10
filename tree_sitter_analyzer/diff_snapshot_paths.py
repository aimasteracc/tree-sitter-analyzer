"""Path inventory accounting for frozen diff snapshots."""

from __future__ import annotations

import os
from collections.abc import Collection

from .git_path_codec import path_storage
from .source_oracle import SourceOracleError, normalize_repo_path
from .source_oracle_git import GitEpoch


def path_collection_storage(paths: Collection[str]) -> int:
    """Charge retained raw paths and their wire-safe public representations."""
    return sum(path_storage(path) for path in paths)


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
            key=os.fsencode,
        )
    )
    if path_collection_storage(paths) > limit:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return paths
