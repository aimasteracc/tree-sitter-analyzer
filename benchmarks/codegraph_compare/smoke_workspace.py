"""Strict physical-workspace isolation for the NO1-001B Gin Smoke."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.integrity import ExperimentManifestV1
from benchmarks.codegraph_compare.smoke_evidence import (
    INDEX_LAYOUT,
    canonical_semantic_digest,
    index_content_hash,
    inspect_frozen_index,
    repository_fingerprint,
    tracked_paths,
)

_ARMS = ("native-only", "tsa-warm", "codegraph-warm")
_INDEX_DIRS = {
    "native-only": None,
    "tsa-warm": ".ast-cache",
    "codegraph-warm": ".codegraph",
}
_WORKSPACE_KEYS = frozenset(
    {"schema_version", "experiment_id", "manifest_hash", "cells"}
)
_CELL_KEYS = frozenset({"arm_id", "checkout_path", "index_path", "artifact_path"})


class IndexContentDriftError(ValueError):
    """The live index no longer matches its manifest-bound content."""


@dataclass(frozen=True)
class WorkspaceCellV1:
    """One arm's physical checkout, index, and artifact boundaries."""

    arm_id: str
    checkout_path: Path
    index_path: Path | None
    artifact_path: Path


@dataclass(frozen=True)
class SmokeWorkspaceV1:
    """Manifest-bound physical namespaces for all three Smoke arms."""

    experiment_id: str
    manifest_hash: str
    cells: tuple[WorkspaceCellV1, ...]

    def cell(self, arm_id: str) -> WorkspaceCellV1:
        return next(cell for cell in self.cells if cell.arm_id == arm_id)


