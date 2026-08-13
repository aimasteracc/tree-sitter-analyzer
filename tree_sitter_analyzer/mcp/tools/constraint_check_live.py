"""Live configuration and raw-path scope helpers for constraint checks."""

from __future__ import annotations

import os
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...constraints.parser import load_constraints_bytes
from ...git_path_codec import path_to_wire
from ...source_oracle import SourceOracleError, safe_workspace_path

_CONFIG_CANDIDATES = (
    "architectural-constraints.yml",
    ".tree-sitter-analyzer/constraints.yml",
)


def _identity(info: os.stat_result) -> bytes:
    values = (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        getattr(info, "st_file_attributes", 0),
    )
    return b",".join(str(value).encode("ascii") for value in values)


def _is_reparse(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return stat.S_ISLNK(info.st_mode) or bool(reparse and attributes & reparse)


def _portable_probe(
    project_root: str, candidate: str, deadline: float
) -> tuple[bytes | None, tuple[bytes, ...], str]:
    """Read one bounded regular path while authenticating its complete chain."""
    current = Path(project_root)
    metadata: list[bytes] = []
    chain: list[tuple[Path, bytes]] = []
    try:
        for part in candidate.split("/")[:-1]:
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                return None, tuple(metadata + [b"missing"]), "missing"
            if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
                raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
            identity = _identity(info)
            metadata.append(identity)
            chain.append((current, identity))
            current /= part
        try:
            parent = os.lstat(current)
        except FileNotFoundError:
            return None, tuple(metadata + [b"missing"]), "missing"
        if not stat.S_ISDIR(parent.st_mode) or _is_reparse(parent):
            raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
        parent_identity = _identity(parent)
        metadata.append(parent_identity)
        chain.append((current, parent_identity))
        leaf = current / candidate.rsplit("/", 1)[-1]
        try:
            before = os.lstat(leaf)
        except FileNotFoundError:
            return None, tuple(metadata + [b"missing"]), "missing"
        metadata.append(_identity(before))
        if _is_reparse(before):
            raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
        if stat.S_ISDIR(before.st_mode):
            return None, tuple(metadata), "directory"
        if not stat.S_ISREG(before.st_mode):
            raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
        data = bytearray()
        with leaf.open("rb", buffering=0) as stream:
            opened = os.fstat(stream.fileno())
            if _identity(opened) != _identity(before):
                raise SourceOracleError("CONSTRAINT_CONFIG_CHANGED")
            while True:
                if time.monotonic() >= deadline:
                    raise RuntimeError("CONSTRAINT_CONFIG_DEADLINE")
                chunk = stream.read(min(64 * 1024, 1024 * 1024 - len(data) + 1))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 1024 * 1024:
                    raise SourceOracleError("CONSTRAINT_CONFIG_CAPACITY")
            if _identity(os.fstat(stream.fileno())) != _identity(opened):
                raise SourceOracleError("CONSTRAINT_CONFIG_CHANGED")
        if _identity(os.lstat(leaf)) != _identity(opened):
            raise SourceOracleError("CONSTRAINT_CONFIG_CHANGED")
        if any(_identity(os.lstat(path)) != identity for path, identity in chain):
            raise SourceOracleError("CONSTRAINT_CONFIG_CHANGED")
        return bytes(data), tuple(metadata), "file"
    except SourceOracleError:
        raise
    except OSError as exc:
        raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE") from exc


def _portable_config_required() -> bool:
    return os.name == "nt"


def live_config_snapshot(
    project_root: str, deadline: float
) -> tuple[str | None, bytes | None, tuple[bytes, ...]]:
    """Read discovery, bytes, and identity for one live constraints plane."""
    if _portable_config_required():
        for candidate in _CONFIG_CANDIDATES:
            data, metadata, kind = _portable_probe(project_root, candidate, deadline)
            if kind in {"missing", "directory"}:
                continue
            return candidate, data, metadata
        return None, None, ()
    for candidate in _CONFIG_CANDIDATES:
        probe = safe_workspace_path(
            project_root,
            candidate,
            deadline=deadline,
            limit=1024 * 1024,
            allow_directory=True,
        )
        if probe.kind in {"missing", "directory"}:
            continue
        if probe.kind != "file" or probe.data is None:
            raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
        return candidate, probe.data, probe.metadata
    return None, None, ()


def load_live_constraints(
    project_root: str, deadline: float
) -> tuple[
    tuple[str | None, bytes | None, tuple[bytes, ...]],
    list[Any],
]:
    """Parse constraints from the same bounded bytes retained for revalidation."""
    snapshot = live_config_snapshot(project_root, deadline)
    config_path, config_data, _metadata = snapshot
    constraints = (
        load_constraints_bytes(config_data or b"", config_path or "<none>")
        if config_path is not None
        else []
    )
    return snapshot, constraints


def config_changed_response(
    project_root: str,
    before: tuple[str | None, bytes | None, tuple[bytes, ...]],
    deadline: float,
    output_format: str,
    error_response: Callable[[str, str, str | None], dict[str, Any]],
    snapshot: Callable[
        [str, float], tuple[str | None, bytes | None, tuple[bytes, ...]]
    ] = live_config_snapshot,
) -> dict[str, Any] | None:
    """Fail closed if a read-only verdict no longer uses the live rules plane."""
    try:
        if snapshot(project_root, deadline) != before:
            return error_response("CONSTRAINT_CONFIG_CHANGED", output_format, None)
    except (OSError, RuntimeError, SourceOracleError) as exc:
        return error_response("CONSTRAINT_CONFIG_UNKNOWN", output_format, str(exc))
    return None


def path_is_in_scope(path: str, scope_paths: frozenset[str]) -> bool:
    """Match a raw repository path against exact wire scopes or descendants."""
    wire_path = path_to_wire(path).rstrip("/")
    for scope in scope_paths:
        normalized = scope.rstrip("/")
        if normalized in {"", "."}:
            return True
        if wire_path == normalized or wire_path.startswith(normalized + "/"):
            return True
    return False
