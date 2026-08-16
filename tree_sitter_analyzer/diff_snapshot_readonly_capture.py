"""RFC-0022 P0.4 zero-write diff payload materialization (Phase A groundwork).

The frozen capture (``diff_snapshot_capture._capture_payload``) reproduces
the complete P0.2 patch, status, blob, config, attribute, ordering and
source-generation semantics through a temporary index/object store (P0.2
allows this). This module reproduces the same payload **in memory** with
zero filesystem writes: every git command runs read-only against the live
index with ``GIT_OPTIONAL_LOCKS=0`` (``git_readonly``), worktree content is
read through the same descriptor-verified ``safe_workspace_path`` reader as
the frozen capture, and the only sections git cannot emit itself (new-file
patches for untracked paths) are produced with the byte-identical
``git diff --no-index`` format (RFC-0022 P0.4).

Equivalence contract (proved by the differential golden suite in
``tests/unit/test_diff_snapshot_readonly_capture.py``):

- ``mode="staged"`` payloads are byte-identical: git compares the live
  index (oracle-validated against the captured epoch) with HEAD using the
  exact frozen argument set.
- ``mode="diff"`` tracked rows, binary flags, patch sections, ordering and
  blob bytes are byte-identical to the frozen payload on conversion-free
  repositories. Worktree renames with unchanged content are detected as
  exact (R100) renames; renames with modified content surface as explicit
  delete+add pairs (the frozen backend reports an inexact R — a documented
  divergence, see ``_pair_exact_renames``).
- Repositories whose checkin conversion (``core.autocrlf``, ``eol`` or
  ``working-tree-encoding`` attributes) would change any materialized
  worktree byte fail closed with ``DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION``:
  the raw worktree bytes are only publishable when they equal the frozen
  backend's cleaned bytes.
"""

from __future__ import annotations

import hashlib
import os

from .diff_snapshot_capture import (
    ChangedFile,
    FrozenFile,
    _entry_parts,
    _row_sort_key,
    _safe_mode,
)
from .diff_snapshot_readonly import (
    _git_output_readonly,
    _head_entries_readonly,
    _live_index_output,
)
from .git_path_codec import raw_to_path
from .source_oracle import (
    SafePath,
    SourceOracleError,
    WorkspaceManifestEntry,
    _remaining,
    safe_workspace_path,
)
from .source_oracle_git import GitEpoch

_MAX_BINARY_PROBE = 8000
_EMPTY_OID = b"0" * 40


def _blob_readonly(
    root: str, oid: str | None, kind: str, deadline: float, limit: int
) -> bytes | None:
    """Read one blob through the zero-write runner (gitlinks have no blob)."""
    if oid is None or kind == "gitlink":
        return None
    return _git_output_readonly(
        root, ["cat-file", "blob", oid], deadline=deadline, limit=limit
    )


def _is_binary(data: bytes) -> bool:
    """Git's ``buffer_is_binary``: NUL within the first 8000 bytes."""
    return b"\0" in data[:_MAX_BINARY_PROBE]


def _readonly_rows(
    root: str, mode: str, head: bytes, deadline: float, limit: int
) -> list[tuple[str, bytes | None, bytes]]:
    """Live zero-write name-status rows for tracked index/worktree changes."""
    args = (["diff", "--cached"] if mode == "staged" else ["diff"]) + [
        "--name-status",
        "-z",
        "--find-renames",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
    ]
    if mode == "staged":
        args.append(os.fsdecode(head))
    raw = _live_index_output(root, b"", args, deadline=deadline, limit=limit)
    tokens = [item for item in raw.split(b"\0") if item]
    rows: list[tuple[str, bytes | None, bytes]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index][:1].decode("ascii", "strict")
        index += 1
        try:
            if status in ("R", "C"):
                old, path = tokens[index], tokens[index + 1]
                index += 2
            else:
                old, path = None, tokens[index]
                index += 1
            raw_to_path(path)
            if old is not None:
                raw_to_path(old)
        except (IndexError, UnicodeError, ValueError) as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        rows.append(("R" if status in ("R", "C") else status, old, path))
    return rows


