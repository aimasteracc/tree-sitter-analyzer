#!/usr/bin/env python3
"""Strict helpers for native wheel qualification evidence."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import signal
import subprocess
import time
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from packaging.utils import parse_wheel_filename

PROJECT = "tree-sitter-analyzer"
STAGES = ("verify_wheel", "install", "metadata_provenance", "mcp_protocol")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", "utf-8")
    os.replace(temporary, path)


def canonical_name(value: str) -> str:
    return "-".join(filter(None, value.lower().replace("_", "-").split("-")))


def wheel_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.suffix != ".whl":
        raise ValueError("wheel must be one regular, non-symlink .whl file")
    with zipfile.ZipFile(path) as archive:
        metadata_names = [
            n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
        ]
        record_names = [
            n for n in archive.namelist() if n.endswith(".dist-info/RECORD")
        ]
        if len(metadata_names) != 1 or len(record_names) != 1:
            raise ValueError("wheel must contain exactly one METADATA and RECORD")
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        name, version = metadata.get("Name"), metadata.get("Version")
        if not name or not version or canonical_name(name) != PROJECT:
            raise ValueError("wheel METADATA has invalid project Name or Version")
        rows = list(
            csv.reader(archive.read(record_names[0]).decode("utf-8").splitlines())
        )
        members = archive.namelist()
        archived = set(members)
        if len(archived) != len(members) or archive.testzip() is not None:
            raise ValueError("wheel archive has duplicate or corrupt members")
        if not rows or any(len(row) != 3 or row[0] not in archived for row in rows):
            raise ValueError("wheel RECORD does not enumerate archive members")
        for filename, digest, size in rows:
            data = archive.read(filename)
            if size and int(size) != len(data):
                raise ValueError("wheel RECORD size mismatch")
            if digest:
                algorithm, encoded = digest.split("=", 1)
                actual = (
                    base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest())
                    .rstrip(b"=")
                    .decode()
                )
                if actual != encoded:
                    raise ValueError("wheel RECORD digest mismatch")
        filename_name, filename_version, _, _ = parse_wheel_filename(path.name)
        if canonical_name(filename_name) != PROJECT or str(filename_version) != version:
            raise ValueError("wheel filename Name/Version differs from METADATA")
    return {
        "filename": path.name,
        "sha256": sha256(path),
        "size": path.stat().st_size,
        "name": canonical_name(name),
        "version": version,
    }


def inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=True).relative_to(parent.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def terminate_tree(proc: subprocess.Popen[bytes], grace: float = 2.0) -> None:
    """Bounded best-effort termination of the complete process tree."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=grace,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pass
        return
    # Kill the process group even if its leader already exited: descendants may remain.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: int
) -> tuple[int, bytes, bytes, float]:
    started = time.monotonic()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=flags,
        start_new_session=os.name != "nt",
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        terminate_tree(proc)
        try:
            tail_out, tail_err = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            terminate_tree(proc, 0.2)
            tail_out, tail_err = b"", b""
        return (
            124,
            (exc.output or b"") + tail_out,
            (exc.stderr or b"") + tail_err,
            time.monotonic() - started,
        )


def direct_url_hash(value: dict[str, Any]) -> str:
    archive = value.get("archive_info", {})
    legacy = archive.get("hash", "")
    if isinstance(legacy, str) and legacy.startswith("sha256="):
        return legacy.removeprefix("sha256=")
    hashes = archive.get("hashes", {})
    return hashes.get("sha256", "") if isinstance(hashes, dict) else ""


def validate_installed_provenance(
    metadata: dict[str, Any],
    runtime: dict[str, Any],
    envroot: Path,
    wheel: dict[str, Any],
) -> dict[str, Any]:
    strict_paths = [
        metadata[key]
        for key in ("location", "module_file", "module_origin", "direct_url_path")
    ]
    strict_paths.append(runtime["prefix"])
    runtime_inside = (
        Path(runtime["executable"]).absolute().is_relative_to(envroot.absolute())
    )
    if (
        not all(inside(Path(item), envroot) for item in strict_paths)
        or not runtime_inside
    ):
        raise ValueError(
            "distribution/module/runtime/console provenance escaped fresh venv"
        )
    if (
        metadata["module_file"] != metadata["module_origin"]
        or metadata["module_recorded"] is not True
    ):
        raise ValueError("module origin is not the wheel RECORD module")
    if (
        canonical_name(metadata["name"]) != PROJECT
        or metadata["version"] != wheel["version"]
    ):
        raise ValueError("installed distribution metadata differs from wheel")
    digest = direct_url_hash(metadata["direct_url"])
    if digest != wheel["sha256"]:
        raise ValueError("direct_url archive hash does not bind the exact wheel")
    return {**metadata, "all_paths_in_fresh_venv": True, "direct_url_sha256": digest}


def stage_error(report: dict[str, Any], stage: str, exc: BaseException) -> None:
    report["passed"] = False
    report["failure"] = {
        "stage": stage,
        "type": type(exc).__name__,
        "message": str(exc)[:2000],
    }


def validate_stage_semantics(report: dict[str, Any]) -> str | None:
    ids = [item.get("id") for item in report.get("stages", [])]
    passed = report.get("passed") is True
    expected = list(STAGES) if passed else list(STAGES[: len(ids)])
    if ids != expected or any(
        item.get("passed") is not True for item in report.get("stages", [])
    ):
        return "stages are not the exact ordered successful prefix"
    failure = report.get("failure")
    if not passed:
        expected_failure = STAGES[len(ids)] if len(ids) < len(STAGES) else "finalize"
        if not isinstance(failure, dict) or failure.get("stage") != expected_failure:
            return "failure.stage does not identify the next incomplete stage"
    elif failure is not None:
        return "successful report contains failure"
    return None


def identity(value: dict[str, Any], *, include_job: bool = False) -> tuple[Any, ...]:
    source, workflow = value.get("source", {}), value.get("workflow", {})
    fields = (
        source.get("repository"),
        source.get("commit"),
        source.get("ref"),
        workflow.get("event"),
        workflow.get("run_id"),
        workflow.get("run_attempt"),
        workflow.get("workflow_ref"),
        workflow.get("run_url"),
    )
    return fields + ((workflow.get("job"),) if include_job else ())
