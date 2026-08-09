"""Descriptor-safe deterministic input staging for NO1-008A."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tarfile
from pathlib import Path

from benchmarks.codegraph_compare.setup_qualification_paths import _open_beneath


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
            os.fchmod(out, mode)  # creation mode is otherwise reduced by the umask
            while chunk := os.read(fd, 1024 * 1024):
                os.write(out, chunk)
            os.fsync(out)
        finally:
            os.close(out)
    finally:
        os.close(fd)


def _blob_oid(payload: bytes, expected: str) -> str:
    algorithms = {40: hashlib.sha1, 64: hashlib.sha256}
    try:
        algorithm = algorithms[len(expected)]
    except KeyError as exc:
        raise ValueError("unsupported Git object format") from exc
    return algorithm(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()


def _inventory(payload: bytes) -> list[tuple[str, str, str, int, str]]:
    document = json.loads(payload)
    eligibility = document.get("eligibility", document)
    files = eligibility.get("tracked_files")
    if type(files) is not list:
        raise ValueError("inventory lacks tracked_files")
    result: list[tuple[str, str, str, int, str]] = []
    for item in files:
        if type(item) is not list or len(item) != 5:
            raise ValueError("tracked file record is malformed")
        path, mode, oid, size, digest = item
        pure = __import__("pathlib").PurePosixPath(path)
        if (
            type(path) is not str
            or str(pure) != path
            or pure.is_absolute()
            or any(part in ("", ".", "..") for part in pure.parts)
            or mode not in {"100644", "100755"}
            or type(size) is not int
        ):
            raise ValueError("tracked file identity is invalid")
        result.append((path, mode, oid, size, digest))
    if result != sorted(result) or len({item[0] for item in result}) != len(result):
        raise ValueError("tracked files must be sorted and unique")
    return result


def stage_inventory_tree(
    source: Path, destination: Path, archive: Path, inventory: Path
) -> None:
    """Stage only pinned regular Git blobs and emit byte-deterministic tar evidence."""
    inventory_fd = os.open(inventory, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(inventory_fd).st_mode):
            raise ValueError("inventory is not regular")
        inventory_bytes = bytearray()
        while chunk := os.read(inventory_fd, 1024 * 1024):
            inventory_bytes.extend(chunk)
            if len(inventory_bytes) > 16 * 1024 * 1024:
                raise ValueError("inventory exceeds size ceiling")
    finally:
        os.close(inventory_fd)
    files = _inventory(bytes(inventory_bytes))
    destination.mkdir(mode=0o755)
    root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        for relative, mode, oid, expected_size, expected_sha in files:
            parts = relative.split("/")
            parent = destination
            for component in parts[:-1]:
                parent /= component
                if not parent.exists():
                    parent.mkdir(mode=0o755)
                elif not parent.is_dir() or parent.is_symlink():
                    raise ValueError("staging path collision")
            fd = _open_beneath(root, relative)
            try:
                metadata = os.fstat(fd)
                if not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("tracked worktree entry is not regular")
                chunks = bytearray()
                while chunk := os.read(fd, 1024 * 1024):
                    chunks.extend(chunk)
                payload = bytes(chunks)
            finally:
                os.close(fd)
            if (
                len(payload) != expected_size
                or hashlib.sha256(payload).hexdigest() != expected_sha
                or _blob_oid(payload, oid) != oid
            ):
                raise ValueError("tracked worktree bytes differ from pinned inventory")
            target = destination / relative
            out_mode = 0o755 if mode == "100755" else 0o644
            out = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, out_mode
            )
            try:
                os.write(out, payload)
                os.fsync(out)
            finally:
                os.close(out)
        for directory in sorted(
            (path for path in destination.rglob("*") if path.is_dir()), reverse=True
        ):
            os.chmod(directory, 0o555)  # nosec B103 - immutable traversal directory
        os.chmod(destination, 0o555)  # nosec B103 - immutable traversal root
        with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as tar:
            for relative, mode, _oid, _size, _sha in files:
                target = destination / relative
                info = tar.gettarinfo(str(target), arcname=relative)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                info.mode = 0o755 if mode == "100755" else 0o644
                with target.open("rb") as stream:
                    tar.addfile(info, stream)
        os.chmod(archive, 0o444)
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
    if digest_file(trusted) != expected or digest_file(evidence) != expected:
        raise ValueError("evidence public config differs from supplied diagnostic copy")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    file_parser = sub.add_parser("file")
    file_parser.add_argument("source")
    file_parser.add_argument("destination")
    tree = sub.add_parser("tree")
    tree.add_argument("source")
    tree.add_argument("destination")
    tree.add_argument("archive")
    tree.add_argument("inventory")
    digest = sub.add_parser("digest")
    digest.add_argument("source")
    compare = sub.add_parser("compare")
    compare.add_argument("trusted")
    compare.add_argument("evidence")
    compare.add_argument("sha256")
    args = parser.parse_args(argv)
    if args.command == "file":
        copy_file(Path(args.source), Path(args.destination))
    elif args.command == "tree":
        stage_inventory_tree(
            Path(args.source),
            Path(args.destination),
            Path(args.archive),
            Path(args.inventory),
        )
    elif args.command == "digest":
        print(digest_file(Path(args.source)))
    else:
        compare_files(Path(args.trusted), Path(args.evidence), args.sha256)


if __name__ == "__main__":
    main()