def _readonly_binaries(
    root: str, mode: str, head: bytes, deadline: float, limit: int
) -> set[bytes]:
    """Live zero-write numstat binary-path set (tracked rows only)."""
    args = (["diff", "--cached"] if mode == "staged" else ["diff"]) + [
        "--numstat",
        "-z",
        "--find-renames",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
    ]
    if mode == "staged":
        args.append(os.fsdecode(head))
    raw = _live_index_output(root, b"", args, deadline=deadline, limit=limit)
    tokens = raw.split(b"\0")
    result: set[bytes] = set()
    index = 0
    while index < len(tokens):
        row = tokens[index]
        index += 1
        if not row:
            continue
        fields = row.split(b"\t", 2)
        if len(fields) != 3:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        path = fields[2]
        if not path:
            try:
                old, path = tokens[index], tokens[index + 1]
            except IndexError as exc:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
            index += 2
            if not old or not path:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if fields[0] == fields[1] == b"-":
            result.add(path)
    return result


_QUOTE_SHORTHAND = {
    0x07: b"\\a",
    0x08: b"\\b",
    0x0C: b"\\f",
    0x0A: b"\\n",
    0x0D: b"\\r",
    0x09: b"\\t",
    0x0B: b"\\v",
    0x5C: b"\\\\",
    0x22: b'\\"',
}
_UNQUOTE_SHORTHAND = {
    b"a": 0x07,
    b"b": 0x08,
    b"f": 0x0C,
    b"n": 0x0A,
    b"r": 0x0D,
    b"t": 0x09,
    b"v": 0x0B,
    b"\\": 0x5C,
    b'"': 0x22,
}


def _git_quote_path(raw: bytes) -> bytes:
    """Quote one path for a synthetic diff header (git ``quote_c_style``).

    Git quotes the whole ``a/<path>`` token (prefix included) when any
    byte needs quoting; spaces are never quoted, so callers pass the
    prefixed path when emitting ``diff --git`` headers.
    """
    needs = any(value < 0x20 or value > 0x7E or value in (0x22, 0x5C) for value in raw)
    if not needs:
        return raw
    out = bytearray(b'"')
    for value in raw:
        if value in _QUOTE_SHORTHAND:
            out.extend(_QUOTE_SHORTHAND[value])
        elif value < 0x20 or value > 0x7E:
            out.extend(f"\\{value:03o}".encode("ascii"))
        else:
            out.append(value)
    out.append(0x22)
    return bytes(out)


def _git_unquote(raw: bytes) -> bytes:
    """Decode one git C-quoted token (the inverse of ``quote_c_style``)."""
    if not raw.startswith(b'"') or not raw.endswith(b'"'):
        return raw
    body = raw[1:-1]
    out = bytearray()
    index = 0
    while index < len(body):
        value = body[index]
        if value != 0x5C:
            out.append(value)
            index += 1
            continue
        index += 1
        if index >= len(body):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        escape = body[index : index + 1]
        if escape in _UNQUOTE_SHORTHAND:
            out.append(_UNQUOTE_SHORTHAND[escape])
            index += 1
            continue
        octal = body[index : index + 3]
        if len(octal) == 3 and all(0x30 <= value <= 0x37 for value in octal):
            out.append(int(octal, 8))
            index += 3
            continue
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return bytes(out)


def _quoted_token_end(raw: bytes, start: int) -> int:
    """Return the index just past an unescaped closing quote from ``start``."""
    index = start
    while index < len(raw):
        if raw[index] == 0x5C:
            index += 2
            continue
        if raw[index] == 0x22:
            return index + 1
        index += 1
    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")


def _no_index_new_file_patch(
    root: str, raw: bytes, deadline: float, limit: int
) -> bytes:
    """Emit the byte-identical new-file patch git itself would produce.

    ``git diff --no-index /dev/null <path>`` renders the exact new-file
    section format used by ``diff --cached`` against a base tree (mode,
    full index line, ``/dev/null`` old side, text hunks or ``GIT binary
    patch`` literal), and exits 1 whenever the paths differ — the exit
    code is the result, so the runner accepts it explicitly.
    """
    return _live_index_output(
        root,
        b"",
        [
            "diff",
            "--no-index",
            "--binary",
            "--full-index",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--",
            "/dev/null",
            os.fsdecode(raw),
        ],
        deadline=deadline,
        limit=limit,
        ok_returncodes=frozenset({0, 1}),
    )


