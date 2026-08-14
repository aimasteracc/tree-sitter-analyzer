#!/usr/bin/env python3
"""Fail-closed Linux strace authority instrument for RFC-0022 P0.4.

This qualifies the monitor only.  It does not call an adapter and must not be
used as evidence that any ``read_existing`` route is supported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rfc0022_strace_model import AuthorityError, Violation
from rfc0022_strace_parser import parse_trace_directory
from rfc0022_strace_runtime import (
    cleanup_candidates,
    surviving_token_pids,
    write_failure_report,
    write_report,
)

POLICY_SHA256 = "49d907007172a9804261f8d8492295062964d37c03652b01124101b3b39707ab"  # pragma: allowlist secret
POLICY_KEYS = {
    "always_violation_syscalls",
    "async_syscalls",
    "authority_id",
    "enotty_ioctl_commands",
    "fd_sinks",
    "mapping_syscalls",
    "minimum_strace_version",
    "nonfilesystem_fd_prefixes",
    "page_size",
    "path_mutators",
    "process_syscalls",
    "safe_fcntl_commands",
    "safe_ioctl_commands",
    "safe_syscalls",
    "schema_version",
    "trace_arguments",
    "unix_path_mutators",
    "write_open_flags",
}
VERSION_RE = re.compile(r"strace -- version (\d+(?:\.\d+){1,2})")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_policy(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != POLICY_SHA256:
        raise AuthorityError(
            f"policy digest mismatch: expected {POLICY_SHA256}, got {digest}"
        )
    try:
        policy = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthorityError(f"invalid policy JSON: {exc}") from exc
    if not isinstance(policy, dict) or set(policy) != POLICY_KEYS:
        raise AuthorityError("policy keys do not match the closed v1 schema")
    if policy["schema_version"] != 1:
        raise AuthorityError("unsupported policy schema_version")
    if policy["authority_id"] != "rfc0022-linux-strace-v1":
        raise AuthorityError("unsupported authority_id")
    required_args = {"-ff", "-yy", "-q", "-ttt", "-v", "--kill-on-exit"}
    if not required_args.issubset(set(policy["trace_arguments"])):
        raise AuthorityError("policy omits a mandatory strace qualifier")
    required_flags = {"O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_TMPFILE"}
    if not required_flags.issubset(set(policy["write_open_flags"])):
        raise AuthorityError("policy omits a write-capable open flag")
    if policy["minimum_strace_version"] != "6.8":
        raise AuthorityError("minimum strace version must remain exactly 6.8")
    if policy["page_size"] != 4096:
        raise AuthorityError("policy page_size must remain exactly 4096")
    for key in (
        "always_violation_syscalls",
        "async_syscalls",
        "enotty_ioctl_commands",
        "mapping_syscalls",
        "nonfilesystem_fd_prefixes",
        "process_syscalls",
        "safe_fcntl_commands",
        "safe_ioctl_commands",
        "safe_syscalls",
        "trace_arguments",
        "unix_path_mutators",
        "write_open_flags",
    ):
        if not isinstance(policy[key], list) or not all(
            isinstance(value, str) for value in policy[key]
        ):
            raise AuthorityError(f"policy {key} must be a string array")
    for key in ("fd_sinks", "path_mutators"):
        if not isinstance(policy[key], dict):
            raise AuthorityError(f"policy {key} must be an object")
    return policy, digest


def strace_preflight(minimum: str, executable: str = "strace") -> dict[str, str | None]:
    resolved = shutil.which(executable)
    if resolved is None:
        raise AuthorityError("strace is absent")
    resolved_path = Path(resolved).resolve()
    try:
        result = subprocess.run(
            [os.fspath(resolved_path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            close_fds=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired as exc:
        raise AuthorityError("strace version preflight timed out") from exc
    match = VERSION_RE.search(result.stdout)
    if result.returncode != 0 or match is None:
        raise AuthorityError("strace version preflight failed")
    actual = match.group(1)
    actual_tuple = tuple(int(part) for part in actual.split("."))
    minimum_tuple = tuple(int(part) for part in minimum.split("."))
    width = max(len(actual_tuple), len(minimum_tuple))
    if actual_tuple + (0,) * (width - len(actual_tuple)) < minimum_tuple + (0,) * (
        width - len(minimum_tuple)
    ):
        raise AuthorityError(f"strace {actual} is older than required {minimum}")
    package: str | None = None
    dpkg_query = shutil.which("dpkg-query")
    if dpkg_query is not None:
        package_result = subprocess.run(
            [dpkg_query, "-W", "-f=${Package}=${Version}", "strace"],
            check=False,
            capture_output=True,
            text=True,
            close_fds=True,
            timeout=5,
        )
        if package_result.returncode != 0 or not package_result.stdout.strip():
            raise AuthorityError("strace package provenance query failed")
        package = package_result.stdout.strip()
    return {
        "version": actual,
        "executable": os.fspath(resolved_path),
        "sha256": _sha256(resolved_path),
        "package": package,
    }


def snapshot_root(root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in sorted([root, *root.rglob("*")], key=lambda item: os.fspath(item)):
        stat = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        record: dict[str, Any] = {
            "path": relative,
            "mode": stat.st_mode,
            "uid": stat.st_uid,
            "gid": stat.st_gid,
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns,
        }
        if path.is_symlink():
            record["kind"] = "symlink"
            record["target"] = os.readlink(path)
        elif path.is_file():
            record["kind"] = "file"
            record["sha256"] = _sha256(path)
        elif path.is_dir():
            record["kind"] = "directory"
        else:
            record["kind"] = "other"
        records.append(record)
    return {"root": os.fspath(root), "records": records}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def run_authority(
    *,
    policy_path: Path,
    trace_dir: Path,
    report_path: Path,
    monitor_roots: list[Path],
    target_cwd: Path,
    target: list[str],
    timeout: float,
    expected_returncode: int = 0,
) -> tuple[int, dict[str, Any]]:
    policy, policy_digest = load_policy(policy_path)
    trace_dir = trace_dir.resolve()
    report_path = report_path.resolve()
    if _inside(report_path, trace_dir):
        raise AuthorityError("report path must be outside the raw trace directory")
    strace_identity = strace_preflight(policy["minimum_strace_version"])
    strace_executable = strace_identity["executable"]
    if strace_executable is None:
        raise AuthorityError("strace executable provenance is absent")
    roots = [root.resolve(strict=True) for root in monitor_roots]
    target_cwd = target_cwd.resolve(strict=True)
    if not target or not target[0]:
        raise AuthorityError("target argv is empty")
    if trace_dir.exists() and any(trace_dir.iterdir()):
        raise AuthorityError("trace directory must be absent or empty")
    trace_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    isolation = trace_dir.parent / f"isolation-{token}"
    if isolation.exists():
        raise AuthorityError("isolation root collision")
    home = isolation / "home"
    cache = isolation / "cache"
    temp = isolation / "tmp"
    config = isolation / "config"
    data = isolation / "data"
    for directory in (home, cache, temp, config, data):
        directory.mkdir(parents=True)
    roots.extend((home, cache, temp, config, data))
    for root in roots:
        if _inside(trace_dir, root) or _inside(report_path, root):
            raise AuthorityError("authority artifacts overlap a monitored root")
    before = [snapshot_root(root) for root in roots]
    environment = {
        "HOME": os.fspath(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "RFC0022_AUTHORITY_TOKEN": token,
        "TMP": os.fspath(temp),
        "TEMP": os.fspath(temp),
        "TMPDIR": os.fspath(temp),
        "XDG_CACHE_HOME": os.fspath(cache),
        "XDG_CONFIG_HOME": os.fspath(config),
        "XDG_DATA_HOME": os.fspath(data),
    }
    trace_prefix = trace_dir / "trace"
    invocation = [
        strace_executable,
        *policy["trace_arguments"],
        "-o",
        os.fspath(trace_prefix),
        "--",
        *target,
    ]
    report: dict[str, Any] = {
        "schema_version": 1,
        "authority_id": policy["authority_id"],
        "authority_status": "error",
        "outcome": "indeterminate",
        "errors": [],
        "cleanup_survivor_pids": [],
        "cleanup_remaining_pids": [],
        "invocation": invocation,
        "policy": {
            "path": os.fspath(policy_path.resolve()),
            "sha256": policy_digest,
            "minimum_strace_version": policy["minimum_strace_version"],
            "strace": strace_identity,
        },
        "monitor_roots": [os.fspath(root) for root in roots],
        "snapshots": {"before": before},
        "trace_files": [],
        "violations": [],
    }
    process: subprocess.Popen[bytes] | None = None
    stdout = b""
    stderr = b""
    timed_out = False
    try:
        process = subprocess.Popen(
            invocation,
            cwd=target_cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired as exc:
                stdout = exc.output or b""
                stderr = exc.stderr or b""
        if timed_out:
            raise AuthorityError("strace target timed out")
        diagnostics = [
            line
            for line in stderr.decode("utf-8", "replace").splitlines()
            if line.startswith("strace:")
        ]
        if diagnostics:
            raise AuthorityError(f"strace diagnostics: {diagnostics}")
        if process.returncode != expected_returncode:
            raise AuthorityError(
                "target return code mismatch: "
                f"expected {expected_returncode}, got {process.returncode}"
            )
        violations, trace_metadata, trace_pids = parse_trace_directory(
            trace_dir,
            policy,
            target_cwd,
            expected_executable=target[0],
        )
        report["trace_files"] = trace_metadata
        survivors = sorted(
            set(surviving_token_pids(token))
            | {pid for pid in trace_pids if Path(f"/proc/{pid}").exists()}
        )
        if survivors:
            cleaned, remaining = cleanup_candidates(token, trace_dir)
            report["cleanup_survivor_pids"] = cleaned
            report["cleanup_remaining_pids"] = remaining
            raise AuthorityError(f"surviving traced descendants: {survivors}")
        after = [snapshot_root(root) for root in roots]
        report["snapshots"]["after"] = after
        report["snapshots"]["equal"] = before == after
        if before != after:
            for index, (old, new) in enumerate(zip(before, after, strict=False)):
                if old != new:
                    violations.append(
                        Violation(
                            "supplemental",
                            0,
                            index + 1,
                            "snapshot",
                            "supplemental_snapshot_mismatch",
                            old["root"],
                            "changed",
                        )
                    )
        report["violations"] = [asdict(item) for item in violations]
        report["authority_status"] = "healthy"
        report["outcome"] = "violation" if violations else "clean"
        return (1 if violations else 0), report
    except (AuthorityError, OSError, subprocess.SubprocessError) as exc:
        report["errors"].append(str(exc))
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=2)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    report["errors"].append("strace process survived cleanup")
        cleanup_pids, remaining_pids = cleanup_candidates(token, trace_dir)
        if cleanup_pids:
            report["cleanup_survivor_pids"] = cleanup_pids
        if remaining_pids:
            report["cleanup_remaining_pids"] = remaining_pids
            report["errors"].append(f"descendants survived cleanup: {remaining_pids}")
        if "after" not in report["snapshots"]:
            try:
                report["snapshots"]["after"] = [snapshot_root(root) for root in roots]
                report["snapshots"]["equal"] = before == report["snapshots"]["after"]
            except OSError as snapshot_exc:
                report["errors"].append(f"after snapshot failed: {snapshot_exc}")
        return 2, report
    finally:
        report["target"] = {
            "expected_returncode": expected_returncode,
            "returncode": None if process is None else process.returncode,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        }
        write_report(report_path, report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--policy", required=True, type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("--policy", required=True, type=Path)
    run.add_argument("--trace-dir", required=True, type=Path)
    run.add_argument("--report", required=True, type=Path)
    run.add_argument("--monitor-root", required=True, action="append", type=Path)
    run.add_argument("--target-cwd", required=True, type=Path)
    run.add_argument("--timeout", type=float, default=20.0)
    run.add_argument("--expected-returncode", type=int, default=0)
    run.add_argument("target", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy, _ = load_policy(args.policy)
        if args.command == "preflight":
            identity = strace_preflight(policy["minimum_strace_version"])
            print(
                json.dumps(
                    {
                        "authority_id": policy["authority_id"],
                        "status": "available",
                        "strace": identity,
                    },
                    sort_keys=True,
                )
            )
            return 0
        target = list(args.target)
        if target and target[0] == "--":
            target.pop(0)
        code, _ = run_authority(
            policy_path=args.policy,
            trace_dir=args.trace_dir,
            report_path=args.report,
            monitor_roots=args.monitor_root,
            target_cwd=args.target_cwd,
            target=target,
            timeout=args.timeout,
            expected_returncode=args.expected_returncode,
        )
        return code
    except (AuthorityError, OSError) as exc:
        if args.command == "run":
            report_path = args.report.resolve()
            trace_dir = args.trace_dir.resolve()
            if not _inside(report_path, trace_dir):
                target = list(args.target)
                if target and target[0] == "--":
                    target.pop(0)
                write_failure_report(
                    report_path,
                    error=str(exc),
                    policy_path=args.policy,
                    target=target,
                    expected_returncode=args.expected_returncode,
                )
        print(f"RFC0022_STRACE_AUTHORITY_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