def _exact_keys(raw: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(raw)
    if actual != expected:
        raise ValueError(
            f"{label} keys mismatch; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _absolute_path(value: Any, label: str) -> Path:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path.absolute()


def parse_workspace_v1(raw: Any) -> SmokeWorkspaceV1:
    """Parse a strict workspace sidecar without accepting extension fields."""

    if not isinstance(raw, dict):
        raise ValueError("workspace evidence must be a JSON object")
    _exact_keys(raw, _WORKSPACE_KEYS, "workspace")
    if raw["schema_version"] != 1:
        raise ValueError("workspace schema_version must equal 1")
    if not isinstance(raw["cells"], list):
        raise ValueError("workspace cells must be a list")
    cells: list[WorkspaceCellV1] = []
    for index, item in enumerate(raw["cells"]):
        if not isinstance(item, dict):
            raise ValueError(f"workspace cell {index} must be an object")
        _exact_keys(item, _CELL_KEYS, f"workspace cell {index}")
        arm_id = item["arm_id"]
        if type(arm_id) is not str:
            raise ValueError(f"workspace cell {index} arm_id must be a string")
        index_value = item["index_path"]
        index_path = (
            None
            if index_value is None
            else _absolute_path(index_value, f"{arm_id} index_path")
        )
        cells.append(
            WorkspaceCellV1(
                arm_id=arm_id,
                checkout_path=_absolute_path(
                    item["checkout_path"], f"{arm_id} checkout_path"
                ),
                index_path=index_path,
                artifact_path=_absolute_path(
                    item["artifact_path"], f"{arm_id} artifact_path"
                ),
            )
        )
    experiment_id = raw["experiment_id"]
    manifest_hash = raw["manifest_hash"]
    if any(
        type(value) is not str or not value for value in (experiment_id, manifest_hash)
    ):
        raise ValueError("workspace identity fields must be non-empty strings")
    return SmokeWorkspaceV1(experiment_id, manifest_hash, tuple(cells))


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _require_disjoint(paths: tuple[Path, ...], label: str) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if _paths_overlap(left, right):
                raise ValueError(f"{label} namespace collision: {left} <> {right}")


def _canonical_root(path: Path, label: str) -> Path:
    """Reject symlinks in every existing component and return physical identity."""

    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() and current.is_symlink():
            raise ValueError(f"{label} namespace contains a symlink: {current}")
    return path.resolve(strict=False)


def _reject_special_tree(root: Path, label: str) -> None:
    """Require every existing index node to be a physical file or directory."""

    if not root.exists():
        return
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            path = Path(current) / name
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"{label} namespace contains a special node: {path}")
            if stat.S_ISREG(mode) and path.stat().st_nlink != 1:
                raise ValueError(
                    f"{label} namespace contains a hardlinked file: {path}"
                )


def _regular_inventory(root: Path, database_name: str) -> dict[str, str]:
    """Classify every regular file; reject undeclared DBs and sidecars."""

    inventory = {}
    primary = Path(database_name)
    allowed_sidecars = {
        Path(database_name + suffix) for suffix in ("-wal", "-shm", "-journal")
    }
    primary_count = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if relative == primary:
            primary_count += 1
            continue
        if relative in allowed_sidecars:
            continue
        if path.name.endswith(("-wal", "-shm", "-journal")):
            raise ValueError(f"undeclared SQLite sidecar: {relative.as_posix()}")
        if path.suffix in {".db", ".sqlite", ".sqlite3"}:
            raise ValueError(f"undeclared SQLite database: {relative.as_posix()}")
        inventory[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if primary_count != 1:
        raise ValueError("index must contain exactly one top-level primary database")
    return inventory


def create_frozen_index_snapshot(
    source: Path,
    target: Path,
    arm: str,
    expected_paths: tuple[str, ...],
) -> Path:
    """Create one consistent arm-specific frozen index via SQLite backup."""

    if arm not in INDEX_LAYOUT:
        raise ValueError(f"Unsupported indexed Smoke arm: {arm}")
    _, database_name = INDEX_LAYOUT[arm]
    source_root = _canonical_root(source, "live index")
    target_root = target.absolute()
    temporary = target_root.with_name(target_root.name + ".materializing")
    if _paths_overlap(source_root, target_root) or _paths_overlap(
        source_root, temporary
    ):
        raise ValueError("frozen snapshot overlaps live index")
    if os.path.lexists(target_root) or os.path.lexists(temporary):
        raise ValueError("frozen snapshot destination already exists")
    _reject_special_tree(source_root, "live index")
    before = _regular_inventory(source_root, database_name)
    try:
        temporary.mkdir(parents=True)
        for relative in before:
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / relative, destination)
        source_db = sqlite3.connect(
            f"file:{source_root / database_name}?mode=ro", uri=True, timeout=0
        )
        destination_db = sqlite3.connect(temporary / database_name)
        try:
            source_db.backup(destination_db)
        finally:
            destination_db.close()
            source_db.close()
        if _regular_inventory(source_root, database_name) != before:
            raise ValueError("live non-database index files changed during snapshot")
        observed_paths = inspect_frozen_index(arm, temporary)
        if observed_paths != expected_paths:
            raise ValueError("frozen index paths do not match index evidence")
        temporary.rename(target_root)
    except Exception:
        if os.path.lexists(temporary) and not temporary.is_symlink():
            shutil.rmtree(temporary)
        raise
    return target_root


def runtime_index_path(checkout: Path, index_name: str) -> Path:
    """Resolve the one permitted runtime index path under a checkout."""

    if index_name not in {".ast-cache", ".codegraph"}:
        raise ValueError(f"unsupported runtime index name: {index_name}")
    checkout_root = _canonical_root(checkout, "checkout")
    return checkout_root / index_name


def materialize_runtime_index(
    baseline: Path,
    checkout: Path,
    arm: str,
    expected_hash: str,
    expected_paths: tuple[str, ...],
) -> Path:
    """Publish a verified private index copy at the tool's fixed namespace."""

    if arm not in INDEX_LAYOUT:
        raise ValueError(f"Unsupported indexed Smoke arm: {arm}")
    index_name, _ = INDEX_LAYOUT[arm]
    baseline_root = _canonical_root(baseline, "frozen index")
    runtime = runtime_index_path(checkout, index_name)
    temporary = runtime.with_name(runtime.name + ".materializing")
    if _paths_overlap(baseline_root, _canonical_root(checkout, "checkout")):
        raise ValueError("frozen index overlaps checkout")
    if _paths_overlap(baseline_root, runtime) or _paths_overlap(
        baseline_root, temporary
    ):
        raise ValueError("frozen index overlaps runtime namespace")
    if os.path.lexists(runtime):
        raise ValueError("runtime index already exists")
    if os.path.lexists(temporary):
        raise ValueError("materialization residue exists")
    _reject_special_tree(baseline_root, "frozen index")
    baseline_before = index_content_hash(baseline_root)
    if baseline_before != expected_hash:
        raise IndexContentDriftError("frozen index content hash mismatch")
    try:
        shutil.copytree(baseline_root, temporary, copy_function=shutil.copy2)
        _reject_special_tree(temporary, "runtime index")
        if index_content_hash(temporary) != expected_hash:
            raise IndexContentDriftError("runtime index copy hash mismatch")
        if inspect_frozen_index(arm, temporary) != expected_paths:
            raise ValueError("runtime index paths do not match index evidence")
        if index_content_hash(temporary) != expected_hash:
            raise ValueError("fixed oracle mutated runtime index")
        if index_content_hash(baseline_root) != expected_hash:
            raise IndexContentDriftError("frozen index changed during materialization")
        _require_distinct_file_inodes(baseline_root, temporary)
        temporary.rename(runtime)
    except Exception:
        if os.path.lexists(temporary) and not temporary.is_symlink():
            shutil.rmtree(temporary)
        raise
    return runtime


def audit_runtime_index(
    runtime: Path,
    audit_target: Path,
    arm: str,
    expected_paths: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    """Snapshot a quiesced runtime index and return canonical semantics."""

    snapshot = create_frozen_index_snapshot(runtime, audit_target, arm, expected_paths)
    _, database_name = INDEX_LAYOUT[arm]
    try:
        paths = inspect_frozen_index(arm, snapshot)
        digest = canonical_semantic_digest(snapshot / database_name)
    finally:
        shutil.rmtree(snapshot)
    return digest, paths


def _require_distinct_file_inodes(baseline: Path, runtime: Path) -> None:
    """Prove corresponding regular files are physical copies."""

    for source in sorted(path for path in baseline.rglob("*") if path.is_file()):
        target = runtime / source.relative_to(baseline)
        if not target.is_file():
            raise ValueError(f"runtime index file missing: {target}")
        if (source.stat().st_dev, source.stat().st_ino) == (
            target.stat().st_dev,
            target.stat().st_ino,
        ):
            raise ValueError(f"runtime index shares inode: {target}")


def cleanup_runtime_index(checkout: Path, index_name: str, target: Path) -> None:
    """Remove only the exact derived runtime namespace, never an arbitrary path."""

    expected = runtime_index_path(checkout, index_name)
    target_normalized = Path(os.path.normpath(os.fspath(target.absolute())))
    if target_normalized != expected.absolute():
        raise ValueError("runtime cleanup target mismatch")
    if os.path.lexists(target) and target.is_symlink():
        raise ValueError("runtime cleanup target is a symlink")
    if target.exists():
        _reject_special_tree(target, "runtime index")
        shutil.rmtree(target)


def validate_index_content_v1(
    workspace: SmokeWorkspaceV1,
    manifest: ExperimentManifestV1,
    arm_id: str,
) -> None:
    """Revalidate one indexed arm against its manifest-bound byte digest."""

    cell = workspace.cell(arm_id)
    expected = dict(manifest.index_content_hashes).get(arm_id)
    if cell.index_path is None or expected is None:
        raise IndexContentDriftError(f"{arm_id} lacks manifest-bound index content")
    _reject_special_tree(cell.index_path, "index")
    if index_content_hash(cell.index_path) != expected:
        raise IndexContentDriftError(f"{arm_id} index content hash mismatch")


def _git_output(checkout: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _unprovenanced_paths(checkout: Path, allowed_root: str | None) -> tuple[str, ...]:
    paths: set[str] = set()
    for args in (
        ("ls-files", "-z", "--others", "--exclude-standard"),
        ("ls-files", "-z", "--others", "--ignored", "--exclude-standard"),
    ):
        output = subprocess.run(
            ["git", *args],
            cwd=checkout,
            capture_output=True,
            check=True,
        ).stdout
        paths.update(item.decode("utf-8") for item in output.split(b"\0") if item)
    if allowed_root is not None:
        prefix = allowed_root + "/"
        paths = {
            path
            for path in paths
            if path != allowed_root and not path.startswith(prefix)
        }
    return tuple(sorted(paths))


def validate_workspace_v1(
    workspace: SmokeWorkspaceV1,
    manifest: ExperimentManifestV1,
) -> None:
    """Prove checkout identity and namespace isolation before model execution."""

    if (
        workspace.experiment_id != manifest.experiment_id
        or workspace.manifest_hash != manifest.manifest_hash
    ):
        raise ValueError("workspace identity does not match the manifest")
    arms = tuple(cell.arm_id for cell in workspace.cells)
    if arms != manifest.required_arms or arms != _ARMS:
        raise ValueError(f"workspace arms must equal {_ARMS}")
    checkouts = tuple(cell.checkout_path for cell in workspace.cells)
    artifacts = tuple(cell.artifact_path for cell in workspace.cells)
    indexes = tuple(
        cell.index_path for cell in workspace.cells if cell.index_path is not None
    )
    checkouts = tuple(_canonical_root(path, "checkout") for path in checkouts)
    artifacts = tuple(_canonical_root(path, "artifact") for path in artifacts)
    indexes = tuple(_canonical_root(path, "index") for path in indexes)
    _require_disjoint(checkouts, "checkout")
    _require_disjoint(artifacts, "artifact")
    _require_disjoint(indexes, "index")
    runtime_indexes = tuple(
        cell.checkout_path / _INDEX_DIRS[cell.arm_id]
        for cell in workspace.cells
        if _INDEX_DIRS[cell.arm_id] is not None
    )
    for index in indexes:
        if any(_paths_overlap(index, checkout) for checkout in checkouts):
            raise ValueError("frozen index overlaps checkout")
        if any(_paths_overlap(index, artifact) for artifact in artifacts):
            raise ValueError("frozen index overlaps artifact")
        if any(_paths_overlap(index, runtime) for runtime in runtime_indexes):
            raise ValueError("frozen index overlaps runtime")
        _reject_special_tree(index, "index")
    for cell in workspace.cells:
        expected_index_hash = dict(manifest.index_content_hashes).get(cell.arm_id)
        if cell.index_path is not None and expected_index_hash is not None:
            validate_index_content_v1(workspace, manifest, cell.arm_id)
    if any(
        _paths_overlap(artifact, checkout)
        for artifact in artifacts
        for checkout in checkouts
    ):
        raise ValueError("artifact namespaces must be outside every checkout")

    expected_commit = dict(manifest.repo_commits)["gin"]
    expected_fingerprint = dict(manifest.repo_fingerprints)["gin"]
    for cell in workspace.cells:
        if not cell.checkout_path.is_dir():
            raise ValueError(f"{cell.arm_id} checkout does not exist")
        if _git_output(cell.checkout_path, "rev-parse", "HEAD") != expected_commit:
            raise ValueError(f"{cell.arm_id} checkout commit mismatch")
        if _git_output(
            cell.checkout_path, "status", "--porcelain", "--untracked-files=no"
        ):
            raise ValueError(f"{cell.arm_id} checkout has tracked modifications")
        if (
            repository_fingerprint(
                cell.checkout_path, tracked_paths(cell.checkout_path)
            )
            != expected_fingerprint
        ):
            raise ValueError(f"{cell.arm_id} repository fingerprint mismatch")

        index_name = _INDEX_DIRS[cell.arm_id]
        if index_name is None and cell.index_path is not None:
            raise ValueError(f"{cell.arm_id} cannot have frozen index content")
        if index_name is not None and cell.index_path is None:
            raise ValueError(f"{cell.arm_id} lacks frozen index content")
        forbidden = (
            (".ast-cache", ".codegraph")
            if cell.arm_id == "native-only"
            else (".codegraph",)
            if cell.arm_id == "tsa-warm"
            else (".ast-cache",)
        )
        if any((cell.checkout_path / name).exists() for name in forbidden):
            raise ValueError(f"{cell.arm_id} contains a foreign index namespace")
        runtime_index = None if index_name is None else cell.checkout_path / index_name
        if runtime_index is not None and runtime_index.exists():
            raise ValueError(f"{cell.arm_id} runtime index already exists")
        residue = (
            None
            if runtime_index is None
            else runtime_index.with_name(runtime_index.name + ".materializing")
        )
        if residue is not None and residue.exists():
            raise ValueError(f"{cell.arm_id} materialization residue exists")
        unprovenanced = _unprovenanced_paths(cell.checkout_path, None)
        if unprovenanced:
            raise ValueError(
                f"{cell.arm_id} contains unprovenanced paths: {unprovenanced}"
            )
        if cell.index_path is not None and not cell.index_path.is_dir():
            raise ValueError(f"{cell.arm_id} index namespace does not exist")
        if not cell.artifact_path.is_dir():
            raise ValueError(f"{cell.arm_id} artifact namespace does not exist")
        if any(cell.artifact_path.iterdir()):
            raise ValueError(f"{cell.arm_id} artifact namespace is not empty")
