"""Strict physical-workspace isolation for the NO1-001B Gin Smoke."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.integrity import ExperimentManifestV1
from benchmarks.codegraph_compare.smoke_evidence import (
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
_CELL_KEYS = frozenset(
    {"arm_id", "checkout_path", "index_path", "artifact_path"}
)


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
    if any(type(value) is not str or not value for value in (experiment_id, manifest_hash)):
        raise ValueError("workspace identity fields must be non-empty strings")
    return SmokeWorkspaceV1(experiment_id, manifest_hash, tuple(cells))


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _require_disjoint(paths: tuple[Path, ...], label: str) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if _paths_overlap(left, right):
                raise ValueError(f"{label} namespace collision: {left} <> {right}")


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
        paths.update(
            item.decode("utf-8") for item in output.split(b"\0") if item
        )
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
    _require_disjoint(checkouts, "checkout")
    _require_disjoint(artifacts, "artifact")
    _require_disjoint(indexes, "index")
    if any(path.is_symlink() for path in (*checkouts, *artifacts)):
        raise ValueError("checkout and artifact namespaces cannot be symlinks")
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
        expected_index = (
            None if index_name is None else cell.checkout_path / index_name
        )
        if cell.index_path != expected_index:
            raise ValueError(f"{cell.arm_id} index namespace mismatch")
        forbidden = (
            (".ast-cache", ".codegraph")
            if cell.arm_id == "native-only"
            else (".codegraph",)
            if cell.arm_id == "tsa-warm"
            else (".ast-cache",)
        )
        if any((cell.checkout_path / name).exists() for name in forbidden):
            raise ValueError(f"{cell.arm_id} contains a foreign index namespace")
        if cell.index_path is not None:
            if cell.index_path.is_symlink():
                raise ValueError(f"{cell.arm_id} index namespace is a symlink")
            if cell.index_path.resolve().parent != cell.checkout_path.resolve():
                raise ValueError(f"{cell.arm_id} index namespace escapes checkout")
        unprovenanced = _unprovenanced_paths(cell.checkout_path, index_name)
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