def _reject_worktree_conversion(
    root: str,
    safe_paths: dict[bytes, SafePath],
    deadline: float,
) -> None:
    """Fail closed when any materialized worktree byte would be cleaned.

    The frozen backend hashes dirty/untracked leaves with
    ``hash-object --path``, so its published ``new_bytes`` are the
    *cleaned* bytes (autocrlf/eol/encoding conversions applied). The
    zero-write backend publishes raw worktree bytes; those are equal only
    when no checkin conversion applies. ``working-tree-encoding`` and
    ``ident`` can alter any content (UTF-16 files, expanded ``$Id$``
    markers), so they are probed for every materialized path;
    ``core.autocrlf``/``eol`` only alter non-binary files that already
    contain CRLF, so the CRLF guard scopes those probes.
    """
    materialized = sorted(
        (raw, safe)
        for raw, safe in safe_paths.items()
        if safe.kind in ("file", "symlink") and safe.data is not None
    )
    if not materialized:
        return
    attr_input = b"".join(raw + b"\0" for raw, _safe in materialized)
    attributes = _live_index_output(
        root,
        b"",
        ["check-attr", "-z", "working-tree-encoding", "ident", "eol", "--stdin"],
        deadline=deadline,
        limit=16 * 1024 * 1024,
        input_=attr_input,
    )
    tokens = [token for token in attributes.split(b"\0") if token]
    if len(tokens) % 3 != 0:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    per_path: dict[bytes, dict[bytes, bytes]] = {}
    for index in range(0, len(tokens), 3):
        path, attr, value = tokens[index : index + 3]
        per_path.setdefault(path, {})[attr] = value
    for raw, _safe in materialized:
        attrs = per_path.get(raw, {})
        if attrs.get(b"working-tree-encoding", b"unspecified") not in (
            b"unspecified",
            b"unset",
        ):
            raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION")
        if attrs.get(b"ident") == b"set":
            raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION")
    crlf_candidates: list[tuple[bytes, SafePath]] = []
    for raw, safe in materialized:
        data = safe.data
        if data is not None and not _is_binary(data) and b"\r\n" in data:
            crlf_candidates.append((raw, safe))
    if not crlf_candidates:
        return
    config_list = _git_output_readonly(
        root,
        ["config", "--null", "--list", "--includes"],
        deadline=deadline,
        limit=16 * 1024 * 1024,
    )
    settings: dict[bytes, bytes] = {}
    for record in config_list.split(b"\0"):
        if not record:
            continue
        key, _, value = record.partition(b"\n")
        settings[key.lower()] = value.strip()
    if settings.get(b"core.autocrlf", b"false").lower() in (b"true", b"input"):
        raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION")
    for raw, _safe in crlf_candidates:
        if per_path.get(raw, {}).get(b"eol") in (b"crlf", b"lf"):
            raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION")


def _workspace_mode(
    epoch: GitEpoch, safe: SafePath, existing_mode: bytes | None
) -> bytes:
    """Replicate ``FrozenGitEnvironment.apply_workspace`` mode computation."""
    emulated_symlink = (
        not epoch.core_symlinks and safe.kind == "file" and existing_mode == b"120000"
    )
    if safe.kind == "symlink" or emulated_symlink:
        return b"120000"
    if not epoch.core_filemode:
        mode = existing_mode or b"100644"
        return mode if mode in (b"100644", b"100755") else b"100644"
    try:
        bits = int(safe.metadata[-1].split(b",")[2])
    except (IndexError, ValueError) as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH") from exc
    return b"100755" if bits & 0o111 else b"100644"


