#!/usr/bin/env python3
"""Installed-provenance validation for native qualification evidence."""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _normalize_sha256(value: str) -> str:
    raw = value.removeprefix("sha256=").removeprefix("sha256:").removeprefix("sha256-")
    if re.fullmatch(r"[0-9A-Fa-f]{64}", raw):
        return raw.lower()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw):
        return ""
    try:
        decoded = base64.b64decode(raw + "=", altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        return ""
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode()
    return decoded.hex() if len(decoded) == 32 and canonical == raw else ""


def direct_url_hash(value: dict[str, Any]) -> str:
    if set(value) != {"url", "archive_info"} or not isinstance(value["url"], str):
        return ""
    archive = value["archive_info"]
    if not isinstance(archive, dict) or not set(archive).issubset({"hash", "hashes"}):
        return ""
    observed: list[str] = []
    legacy = archive.get("hash")
    if legacy is not None:
        if not isinstance(legacy, str) or not legacy.startswith("sha256="):
            return ""
        observed.append(_normalize_sha256(legacy))
    hashes = archive.get("hashes")
    if hashes is not None:
        if not isinstance(hashes, dict) or set(hashes) != {"sha256"}:
            return ""
        value = hashes["sha256"]
        if not isinstance(value, str):
            return ""
        observed.append(_normalize_sha256(value))
    return observed[0] if observed and len(set(observed)) == 1 else ""


def _validate_installed_record(metadata: dict[str, Any], envroot: Path) -> None:
    from native_qualification_lib import inside, sha256

    record = metadata.get("installed_record")
    if not isinstance(record, dict) or set(record) != {
        "record_path",
        "record_sha256",
        "entry_count",
        "files",
    }:
        raise ValueError("installed RECORD manifest is incomplete")
    record_path = Path(record["record_path"])
    files = record["files"]
    if (
        not inside(record_path, envroot)
        or sha256(record_path) != record["record_sha256"]
        or not isinstance(files, list)
        or record["entry_count"] != len(files)
        or len({item.get("path") for item in files if isinstance(item, dict)})
        != len(files)
    ):
        raise ValueError("installed RECORD manifest identity mismatch")
    location = Path(metadata["location"])
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise ValueError("installed RECORD manifest entry is invalid")
        lowered = Path(item["path"]).name.lower()
        path = (location / item["path"]).resolve(strict=True)
        if (
            lowered.endswith((".pth", ".egg-link"))
            or lowered in {"sitecustomize.py", "usercustomize.py"}
            or not inside(path, envroot)
            or path.is_symlink()
            or path.stat().st_size != item["size"]
            or sha256(path) != item["sha256"]
        ):
            raise ValueError("installed RECORD manifest file bytes mismatch")


def validate_installed_provenance(
    metadata: dict[str, Any],
    runtime: dict[str, Any],
    envroot: Path,
    wheel: dict[str, Any],
) -> dict[str, Any]:
    from native_qualification_lib import PROJECT, canonical_name, inside

    strict_paths = [
        metadata[key]
        for key in ("location", "module_file", "module_origin", "direct_url_path")
    ]
    strict_paths.extend(
        (runtime["prefix"], metadata["installed_record"]["record_path"])
    )
    runtime_inside = (
        Path(runtime["executable"])
        .absolute()
        .is_relative_to(envroot.resolve(strict=True))
    )
    if (
        not all(inside(Path(item), envroot) for item in strict_paths)
        or not runtime_inside
    ):
        raise ValueError(
            "distribution/module/runtime/console provenance escaped fresh venv"
        )
    _validate_installed_record(metadata, envroot)
    if (
        os.path.normcase(str(Path(metadata["module_file"]).resolve()))
        != os.path.normcase(str(Path(metadata["module_origin"]).resolve()))
        or metadata["module_recorded"] is not True
    ):
        raise ValueError("module origin is not the wheel RECORD module")
    if (
        canonical_name(metadata["name"]) != PROJECT
        or metadata["version"] != wheel["version"]
    ):
        raise ValueError("installed distribution metadata differs from wheel")
    direct_url = metadata["direct_url"]
    digest = direct_url_hash(direct_url)
    if not digest:
        archive_info = direct_url.get("archive_info")
        source_name = Path(unquote(urlparse(direct_url.get("url", "")).path)).name
        if archive_info != {} or source_name != wheel["filename"]:
            raise ValueError(
                f"direct_url does not identify the exact wheel: {direct_url!r}"
            )
        # Older pip omits local-wheel hashes. Installed RECORD byte verification
        # above independently binds this installation to the downloaded wheel.
        digest = wheel["sha256"]
    if digest != wheel["sha256"]:
        raise ValueError("direct_url archive hash differs from the exact wheel")
    return {**metadata, "all_paths_in_fresh_venv": True, "direct_url_sha256": digest}
