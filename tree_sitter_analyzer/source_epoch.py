"""Bounded Git attribute and configuration identities for frozen captures."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .frozen_git_index import frozen_index_output
from .frozen_git_settings import config_fingerprint, parse_effective_config
from .source_oracle import SourceOracleError

if TYPE_CHECKING:
    from .frozen_git_settings import FrozenGitSettings

_MAX_SETTINGS_BYTES = 16 * 1024 * 1024
_MAX_SETTINGS_PATH_BYTES = 16 * 1024 * 1024
_EMPTY_TREE_SHA1 = (
    b"4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # pragma: allowlist secret
)
_EMPTY_TREE_SHA256 = b"6ef19b41225c5369f1c104d45d8d85efa9b057b53b14b4b9b939dd74decc5321"  # pragma: allowlist secret


@dataclass(frozen=True)
class SourceEpoch:
    """Non-content Git inputs capable of changing cleaned blobs or diffs."""

    attribute_fingerprint: bytes
    config_hash: bytes


@dataclass(frozen=True)
class GitEpoch:
    """Exact content and settings identities captured by the first oracle pass."""

    head: bytes
    object_format: str
    index_entries: tuple[tuple[bytes, bytes], ...]
    tracked_paths: tuple[bytes, ...]
    dirty_paths: tuple[bytes, ...]
    untracked_paths: tuple[bytes, ...]
    workspace_gitlinks: tuple[tuple[bytes, bytes], ...] = ()
    core_filemode: bool = True
    core_symlinks: bool = True
    index_bytes: bytes = b""
    source_epoch: SourceEpoch | None = None
    git_settings: FrozenGitSettings | None = None
    settings_inventory: tuple[bytes, ...] = ()

    def index_map(self) -> dict[bytes, bytes]:
        return dict(self.index_entries)

    @property
    def empty_tree(self) -> bytes:
        return (
            _EMPTY_TREE_SHA256 if self.object_format == "sha256" else _EMPTY_TREE_SHA1
        )


def core_bool(
    root: str,
    name: str,
    deadline: float,
    git_output: Callable[..., bytes],
) -> bool:
    value = git_output(
        root,
        ["config", "--bool", "--default", "true", name],
        deadline=deadline,
        limit=16,
    ).strip()
    if value in (b"", b"true"):
        return True
    if value == b"false":
        return False
    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")


def capture_source_epoch(
    root: str,
    index_bytes: bytes,
    paths: tuple[bytes, ...],
    *,
    deadline: float,
    object_format: str,
    frozen_output: Callable[..., bytes] = frozen_index_output,
    byte_ceiling: int = _MAX_SETTINGS_BYTES,
) -> SourceEpoch:
    """Hash exact bounded attributes and config without retaining config values."""
    path_input = b"".join(path + b"\0" for path in paths)
    temporary_bytes = len(index_bytes)
    available = min(_MAX_SETTINGS_BYTES, byte_ceiling) - temporary_bytes
    if len(path_input) > min(_MAX_SETTINGS_PATH_BYTES, available):
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    extra_env = {"GIT_ATTR_NOSYSTEM": "1"}
    attributes = frozen_output(
        root,
        index_bytes,
        ["check-attr", "-z", "--all", "--stdin"],
        deadline=deadline,
        limit=available - len(path_input),
        object_format=object_format,
        input_=path_input,
        extra_env=extra_env,
    )
    config_available = available - len(attributes)
    if config_available <= 0:  # pragma: no cover - output bound enforces first
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    config = frozen_output(
        root,
        index_bytes,
        ["config", "--null", "--list", "--show-origin", "--includes"],
        deadline=deadline,
        limit=config_available,
        object_format=object_format,
        extra_env=extra_env,
    )
    attribute_digest = hashlib.sha256(b"tsa-attributes-v1\0" + attributes).digest()
    config_digest = config_fingerprint(parse_effective_config(config))
    return SourceEpoch(attribute_digest, config_digest)
