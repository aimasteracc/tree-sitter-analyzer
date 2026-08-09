"""Git-backed source inventory for NO1-008A qualification plans."""

from __future__ import annotations

import hashlib
import os
import queue
import subprocess
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Protocol

from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_regular_descriptor,
    _open_beneath,
    _open_root,
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    EligibilityV1,
    SourceRulesV1,
)

_REGULAR_MODES = {"100644", "100755"}
_GIT_TIMEOUT_SECONDS = 30
_GIT_BLOB_CEILING_BYTES = 1024 * 1024 * 1024
_GIT_TOTAL_CEILING_BYTES = 16 * 1024 * 1024 * 1024
_STREAM_CHUNK_BYTES = 1024 * 1024


class _BinaryReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


def _git(repo: Path, *arguments: str, input: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        input=input,
        capture_output=True,
        check=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).stdout


def _canonical_repo(repo: Path) -> Path:
    resolved = repo.resolve()
    raw_root = _git(resolved, "rev-parse", "--show-toplevel")
    try:
        root = Path(raw_root.decode("utf-8").strip()).resolve()
    except UnicodeDecodeError as exc:
        raise ValueError("Git worktree root is not UTF-8") from exc
    if resolved != root:
        raise ValueError(
            "Qualification repository must be the canonical Git worktree root"
        )
    return root


