#!/usr/bin/env python3
# ruff: noqa: E701, E702
# fmt: off
"""Bounded subprocess, Git blob, and safe I/O helpers for NO1-006B."""
from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_CAPTURE_BYTES = 8 * 1024 * 1024

def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_file_budget(path: Path, maximum: int, label: str) -> None:
    size=path.stat().st_size
    if size>maximum: raise RuntimeError(f"{label} exceeded {maximum} byte disk budget: {size}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    # Fail closed against user/project uv configuration. UV_CACHE_DIR is the only
    # inherited UV_* input: it selects already-downloaded offline artifacts, not
    # resolution or index policy.
    keep = {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "UV_CACHE_DIR") if key in os.environ}
    clean = {**keep, "UV_NO_CONFIG": "1", "UV_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C", "LANG": "C",
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    for key,value in (overrides or {}).items():
        if key.startswith("UV_"): raise ValueError(f"uv environment override is not allowed: {key}")
        clean[key]=value
    return clean


def run(command: list[str], *, cwd: Path, timeout: int = 180, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    process=subprocess.Popen(command,cwd=cwd,env=clean_env(env_overrides),stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    assert process.stdout is not None and process.stderr is not None
    selector=selectors.DefaultSelector(); selector.register(process.stdout,selectors.EVENT_READ,"stdout"); selector.register(process.stderr,selectors.EVENT_READ,"stderr")
    buffers={"stdout":bytearray(),"stderr":bytearray()}; deadline=time.monotonic()+timeout
    try:
        while selector.get_map() and time.monotonic()<deadline:
            for key,_ in selector.select(max(0,deadline-time.monotonic())):
                block=os.read(key.fileobj.fileno(),65536)
                if not block: selector.unregister(key.fileobj); continue
                buffers[key.data].extend(block)
                if sum(map(len,buffers.values()))>MAX_CAPTURE_BYTES: raise RuntimeError(f"subprocess output exceeded {MAX_CAPTURE_BYTES} bytes")
        if selector.get_map(): raise TimeoutError(f"command exceeded {timeout} seconds")
        returncode=process.wait(timeout=3)
    except BaseException:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=3); raise
    finally: selector.close()
    result=subprocess.CompletedProcess(command,returncode,bytes(buffers["stdout"]),bytes(buffers["stderr"]))
    if result.returncode:
        detail=result.stderr[-4096:].decode(errors="replace")
        raise RuntimeError(f"command failed ({result.returncode}): {command!r}: {detail}")
    return result


def git(repo: Path, *args: str) -> bytes:
    return run(["git", *args], cwd=repo, timeout=60).stdout


def bounded_git(repo: Path, *args: str, timeout: int = 60) -> bytes:
    # Git provenance reads must work on Windows, whose default selector cannot
    # monitor anonymous subprocess pipes. Regular temporary files also let us
    # enforce the byte ceiling while git is still running.
    with tempfile.TemporaryDirectory(prefix="no1-006b-git-") as raw:
        stdout_path=Path(raw)/"stdout"; stderr_path=Path(raw)/"stderr"
        with stdout_path.open("w+b") as stdout, stderr_path.open("w+b") as stderr:
            process=subprocess.Popen(["git",*args],cwd=repo,env=clean_env(),stdout=stdout,stderr=stderr,start_new_session=True)
            deadline=time.monotonic()+timeout
            while process.poll() is None:
                if time.monotonic() >= deadline or stdout_path.stat().st_size+stderr_path.stat().st_size > MAX_CAPTURE_BYTES:
                    process.kill(); process.wait(timeout=3)
                    if time.monotonic() >= deadline: raise TimeoutError(f"git command exceeded {timeout} seconds")
                    raise RuntimeError(f"git output exceeded {MAX_CAPTURE_BYTES} bytes")
                time.sleep(0.01)
            stdout.flush(); stderr.flush()
            if stdout_path.stat().st_size+stderr_path.stat().st_size > MAX_CAPTURE_BYTES:
                raise RuntimeError(f"git output exceeded {MAX_CAPTURE_BYTES} bytes")
            stdout.seek(0); stderr.seek(0); output=stdout.read(); detail=stderr.read()
        if process.returncode:
            raise RuntimeError(f"git command failed ({process.returncode}): {args!r}: {detail[-4096:].decode(errors='replace')}")
        return output


def bound_blob(repo: Path, commit: str, relative: str) -> bytes:
    tracked=bounded_git(repo,"ls-files","--error-unmatch","--",relative).decode().strip()
    if tracked != relative: raise RuntimeError(f"collector provenance path is not tracked: {relative}")
    return bounded_git(repo,"show",f"{commit}:{relative}")


def canonical_inventory_rows(rows: list[dict[str,str]]) -> str:
    return digest_bytes(json.dumps(rows,sort_keys=True,separators=(",",":")).encode())


def canonical_hash(report: dict[str, Any]) -> str:
    body=dict(report); body.pop("canonical_payload_sha256",None)
    return digest_bytes(json.dumps(body,sort_keys=True,separators=(",",":")).encode())


RFC3339_PATTERN = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


def parse_rfc3339(value: str) -> datetime:
    if RFC3339_PATTERN.fullmatch(value) is None:
        raise ValueError(f"timestamp is not strict RFC 3339: {value!r}")
    parsed=datetime.fromisoformat(value[:-1]+"+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {value!r}")
    if datetime.fromisoformat(parsed.isoformat()) != parsed:
        raise ValueError(f"timestamp does not round-trip: {value!r}")
    return parsed


def safe_write(output: Path, data: bytes, subject: Path) -> None:
    if subject.resolve() == output.resolve() or subject.resolve() in output.resolve().parents:
        raise ValueError("output must be outside the measured subject repository")
    parent=output.parent
    if not parent.exists(): raise ValueError("output parent must already exist")
    current=parent
    while True:
        if stat.S_ISLNK(current.lstat().st_mode): raise ValueError("output parent chain must not contain symlinks")
        if current == current.parent: break
        current=current.parent
    if output.is_symlink(): raise ValueError("output must not be a symlink")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    temp=parent/f".{output.name}.{os.getpid()}.tmp"
    fd=os.open(temp,flags,0o600)
    try:
        with os.fdopen(fd,"wb",closefd=True) as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,output)
        directory=os.open(parent,os.O_RDONLY); os.fsync(directory); os.close(directory)
    finally:
        if temp.exists(): temp.unlink()


# fmt: on
