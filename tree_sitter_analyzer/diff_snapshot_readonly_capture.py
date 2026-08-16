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


def _git_quote_path(raw: bytes) -> bytes:
    """Quote one path for a synthetic diff header (git ``quote_c_style``)."""
    needs = any(value < 0x20 or value > 0x7E or value in (0x22, 0x5C) for value in raw)
    if not needs:
        return raw
    out = bytearray(b'"')
    shorthand = {
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
    for value in raw:
        if value in shorthand:
            out.extend(shorthand[value])
        elif value < 0x20 or value > 0x7E:
            out.extend(f"\\{value:03o}".encode("ascii"))
        else:
            out.append(value)
    out.append(0x22)
    return bytes(out)


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
    when no checkin conversion applies. Conversions can only alter a
    non-binary file that already contains CRLF, so the guard is: any such
    file plus an active conversion configuration (``core.autocrlf``,
    ``eol`` attribute, or ``working-tree-encoding`` attribute) fails the
    route closed with a stable code.
    """
    candidates = sorted(
        (raw, safe)
        for raw, safe in safe_paths.items()
        if safe.kind in ("file", "symlink")
        and safe.data is not None
        and not _is_binary(safe.data)
        and b"\r\n" in safe.data
    )
    if not candidates:
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
    attr_input = b"".join(raw + b"\0" for raw, _safe in candidates)
    attributes = _live_index_output(
        root,
        b"",
        ["check-attr", "-z", "eol", "working-tree-encoding", "--stdin"],
        deadline=deadline,
        limit=16 * 1024 * 1024,
        input_=attr_input,
    )
    tokens = [token for token in attributes.split(b"\0") if token]
    if len(tokens) % 3 != 0:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    for index in range(0, len(tokens), 3):
        _path, attr, value = tokens[index : index + 3]
        if attr == b"eol" and value in (b"crlf", b"lf"):
            raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION")
        if attr == b"working-tree-encoding" and value not in (
            b"unspecified",
            b"unset",
        ):
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
    ``R100``. This replicates the exact-rename half with a deterministic
    greedy pairing; content-modified moves stay delete+add pairs (a
    documented divergence from the frozen inexact ``R``).
    """
    deleted = [
        row for row in rows if row[0] == "D" and (row[1] or row[2]) in index_entries
    ]
    added = [row for row in rows if row[0] == "A" and row[2] in safe_paths]
    if not deleted or not added:
        return rows
    added_paths = {row[2] for row in added}
    pairs: dict[bytes, bytes] = {}
    used: set[bytes] = set()
    for _status, old_raw, raw in deleted:
        lookup = old_raw or raw
        mode, oid, kind = _entry_parts(index_entries[lookup])
        old = _blob_readonly(root, oid, kind, deadline, limit)
        if old is None:
            continue
        for _new_status, _new_old, new_raw in added:
            if new_raw in used:
                continue
            safe = safe_paths[new_raw]
            if safe.data == old:
                pairs[lookup] = new_raw
                used.add(new_raw)
                break
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
        body = body[len(b"diff --git ") :]
        if body.startswith(b'"'):
            end = body.find(b'"', 1)
            if end < 0:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            first = body[1:end]
        else:
            first = body.split(b" ", 1)[0]
        if not first.startswith(b"a/"):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        destination = first[2:]
        sections.setdefault(destination, _strip_one_newline(token))
    return sections


def _synthesize_rename_section(old_raw: bytes, new_raw: bytes) -> bytes:
    """Byte-identical 100%-rename section header body."""
    return (
        b"diff --git a/"
        + _git_quote_path(old_raw)
        + b" b/"
        + _git_quote_path(new_raw)
        + b"\nsimilarity index 100%\nrename from "
        + _git_quote_path(old_raw)
        + b"\nrename to "
        + _git_quote_path(new_raw)
        + b"\n"
    )


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
                synthetic[raw] = _synthesize_rename_section(old_raw or raw, raw)
            elif status == "A" and raw in safe_paths and raw not in sections:
                synthetic[raw] = _no_index_new_file_patch(
                    root, raw, deadline, min(64 * 1024 * 1024, remaining)
                )
                remaining -= len(synthetic[raw])
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
