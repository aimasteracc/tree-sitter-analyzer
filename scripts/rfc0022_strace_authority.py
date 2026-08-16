#!/usr/bin/env python3
"""Fail-closed RFC-0022 Linux monitor; this does not certify any adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if os.fspath(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIRECTORY))

from rfc0022_strace_model import AuthorityError, Violation  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402
from rfc0022_strace_preflight import (  # noqa: E402
    PINNED_STRACE_EXECUTABLE,
    require_isolated_root_runtime,
    strace_preflight,
)
from rfc0022_strace_privilege import (  # noqa: E402
    build_invocation,
    normalize_target,
    prepare_target_identity,
)
from rfc0022_strace_runtime import (  # noqa: E402
    ProcessIdentity,
    capture_cleanup_identities,
    cleanup_candidates,
    close_process_identities,
    raw_trace_metadata,
    record_error_trace_metadata,
    require_pidfd_support,
    seal_trace_directory,
    write_failure_report,
    write_report,
)
from rfc0022_strace_snapshot import snapshot_root  # noqa: E402

POLICY_SHA256 = "8c272dab34801b0a977a7d1d0b22368ef066a0c3dad0c31a69a1b395ef3a220a"  # pragma: allowlist secret
POLICY_KEYS = {
    "always_violation_syscalls",
    "async_syscalls",
    "authority_id",
    "enotty_ioctl_commands",
    "fd_sinks",
    "global_write_syscalls",
    "mapping_syscalls",
    "minimum_strace_version",
    "nonfilesystem_device_markers",
    "nonfilesystem_fd_prefixes",
    "page_size",
    "path_mutators",
    "process_syscalls",
    "safe_fcntl_commands",
    "safe_ioctl_commands",
    "safe_syscalls",
    "schema_version",
    "target_user",
    "trace_arguments",
    "unix_path_mutators",
    "write_open_flags",
}


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
    if policy["target_user"] != "rfc0022-target":
        raise AuthorityError("unsupported target_user")
    if "trace=all" not in policy["trace_arguments"]:
        raise AuthorityError("policy must trace every syscall")
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
        "global_write_syscalls",
        "mapping_syscalls",
        "nonfilesystem_device_markers",
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
    require_isolated_root_runtime()
    policy, policy_digest = load_policy(policy_path)
    trace_dir = trace_dir.resolve()
    report_path = report_path.resolve()
    if _inside(report_path, trace_dir):
        raise AuthorityError("report path must be outside the raw trace directory")
    strace_identity = strace_preflight(
        policy["minimum_strace_version"], PINNED_STRACE_EXECUTABLE
    )
    strace_executable = strace_identity["executable"]
    if strace_executable is None:
        raise AuthorityError("strace executable provenance is absent")
    roots = [root.resolve(strict=True) for root in monitor_roots]
    target_cwd = target_cwd.resolve(strict=True)
    target = normalize_target(target)
    for root in roots:
        if _inside(trace_dir, root) or _inside(report_path, root):
            raise AuthorityError("authority artifacts overlap a monitored root")
    if trace_dir.exists() and any(trace_dir.iterdir()):
        raise AuthorityError("trace directory must be absent or empty")
    trace_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    trace_dir.chmod(0o700)
    token = uuid.uuid4().hex
    isolation = trace_dir.parent / f"isolation-{token}"
    if isolation.exists():
        raise AuthorityError("isolation root collision")
    home = isolation / "home"
    cache = isolation / "cache"
    temp = isolation / "tmp"
    config = isolation / "config"
    data = isolation / "data"
    isolation_directories = (home, cache, temp, config, data)
    for directory in isolation_directories:
        directory.mkdir(parents=True)
    launcher = Path(__file__).with_name("rfc0022_strace_target_launcher.py")
    target_identity = prepare_target_identity(
        policy["target_user"], isolation_directories, launcher
    )
    roots.extend(isolation_directories)
    for root in isolation_directories:
        if _inside(trace_dir, root) or _inside(report_path, root):
            raise AuthorityError("authority artifacts overlap an isolation root")
    before = [snapshot_root(root, require_noatime=True) for root in roots]
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
    invocation = build_invocation(
        strace_executable, policy, trace_prefix, launcher, target
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "authority_id": policy["authority_id"],
        "authority_status": "error",
        "outcome": "indeterminate",
        "errors": [],
        "cleanup_survivor_pids": [],
        "cleanup_remaining_pids": [],
        "invocation": invocation,
        "raw_trace_files": [],
        "policy": {
            "path": os.fspath(policy_path.resolve()),
            "sha256": policy_digest,
            "minimum_strace_version": policy["minimum_strace_version"],
            "strace": strace_identity,
        },
        "monitor_roots": [os.fspath(root) for root in roots],
        "snapshots": {"before": before},
        "target_identity": target_identity,
        "trace_files": [],
        "violations": [],
    }
    process: subprocess.Popen[bytes] | None = None
    stdout = b""
    stderr = b""
    timed_out = False
    cleanup_identities: list[ProcessIdentity] = []
    try:
        require_pidfd_support()
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
            cleanup_identities = capture_cleanup_identities(
                token,
                trace_dir,
                tracer_pid=process.pid,
                exclude_pids=frozenset({process.pid}),
            )
            report["cleanup_survivor_pids"] = sorted(
                identity.pid for identity in cleanup_identities
            )
            try:
                # The unreaped Popen leader pins this numeric process-group identity.
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
        violations, trace_metadata, _trace_pids = parse_trace_directory(
            trace_dir,
            policy,
            target_cwd,
            expected_executable=target[0],
            expected_argv=target,
            minimum_root_execs=2,
        )
        report["trace_files"] = trace_metadata
        cleanup_identities = capture_cleanup_identities(token)
        survivors = sorted(identity.pid for identity in cleanup_identities)
        if survivors:
            report["cleanup_survivor_pids"] = survivors
            captured, cleanup_identities = cleanup_identities, []
            cleaned, remaining = cleanup_candidates(token, captured)
            report["cleanup_survivor_pids"] = cleaned
            report["cleanup_remaining_pids"] = remaining
            raise AuthorityError(f"surviving traced descendants: {survivors}")
        after = [snapshot_root(root, require_noatime=True) for root in roots]
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
        report["raw_trace_files"] = raw_trace_metadata(trace_dir)
        seal_trace_directory(trace_dir)
        report["authority_status"] = "healthy"
        report["outcome"] = "violation" if violations else "clean"
        return (1 if violations else 0), report
    except (AuthorityError, OSError, subprocess.SubprocessError) as exc:
        report["errors"].append(str(exc))
        if process is not None and process.poll() is None:
            try:
                if not cleanup_identities:
                    cleanup_identities = capture_cleanup_identities(
                        token,
                        trace_dir,
                        tracer_pid=process.pid,
                        exclude_pids=frozenset({process.pid}),
                    )
                report["cleanup_survivor_pids"] = sorted(
                    {identity.pid for identity in cleanup_identities}
                )
            except (AuthorityError, OSError) as cleanup_exc:
                report["errors"].append(f"descendant capture failed: {cleanup_exc}")
            try:
                # The unreaped Popen leader pins this numeric process-group identity.
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=2)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    report["errors"].append("strace process survived cleanup")
                except OSError as process_cleanup_exc:
                    report["errors"].append(
                        f"strace process cleanup failed: {process_cleanup_exc}"
                    )
            except OSError as process_cleanup_exc:
                report["errors"].append(
                    f"strace process cleanup failed: {process_cleanup_exc}"
                )
        captured, cleanup_identities = cleanup_identities, []
        cleanup_pids: list[int]
        remaining_pids: list[int]
        if process is None and not captured:
            cleanup_pids, remaining_pids = [], []
        else:
            try:
                cleanup_pids, remaining_pids = cleanup_candidates(token, captured)
            except (AuthorityError, OSError) as cleanup_exc:
                cleanup_pids, remaining_pids = [], []
                report["errors"].append(f"descendant cleanup failed: {cleanup_exc}")
        if cleanup_pids:
            report["cleanup_survivor_pids"] = cleanup_pids
        if remaining_pids:
            report["cleanup_remaining_pids"] = remaining_pids
            report["errors"].append(f"descendants survived cleanup: {remaining_pids}")
        if "after" not in report["snapshots"]:
            try:
                report["snapshots"]["after"] = [
                    snapshot_root(root, require_noatime=True) for root in roots
                ]
                report["snapshots"]["equal"] = before == report["snapshots"]["after"]
            except (AuthorityError, OSError) as snapshot_exc:
                report["errors"].append(f"after snapshot failed: {snapshot_exc}")
        record_error_trace_metadata(report, trace_dir)
        return 2, report
    finally:
        close_process_identities(cleanup_identities)
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
            identity = strace_preflight(
                policy["minimum_strace_version"], PINNED_STRACE_EXECUTABLE
            )
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
