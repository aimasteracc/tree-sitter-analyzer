#!/usr/bin/env python3
"""Fresh-exec positive controls for the RFC-0022 Linux strace authority.

This module is a target, never an authority.  It deliberately attempts one
filesystem mutation selected on the command line so the native monitor can
prove that it observes the attempt (including attempts later undone).
"""

from __future__ import annotations

import argparse
import errno
import json
import mmap
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path


def _inside(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"control path escapes root: {candidate}") from exc
    return candidate


def _fixture(root: Path) -> Path:
    path = _inside(root, "fixture.txt")
    if not path.is_file():
        raise FileNotFoundError("fixture.txt must be prepared before target exec")
    return path


def _clean(root: Path, _: Path | None) -> None:
    if not root.is_dir():
        raise FileNotFoundError(root)


def _create_unlink(root: Path, _: Path | None) -> None:
    path = _inside(root, "native-created.txt")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, b"native\n")
    finally:
        os.close(fd)
    os.unlink(path)


def _descendant_create_unlink(root: Path, _: Path | None) -> None:
    path = _inside(root, "descendant-created.txt")
    code = (
        "import os,sys; p=sys.argv[1]; "
        "fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); "
        "os.write(fd,b'child\\n'); os.close(fd); os.unlink(p)"
    )
    subprocess.run([sys.executable, "-c", code, os.fspath(path)], check=True)


def _truncate_restore(root: Path, _: Path | None) -> None:
    path = _fixture(root)
    original = path.read_bytes()
    os.truncate(path, 0)
    fd = os.open(path, os.O_WRONLY)
    try:
        os.write(fd, original)
    finally:
        os.close(fd)


def _rename_restore(root: Path, _: Path | None) -> None:
    source = _fixture(root)
    moved = _inside(root, "fixture.moved")
    os.rename(source, moved)
    os.rename(moved, source)


def _mkdir_rmdir(root: Path, _: Path | None) -> None:
    path = _inside(root, "made-directory")
    os.mkdir(path, 0o700)
    os.rmdir(path)


def _sqlite_sidecar(root: Path, _: Path | None) -> None:
    path = _inside(root, "authority.sqlite3")
    connection = sqlite3.connect(path)
    try:
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        if mode is None or str(mode[0]).lower() != "wal":
            raise RuntimeError(f"SQLite did not enter WAL mode: {mode!r}")
        connection.execute("CREATE TABLE IF NOT EXISTS events(value TEXT NOT NULL)")
        connection.execute("INSERT INTO events(value) VALUES ('attempt')")
        connection.commit()
    finally:
        connection.close()


def _absolute_write(root: Path, absolute_target: Path | None) -> None:
    if absolute_target is None or not absolute_target.is_absolute():
        raise ValueError("absolute-write requires an absolute --absolute-target")
    target = absolute_target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "absolute target must remain inside the supplied root"
        ) from exc
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, b"absolute\n")
    finally:
        os.close(fd)
    os.unlink(target)


def _permission_denied(root: Path, absolute_target: Path | None) -> None:
    del root
    if absolute_target is None or not absolute_target.is_absolute():
        raise ValueError("permission-denied requires an absolute --absolute-target")
    path = absolute_target.resolve()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
            return
        raise
    else:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise RuntimeError("permission-denied control unexpectedly opened its target")


def _write_then_delete(root: Path, _: Path | None) -> None:
    path = _inside(root, "write-then-delete.txt")
    path.write_bytes(b"temporary bytes\n")
    path.unlink()


def _inherited_fd(root: Path, _: Path | None) -> None:
    path = _fixture(root)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        code = "import os,sys; os.write(int(sys.argv[1]),b'inherited\\n')"
        subprocess.run(
            [sys.executable, "-c", code, str(fd)],
            check=True,
            close_fds=True,
            pass_fds=(fd,),
        )
    finally:
        os.close(fd)


def _shared_writable_mmap(root: Path, _: Path | None) -> None:
    path = _fixture(root)
    if path.stat().st_size == 0:
        raise ValueError("fixture.txt must be non-empty")
    fd = os.open(path, os.O_RDWR)
    try:
        with mmap.mmap(fd, 0, access=mmap.ACCESS_WRITE) as mapping:
            original = mapping[0]
            mapping[0] = (original + 1) % 256
            mapping.flush()
            mapping[0] = original
            mapping.flush()
    finally:
        os.close(fd)


def _timeout_detached_descendant(root: Path, _: Path | None) -> None:
    token = os.environ.get("RFC0022_AUTHORITY_TOKEN", "missing-token")
    code = "import time; time.sleep(300)"
    subprocess.Popen(  # noqa: S603 - fixed interpreter and fixed code
        [sys.executable, "-c", code],
        cwd=root,
        env={**os.environ, "RFC0022_AUTHORITY_TOKEN": token},
        start_new_session=True,
    )
    time.sleep(0.05)


CONTROLS: dict[str, Callable[[Path, Path | None], None]] = {
    "absolute-write": _absolute_write,
    "clean": _clean,
    "create-unlink": _create_unlink,
    "descendant-create-unlink": _descendant_create_unlink,
    "inherited-fd": _inherited_fd,
    "mkdir-rmdir": _mkdir_rmdir,
    "permission-denied": _permission_denied,
    "rename-restore": _rename_restore,
    "shared-writable-mmap": _shared_writable_mmap,
    "sqlite-sidecar": _sqlite_sidecar,
    "timeout-detached-descendant": _timeout_detached_descendant,
    "truncate-restore": _truncate_restore,
    "write-then-delete": _write_then_delete,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", choices=sorted(CONTROLS))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--absolute-target", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve(strict=True)
    if not root.is_dir():
        parser.error("--root must be a directory")
    CONTROLS[args.control](root, args.absolute_target)
    print(json.dumps({"control": args.control, "status": "completed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
