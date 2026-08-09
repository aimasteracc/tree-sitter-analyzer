"""Build-time NO1-008A root-of-trust resource handling."""

from __future__ import annotations

import os
import stat
from pathlib import Path

ROOT_RESOURCE = Path(__file__).with_name("no1_008a_root_public_key.hex")


def _require_unshadowed_readonly_image_resource() -> None:
    raw = Path("/proc/self/mountinfo").read_text(encoding="ascii")
    resource = str(ROOT_RESOURCE.resolve(strict=True))
    root_readonly = False
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 6:
            raise ValueError("process mount table is malformed")
        mountpoint = fields[4].replace("\\040", " ").replace("\\134", "\\")
        if mountpoint == "/":
            root_readonly = "ro" in fields[5].split(",")
        elif resource == mountpoint or resource.startswith(
            mountpoint.rstrip("/") + "/"
        ):
            raise ValueError("baked root resource is shadowed by a runtime mount")
    if not root_readonly:
        raise ValueError("production trust resource requires a read-only image root")


def baked_root_public_key() -> bytes:
    """Read the image-baked root; no environment or CLI override is accepted."""
    _require_unshadowed_readonly_image_resource()
    fd = os.open(ROOT_RESOURCE, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o222:
            raise ValueError("baked root resource must be a read-only regular file")
        payload = os.read(fd, 65)
        if os.read(fd, 1):
            raise ValueError("baked root resource is oversized")
    finally:
        os.close(fd)
    try:
        text = payload.decode("ascii").strip()
        root = bytes.fromhex(text)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("baked root resource is malformed") from exc
    if len(root) != 32 or text != root.hex():
        raise ValueError("baked root resource must be 32 lowercase hexadecimal bytes")
    return root
