"""Keyless single-cell producer entrypoint for NO1-008A.

The operator supplies one closed cell plan inside an already isolated container.
This process executes it once, records raw bytes, and never creates a receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

PLAN_KEYS = frozenset(
    {"schema_version", "cell", "executions", "wall_timeout_seconds", "environment"}
)
CELL_KEYS = frozenset({"repo_id", "arm_id", "attempt"})
EXECUTION_KEYS = frozenset({"id", "argv", "cwd", "environment_digest", "query"})
ENVIRONMENT_KEYS = frozenset({"HOME", "LANG", "LC_ALL", "PATH"})
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
            type(cell[name]) is not str or not cell[name]
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
    environment = _exact(plan["environment"], ENVIRONMENT_KEYS, "environment")
    if (
        environment["HOME"] != "/nonexistent"
        or environment["LANG"] != "C.UTF-8"
        or environment["LC_ALL"] != "C.UTF-8"
    ):
        raise ValueError("producer environment is not frozen")
    if type(environment["PATH"]) is not str or not environment["PATH"]:
        raise ValueError("producer PATH is absent")
    executions = plan["executions"]
    if type(executions) is not list or len(executions) < 4:
        raise ValueError(
            "producer requires delete, build, health, and oracle executions"
        )
    ids: list[str] = []
    for number, execution in enumerate(executions):
        item = _exact(execution, EXECUTION_KEYS, f"execution {number}")
        if (
            type(item["id"]) is not str
            or not item["id"]
            or type(item["argv"]) is not list
            or not item["argv"]
            or any(type(arg) is not str or not arg for arg in item["argv"])
        ):
            raise ValueError("execution identity and argv must be exact")
        if (
            not item["argv"][0].startswith("/")
            or type(item["cwd"]) is not str
            or not item["cwd"].startswith("/")
        ):
            raise ValueError("execution argv[0] and cwd must be absolute")
        if (
            type(item["environment_digest"]) is not str
            or len(item["environment_digest"]) != 64
        ):
            raise ValueError("execution environment digest is invalid")
        if type(item["query"]) is not dict:
            raise ValueError("execution query must be an object")
        ids.append(item["id"])
    if ids[:3] != ["delete", "build", "health"] or len(ids) != len(set(ids)):
        raise ValueError("execution order or uniqueness is invalid")
    encoded = canonical_json_bytes(plan).decode("utf-8").upper()
    if any(
        fragment in encoded
        for fragment in ("PRIVATE_KEY", "EXECUTOR_KEY", "APPROVER_KEY")
    ):
        raise ValueError("producer plan must not contain role keys")
    return dict(plan)


def _blob(raw: Path, name: str, payload: bytes) -> dict[str, Any]:
    path = raw / name
    with path.open("xb") as stream:
        stream.write(payload)
    return {
        "path": f"raw/{name}",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _index_bytes(index: Path) -> bytes:
    records = []
    if index.exists():
        for path in sorted(index.rglob("*")):
            if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                raise ValueError("index contains an unsupported file")
            if path.is_file():
                payload = path.read_bytes()
                records.append(
                    {
                        "path": path.relative_to(index).as_posix(),
                        "size_bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
    return canonical_json_bytes(records)


def _clean_host_environment(frozen: Mapping[str, str]) -> dict[str, str]:
    if any(
        any(fragment in key.upper() for fragment in FORBIDDEN_ENV_FRAGMENTS)
        for key in os.environ
    ):
        # Host credentials are not inherited; their presence is not authorization.
        pass
    return dict(frozen)


def produce_cell(plan: Mapping[str, Any], out: Path) -> dict[str, Any]:
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
    records: list[dict[str, Any]] = []
    deadline = time.monotonic() + plan["wall_timeout_seconds"]
    terminal_failure = False
    for number, execution in enumerate(plan["executions"]):
        if terminal_failure:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("cell wall timeout expired")
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        try:
            completed = subprocess.run(
                execution["argv"],
                cwd=execution["cwd"],
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=remaining,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as error:
            exit_code = 124
            stdout = error.stdout or b""
            stderr = error.stderr or b""
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        query = canonical_json_bytes(execution["query"])
        index_snapshot = _index_bytes(index)
        prefix = f"{number:02d}-{execution['id']}"
        records.append(
            {
                "id": execution["id"],
                "argv": execution["argv"],
                "cwd": execution["cwd"],
                "environment_digest": execution["environment_digest"],
                "exit_code": exit_code,
                "stdout_bytes": _blob(raw, prefix + "-stdout", stdout),
                "stderr_bytes": _blob(raw, prefix + "-stderr", stderr),
                "query_bytes": _blob(raw, prefix + "-query", query),
                "index_bytes": _blob(raw, prefix + "-index", index_snapshot),
                "cpu_seconds": (after.ru_utime + after.ru_stime)
                - (before.ru_utime + before.ru_stime),
            }
        )
        terminal_failure = exit_code != 0
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
    (core / "producer-result.json").write_bytes(canonical_json_bytes(result) + b"\n")
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
