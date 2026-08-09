"""Race-resistant non-key input staging through O_NOFOLLOW descriptors."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import tarfile
from pathlib import Path


def copy_file(source: Path, destination: Path, mode: int = 0o444) -> None:
    fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise ValueError("staged input is not regular")
        out = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode
        )
        try:
            while chunk := os.read(fd, 1024 * 1024):
                os.write(out, chunk)
            os.fsync(out)
        finally:
            os.close(out)
    finally:
        os.close(fd)


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(mode=0o555)
    root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)

    def walk(fd: int, out: Path) -> None:
        for name in sorted(os.listdir(fd)):
            child = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            meta = os.fstat(child)
            target = out / name
            try:
                if stat.S_ISDIR(meta.st_mode):
                    target.mkdir(mode=0o555)
                    walk(child, target)
                elif stat.S_ISREG(meta.st_mode):
                    dest = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o444,
                    )
                    try:
                        while chunk := os.read(child, 1024 * 1024):
                            os.write(dest, chunk)
                        os.fsync(dest)
                    finally:
                        os.close(dest)
                else:
                    raise ValueError("source snapshot contains link or special file")
            finally:
                os.close(child)

    try:
        walk(root, destination)
    finally:
        os.close(root)


def digest_file(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("trusted input is not regular")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def compare_files(trusted: Path, evidence: Path, expected: str) -> None:
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("trusted digest must be lowercase SHA-256")
    trusted_digest = digest_file(trusted)
    evidence_digest = digest_file(evidence)
    if trusted_digest != expected or evidence_digest != expected:
        raise ValueError("evidence public config is not the externally trusted config")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("file")
    f.add_argument("source")
    f.add_argument("destination")
    t = sub.add_parser("tree")
    t.add_argument("source")
    t.add_argument("destination")
    t.add_argument("archive")
    d = sub.add_parser("digest")
    d.add_argument("source")
    c = sub.add_parser("compare")
    c.add_argument("trusted")
    c.add_argument("evidence")
    c.add_argument("sha256")
    a = p.parse_args(argv)
    if a.command == "file":
        copy_file(Path(a.source), Path(a.destination))
    elif a.command == "digest":
        print(digest_file(Path(a.source)))
    elif a.command == "compare":
        compare_files(Path(a.trusted), Path(a.evidence), a.sha256)
    else:
        copy_tree(Path(a.source), Path(a.destination))
        with tarfile.open(a.archive, "w", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(Path(a.destination).rglob("*")):
                info = archive.gettarinfo(
                    path, arcname=path.relative_to(a.destination).as_posix()
                )
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                if path.is_file():
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                else:
                    archive.addfile(info)
        os.chmod(a.archive, 0o444)


if __name__ == "__main__":
    main()
