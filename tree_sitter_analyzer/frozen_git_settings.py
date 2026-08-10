"""Capture and materialize immutable Git settings for frozen payloads."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .source_oracle import (
    SafePath,
    SourceOracleError,
    _safe_absolute_regular,
    normalize_repo_path,
    safe_workspace_path,
)

_MAX_SETTINGS_BYTES = 16 * 1024 * 1024
_MAX_SETTINGS_FILES = 200_000
_KEY_PART = re.compile(rb"^[A-Za-z][A-Za-z0-9-]*$")


@dataclass(frozen=True)
class ConfigEntry:
    """One ordered effective config entry; ``None`` is an implicit value."""

    key: bytes
    value: bytes | None


@dataclass(frozen=True)
class FrozenSettingFile:
    """One no-follow file identity and its exact bytes when regular."""

    path: bytes
    kind: str
    data: bytes | None


@dataclass(frozen=True)
class FrozenGitSettings:
    """All mutable Git settings needed by frozen payload commands."""

    config_entries: tuple[ConfigEntry, ...]
    core_attributes_path: bytes | None
    core_attributes: FrozenSettingFile | None
    info_attributes: FrozenSettingFile
    worktree_attributes: tuple[FrozenSettingFile, ...]
    object_directory: bytes
    fingerprint: bytes


def _frame(digest: Any, label: bytes, value: bytes) -> None:
    update = digest.update
    update(len(label).to_bytes(4, "big"))
    update(label)
    update(len(value).to_bytes(8, "big"))
    update(value)


def _is_include_directive(key: bytes) -> bool:
    lowered = key.lower()
    return lowered == b"include.path" or (
        lowered.startswith(b"includeif.") and lowered.endswith(b".path")
    )


def parse_effective_config(raw: bytes) -> tuple[ConfigEntry, ...]:
    """Parse ``config -z --list --show-origin`` into ordered multi-values."""
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    if len(tokens) % 2:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    entries: list[ConfigEntry] = []
    for index in range(0, len(tokens), 2):
        # The origin is deliberately validated then discarded: includes have
        # already been flattened and shadow origins necessarily differ.
        origin, item = tokens[index], tokens[index + 1]
        if not origin or b"\0" in origin:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if b"\n" in item:
            key, value = item.split(b"\n", 1)
        else:
            key, value = item, None
        if not key or b"\0" in key or _is_include_directive(key):
            if _is_include_directive(key):
                continue
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        lowered = key.lower()
        # Snapshot Git supplies its own validated empty order file.  Never bind
        # payload identity or shadow config to an external diff.orderFile.
        if lowered == b"diff.orderfile":
            continue
        if (
            origin.startswith(b"command line:")
            and lowered == b"core.fsmonitor"
            and value == b"false"
        ):
            continue
        entries.append(ConfigEntry(key, value))
    return tuple(entries)


def config_fingerprint(entries: Iterable[ConfigEntry]) -> bytes:
    digest = hashlib.sha256()
    _frame(digest, b"domain", b"tsa-effective-config-v2")
    for entry in entries:
        _frame(digest, b"config-key", entry.key)
        _frame(
            digest,
            b"config-value",
            b"\0" if entry.value is None else b"\1" + entry.value,
        )
    return digest.digest()


def _record_file(digest: Any, label: bytes, item: FrozenSettingFile) -> None:
    _frame(digest, label + b"-path", item.path)
    _frame(digest, label + b"-kind", item.kind.encode("ascii"))
    if item.data is not None:
        _frame(digest, label + b"-bytes", item.data)


def settings_fingerprint(
    entries: tuple[ConfigEntry, ...],
    core_path: bytes | None,
    core_file: FrozenSettingFile | None,
    info_file: FrozenSettingFile,
    worktree_files: tuple[FrozenSettingFile, ...],
    object_directory: bytes,
) -> bytes:
    digest = hashlib.sha256()
    _frame(digest, b"domain", b"tsa-frozen-git-settings-v1")
    _frame(digest, b"config", config_fingerprint(entries))
    _frame(digest, b"core-attributes-path", core_path or b"missing")
    if core_file is not None:
        _record_file(digest, b"core-attributes", core_file)
    _record_file(digest, b"info-attributes", info_file)
    for item in worktree_files:
        _record_file(digest, b"worktree-attributes", item)
    _frame(digest, b"object-directory", object_directory)
    return digest.digest()


def _strip_line(raw: bytes) -> bytes:
    if raw.endswith(b"\r\n"):
        return raw[:-2]
    if raw.endswith(b"\n"):
        return raw[:-1]
    return raw


def _absolute_path(root: str, raw: bytes) -> str:
    value = os.fsdecode(raw)
    return os.path.abspath(value if os.path.isabs(value) else os.path.join(root, value))


def _read_absolute(path: str, deadline: float, remaining: int) -> FrozenSettingFile:
    safe = _safe_absolute_regular(
        path, deadline=deadline, limit=remaining, allow_missing=True
    )
    return FrozenSettingFile(os.fsencode(os.path.abspath(path)), safe.kind, safe.data)


def reject_active_filters(raw: bytes, paths: tuple[bytes, ...]) -> None:
    """Reject external clean filters from ``check-attr -z filter`` output.

    Git emits one path/attribute/value triple per input.  ``unspecified`` and
    explicit ``unset`` mean no driver; boolean ``set`` and named values are
    active and therefore unsupported by deterministic snapshots.
    """
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    if len(tokens) % 3:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    rows = tuple(zip(tokens[0::3], tokens[1::3], tokens[2::3], strict=True))
    if len(rows) != len(paths):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    for expected, (path, attribute, value) in zip(paths, rows, strict=True):
        if path != expected or attribute != b"filter":
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if value not in (b"unspecified", b"unset"):
            raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_FILTER")


def capture_frozen_git_settings(
    root: str,
    inventory: tuple[bytes, ...],
    deadline: float,
    git_output: Callable[..., bytes],
) -> FrozenGitSettings:
    """Boundedly capture effective config and every attribute source."""
    raw_config = git_output(
        root,
        ["config", "-z", "--list", "--show-origin", "--includes"],
        deadline=deadline,
        limit=_MAX_SETTINGS_BYTES,
    )
    entries = parse_effective_config(raw_config)
    core_path_raw = _strip_line(
        git_output(
            root,
            ["config", "--path", "--get", "--default", "", "core.attributesFile"],
            deadline=deadline,
            limit=64 * 1024,
        )
    )
    if b"\0" in core_path_raw:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    core_path = (
        os.fsencode(_absolute_path(root, core_path_raw)) if core_path_raw else None
    )
    info_path_raw = _strip_line(
        git_output(
            root,
            ["rev-parse", "--path-format=absolute", "--git-path", "info/attributes"],
            deadline=deadline,
            limit=64 * 1024,
        )
    )
    object_directory = _strip_line(
        git_output(
            root,
            ["rev-parse", "--path-format=absolute", "--git-path", "objects"],
            deadline=deadline,
            limit=64 * 1024,
        )
    )
    # Empty path outputs are supported only by injected unit seams. Real Git
    # always resolves both paths; production safety never relies on discovery.
    info_path = _absolute_path(root, info_path_raw or b".git/info/attributes")
    object_path = os.fsencode(_absolute_path(root, object_directory or b".git/objects"))

    framed_paths = (
        len(core_path or b"") + len(os.fsencode(info_path)) + len(object_path)
    )
    remaining = _MAX_SETTINGS_BYTES - len(raw_config) - framed_paths
    if remaining < 0:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    core_file = (
        _read_absolute(os.fsdecode(core_path), deadline, remaining)
        if core_path
        else None
    )
    remaining -= len(core_file.data or b"") if core_file else 0
    info_file = (
        _read_absolute(info_path, deadline, remaining)
        if info_path_raw
        else FrozenSettingFile(os.fsencode(info_path), "missing", None)
    )
    remaining -= len(info_file.data or b"")

    # Git consults .gitattributes at the root and at every directory on a
    # target path, including attribute files hidden by ignore rules.  Derive
    # this finite candidate set from the already bounded index/worktree target
    # inventory; never walk the workspace to discover settings.
    attribute_paths = {b".gitattributes"}
    for raw in inventory:
        path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
        parts = os.fsencode(path).split(b"/")
        for depth in range(1, len(parts)):
            attribute_paths.add(b"/".join((*parts[:depth], b".gitattributes")))
    ordered_attribute_paths = sorted(attribute_paths)
    setting_file_count = len(ordered_attribute_paths) + 1 + int(core_file is not None)
    if setting_file_count > _MAX_SETTINGS_FILES:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    worktree_files: list[FrozenSettingFile] = []
    for raw in ordered_attribute_paths:
        remaining -= len(raw)
        if remaining < 0:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
        safe: SafePath = safe_workspace_path(
            root, path, deadline=deadline, limit=remaining
        )
        if safe.kind not in ("file", "symlink", "missing"):
            raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
        item = FrozenSettingFile(raw, safe.kind, safe.data)
        remaining -= len(item.data or b"")
        if remaining < 0:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        worktree_files.append(item)
    frozen_files = tuple(worktree_files)
    fingerprint = settings_fingerprint(
        entries, core_path, core_file, info_file, frozen_files, object_path
    )
    return FrozenGitSettings(
        entries,
        core_path,
        core_file,
        info_file,
        frozen_files,
        object_path,
        fingerprint,
    )


def _quoted(raw: bytes) -> bytes:
    result = bytearray(b'"')
    for value in raw:
        escapes = {
            0x08: b"\\b",
            0x09: b"\\t",
            0x0A: b"\\n",
            0x22: b'\\"',
            0x5C: b"\\\\",
        }
        result.extend(escapes.get(value, bytes((value,))))
    result.extend(b'"')
    return bytes(result)


def _key_parts(key: bytes) -> tuple[bytes, bytes | None, bytes]:
    pieces = key.split(b".")
    if len(pieces) < 2:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    section, name = pieces[0], pieces[-1]
    subsection = b".".join(pieces[1:-1]) or None
    if not _KEY_PART.fullmatch(section) or not _KEY_PART.fullmatch(name):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return section, subsection, name


def serialize_config(
    entries: tuple[ConfigEntry, ...], core_attributes_path: bytes | None
) -> tuple[bytes, tuple[ConfigEntry, ...]]:
    """Serialize flattened config without putting values in process argv."""
    output = bytearray()
    materialized: list[ConfigEntry] = []
    for entry in entries:
        lowered = entry.key.lower()
        if lowered == b"diff.orderfile":
            continue
        section, subsection, name = _key_parts(entry.key)
        output.extend(b"[" + section)
        if subsection is not None:
            output.extend(b" " + _quoted(subsection))
        output.extend(b"]\n\t" + name)
        value = entry.value
        if lowered == b"core.attributesfile" and core_attributes_path:
            value = core_attributes_path
        if value is not None:
            output.extend(b" = " + _quoted(value))
        output.extend(b"\n")
        materialized.append(ConfigEntry(entry.key, value))
    return bytes(output), tuple(materialized)
