"""Symlink-safe append-only evidence collection for the production boundary."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _component(value: str, label: str) -> str:
    if not value or value in (".", "..") or "/" in value or "\\" in value:
        raise ValueError(f"{label} must not contain path separators: {value!r}")
    return value


def _open_parent_and_create_root(root: Path) -> tuple[int, int, tuple[int, int]]:
    """Walk from / with openat/O_NOFOLLOW, then exclusively mkdir the root."""
    absolute = root.resolve(strict=False)
    if not absolute.is_absolute() or absolute != root:
        raise ValueError("Artifact root must be a canonical absolute path")
    parts = absolute.parts[1:]
    fd = os.open("/", _DIR_FLAGS)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=fd)
                os.fsync(fd)
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        os.mkdir(parts[-1], 0o700, dir_fd=fd)
        os.fsync(fd)
        root_fd = os.open(parts[-1], _DIR_FLAGS, dir_fd=fd)
        st = os.fstat(root_fd)
        return fd, root_fd, (st.st_dev, st.st_ino)
    except Exception:
        os.close(fd)
        raise


@dataclass(frozen=True)
class ArtifactReceipt:
    kind: str
    run_id: str
    path: str
    sha256: str


@dataclass(frozen=True)
class CollectionReceipt:
    root: str
    artifact_count: int
    ledger_sha256: str
    artifacts: tuple[ArtifactReceipt, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "artifact_count": self.artifact_count,
            "ledger_sha256": self.ledger_sha256,
            "artifacts": [a.__dict__ for a in self.artifacts],
        }


class EvidenceCollector:
    """Collector whose writes remain bound to pinned directory inodes."""

    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root
        try:
            self._parent_fd, self._root_fd, self._pin = _open_parent_and_create_root(
                artifact_root
            )
        except FileExistsError as error:
            raise ValueError(
                f"Artifact root must not pre-exist; cannot guarantee immutability: {artifact_root}"
            ) from error
        self._artifacts: list[ArtifactReceipt] = []
        self._fds: dict[tuple[str, str], tuple[int, int]] = {}
        self._finalized = False

    @property
    def root(self) -> Path:
        return self._root

    def _assert_pin(self) -> None:
        try:
            st = os.stat(self._root, follow_symlinks=False)
        except OSError as error:
            raise RuntimeError("Evidence root inode is no longer reachable") from error
        if stat.S_ISLNK(st.st_mode) or (st.st_dev, st.st_ino) != self._pin:
            raise RuntimeError("Evidence root inode changed during collection")

    def collect(self, run_id: str, kind: str, payload: bytes) -> ArtifactReceipt:
        if self._finalized:
            raise RuntimeError(
                "Collector is already finalised; no further artifacts accepted"
            )
        _component(run_id, "run_id")
        _component(kind, "kind")
        if type(payload) is not bytes:
            raise ValueError("payload must be exact bytes")
        self._assert_pin()
        try:
            os.mkdir(run_id, 0o700, dir_fd=self._root_fd)
            os.fsync(self._root_fd)
        except FileExistsError:
            pass
        run_fd = os.open(run_id, _DIR_FLAGS, dir_fd=self._root_fd)
        descriptor = os.open(
            kind,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o600,
            dir_fd=run_fd,
        )
        visible = True
        try:
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
            os.fsync(run_fd)
        except Exception:
            os.close(descriptor)
            if visible:
                try:
                    os.unlink(kind, dir_fd=run_fd)
                except OSError:
                    pass
            os.close(run_fd)
            raise
        os.close(descriptor)
        digest = hashlib.sha256(payload).hexdigest()
        receipt = ArtifactReceipt(kind, run_id, str(self._root / run_id / kind), digest)
        self._artifacts.append(receipt)
        self._fds[(run_id, kind)] = (
            run_fd,
            os.open(kind, os.O_RDONLY | _FILE_NOFOLLOW, dir_fd=run_fd),
        )
        return receipt

    def finalize(self) -> CollectionReceipt:
        if self._finalized:
            raise RuntimeError("Collector is already finalised")
        self._finalized = True
        self._assert_pin()
        for artifact in self._artifacts:
            run_fd, file_fd = self._fds[(artifact.run_id, artifact.kind)]
            os.lseek(file_fd, 0, os.SEEK_SET)
            chunks = []
            while True:
                chunk = os.read(file_fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            if hashlib.sha256(b"".join(chunks)).hexdigest() != artifact.sha256:
                raise RuntimeError(
                    f"Evidence artifact was modified after collection: {artifact.path}"
                )
            os.fchmod(file_fd, 0o400)
            os.fsync(file_fd)
            os.fsync(run_fd)
        ordered = sorted(self._artifacts, key=lambda a: (a.run_id, a.kind))
        entries = [
            {"kind": a.kind, "run_id": a.run_id, "sha256": a.sha256} for a in ordered
        ]
        data = json.dumps(
            entries,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        self._assert_pin()
        return CollectionReceipt(
            str(self._root),
            len(ordered),
            hashlib.sha256(data).hexdigest(),
            tuple(ordered),
        )

    def close(self) -> None:
        for run_fd, file_fd in self._fds.values():
            for fd in (file_fd, run_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._fds.clear()
        for name in ("_root_fd", "_parent_fd"):
            fd = getattr(self, name, -1)
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, name, -1)

    def __del__(self) -> None:
        self.close()
