"""Bounded read-only owner for the current full-index source scope."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .constants import EXCLUDE_DIRS
from .indexing_limits import DEFAULT_INDEX_MAX_FILES
from .languages.lang_extension_map import EXT_TO_LANG

_SOURCE_DEADLINE_SECONDS = 5.0
_SOURCE_BYTE_BUDGET = 512 * 1024 * 1024
_DEFAULT_EXCLUDES = frozenset({"tests/golden/corpus_*"})


@dataclass(frozen=True, slots=True)
class CurrentSourceSnapshot:
    rows: tuple[tuple[str, str, str], ...]
    fingerprint: str | None
    generation: str | None
    state: Literal["exact", "unsafe", "unknown"]
    reason: str | None


def inventory_fingerprint(rows: tuple[tuple[str, str, str], ...]) -> str:
    """Return the shared owner token for path/content/language inventory."""
    digest = hashlib.sha256(b"tsa-index-source-v2\0")
    for row in sorted(rows):
        for value in row:
            raw = value.encode("utf-8", "surrogatepass")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
    return "sha256:" + digest.hexdigest()


def recorded_source_rows(conn: object) -> tuple[tuple[str, str, str], ...]:
    """Read the cache's claimed source inventory without filesystem access."""
    return tuple(
        sorted(
            (str(row[0]).replace("\\", "/"), str(row[1]), str(row[2]))
            for row in conn.execute(  # type: ignore[attr-defined]
                "SELECT file_path, content_hash, language FROM ast_index"
            )
        )
    )


def capture_current_source_snapshot(project_root: str) -> CurrentSourceSnapshot:
    """Hash a stable, fully bounded view of the authoritative supported scope."""
    deadline = time.monotonic() + _SOURCE_DEADLINE_SECONDS
    root = os.path.realpath(os.path.abspath(project_root))
    try:
        first, unsafe = _inventory(root, deadline, with_content=True)
        second, unsafe_second = _inventory(root, deadline, with_content=False)
    except TimeoutError:
        return CurrentSourceSnapshot((), None, None, "unknown", "SOURCE_SCAN_DEADLINE")
    except OverflowError:
        return CurrentSourceSnapshot(
            (), None, None, "unknown", "SOURCE_SCOPE_UNBOUNDED"
        )
    except OSError:
        return CurrentSourceSnapshot(
            (), None, None, "unknown", "SOURCE_SCOPE_UNREADABLE"
        )

    metadata = {(path, language): marker for path, marker, language in second}
    stable = all(
        metadata.get((path, language)) == marker.split("|", 1)[0]
        for path, marker, language in first
    )
    first_scope = [(r[0], r[2]) for r in first]
    second_scope = [(r[0], r[2]) for r in second]
    unique_scope = len(first_scope) == len(set(first_scope)) and len(
        second_scope
    ) == len(set(second_scope))
    same_paths = set(first_scope) == set(second_scope)
    rows = tuple(
        (path, marker.split("|", 1)[1], language) for path, marker, language in first
    )
    fingerprint = inventory_fingerprint(rows)
    generation = "idxsrc-v2:" + fingerprint.removeprefix("sha256:")
    if unsafe or unsafe_second or not stable or not same_paths or not unique_scope:
        return CurrentSourceSnapshot(
            rows, fingerprint, generation, "unsafe", "SOURCE_SCOPE_UNSAFE"
        )
    return CurrentSourceSnapshot(rows, fingerprint, generation, "exact", None)


def _inventory(
    root: str, deadline: float, *, with_content: bool
) -> tuple[tuple[tuple[str, str, str], ...], bool]:
    rows: list[tuple[str, str, str]] = []
    unsafe = False
    byte_count = 0
    stack = [root]
    while stack:
        if time.monotonic() > deadline:
            raise TimeoutError
        directory = stack.pop()
        entries = sorted(os.scandir(directory), key=lambda item: item.name)
        for entry in entries:
            if time.monotonic() > deadline:
                raise TimeoutError
            rel = os.path.relpath(entry.path, root).replace("\\", "/")
            info = entry.stat(follow_symlinks=False)
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                if entry.name not in EXCLUDE_DIRS and not entry.name.startswith("."):
                    stack.append(entry.path)
                continue
            language = EXT_TO_LANG.get(Path(entry.name).suffix.lower())
            if language is None or any(
                fnmatch.fnmatch(rel, p) for p in _DEFAULT_EXCLUDES
            ):
                continue
            if len(rows) == DEFAULT_INDEX_MAX_FILES:
                raise OverflowError
            if not stat.S_ISREG(mode):
                unsafe = True
                rows.append((rel, _metadata_marker(info) + "|<unsafe>", language))
                continue
            if not with_content:
                rows.append((rel, _metadata_marker(info), language))
                continue
            byte_count += int(info.st_size)
            if byte_count > _SOURCE_BYTE_BUDGET:
                raise OverflowError
            try:
                fd = os.open(entry.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            except OSError:
                unsafe = True
                rows.append((rel, _metadata_marker(info) + "|<unsafe>", language))
                continue
            try:
                opened = os.fstat(fd)
                data = bytearray()
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if time.monotonic() > deadline:
                        raise TimeoutError
                after = os.fstat(fd)
            finally:
                os.close(fd)
            marker = _metadata_marker(after)
            if not _same_file_metadata(info, after) or not stat.S_ISREG(opened.st_mode):
                unsafe = True
            # Match ``open(..., encoding="utf-8", errors="replace")`` in the
            # indexer: TextIOWrapper performs universal-newline translation
            # before the UTF-8 text is hashed.
            content = bytes(data).decode("utf-8", "replace")
            normalized = content.replace("\r\n", "\n").replace("\r", "\n")
            rows.append(
                (
                    rel,
                    marker
                    + "|"
                    + hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                    language,
                )
            )
    return tuple(sorted(rows)), unsafe


def _metadata_marker(info: os.stat_result) -> str:
    return f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}"


def _same_file_metadata(before: os.stat_result, after: os.stat_result) -> bool:
    """Compare path/fd metadata without relying on platform-specific ctime."""
    identity_matches = not (before.st_ino and after.st_ino) or (
        before.st_dev,
        before.st_ino,
    ) == (after.st_dev, after.st_ino)
    return identity_matches and (before.st_size, before.st_mtime_ns) == (
        after.st_size,
        after.st_mtime_ns,
    )
