"""Race-resistant non-key input staging through O_NOFOLLOW descriptors."""

from __future__ import annotations

import argparse
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
    a = p.parse_args(argv)
    if a.command == "file":
        copy_file(Path(a.source), Path(a.destination))
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
