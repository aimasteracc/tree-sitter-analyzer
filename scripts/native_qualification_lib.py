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
import threading
import time
import uuid
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import psutil
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
        recorded = [row[0] for row in rows if len(row) == 3]
        if len(archived) != len(members) or archive.testzip() is not None:
            raise ValueError("wheel archive has duplicate or corrupt members")
        if (
            not rows
            or any(len(row) != 3 for row in rows)
            or len(recorded) != len(set(recorded))
            or set(recorded) != archived
        ):
            raise ValueError("wheel RECORD must exactly enumerate archive members once")
        for filename, digest, size in rows:
            lowered = Path(filename).name.lower()
            if (
                filename.startswith(("/", "\\"))
                or ".." in Path(filename).parts
                or lowered.endswith((".pth", ".egg-link"))
                or lowered in {"sitecustomize.py", "usercustomize.py"}
            ):
                raise ValueError(
                    "wheel contains an unsafe install-time injection member"
                )
            data = archive.read(filename)
            is_record = filename == record_names[0]
            if is_record:
                if digest or size:
                    raise ValueError(
                        "wheel RECORD self-entry must have empty hash and size"
                    )
                continue
            if not digest or not size or int(size) != len(data):
                raise ValueError("wheel RECORD requires exact size for every member")
            try:
                algorithm, encoded = digest.split("=", 1)
                actual = (
                    base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest())
                    .rstrip(b"=")
                    .decode()
                )
            except (ValueError, TypeError) as exc:
                raise ValueError("wheel RECORD digest is invalid") from exc
            if algorithm != "sha256" or actual != encoded:
                raise ValueError("wheel RECORD sha256 digest mismatch")
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


def installed_files_sidecar(metadata: dict[str, Any], output: Path) -> str:
    """Snapshot every installed RECORD row under deterministic safe ZIP names."""
    record, location = metadata["installed_record"], Path(metadata["location"])
    rows = record["files"]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "installed-record.csv", Path(record["record_path"]).read_bytes()
        )
        for index, item in enumerate(rows):
            source = (location / item["path"]).resolve(strict=True)
            if source.is_symlink() or not source.is_file():
                raise ValueError("installed sidecar source is not a regular file")
            archive.writestr(f"files/{index:06d}", source.read_bytes())
    with zipfile.ZipFile(output) as archive:
        expected = ["installed-record.csv"] + [
            f"files/{index:06d}" for index in range(len(rows))
        ]
        unsafe = any(
            item.is_dir() or (item.external_attr >> 16) & 0o170000 == 0o120000
            for item in archive.infolist()
        )
        if archive.namelist() != expected or archive.testzip() is not None or unsafe:
            raise ValueError("installed sidecar lacks exact safe regular members")
    return sha256(output)


def inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=True).relative_to(parent.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _watch_descendants(
    proc: subprocess.Popen[bytes],
    tracked: dict[int, psutil.Process],
    stop: threading.Event,
) -> None:
    """Retain descendant identities before an exited parent is reaped/reparented."""
    parent = psutil.Process(proc.pid)
    while not stop.is_set():
        try:
            for child in parent.children(recursive=True):
                tracked.setdefault(child.pid, child)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        stop.wait(0.005)


def terminate_tree(
    proc: subprocess.Popen[bytes],
    tracked: dict[int, psutil.Process] | None = None,
    grace: float = 2.0,
) -> None:
    """Boundedly terminate the owned group and every observed descendant."""
    descendants = list((tracked or {}).values())
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
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for child in descendants:
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(descendants, timeout=grace)
    if os.name != "nt":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for child in alive:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(alive, timeout=min(grace, 1.0))


def _token_processes(token: str, deadline: float) -> dict[int, psutil.Process]:
    """Find cooperative descendants by their per-run inherited ownership token."""
    found: dict[int, psutil.Process] = {}
    for process in psutil.process_iter():
        if time.monotonic() >= deadline:
            break
        try:
            if process.environ().get("TSA_QUALIFICATION_PROCESS_TOKEN") == token:
                found[process.pid] = process
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return found


def run(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: int
) -> tuple[int, bytes, bytes, float]:
    """Run and boundedly clean cooperative descendants on every exit path.

    Each run owns a unique inherited environment token, closing the watcher race for
    an immediate-exit parent whose child creates a new session. A hostile child that
    deliberately clears the token is outside this cooperative qualification invariant.
    """
    started = time.monotonic()
    token = uuid.uuid4().hex
    child_env = {**env, "TSA_QUALIFICATION_PROCESS_TOKEN": token}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=flags,
        start_new_session=os.name != "nt",
    )
    tracked: dict[int, psutil.Process] = {}
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_descendants, args=(proc, tracked, stop), daemon=True
    )
    watcher.start()
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
        returncode = int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        out, err = exc.output or b"", exc.stderr or b""
        terminate_tree(proc, tracked)
        try:
            tail_out, tail_err = proc.communicate(timeout=3)
            out, err = out + tail_out, err + tail_err
        except subprocess.TimeoutExpired:
            terminate_tree(proc, tracked, 0.2)
    finally:
        stop.set()
        watcher.join(timeout=0.5)
        # The token scan catches descendants detached before the watcher sampled them.
        tracked.update(_token_processes(token, time.monotonic() + 1.0))
        # Cleanup is an invariant on successful, failed, and timed-out commands.
        terminate_tree(proc, tracked, 0.5)
    return (124 if timed_out else returncode), out, err, time.monotonic() - started


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
        observed.append(legacy.removeprefix("sha256="))
    hashes = archive.get("hashes")
    if hashes is not None:
        if not isinstance(hashes, dict) or set(hashes) != {"sha256"}:
            return ""
        observed.append(hashes["sha256"])
    return observed[0] if observed and len(set(observed)) == 1 else ""


def _validate_installed_record(metadata: dict[str, Any], envroot: Path) -> None:
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