def _pair_exact_renames(
    root: str,
    rows: list[tuple[str, bytes | None, bytes]],
    index_entries: dict[bytes, bytes],
    safe_paths: dict[bytes, SafePath],
    deadline: float,
    limit: int,
) -> list[tuple[str, bytes | None, bytes]]:
    """Pair delete+untracked rows with identical content into R100 renames.

    The live ``git diff`` queue never contains untracked paths, so git
    cannot detect worktree renames for it; the frozen backend's temporary
    index does contain them and reports content-identical moves as
    ``R100``. This replicates the exact-rename half with content hashing:
    a pair is formed only when exactly one deleted file and one added file
    share the content hash (Git's own tie-breaking for ambiguous identical
    candidates is not reproduced, so ambiguous matches stay delete+add
    pairs rather than guessing a wrong lineage). Content-modified moves
    stay delete+add pairs (a documented divergence from the frozen
    inexact ``R``). Matching is O(n) and deadline-bounded.
    """
    deleted = [
        row for row in rows if row[0] == "D" and (row[1] or row[2]) in index_entries
    ]
    added = [row for row in rows if row[0] == "A" and row[2] in safe_paths]
    if not deleted or not added:
        return rows
    added_paths = {row[2] for row in added}
    hasher = hashlib.sha256
    added_hashes: dict[bytes, bytes] = {}
    for _status, _old_raw, raw in added:
        safe = safe_paths[raw]
        if safe.kind in ("file", "symlink") and safe.data is not None:
            added_hashes[raw] = hasher(safe.data).digest()
        _remaining(deadline)
    deleted_hashes: dict[bytes, bytes] = {}
    for _status, old_raw, raw in deleted:
        lookup = old_raw or raw
        mode, oid, kind = _entry_parts(index_entries[lookup])
        blob = _blob_readonly(root, oid, kind, deadline, limit)
        if blob is not None:
            deleted_hashes[lookup] = hasher(blob).digest()
        _remaining(deadline)
    members_by_hash: dict[bytes, list[bytes]] = {}
    for path, digest in added_hashes.items():
        members_by_hash.setdefault(digest, []).append(path)
    for path, digest in deleted_hashes.items():
        members_by_hash.setdefault(digest, []).append(path)
    pairs: dict[bytes, bytes] = {}
    used: set[bytes] = set()
    for _digest, members in members_by_hash.items():
        if len(members) != 2:
            continue
        deleted_members = [path for path in members if path in deleted_hashes]
        added_members = [path for path in members if path in added_hashes]
        if len(deleted_members) == 1 and len(added_members) == 1:
            if added_members[0] not in used:
                pairs[deleted_members[0]] = added_members[0]
                used.add(added_members[0])
        _remaining(deadline)
    if not pairs:
        return rows
    result: list[tuple[str, bytes | None, bytes]] = []
    for row in rows:
        if row[0] == "D" and (row[1] or row[2]) in pairs:
            continue
        if row[0] == "A" and row[2] in added_paths:
            continue
        result.append(row)
    for old_path, new_raw in sorted(pairs.items()):
        result.append(("R", old_path, new_raw))
    for status, _old_raw, raw in added:
        if raw not in used:
            result.append((status, None, raw))
    return result


def _strip_one_newline(section: bytes) -> bytes:
    """Normalize one section boundary (git diff ends every line with LF)."""
    return section[:-1] if section.endswith(b"\n") else section


def _patch_section_paths(patch: bytes) -> dict[bytes, bytes]:
    """Split one git diff stream into per-destination-path sections.

    Returns ``{destination_raw: section_without_trailing_newline}`` so the
    zero-write backend can drop delete sections consumed by renames and
    merge synthetic untracked sections in git's destination-path order.
    Git never quotes spaces, so unquoted headers are split on the literal
    `` b/`` separator (git's own parsing convention); quoted tokens are
    C-unquoted with their ``a/`` prefix inside the quotes.
    """
    sections: dict[bytes, bytes] = {}
    for token in patch.split(b"\ndiff --git "):
        if not token:
            continue
        first_line = token.split(b"\n", 1)[0]
        body = (
            first_line
            if first_line.startswith(b"diff --git ")
            else b"diff --git " + first_line
        )
        rest = body[len(b"diff --git ") :]
        if rest.startswith(b'"'):
            end = _quoted_token_end(rest, 1)
            first = rest[1 : end - 1]
            second_start = end
            if second_start >= len(rest) or rest[second_start] != 0x20:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            second = rest[second_start + 1 :]
            if not second.startswith(b'"'):
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            second = second[1 : _quoted_token_end(second, 1) - 1]
            if not second.startswith(b"b/"):
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            first = _git_unquote(first)
        else:
            marker = rest.find(b" b/")
            if marker < 0:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            first = rest[:marker]
        if not first.startswith(b"a/"):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        destination = _git_unquote(first[2:])
        sections.setdefault(destination, _strip_one_newline(token))
    return sections


def _rewrite_new_file_mode(section: bytes, mode: bytes) -> bytes:
    """Align a synthetic new-file section's mode line with the record mode."""
    marker = b"new file mode "
    index = section.find(marker)
    if index < 0:
        return section
    end = section.find(b"\n", index)
    if end < 0:
        return section
    replacement = marker + mode
    if section[index:end] == replacement:
        return section
    return section[:index] + replacement + section[end:]


