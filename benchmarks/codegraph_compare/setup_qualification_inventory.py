"""Git-backed source inventory for NO1-008A qualification plans."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path, PurePosixPath

from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.setup_qualification_paths import (
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    EligibilityV1,
    SourceRulesV1,
    _bytes_hash,
)

_REGULAR_MODES = {"100644", "100755"}
_GIT_TIMEOUT_SECONDS = 30


def _git(repo: Path, *arguments: str, input: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        input=input,
        capture_output=True,
        check=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).stdout


def _tracked_stage(repo: Path) -> tuple[tuple[str, str, str], ...]:
    records = []
    for raw in _git(repo, "ls-files", "-z", "--stage").split(b"\0"):
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


def _git_object_id(payload: bytes, expected: str) -> str:
    """Recompute a loose-object identity without spawning another Git process."""
    algorithms = {40: "sha1", 64: "sha256"}
    try:
        algorithm = algorithms[len(expected)]
    except KeyError as exc:
        raise ValueError("Unsupported Git object ID length") from exc
    digest = hashlib.new(algorithm)
    digest.update(f"blob {len(payload)}\0".encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


def _parse_batch_blobs(
    output: bytes, requests: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, bytes], ...]:
    """Parse ``git cat-file --batch -Z`` output without delimiter ambiguity."""
    offset = 0
    results: list[tuple[str, bytes]] = []
    for relative, expected_id in requests:
        header_end = output.find(b"\0", offset)
        if header_end < 0:
            raise ValueError(f"Missing Git batch header terminator: {relative}")
        try:
            fields = output[offset:header_end].decode("ascii").split(" ")
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
        payload_start = header_end + 1
        payload_end = payload_start + size
        if payload_end >= len(output) or output[payload_end : payload_end + 1] != b"\0":
            raise ValueError(
                f"Git batch payload size or terminator mismatch: {relative}"
            )
        payload = output[payload_start:payload_end]
        if _git_object_id(payload, expected_id) != expected_id:
            raise ValueError(f"Pinned Git object mismatch: {relative}")
        results.append((relative, payload))
        offset = payload_end + 1
    if offset != len(output):
        raise ValueError("Unexpected trailing Git batch output")
    return tuple(results)


def _batch_blobs(
    repo: Path, requests: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, bytes], ...]:
    """Read every requested pinned blob through one bounded Git process."""
    if not requests:
        return ()
    process = subprocess.Popen(
        ["git", "cat-file", "--batch", "-Z"],
        cwd=repo,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    request_bytes = b"".join(
        object_id.encode("ascii") + b"\0" for _, object_id in requests
    )
    try:
        output, stderr = process.communicate(
            input=request_bytes, timeout=_GIT_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    except BaseException:
        process.kill()
        process.communicate()
        raise
    if process.returncode:
        raise subprocess.CalledProcessError(
            process.returncode,
            process.args,
            output=output,
            stderr=stderr,
        )
    return _parse_batch_blobs(output, requests)


def inventory_sources(repo_id: str, repo: Path, rules: SourceRulesV1) -> EligibilityV1:
    """Compute the complete plan-bound source partition from pinned Git blobs."""
    records = _tracked_stage(repo)
    commit = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked qualification checkout is dirty")
    regular: list[str] = []
    eligible: list[str] = []
    excluded: list[tuple[str, str]] = []
    file_hashes: list[tuple[str, str, str, str]] = []
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

    # Every regular blob binds the repository fingerprint, but only paths that
    # survive metadata rules need content inspection for generated markers.
    requests = tuple(
        (relative, object_id) for relative, _, object_id in regular_records
    )
    payloads = dict(_batch_blobs(repo, requests))
    for relative, mode, object_id in regular_records:
        payload = payloads[relative]
        file_hashes.append((relative, mode, object_id, _bytes_hash(payload)))
        reason = preclassified[relative]
        if reason is None and any(
            marker in payload[:4096] for marker in rules.generated_markers
        ):
            reason = "generated"
        if reason is None:
            eligible.append(relative)
        else:
            excluded.append((relative, reason))
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked qualification checkout changed during inventory")
    if (
        _tracked_stage(repo) != records
        or _git(repo, "rev-parse", "HEAD").decode("ascii").strip() != commit
    ):
        raise ValueError("Pinned Git objects changed during inventory")
    eligible_paths = tuple(eligible)
    return EligibilityV1(
        repo_id,
        rules.digest,
        commit,
        tuple(regular),
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