def _tracked_stage(repo: Path) -> tuple[tuple[str, str, str], ...]:
    records = []
    for raw in _git(repo, "ls-files", "-z", "--stage", "--full-name").split(b"\0"):
        if not raw:
            continue
        try:
            metadata, encoded = raw.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split(" ")
            relative = canonical_relative_path(encoded.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError(
                "Malformed, non-UTF-8, or non-canonical tracked path"
            ) from exc
        if stage != "0":
            raise ValueError("Only stage-zero tracked paths are allowed")
        records.append((relative, mode, object_id))
    records.sort()
    if len({item[0] for item in records}) != len(records):
        raise ValueError("Duplicate tracked paths")
    return tuple(records)


def _tracked_flags(repo: Path) -> tuple[tuple[str, str], ...]:
    """Return tracked path tags, rejecting hidden worktree/index divergence flags."""
    records: list[tuple[str, str]] = []
    for raw in _git(repo, "ls-files", "-v", "-z", "--full-name").split(b"\0"):
        if not raw:
            continue
        try:
            tag_bytes, encoded = raw.split(b" ", 1)
            tag = tag_bytes.decode("ascii")
            relative = canonical_relative_path(encoded.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("Malformed tracked index flags") from exc
        if len(tag) != 1:
            raise ValueError("Malformed tracked index flags")
        if tag.islower() or tag == "S":
            raise ValueError(f"Hidden tracked index flag {tag}: {relative}")
        records.append((relative, tag))
    records.sort()
    if len({path for path, _ in records}) != len(records):
        raise ValueError("Duplicate tracked index flag paths")
    return tuple(records)


def _read_exact(stream: _BinaryReader, size: int, relative: str) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise ValueError(f"Git batch payload ended early: {relative}")
        chunks.extend(chunk)
    return bytes(chunks)


def _read_header(stream: _BinaryReader, relative: str) -> bytes:
    header = bytearray()
    while True:
        byte = stream.read(1)
        if not byte:
            raise ValueError(f"Missing Git batch header terminator: {relative}")
        if byte == b"\0":
            return bytes(header)
        header.extend(byte)
        if len(header) > 256:
            raise ValueError(f"Oversized Git batch header: {relative}")


def _parse_header(header: bytes, relative: str, expected_id: str) -> int:
    try:
        fields = header.decode("ascii").split(" ")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Non-ASCII Git batch header: {relative}") from exc
    if len(fields) != 3:
        raise ValueError(f"Malformed Git batch header: {relative}")
    returned_id, object_type, encoded_size = fields
    if (
        returned_id != expected_id
        or object_type != "blob"
        or not encoded_size.isdigit()
        or (len(encoded_size) > 1 and encoded_size.startswith("0"))
    ):
        raise ValueError(f"Unexpected Git batch header: {relative}")
    size = int(encoded_size)
    if size > _GIT_BLOB_CEILING_BYTES:
        raise ValueError(f"Git blob exceeds trusted size ceiling: {relative}")
    return size


def _stream_blob(
    stream: _BinaryReader,
    relative: str,
    expected_id: str,
    total_before: int,
    generated_markers: tuple[bytes, ...] = (),
) -> tuple[str, bool, int]:
    size = _parse_header(_read_header(stream, relative), relative, expected_id)
    if size > _GIT_TOTAL_CEILING_BYTES - total_before:
        raise ValueError("Git blobs exceed trusted total size ceiling")
    algorithms = {40: "sha1", 64: "sha256"}
    try:
        object_digest = hashlib.new(algorithms[len(expected_id)])
    except KeyError as exc:
        raise ValueError("Unsupported Git object ID length") from exc
    object_digest.update(f"blob {size}\0".encode("ascii"))
    content_digest = hashlib.sha256()
    generated = False
    overlap = b""
    overlap_bytes = max((len(marker) for marker in generated_markers), default=1) - 1
    remaining = size
    while remaining:
        chunk = _read_exact(stream, min(remaining, _STREAM_CHUNK_BYTES), relative)
        remaining -= len(chunk)
        object_digest.update(chunk)
        content_digest.update(chunk)
        marker_window = overlap + chunk
        if not generated and any(
            marker in marker_window for marker in generated_markers
        ):
            generated = True
        overlap = marker_window[-overlap_bytes:] if overlap_bytes else b""
    if _read_exact(stream, 1, relative) != b"\0":
        raise ValueError(f"Git batch payload size or terminator mismatch: {relative}")
    if object_digest.hexdigest() != expected_id:
        raise ValueError(f"Pinned Git object mismatch: {relative}")
    return content_digest.hexdigest(), generated, size


def _terminate(process: subprocess.Popen[bytes]) -> None:
    process.kill()
    process.wait()


def _batch_blob_metadata(
    repo: Path,
    requests: tuple[tuple[str, str], ...],
    on_blob: Callable[[str, str, bool, int], None] | None = None,
    generated_markers: tuple[bytes, ...] = (),
) -> tuple[tuple[str, str, bool, int], ...]:
    """Stream pinned blobs once, retaining hashes and marker classifications."""
    if not requests:
        return ()
    with tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            ["git", "cat-file", "--batch", "-Z"],
            cwd=repo,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
        )
        assert process.stdin is not None and process.stdout is not None
        stdin = process.stdin
        stdout = process.stdout
        responses: queue.Queue[tuple[str, str, bool, int] | BaseException] = (
            queue.Queue(maxsize=1)
        )

        def read_responses() -> None:
            total = 0
            try:
                for relative, expected_id in requests:
                    digest, generated, size = _stream_blob(
                        stdout, relative, expected_id, total, generated_markers
                    )
                    total += size
                    responses.put((relative, digest, generated, size))
            except BaseException as exc:
                responses.put(exc)

        reader = threading.Thread(target=read_responses, daemon=True)
        reader.start()
        results: list[tuple[str, str, bool, int]] = []
        try:
            for relative, object_id in requests:
                stdin.write(object_id.encode("ascii") + b"\0")
                stdin.flush()
                try:
                    response = responses.get(timeout=_GIT_TIMEOUT_SECONDS)
                except queue.Empty as exc:
                    raise subprocess.TimeoutExpired(
                        process.args, _GIT_TIMEOUT_SECONDS
                    ) from exc
                if isinstance(response, BaseException):
                    raise response
                if response[0] != relative:
                    raise ValueError("Git batch response order mismatch")
                if on_blob is None:
                    results.append(response)
                else:
                    on_blob(*response)
            stdin.close()
            try:
                returncode = process.wait(timeout=_GIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                _terminate(process)
                raise
            if returncode:
                stderr.seek(0)
                raise subprocess.CalledProcessError(
                    returncode, process.args, stderr=stderr.read()
                )
        except BaseException:
            if process.poll() is None:
                _terminate(process)
            raise
        finally:
            reader.join(timeout=1)
        return tuple(results)


def inventory_sources(repo_id: str, repo: Path, rules: SourceRulesV1) -> EligibilityV1:
    """Compute the complete plan-bound source partition from pinned Git blobs."""
    repo = _canonical_repo(repo)
    records = _tracked_stage(repo)
    flags = _tracked_flags(repo)
    if tuple(path for path, _ in flags) != tuple(path for path, _, _ in records):
        raise ValueError("Tracked index flags do not match the pinned inventory")
    commit = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"
    ):
        raise ValueError("Qualification checkout contains tracked or untracked changes")
    regular: list[str] = []
    eligible: list[str] = []
    excluded: list[tuple[str, str]] = []
    file_hashes: list[tuple[str, str, str, str]] = []
    tracked_files: list[tuple[str, str, str, int, str]] = []
    extensions = rules.extensions(repo_id)
    regular_records: list[tuple[str, str, str]] = []
    preclassified: dict[str, str | None] = {}
    for relative, mode, object_id in records:
        if mode in {"160000", "120000"}:
            excluded.append((relative, "gitlink" if mode == "160000" else "symlink"))
            continue
        if mode not in _REGULAR_MODES:
            raise ValueError(f"Unsupported tracked mode {mode}: {relative}")
        regular.append(relative)
        regular_records.append((relative, mode, object_id))
        components = relative.split("/")
        reason = None
        if PurePosixPath(relative).suffix not in extensions:
            reason = "extension"
        elif any(part in rules.excluded_components for part in components[:-1]):
            reason = "excluded-component"
        elif any(relative.endswith(suffix) for suffix in rules.minified_suffixes):
            reason = "minified"
        preclassified[relative] = reason

    requests = tuple(
        (relative, object_id) for relative, _, object_id in regular_records
    )
    record_by_path = {
        relative: (mode, object_id) for relative, mode, object_id in regular_records
    }

    root_fd = _open_root(repo)
    worktree_bytes_consumed = 0

    def consume_blob(
        relative: str, content_hash: str, generated: bool, size: int
    ) -> None:
        nonlocal worktree_bytes_consumed
        mode, object_id = record_by_path[relative]
        file_hashes.append((relative, mode, object_id, content_hash))
        tracked_files.append((relative, mode, object_id, size, content_hash))
        reason = preclassified[relative]
        if reason is None and generated:
            reason = "generated"
        if reason is None:
            descriptor: int | None = None
            try:
                descriptor = _open_beneath(root_fd, relative)
                size = os.fstat(descriptor).st_size
                if size > _GIT_BLOB_CEILING_BYTES or (
                    size > _GIT_TOTAL_CEILING_BYTES - worktree_bytes_consumed
                ):
                    raise ValueError(
                        f"Eligible worktree file exceeds trusted size ceiling: {relative}"
                    )
                worktree_hash = _hash_regular_descriptor(
                    descriptor, expected_size=size, max_bytes=_GIT_BLOB_CEILING_BYTES
                )
                if worktree_hash != content_hash:
                    raise ValueError(
                        f"Eligible worktree bytes do not match pinned blob: {relative}"
                    )
                worktree_bytes_consumed += size
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            eligible.append(relative)
        else:
            excluded.append((relative, reason))

    try:
        _batch_blob_metadata(
            repo,
            requests,
            on_blob=consume_blob,
            generated_markers=rules.generated_markers,
        )
    finally:
        os.close(root_fd)
    if _git(
        repo, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"
    ):
        raise ValueError("Qualification checkout changed during inventory")
    if (
        _tracked_stage(repo) != records
        or _tracked_flags(repo) != flags
        or _git(repo, "rev-parse", "HEAD").decode("ascii").strip() != commit
    ):
        raise ValueError("Pinned Git objects changed during inventory")
    eligible_paths = tuple(eligible)
    return EligibilityV1(
        repo_id,
        rules.digest,
        commit,
        tuple(regular),
        records,
        tuple(tracked_files),
        eligible_paths,
        tuple(sorted(excluded)),
        _sha256([(p, m, oid) for p, m, oid in records]),
        _sha256(list(eligible_paths)),
        _sha256(
            {
                "commit": commit,
                "inventory": [(p, m, oid) for p, m, oid in records],
                "files": file_hashes,
            }
        ),
    )
