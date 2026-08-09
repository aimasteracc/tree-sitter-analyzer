"""Git-backed source inventory for NO1-008A qualification plans."""

from __future__ import annotations

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


def inventory_sources(repo_id: str, repo: Path, rules: SourceRulesV1) -> EligibilityV1:
    """Compute the complete plan-bound source partition from Git and worktree bytes."""
    records = _tracked_stage(repo)
    commit = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked qualification checkout is dirty")
    regular: list[str] = []
    eligible: list[str] = []
    excluded: list[tuple[str, str]] = []
    file_hashes: list[tuple[str, str, str, str]] = []
    extensions = rules.extensions(repo_id)
    for relative, mode, object_id in records:
        if mode in {"160000", "120000"}:
            excluded.append((relative, "gitlink" if mode == "160000" else "symlink"))
            continue
        if mode not in _REGULAR_MODES:
            raise ValueError(f"Unsupported tracked mode {mode}: {relative}")
        # Qualification reads the immutable stage-zero object, never mutable
        # worktree bytes. Verify Git still identifies those exact bytes.
        payload = _git(repo, "cat-file", "blob", object_id)
        verified_object_id = (
            _git(repo, "hash-object", "--stdin", input=payload).decode("ascii").strip()
        )
        if verified_object_id != object_id:
            raise ValueError(f"Pinned Git object mismatch: {relative}")
        regular.append(relative)
        file_hashes.append((relative, mode, object_id, _bytes_hash(payload)))
        components = relative.split("/")
        reason = None
        if PurePosixPath(relative).suffix not in extensions:
            reason = "extension"
        elif any(part in rules.excluded_components for part in components[:-1]):
            reason = "excluded-component"
        elif any(relative.endswith(suffix) for suffix in rules.minified_suffixes):
            reason = "minified"
        elif any(marker in payload[:4096] for marker in rules.generated_markers):
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
