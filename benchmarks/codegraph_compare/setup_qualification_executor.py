"""Keyless single-cell producer entrypoint for NO1-008A.

The operator supplies one closed cell plan inside an already isolated container.
This process executes it once, records raw bytes, and never creates a receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import time

try:
    import resource as _resource
except ImportError:  # pragma: no cover - exercised on Windows
    _resource = None  # type: ignore[assignment]
from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.execution_budget import (
    MAX_OUTPUT_ENTRIES,
    OUTPUT_ENTRY_METADATA_CHARGE_BYTES,
)
from benchmarks.codegraph_compare.receipt_v3 import (
    MAX_JSON_BYTES,
    MAX_NODES,
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_regular_descriptor,
    _open_root,
    _visit_tree,
)

PLAN_KEYS = frozenset(
    {
        "schema_version",
        "cell",
        "executions",
        "wall_timeout_seconds",
        "environment",
        "artifact_path",
        "plan_hash",
        "plan_set_hash",
        "tool_sha256",
        "config_sha256",
        "image_digest",
        "seccomp_sha256",
        "resource_plan_digest",
        "resource_ceilings",
        "index_partition",
        "oracle_statement",
    }
)
CELL_KEYS = frozenset({"repo_id", "arm_id", "attempt"})
EXECUTION_KEYS = frozenset(
    {"id", "argv", "cwd", "environment_digest", "query", "expected_result"}
)
ENVIRONMENT_KEYS = frozenset({"HOME", "LANG", "LC_ALL", "PATH"})
MAX_EXPECTED_RESULT_BYTES = 4 * 1024 * 1024


def _bounded_path(value: Any, label: str, *, absolute: bool = False) -> str:
    if type(value) is not str or not value or len(value) > 4096:
        raise ValueError(f"{label} must be a bounded path")
    if (
        "," in value
        or "\\" in value
        or "//" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} is not canonical")
    parts = value.split("/")
    start = 1 if absolute else 0
    if absolute != value.startswith("/") or any(
        part in ("", ".", "..") for part in parts[start:]
    ):
        raise ValueError(f"{label} is not canonical")
    return value


FORBIDDEN_ENV_FRAGMENTS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "CREDENTIAL",
    "PASSWORD",
    "SSH",
    "AWS",
    "AZURE",
    "GCP",
    "GOOGLE",
    "OPENAI",
    "ANTHROPIC",
    "MODEL",
    "PROVIDER",
)


def _exact(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ValueError(f"{label} has unknown or missing fields")
    return value


def validate_producer_plan(plan: Any) -> dict[str, Any]:
    plan = _exact(plan, PLAN_KEYS, "producer plan")
    if plan["schema_version"] != 1 or type(plan["schema_version"]) is not int:
        raise ValueError("producer plan schema must be 1")
    cell = _exact(plan["cell"], CELL_KEYS, "cell")
    if (
        any(
            type(cell[name]) is not str or not cell[name] or len(cell[name]) > 64
            for name in ("repo_id", "arm_id")
        )
        or cell["attempt"] != 1
        or type(cell["attempt"]) is not int
    ):
        raise ValueError("cell identity or attempt is invalid")
    if (
        type(plan["wall_timeout_seconds"]) is not int
        or plan["wall_timeout_seconds"] < 1
    ):
        raise ValueError("wall timeout must be a positive integer")
    for name in (
        "plan_hash",
        "plan_set_hash",
        "tool_sha256",
        "config_sha256",
        "seccomp_sha256",
        "resource_plan_digest",
    ):
        if (
            type(plan[name]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", plan[name]) is None
        ):
            raise ValueError(f"{name} must be exact lowercase sha256")
    if (
        type(plan["image_digest"]) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", plan["image_digest"]) is None
    ):
        raise ValueError("image digest must be exact")
    _bounded_path(plan["artifact_path"], "artifact path")
    if (
        type(plan["oracle_statement"]) is not str
        or not plan["oracle_statement"]
        or len(plan["oracle_statement"]) > 4096
    ):
        raise ValueError("oracle statement must be a bounded non-empty string")
    ceilings = _exact(
        plan["resource_ceilings"],
        frozenset(
            {"wall_ns", "cpu_usec", "io_bytes", "memory_peak_bytes", "pids_peak"}
        ),
        "resource ceilings",
    )
    if any(type(value) is not int or value < 0 for value in ceilings.values()):
        raise ValueError("resource ceilings must be exact non-negative integers")
    expected_resource_digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "wall_timeout_seconds": plan["wall_timeout_seconds"],
                "resource_ceilings": ceilings,
            }
        )
    ).hexdigest()
    if plan["resource_plan_digest"] != expected_resource_digest:
        raise ValueError("canonical resource plan digest mismatch")
    partition = _exact(
        plan["index_partition"],
        frozenset({"indexed_paths", "excluded_paths", "parse_error_paths"}),
        "index partition",
    )
    if any(type(partition[name]) is not list for name in partition):
        raise ValueError("index partition lists are required")
    for name in partition:
        paths = partition[name]
        if any(type(path) is not str for path in paths) or len(paths) != len(
            set(paths)
        ):
            raise ValueError(f"{name} paths must be unique canonical strings")
        for path in paths:
            _bounded_path(path, name)
    environment = _exact(plan["environment"], ENVIRONMENT_KEYS, "environment")
    if (
        environment["HOME"] != "/nonexistent"
        or environment["LANG"] != "C.UTF-8"
        or environment["LC_ALL"] != "C.UTF-8"
    ):
        raise ValueError("producer environment is not frozen")
    if type(environment["PATH"]) is not str or not environment["PATH"]:
        raise ValueError("producer PATH is absent")
    expected_environment_digest = hashlib.sha256(
        canonical_json_bytes(environment)
    ).hexdigest()
    executions = plan["executions"]
    if type(executions) is not list or len(executions) != 5:
        raise ValueError(
            "producer requires exact delete/build/health/symbol/call executions"
        )
    ids: list[str] = []
    for number, execution in enumerate(executions):
        item = _exact(execution, EXECUTION_KEYS, f"execution {number}")
        if (
            type(item["id"]) is not str
            or not item["id"]
            or type(item["argv"]) is not list
            or not item["argv"]
            or any(
                type(arg) is not str or not arg or len(arg) > 4096
                for arg in item["argv"]
            )
        ):
            raise ValueError("execution identity and argv must be exact")
        if not item["argv"][0].startswith("/"):
            raise ValueError("execution argv[0] must be absolute")
        _bounded_path(item["cwd"], "execution cwd", absolute=True)
        if (
            type(item["environment_digest"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", item["environment_digest"]) is None
            or item["environment_digest"] != expected_environment_digest
        ):
            raise ValueError("execution environment digest is not canonical")
        if type(item["query"]) is not dict or type(item["expected_result"]) is not dict:
            raise ValueError("execution query and expected result must be objects")
        if (
            len(canonical_json_bytes(item["expected_result"]))
            > MAX_EXPECTED_RESULT_BYTES
        ):
            raise ValueError("execution expected result exceeds comparison bound")
        ids.append(item["id"])
    if ids != ["delete", "build", "health", "symbol", "call"]:
        raise ValueError(
            "executions must use exact delete/build/health/symbol/call IDs"
        )
    encoded = canonical_json_bytes(plan).decode("utf-8").upper()
    if any(
        fragment in encoded
        for fragment in ("PRIVATE_KEY", "EXECUTOR_KEY", "APPROVER_KEY")
    ):
        raise ValueError("producer plan must not contain role keys")
    return dict(plan)


def _describe_blob(raw: Path, name: str) -> dict[str, Any]:
    path = raw / name
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {
        "path": f"raw/{name}",
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def _blob(raw: Path, name: str, payload: bytes) -> dict[str, Any]:
    path = raw / name
    with path.open("xb") as stream:
        stream.write(payload)
    return _describe_blob(raw, name)


def _write_final_index_observation(
    index: Path, raw: Path, name: str, *, deadline_monotonic: float
) -> dict[str, Any]:
    """Stream one receipt-parser-bounded canonical index observation to disk."""
    destination = raw / name
    payload_digest = hashlib.sha256()
    payload_size = 0
    record_count = 0
    # strict_json_loads sees {"records": <payload>}; account for its wrapper too.
    wrapper_bytes = len(b'{"records":}')
    max_records = (MAX_NODES - 3) // 7

    with destination.open("xb") as output:

        def emit(chunk: bytes) -> None:
            nonlocal payload_size
            if payload_size + len(chunk) + wrapper_bytes > MAX_JSON_BYTES:
                raise ValueError("final index observation exceeds receipt JSON bound")
            if time.monotonic() >= deadline_monotonic:
                raise TimeoutError("final index observation deadline expired")
            output.write(chunk)
            payload_digest.update(chunk)
            payload_size += len(chunk)

        emit(b"[")
        if index.exists():
            root_fd = _open_root(index)
            try:

                def record(descriptor: int, relative: str) -> None:
                    nonlocal record_count
                    record_count += 1
                    if record_count > max_records:
                        raise ValueError(
                            "final index observation exceeds receipt node bound"
                        )
                    metadata = os.fstat(descriptor)
                    digest = _hash_regular_descriptor(
                        descriptor,
                        expected_size=metadata.st_size,
                        max_bytes=metadata.st_size,
                        deadline_monotonic=deadline_monotonic,
                    )
                    encoded = canonical_json_bytes(
                        {
                            "path": relative,
                            "sha256": digest,
                            "size_bytes": metadata.st_size,
                        }
                    )
                    emit((b"," if record_count > 1 else b"") + encoded)

                _visit_tree(
                    root_fd,
                    record,
                    deadline_monotonic=deadline_monotonic,
                )
            finally:
                os.close(root_fd)
        emit(b"]")
    return {
        "path": f"raw/{name}",
        "size_bytes": payload_size,
        "sha256": payload_digest.hexdigest(),
    }


def _clean_host_environment(frozen: Mapping[str, str]) -> dict[str, str]:
    if any(
        any(fragment in key.upper() for fragment in FORBIDDEN_ENV_FRAGMENTS)
        for key in os.environ
    ):
        # Host credentials are not inherited; their presence is not authorization.
        pass
    return dict(frozen)


def _producer_start_monotonic() -> float:
    """Return PID 1/process start on the host monotonic clock when available."""
    try:
        fields = Path("/proc/self/stat").read_text(encoding="ascii").split()
        return int(fields[21]) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        # Non-Linux unit-test hosts do not execute the production container.
        return time.monotonic()


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("cell wall timeout expired")
    return remaining


_MAX_OUTPUT_ENTRIES = MAX_OUTPUT_ENTRIES


def _output_size(root: Path, *, strict: bool = True, ceiling: int | None = None) -> int:
    """Charge allocated blocks and bounded metadata for one producer-tree scan."""
    if ceiling is not None and (type(ceiling) is not int or ceiling < 0):
        raise ValueError("producer output ceiling is invalid")
    total = 0
    entries = 0

    def walk_error(error: OSError) -> None:
        if not strict and isinstance(error, (FileNotFoundError, NotADirectoryError)):
            return
        raise error

    for current, directories, files in os.walk(
        root, followlinks=False, onerror=walk_error
    ):
        for name in directories + files:
            try:
                metadata = os.lstat(Path(current) / name)
            except (FileNotFoundError, NotADirectoryError):
                if strict:
                    raise
                continue
            entries += 1
            if entries > _MAX_OUTPUT_ENTRIES:
                raise ValueError(
                    "producer output entry count exceeds authority maximum"
                )
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("producer output contains a symlink")
            if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
                raise ValueError("producer output contains unsupported entry")
            allocated = getattr(metadata, "st_blocks", 0) * 512
            if allocated < 0:
                raise ValueError("producer output allocated block count is invalid")
            total += allocated + OUTPUT_ENTRY_METADATA_CHARGE_BYTES
            if ceiling is not None and total > ceiling:
                raise ValueError("producer output exceeds signed I/O ceiling")
    return total


def _child_file_limit(limit: int) -> None:
    if _resource is None:
        raise RuntimeError(
            "production producer execution requires POSIX resource limits"
        )
    soft, hard = _resource.getrlimit(_resource.RLIMIT_FSIZE)
    effective = min(limit, hard) if hard != _resource.RLIM_INFINITY else limit
    _resource.setrlimit(_resource.RLIMIT_FSIZE, (effective, effective))


def _wait_bounded(
    process: subprocess.Popen[bytes], deadline: float, output: Path, ceiling: int
) -> int:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            os.killpg(process.pid, 9)
            process.wait()
            return 124
        try:
            return process.wait(timeout=min(1.0, remaining))
        except subprocess.TimeoutExpired:
            if _output_size(output, strict=False, ceiling=ceiling) > ceiling:
                os.killpg(process.pid, 9)
                process.wait()
                raise ValueError("producer output exceeds signed I/O ceiling") from None


def produce_cell(plan: Mapping[str, Any], out: Path) -> dict[str, Any]:
    if _resource is None:
        raise RuntimeError(
            "production producer execution requires POSIX resource limits"
        )
    if out.exists():
        if not out.is_dir() or tuple(out.iterdir()) != ():
            raise ValueError("producer output root must be a fresh empty directory")
    else:
        out.mkdir(mode=0o700)
    plan = validate_producer_plan(plan)
    core = out / "core"
    raw = core / "raw"
    index = core / "index"
    core.mkdir()
    raw.mkdir()
    if index.exists():
        raise ValueError("index must not exist before producer start")
    environment = _clean_host_environment(plan["environment"])
    output_ceiling = plan["resource_ceilings"]["io_bytes"]
    records: list[dict[str, Any]] = []
    # The budget begins at producer PID start, so Python setup, observations,
    # serialization, and command execution share Docker's StartedAt→FinishedAt limit.
    deadline = _producer_start_monotonic() + plan["wall_timeout_seconds"]
    terminal_failure = False
    for number, execution in enumerate(plan["executions"]):
        if terminal_failure:
            break
        _remaining(deadline)
        before = _resource.getrusage(_resource.RUSAGE_CHILDREN)
        prefix = f"{number:02d}-{execution['id']}"
        stdout_name = prefix + "-stdout"
        stderr_name = prefix + "-stderr"
        stdout_stream = (raw / stdout_name).open("xb")
        try:
            stderr_stream = (raw / stderr_name).open("xb")
        except BaseException:
            stdout_stream.close()
            raise
        try:
            remaining_ceiling = output_ceiling - _output_size(
                core, ceiling=output_ceiling
            )
            if remaining_ceiling <= 0:
                raise ValueError("producer output exceeds signed I/O ceiling")
            process = subprocess.Popen(
                execution["argv"],
                cwd=execution["cwd"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_stream,
                stderr=stderr_stream,
                start_new_session=True,
                preexec_fn=partial(_child_file_limit, remaining_ceiling),
            )
            try:
                exit_code = _wait_bounded(process, deadline, core, output_ceiling)
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, 9)
                    process.wait()
                raise
        finally:
            stdout_stream.close()
            stderr_stream.close()
        after = _resource.getrusage(_resource.RUSAGE_CHILDREN)
        _remaining(deadline)
        query = canonical_json_bytes(execution["query"])
        index_observation = _write_final_index_observation(
            index, raw, prefix + "-index", deadline_monotonic=deadline
        )
        _remaining(deadline)
        if _output_size(core, ceiling=output_ceiling) > output_ceiling:
            raise ValueError("producer output exceeds signed I/O ceiling")
        records.append(
            {
                "id": execution["id"],
                "argv": execution["argv"],
                "cwd": execution["cwd"],
                "environment_digest": execution["environment_digest"],
                "exit_code": exit_code,
                "stdout_bytes": _describe_blob(raw, stdout_name),
                "stderr_bytes": _describe_blob(raw, stderr_name),
                "query_bytes": _blob(raw, prefix + "-query", query),
                "final_index_observation": index_observation,
                "cpu_seconds": (after.ru_utime + after.ru_stime)
                - (before.ru_utime + before.ru_stime),
            }
        )
        if _output_size(core, ceiling=output_ceiling) > output_ceiling:
            raise ValueError("producer output exceeds signed I/O ceiling")
        _remaining(deadline)
        terminal_failure = exit_code != 0
    _remaining(deadline)
    result = {
        "schema_version": 1,
        "cell": plan["cell"],
        "executions": records,
        "terminal_failure": terminal_failure,
        "attempt": 1,
        "counters": {
            "api_cost_usd": 0,
            "input_tokens": 0,
            "model_calls": 0,
            "network_requests": 0,
            "output_tokens": 0,
            "provider_requests": 0,
        },
        "evaluation_stage": "E0",
        "status": "NOT_EVALUATED",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "unlock_allowed": False,
    }
    payload = canonical_json_bytes(result) + b"\n"
    _remaining(deadline)
    (core / "producer-result.json").write_bytes(payload)
    if _output_size(core, ceiling=output_ceiling) > output_ceiling:
        raise ValueError("producer output exceeds signed I/O ceiling")
    _remaining(deadline)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    plan = strict_json_loads(Path(args.plan).read_bytes())
    result = produce_cell(plan, Path(args.out))
    print(json.dumps(result, sort_keys=True))
    return 1 if result["terminal_failure"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
