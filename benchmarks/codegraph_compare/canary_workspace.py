"""Model-free checkout immutability evidence for the NO1-002C canary."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from benchmarks.codegraph_compare.smoke_evidence import (
    repository_fingerprint,
    tracked_paths,
)
from benchmarks.codegraph_compare.smoke_workspace import cleanup_runtime_index

RUNTIME_NAMESPACES = {"tsa-warm": ".ast-cache", "codegraph-warm": ".codegraph"}


@dataclass(frozen=True)
class CanaryCheckoutSnapshot:
    """Byte-level identity of a canary checkout outside its runtime namespace."""

    arm: str
    checkout_root: Path
    head_commit: str
    tracked_paths: tuple[str, ...]
    repository_fingerprint: str
    source_inventory: tuple[tuple[str, str], ...]
    runtime_namespace: str
    runtime_before: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CanaryWorkspaceAudit:
    """Before/after evidence kept separately for the derived runtime namespace."""

    checkout_root: Path
    head_commit: str
    tracked_paths: tuple[str, ...]
    repository_fingerprint: str
    source_before: tuple[tuple[str, str], ...]
    source_after: tuple[tuple[str, str], ...]
    runtime_namespace: str
    runtime_before: tuple[tuple[str, str], ...]
    runtime_after: tuple[tuple[str, str], ...]


def _git(checkout: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _require_physical_directory(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be a real directory")


def _hash_inventory(
    root: Path, excluded_root: str | None
) -> tuple[tuple[str, str], ...]:
    inventory: list[tuple[str, str]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        relative_dir = Path(current).relative_to(root)
        directories[:] = sorted(
            name
            for name in directories
            if not (
                relative_dir == Path(".")
                and (
                    name == excluded_root
                    or (excluded_root is not None and name == ".git")
                )
            )
        )
        for name in (*directories, *sorted(files)):
            path = Path(current) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"checkout inventory contains symlink: {path}")
            if stat.S_ISREG(mode):
                if path.stat().st_nlink != 1:
                    raise ValueError(f"checkout inventory contains hardlink: {path}")
                relative = path.relative_to(root).as_posix()
                inventory.append(
                    (relative, hashlib.sha256(path.read_bytes()).hexdigest())
                )
            elif not stat.S_ISDIR(mode):
                raise ValueError(f"checkout inventory contains special node: {path}")
    return tuple(sorted(inventory))


def _runtime_path(root: Path, namespace: str) -> Path:
    runtime = root / namespace
    if runtime.parent.resolve(strict=True) != root:
        raise ValueError("runtime namespace escapes exact checkout")
    return runtime


def snapshot_canary_checkout(checkout: Path, arm: str) -> CanaryCheckoutSnapshot:
    """Capture a clean checkout before the arm creates its runtime index."""

    if arm not in RUNTIME_NAMESPACES:
        raise ValueError(f"unsupported canary arm: {arm}")
    supplied = checkout.absolute()
    _require_physical_directory(supplied, "checkout")
    root = supplied.resolve(strict=True)
    if supplied != root:
        raise ValueError("checkout path must be its resolved physical root")
    namespace = RUNTIME_NAMESPACES[arm]
    foreign = ".codegraph" if namespace == ".ast-cache" else ".ast-cache"
    if os.path.lexists(root / foreign):
        raise ValueError("checkout contains cross-arm runtime namespace")
    runtime = _runtime_path(root, namespace)
    if os.path.lexists(runtime):
        raise ValueError("declared runtime namespace must be absent before execution")
    tracked = tracked_paths(root)
    return CanaryCheckoutSnapshot(
        arm=arm,
        checkout_root=root,
        head_commit=_git(root, "rev-parse", "HEAD"),
        tracked_paths=tracked,
        repository_fingerprint=repository_fingerprint(root, tracked),
        source_inventory=_hash_inventory(root, namespace),
        runtime_namespace=namespace,
        runtime_before=(),
    )


def audit_canary_checkout(snapshot: CanaryCheckoutSnapshot) -> CanaryWorkspaceAudit:
    """Reject any checkout mutation outside the arm's exact runtime directory."""

    root = snapshot.checkout_root
    _require_physical_directory(root, "checkout")
    if root.resolve(strict=True) != root:
        raise ValueError("checkout root identity changed")
    if _git(root, "rev-parse", "HEAD") != snapshot.head_commit:
        raise ValueError("checkout HEAD changed")
    tracked = tracked_paths(root)
    if tracked != snapshot.tracked_paths:
        raise ValueError("tracked path inventory changed")
    try:
        fingerprint = repository_fingerprint(root, tracked)
    except ValueError as error:
        raise ValueError("tracked repository content changed") from error
    if fingerprint != snapshot.repository_fingerprint:
        raise ValueError("tracked repository content changed")
    source_after = _hash_inventory(root, snapshot.runtime_namespace)
    if source_after != snapshot.source_inventory:
        raise ValueError("non-runtime checkout inventory changed")
    foreign = (
        ".codegraph" if snapshot.runtime_namespace == ".ast-cache" else ".ast-cache"
    )
    if os.path.lexists(root / foreign):
        raise ValueError("checkout contains cross-arm runtime namespace")
    runtime = _runtime_path(root, snapshot.runtime_namespace)
    _require_physical_directory(runtime, "runtime namespace")
    runtime_after = _hash_inventory(runtime, None)
    return CanaryWorkspaceAudit(
        checkout_root=root,
        head_commit=snapshot.head_commit,
        tracked_paths=tracked,
        repository_fingerprint=fingerprint,
        source_before=snapshot.source_inventory,
        source_after=source_after,
        runtime_namespace=snapshot.runtime_namespace,
        runtime_before=snapshot.runtime_before,
        runtime_after=runtime_after,
    )


def cleanup_and_verify_canary_checkout(
    snapshot: CanaryCheckoutSnapshot, audit: CanaryWorkspaceAudit | None
) -> None:
    """Remove only the declared runtime directory and prove checkout restoration."""

    runtime = _runtime_path(snapshot.checkout_root, snapshot.runtime_namespace)
    if audit is not None:
        if audit.checkout_root != snapshot.checkout_root:
            raise ValueError("audit checkout does not match snapshot")
        if (
            audit.runtime_namespace != snapshot.runtime_namespace
            or audit.source_before != snapshot.source_inventory
            or audit.runtime_before != snapshot.runtime_before
        ):
            raise ValueError("audit evidence does not match snapshot")
        if _hash_inventory(runtime, None) != audit.runtime_after:
            raise ValueError("runtime namespace changed after audit")
    if os.path.lexists(runtime):
        cleanup_runtime_index(
            snapshot.checkout_root, snapshot.runtime_namespace, runtime
        )
    if os.path.lexists(runtime):
        raise ValueError("runtime namespace cleanup failed")
    if (
        _hash_inventory(snapshot.checkout_root, snapshot.runtime_namespace)
        != snapshot.source_inventory
    ):
        raise ValueError("checkout changed during runtime cleanup")
    if _git(snapshot.checkout_root, "rev-parse", "HEAD") != snapshot.head_commit:
        raise ValueError("checkout HEAD changed during runtime cleanup")
    tracked = tracked_paths(snapshot.checkout_root)
    if tracked != snapshot.tracked_paths:
        raise ValueError("tracked paths changed during runtime cleanup")
    try:
        fingerprint = repository_fingerprint(snapshot.checkout_root, tracked)
    except ValueError as error:
        raise ValueError("tracked content changed during runtime cleanup") from error
    if fingerprint != snapshot.repository_fingerprint:
        raise ValueError("tracked content changed during runtime cleanup")
