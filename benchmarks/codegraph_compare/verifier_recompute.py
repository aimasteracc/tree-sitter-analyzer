"""Independent recomputation of sealed producer outputs and oracles."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    MAX_JSON_BYTES,
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_executor import (
    MAX_EXPECTED_RESULT_BYTES,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_tree,
    _open_beneath,
    _open_root,
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import ZERO_COUNTERS


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _plan_executions(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    executions = plan.get("executions")
    if type(executions) is not list or len(executions) != 5:
        raise ValueError("trusted plan executions must be exact count five")
    return [_mapping(item, "plan execution") for item in executions]


def _core_blob_size(plan: Mapping[str, Any], expected_size: int) -> int:
    """Bind every descriptor size to the root-authorized aggregate output ceiling."""
    ceilings = plan.get("resource_ceilings")
    output_ceiling = ceilings.get("io_bytes") if type(ceilings) is dict else None
    if (
        type(expected_size) is not int
        or expected_size < 0
        or type(output_ceiling) is not int
        or output_ceiling < 0
        or expected_size > output_ceiling
    ):
        raise ValueError("core blob size exceeds signed output ceiling")
    return expected_size


def _read_core(
    root: Path,
    relative: str,
    expected_size: int,
    plan: Mapping[str, Any],
    *,
    deadline_monotonic: float | None = None,
) -> bytes:
    relative = canonical_relative_path(relative)
    expected_size = _core_blob_size(plan, expected_size)
    root_fd = _open_root(root)
    try:
        descriptor = _open_beneath(root_fd, relative)
        try:
            if os.fstat(descriptor).st_size != expected_size:
                raise ValueError("core blob size mismatch")
            chunks = bytearray()
            while len(chunks) < expected_size:
                if (
                    deadline_monotonic is not None
                    and time.monotonic() >= deadline_monotonic
                ):
                    raise TimeoutError("sealed core read deadline expired")
                chunk = os.read(
                    descriptor, min(1024 * 1024, expected_size - len(chunks))
                )
                if not chunk:
                    break
                chunks.extend(chunk)
            if len(chunks) != expected_size or os.read(descriptor, 1):
                raise ValueError("core blob changed")
            return bytes(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)


def _hash_core(
    root: Path,
    relative: str,
    expected_size: int,
    plan: Mapping[str, Any],
    *,
    deadline_monotonic: float | None = None,
) -> str:
    relative = canonical_relative_path(relative)
    expected_size = _core_blob_size(plan, expected_size)
    root_fd = _open_root(root)
    try:
        descriptor = _open_beneath(root_fd, relative)
        try:
            if os.fstat(descriptor).st_size != expected_size:
                raise ValueError("core blob size mismatch")
            digest = hashlib.sha256()
            size = 0
            while True:
                if (
                    deadline_monotonic is not None
                    and time.monotonic() >= deadline_monotonic
                ):
                    raise TimeoutError("sealed core hashing deadline expired")
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
            if size != expected_size:
                raise ValueError("core blob changed")
            return digest.hexdigest()
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)


def _verify_core_blob(
    root: Path,
    blob: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    deadline_monotonic: float | None = None,
    expected_payload: bytes | None = None,
    allow_trailing_newlines: bool = False,
    capture_limit: int | None = None,
) -> bytes | None:
    """Hash and optionally compare/capture a blob in one bounded read pass."""
    relative = canonical_relative_path(blob["path"])
    expected_size = _core_blob_size(plan, blob["size_bytes"])
    if expected_payload is not None and (
        len(expected_payload) > MAX_EXPECTED_RESULT_BYTES
        or expected_size < len(expected_payload)
    ):
        raise ValueError("expected result bytes mismatch")
    if capture_limit is not None and expected_size > capture_limit:
        raise ValueError("captured core blob exceeds receipt JSON bound")
    root_fd = _open_root(root)
    try:
        descriptor = _open_beneath(root_fd, relative)
        try:
            if os.fstat(descriptor).st_size != expected_size:
                raise ValueError("core blob size mismatch")
            digest = hashlib.sha256()
            captured = bytearray() if capture_limit is not None else None
            offset = 0
            while offset < expected_size:
                if (
                    deadline_monotonic is not None
                    and time.monotonic() >= deadline_monotonic
                ):
                    raise TimeoutError("sealed core read deadline expired")
                chunk = os.read(descriptor, min(1024 * 1024, expected_size - offset))
                if not chunk:
                    raise ValueError("core blob changed")
                digest.update(chunk)
                if captured is not None:
                    captured.extend(chunk)
                if expected_payload is not None:
                    overlap = min(len(chunk), max(0, len(expected_payload) - offset))
                    if chunk[:overlap] != expected_payload[offset : offset + overlap]:
                        raise ValueError("expected result bytes mismatch")
                    if len(chunk) > overlap and (
                        not allow_trailing_newlines or chunk[overlap:].strip(b"\n")
                    ):
                        raise ValueError("expected result bytes mismatch")
                offset += len(chunk)
            if os.read(descriptor, 1):
                raise ValueError("core blob changed")
            if digest.hexdigest() != blob["sha256"]:
                raise ValueError("raw bytes mismatch")
            return bytes(captured) if captured is not None else None
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)


def _stdout_matches_expected(
    root: Path,
    relative: str,
    expected_size: int,
    expected_result: Any,
    plan: Mapping[str, Any],
    *,
    deadline_monotonic: float | None = None,
) -> bool:
    expected_size = _core_blob_size(plan, expected_size)
    expected = canonical_json_bytes(expected_result)
    if len(expected) > MAX_EXPECTED_RESULT_BYTES or expected_size < len(expected):
        return False
    root_fd = _open_root(root)
    try:
        descriptor = _open_beneath(root_fd, canonical_relative_path(relative))
        try:
            if os.fstat(descriptor).st_size != expected_size:
                return False
            offset = 0
            while offset < len(expected):
                if (
                    deadline_monotonic is not None
                    and time.monotonic() >= deadline_monotonic
                ):
                    raise TimeoutError("sealed stdout read deadline expired")
                chunk = os.read(descriptor, min(1024 * 1024, len(expected) - offset))
                if chunk != expected[offset : offset + len(chunk)]:
                    return False
                offset += len(chunk)
            while True:
                if (
                    deadline_monotonic is not None
                    and time.monotonic() >= deadline_monotonic
                ):
                    raise TimeoutError("sealed stdout read deadline expired")
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                if chunk.strip(b"\n"):
                    return False
            return offset == len(expected)
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)


def _hash_list(paths: list[str]) -> str:
    return hashlib.sha256(canonical_json_bytes(paths)).hexdigest()


def _verify_recomputed(
    body: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    core: Path,
    *,
    deadline_monotonic: float | None = None,
) -> None:
    cell = body["cell"]
    if (cell["repo_id"], cell["arm_id"], cell["attempt"]) != (
        plan.get("cell", {}).get("repo_id"),
        plan.get("cell", {}).get("arm_id"),
        plan.get("cell", {}).get("attempt"),
    ):
        raise ValueError("plan identity mismatch")
    if (
        cell["artifact_path"] != plan.get("artifact_path")
        or cell["artifact_path"]
        != f"cells/{cell['repo_id']}/{cell['arm_id']}/cell-receipt.json"
    ):
        raise ValueError("canonical cell artifact identity mismatch")
    eligibility = inventory.get("eligibility", inventory)
    if (
        body["source"]["eligibility"] != eligibility
        or body["source"]["commit"] != eligibility.get("commit")
        or body["source"]["repo_fingerprint"] != eligibility.get("repo_fingerprint")
    ):
        raise ValueError("inventory mismatch")
    expected_plan = {
        key: plan[key]
        for key in (
            "plan_hash",
            "plan_set_hash",
            "tool_sha256",
            "config_sha256",
            "image_digest",
            "seccomp_sha256",
        )
    }
    if body["plan"] != expected_plan:
        raise ValueError("trusted plan hashes mismatch")
    environment = body["environment"]
    if (
        environment["image_digest"] != plan["image_digest"]
        or environment["seccomp_sha256"] != plan["seccomp_sha256"]
        or environment["network_mode"] != "none"
    ):
        raise ValueError("trusted environment mismatch")
    expected_exec = _plan_executions(plan)
    expected_environment_digest = hashlib.sha256(
        canonical_json_bytes(plan["environment"])
    ).hexdigest()
    if any(
        item["environment_digest"] != expected_environment_digest
        for item in expected_exec
    ):
        raise ValueError("canonical execution environment digest mismatch")
    observed = body["executions"]
    expected_tuples = [
        (
            item.get("id", item.get("execution_id")),
            item["argv"],
            item["cwd"],
            item["environment_digest"],
        )
        for item in expected_exec
    ]
    observed_tuples = [
        (item["id"], item["argv"], item["cwd"], item["environment_digest"])
        for item in observed
    ]
    if observed_tuples != expected_tuples or any(
        item["exit_code"] != 0 for item in observed
    ):
        raise ValueError("execution count, order, command, or result mismatch")
    producer_result = strict_json_loads(
        _read_core(
            core,
            "producer-result.json",
            (core / "producer-result.json").stat().st_size,
            plan,
            deadline_monotonic=deadline_monotonic,
        )
    )
    result_executions = [
        {
            key: item[key]
            for key in (
                "id",
                "argv",
                "cwd",
                "environment_digest",
                "exit_code",
                "stdout_bytes",
                "stderr_bytes",
                "query_bytes",
                "final_index_observation",
            )
        }
        for item in producer_result.get("executions", [])
        if type(item) is dict
    ]
    if result_executions != observed or producer_result.get("counters") != dict(
        ZERO_COUNTERS
    ):
        raise ValueError("producer result mismatch")
    index_digest_cache: dict[tuple[str, int], str] = {}
    for ordinal, (item, spec) in enumerate(zip(observed, expected_exec, strict=True)):
        if item["id"] != spec.get("id") or item["argv"] != spec.get("argv"):
            raise ValueError(f"authorized producer command order mismatch at {ordinal}")
        query = canonical_json_bytes(spec.get("query"))
        expected_result = spec.get("expected_result")
        if expected_result is None:
            raise ValueError("expected result bytes mismatch")
        _verify_core_blob(
            core,
            item["stdout_bytes"],
            plan,
            deadline_monotonic=deadline_monotonic,
            expected_payload=canonical_json_bytes(expected_result),
            allow_trailing_newlines=True,
        )
        _verify_core_blob(
            core,
            item["stderr_bytes"],
            plan,
            deadline_monotonic=deadline_monotonic,
        )
        _verify_core_blob(
            core,
            item["query_bytes"],
            plan,
            deadline_monotonic=deadline_monotonic,
            expected_payload=query,
        )
        index_payload = _verify_core_blob(
            core,
            item["final_index_observation"],
            plan,
            deadline_monotonic=deadline_monotonic,
            capture_limit=MAX_JSON_BYTES - len(b'{"records":}'),
        )
        if index_payload is None:
            raise ValueError("final index observation is absent")
        index_records = strict_json_loads(b'{"records":' + index_payload + b"}")[
            "records"
        ]
        if type(index_records) is not list or any(
            type(record) is not dict
            or frozenset(record) != frozenset({"path", "size_bytes", "sha256"})
            for record in index_records
        ):
            raise ValueError("final index observation records invalid")
        for record in index_records:
            key = (record["path"], record["size_bytes"])
            digest = index_digest_cache.get(key)
            if digest is None:
                digest = _hash_core(
                    core / "index",
                    record["path"],
                    record["size_bytes"],
                    plan,
                    deadline_monotonic=deadline_monotonic,
                )
                index_digest_cache[key] = digest
            if digest != record["sha256"]:
                raise ValueError("final index observation content mismatch")
    partition = body["index_partition"]
    names = ("indexed_paths", "excluded_paths", "parse_error_paths")
    for name in names:
        if partition[f"{name}_hash"] != _hash_list(partition[name]):
            raise ValueError("partition hash mismatch")
    sets = [set(partition[name]) for name in names]
    if any(sets[left] & sets[right] for left, right in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("index partition overlaps")
    union = set().union(*sets)
    if union != set(eligibility["eligible_paths"]):
        raise ValueError("partition gap or extra path")
    if (
        _hash_tree(core, deadline_monotonic=deadline_monotonic)
        != body["snapshot"]["tree_hash"]
    ):
        raise ValueError("sealed core tree mismatch")
    index = core / "index"
    if (
        not index.is_dir()
        or _hash_tree(index, deadline_monotonic=deadline_monotonic)
        != body["snapshot"]["index_content_hash"]
    ):
        raise ValueError("index content mismatch")
    if body["counters"] != dict(ZERO_COUNTERS):
        raise ValueError("zero counters mismatch")
    resources = plan.get("resources", {})
    digest = (
        resources.get(
            "digest", resources.get("plan_digest", plan.get("resource_plan_digest"))
        )
        if type(resources) is dict
        else None
    )
    canonical_resource_digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "wall_timeout_seconds": plan["wall_timeout_seconds"],
                "resource_ceilings": plan.get("resource_ceilings", {}),
            }
        )
    ).hexdigest()
    if (
        digest != canonical_resource_digest
        or body["resources"]["plan_digest"] != canonical_resource_digest
    ):
        raise ValueError("canonical resource plan mismatch")
    ceilings = plan.get("resource_ceilings", {})
    if ceilings and any(
        body["resources"].get(name, 0) > limit for name, limit in ceilings.items()
    ):
        raise ValueError("signed host resource observation exceeds plan ceiling")
    if body["resources"]["wall_ns"] > plan["wall_timeout_seconds"] * 1_000_000_000:
        raise ValueError("wall-time observation exceeds plan ceiling")
    oracle_hashes = [item["stdout_bytes"]["sha256"] for item in observed[3:]]
    if (
        body["oracle_approval"]["oracle_results_hash"]
        != hashlib.sha256(canonical_json_bytes(oracle_hashes)).hexdigest()
    ):
        raise ValueError("oracle results hash mismatch")