def _synthesize_rename_section(
    old_raw: bytes,
    new_raw: bytes,
    old_mode: bytes | None = None,
    new_mode: bytes | None = None,
) -> bytes:
    """Byte-identical 100%-rename section header body.

    Git emits the mode-change lines before the similarity/rename lines,
    and quotes each ``a/``/``b/``-prefixed header token as one unit.
    """
    header = (
        b"diff --git "
        + _git_quote_path(b"a/" + old_raw)
        + b" "
        + _git_quote_path(b"b/" + new_raw)
    )
    body = bytearray(header)
    if old_mode is not None and new_mode is not None and old_mode != new_mode:
        body.extend(b"\nold mode " + old_mode + b"\nnew mode " + new_mode)
    body.extend(
        b"\nsimilarity index 100%\nrename from "
        + _git_quote_path(old_raw)
        + b"\nrename to "
        + _git_quote_path(new_raw)
        + b"\n"
    )
    return bytes(body)


def capture_payload_readonly(
    root: str,
    mode: str,
    deadline: float,
    ceiling: int,
    expected_manifest: dict[str, WorkspaceManifestEntry] | None = None,
    epoch: GitEpoch | None = None,
) -> tuple[bytes, tuple[FrozenFile, ...]]:
    """Capture the frozen payload shape with zero filesystem writes.

    Mirrors ``diff_snapshot_capture._capture_payload`` record-for-record:
    same changed-file rows (status/old-path/kind/mode/oid/availability/
    binary/unsupported), same normalized patch, same old/new bytes — all
    from read-only git invocations against the live index and
    descriptor-verified worktree reads.
    """
    if epoch is None:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    remaining = ceiling
    index_entries = epoch.index_map()
    head_entries = (
        _head_entries_readonly(root, deadline=deadline, head=epoch.head)
        if mode == "staged"
        else {}
    )
    safe_paths: dict[bytes, SafePath] = {}
    workspace_entries: dict[bytes, bytes] = {}
    dirty_gitlinks = set(dict(epoch.workspace_gitlinks)) & set(epoch.dirty_paths)
    if mode == "diff":
        raw_paths = set(epoch.dirty_paths) | set(epoch.untracked_paths)
        gitlink_entries = dict(epoch.workspace_gitlinks)
        for raw in sorted(raw_paths):
            path = raw_to_path(raw)
            manifest_entry = (expected_manifest or {}).get(path)
            if manifest_entry is None:
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            if raw in gitlink_entries:
                safe = SafePath(None, (), "directory")
            else:
                safe = safe_workspace_path(
                    root,
                    path,
                    deadline=deadline,
                    limit=remaining,
                    expected_chain=manifest_entry.descriptor_chain,
                    # Regular tracked leaves may have been replaced by dirs.
                    allow_directory=True,
                )
            if safe.data is not None:
                remaining -= len(safe.data)
            if safe.kind == "file":
                raw_changed = manifest_entry.raw_bytes != safe.data
                if raw_changed:  # pragma: no cover - descriptor fails first
                    raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
                safe = SafePath(
                    manifest_entry.raw_bytes,
                    safe.metadata,
                    safe.kind,
                )
            safe_paths[raw] = safe
        _reject_worktree_conversion(root, safe_paths, deadline)
        for raw, safe in sorted(safe_paths.items()):
            existing = index_entries.get(raw)
            existing_mode = existing.split(b" ", 1)[0] if existing is not None else None
            if safe.kind == "missing":
                continue
            if safe.kind == "directory":
                entry = dict(epoch.workspace_gitlinks).get(raw)
                if entry is not None:
                    if not entry.startswith(b"160000 "):
                        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
                    workspace_entries[raw] = entry
                continue
            if safe.kind not in ("file", "symlink") or safe.data is None:
                raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
            workspace_entries[raw] = (
                _workspace_mode(epoch, safe, existing_mode) + b" " + _EMPTY_OID + b" 0"
            )
        row_limit = min(8 * 1024 * 1024, remaining)
        rows = _readonly_rows(root, mode, epoch.head, deadline, row_limit)
        untracked_raw = _live_index_output(
            root,
            b"",
            ["ls-files", "--others", "--exclude-standard", "-z"],
            deadline=deadline,
            limit=row_limit,
        )
        remaining -= len(untracked_raw)
        known = {row[2] for row in rows}
        for item in untracked_raw.split(b"\0"):
            if item:
                raw_to_path(item)
                if item not in known:
                    rows.append(("A", None, item))
        # The live diff reports dirty gitlinks (submodule state), but the
        # frozen backend emits them only through its own workspace-gitlink
        # rows appended below; dedupe the live copies and drop their patch
        # sections so the record/patch surface matches exactly.
        dropped_gitlinks: set[bytes] = set()
        filtered_rows: list[tuple[str, bytes | None, bytes]] = []
        for row in rows:
            if (
                row[0] == "M"
                and row[2] in index_entries
                and index_entries[row[2]].startswith(b"160000 ")
            ):
                dropped_gitlinks.add(row[2])
                continue
            filtered_rows.append(row)
        rows = filtered_rows
        rows = _pair_exact_renames(
            root, rows, index_entries, safe_paths, deadline, row_limit
        )
        binaries = _readonly_binaries(root, mode, epoch.head, deadline, row_limit)
        binaries.update(
            raw
            for raw in safe_paths
            if (data := safe_paths[raw].data) is not None and _is_binary(data)
        )
        # Untracked binary classification honors the effective ``diff``
        # attribute (``binary``/``-diff`` mark a path binary even without a
        # NUL byte), matching numstat's semantics for tracked rows.
        untracked_attr_paths = sorted(
            raw
            for raw in safe_paths
            if raw not in index_entries and safe_paths[raw].kind in ("file", "symlink")
        )
        if untracked_attr_paths:
            attr_input = b"".join(raw + b"\0" for raw in untracked_attr_paths)
            diff_attrs = _live_index_output(
                root,
                b"",
                ["check-attr", "-z", "diff", "--stdin"],
                deadline=deadline,
                limit=16 * 1024 * 1024,
                input_=attr_input,
            )
            diff_tokens = [t for t in diff_attrs.split(b"\0") if t]
            if len(diff_tokens) % 3 != 0:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            for index in range(0, len(diff_tokens), 3):
                token_path, attr, value = diff_tokens[index : index + 3]
                if attr == b"diff" and value == b"unset":
                    binaries.add(token_path)
        tracked_patch = _live_index_output(
            root,
            b"",
            [
                "diff",
                "--binary",
                "--full-index",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                "--find-renames",
                "--no-color",
                "--no-ext-diff",
                "--no-textconv",
                "--submodule=short",
                "--ignore-submodules=none",
            ],
            deadline=deadline,
            limit=min(64 * 1024 * 1024, remaining),
        )
        remaining -= len(tracked_patch)
        sections = _patch_section_paths(tracked_patch)
        # Delete sections consumed by exact renames must not survive: the
        # frozen backend emits only the 100%-rename section for the pair.
        for status, old_raw, _raw in rows:
            if status == "R":
                sections.pop(old_raw or b"", None)
        # Dirty-gitlink sections belong to the appended rows, not the patch.
        for raw in sorted(dropped_gitlinks):
            sections.pop(raw, None)
        synthetic: dict[bytes, bytes] = {}
        for status, old_raw, raw in rows:
            if status == "R":
                lookup = old_raw or raw
                old_mode = _entry_parts(index_entries.get(lookup))[0]
                new_mode = _entry_parts(workspace_entries.get(raw))[0]
                synthetic[raw] = _synthesize_rename_section(
                    lookup,
                    raw,
                    old_mode.encode("ascii") if old_mode is not None else None,
                    new_mode.encode("ascii") if new_mode is not None else None,
                )
            elif status == "A" and raw in safe_paths and raw not in sections:
                new_file = _no_index_new_file_patch(
                    root, raw, deadline, min(64 * 1024 * 1024, remaining)
                )
                # ``git diff --no-index`` reads the filesystem mode, but the
                # published record carries the epoch-derived mode
                # (core.filemode=false normalizes to 100644); align the
                # header so the snapshot cannot contradict itself.
                workspace_mode = workspace_entries.get(raw)
                if workspace_mode is not None:
                    derived = workspace_mode.split(b" ", 1)[0]
                    new_file = _rewrite_new_file_mode(new_file, derived)
                synthetic[raw] = new_file
                remaining -= len(new_file)
        assembled: list[bytes] = []
        for raw in sorted(set(sections) | set(synthetic)):
            section = synthetic.get(raw, sections.get(raw))
            if section is None:  # pragma: no cover - key sets are equal
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            section = _strip_one_newline(section)
            assembled.append(
                section
                if section.startswith(b"diff --git ")
                else b"diff --git " + section
            )
        patch = b"\n".join(assembled)
        if patch:
            patch += b"\n"
        remaining -= len(patch)
        patch_row_paths = {row[2] for row in rows}
        for raw in sorted(dict(epoch.workspace_gitlinks)):
            rows.append(("M", None, raw))
    else:
        row_limit = min(8 * 1024 * 1024, remaining)
        rows = _readonly_rows(root, mode, epoch.head, deadline, row_limit)
        binaries = _readonly_binaries(root, mode, epoch.head, deadline, row_limit)
        patch = _live_index_output(
            root,
            b"",
            [
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                "--find-renames",
                "--no-color",
                "--no-ext-diff",
                "--no-textconv",
                "--submodule=short",
                "--ignore-submodules=none",
                os.fsdecode(epoch.head),
            ],
            deadline=deadline,
            limit=min(64 * 1024 * 1024, remaining),
        )
        remaining -= len(patch)
        patch_row_paths = {row[2] for row in rows}
    rows.sort(key=_row_sort_key)
    final_entries = dict(index_entries)
    if mode == "diff":
        for raw, safe in safe_paths.items():
            if safe.kind in ("missing", "directory") and not (
                safe.kind == "directory" and raw in workspace_entries
            ):
                final_entries.pop(raw, None)
            else:
                final_entries[raw] = workspace_entries[raw]
    files: list[FrozenFile] = []
    for status, old_raw, raw in rows:
        lookup = old_raw or raw
        old_entry = (
            index_entries.get(lookup) if mode == "diff" else head_entries.get(lookup)
        )
        new_entry = final_entries.get(raw)
        old_mode, old_oid, old_kind = _entry_parts(old_entry)
        new_mode, new_oid, new_kind = _entry_parts(new_entry)
        if status == "A":
            # Includes intent-to-add: an added record has no coherent old
            # identity even when the index contains a placeholder.
            old_mode, old_oid, old_kind = None, None, "missing"
        old = (
            _blob_readonly(root, old_oid, old_kind, deadline, remaining)
            if status != "A"
            else None
        )
        remaining -= len(old or b"")
        new = (
            _blob_readonly(root, new_oid, new_kind, deadline, remaining)
            if status != "D" and not (mode == "diff" and raw in safe_paths)
            else None
        )
        remaining -= len(new or b"")
        if mode == "diff" and raw in safe_paths:
            safe = safe_paths[raw]
            if safe.kind == "directory" and raw not in workspace_entries:
                new_mode, new_kind, new_oid, new = None, "missing", None, None
            else:
                workspace_entry = workspace_entries.get(raw)
                emulated_symlink = (
                    safe.kind == "file"
                    and not epoch.core_symlinks
                    and workspace_entry is not None
                    and workspace_entry.startswith(b"120000 ")
                )
                if (
                    safe.kind == "file"
                    and workspace_entry is not None
                    and (not epoch.core_filemode or emulated_symlink)
                ):
                    new_mode, _temporary_oid, new_kind = _entry_parts(workspace_entry)
                else:
                    new_mode, new_kind = _safe_mode(safe.kind, safe.metadata)
                if raw not in dirty_gitlinks:
                    new_oid = None
                if safe.kind == "missing":
                    new = None
                elif safe.kind in ("file", "symlink") and safe.data is not None:
                    # The conversion guard above proves raw == cleaned.
                    new = safe.data
                    remaining -= len(new)
        path = raw_to_path(raw)
        old_path = raw_to_path(old_raw) if old_raw is not None else None
        unsupported = "dirty_gitlink" if raw in dirty_gitlinks else None
        files.append(
            FrozenFile(
                ChangedFile(
                    path=path,
                    status=status,
                    old_available=old is not None or old_kind == "gitlink",
                    new_available=new is not None or new_kind == "gitlink",
                    binary=raw in binaries,
                    old_path=old_path,
                    patch_available=unsupported is None and raw in patch_row_paths,
                    old_kind=old_kind,
                    new_kind=new_kind,
                    old_mode=old_mode,
                    new_mode=new_mode,
                    old_oid=old_oid,
                    new_oid=new_oid,
                    unsupported_kind=unsupported,
                    _raw_path=raw,
                    _raw_old_path=old_raw,
                ),
                old,
                new,
            )
        )
    return patch, tuple(files)
