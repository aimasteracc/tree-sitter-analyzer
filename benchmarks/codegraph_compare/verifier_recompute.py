"""Independent recomputation of sealed producer outputs and oracles."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
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


def _read_core(root: Path, relative: str, expected_size: int) -> bytes:
    relative = canonical_relative_path(relative)
    if (
        expected_size > 512 * 1024 * 1024
        or type(expected_size) is not int
        or expected_size < 0
    ):
        raise ValueError("core blob size is invalid")
    root_fd = _open_root(root)
    try:
        descriptor = _open_beneath(root_fd, relative)
        try:
            if os.fstat(descriptor).st_size != expected_size:
                raise ValueError("core blob size mismatch")
            chunks = bytearray()
            while len(chunks) < expected_size:
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


def _hash_list(paths: list[str]) -> str:
    return hashlib.sha256(canonical_json_bytes(paths)).hexdigest()


def _verify_recomputed(
    body: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    core: Path,
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
            core, "producer-result.json", (core / "producer-result.json").stat().st_size
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
    for ordinal, (item, spec) in enumerate(zip(observed, expected_exec, strict=True)):
        if item["id"] != spec.get("id") or item["argv"] != spec.get("argv"):
            raise ValueError(f"authorized producer command order mismatch at {ordinal}")
        for field in (
            "stdout_bytes",
            "stderr_bytes",
            "query_bytes",
            "final_index_observation",
        ):
            blob = item[field]
            payload = _read_core(core, blob["path"], blob["size_bytes"])
            if hashlib.sha256(payload).hexdigest() != blob["sha256"]:
                raise ValueError("raw bytes mismatch")
        query = spec.get("query")
        if query is not None and _read_core(
            core, item["query_bytes"]["path"], item["query_bytes"]["size_bytes"]
        ) != canonical_json_bytes(query):
            raise ValueError("oracle query bytes mismatch")
        expected_result = spec.get("expected_result")
        stdout = _read_core(
            core, item["stdout_bytes"]["path"], item["stdout_bytes"]["size_bytes"]
        )
        if expected_result is None or stdout.rstrip(b"\n") != canonical_json_bytes(
            expected_result
        ):
            raise ValueError("expected result bytes mismatch")
        index_payload = _read_core(
            core,
            item["final_index_observation"]["path"],
            item["final_index_observation"]["size_bytes"],
        )
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
            payload = _read_core(core / "index", record["path"], record["size_bytes"])
            if hashlib.sha256(payload).hexdigest() != record["sha256"]:
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
    if _hash_tree(core) != body["snapshot"]["tree_hash"]:
        raise ValueError("sealed core tree mismatch")
    index = core / "index"
    if (
        not index.is_dir()
        or _hash_tree(index) != body["snapshot"]["index_content_hash"]
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
