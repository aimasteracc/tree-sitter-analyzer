"""Issue #1376：test_benchmark_harness_receipt_resource_limits 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import os as os
import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_qualification_helpers import (
    _qualification_plans,
    _qualification_verifier_config,
)
from tests.unit._benchmark_harness_receipt_helpers import (
    _resign_qualification_receipt,
    _validate_qualification_receipt,
    _write_valid_qualification_receipt,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_strict_validator_rejects_resource_observation_mutation(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    mutated = copy.deepcopy(receipt)
    mutated["resource_observation"]["peak_processes"] = 3
    _resign_qualification_receipt(mutated)

    assert _validate_qualification_receipt(
        mutated,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RESOURCE_LIMIT_VIOLATION",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_blob_above_trusted_per_blob_ceiling(tmp_path: Path):
    # PR #1247: 生产者控制的 blob 元数据不能授权大规模读取。
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][0]["stdout_bytes"]
    payload = b"x" * (plan.resources.max_index_bytes + 1)
    (cell_root / blob["path"]).write_bytes(payload)
    blob.update(size_bytes=len(payload), sha256=_bytes_hash(payload))
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_cumulative_blob_bytes_above_plan(tmp_path: Path):
    # PR #1247: 每个 blob 各自受限之外，还必须共享可信的总预算。
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    base_plan = _qualification_plans(tmp_path)[0]
    plan = replace(
        base_plan,
        resources=replace(base_plan.resources, max_disk_write_bytes=1500),
    )
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    for execution in receipt["raw_executions"][:2]:
        blob = execution["stdout_bytes"]
        payload = b"x" * 900
        (cell_root / blob["path"]).write_bytes(payload)
        blob.update(size_bytes=len(payload), sha256=_bytes_hash(payload))
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_sparse_execution_blob(tmp_path: Path):
    # PR #1247: 稀疏原始证据必须在哈希或加载之前被拒绝。
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][0]["stdout_bytes"]
    sparse = cell_root / blob["path"]
    with sparse.open("wb") as stream:
        stream.truncate(512)
    if sparse.stat().st_blocks * 512 >= sparse.stat().st_size:
        pytest.skip("tracked: filesystem does not represent sparse allocation")
    payload = b"\x00" * 512
    blob.update(size_bytes=len(payload), sha256=_bytes_hash(payload))
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


_mark_posix_qualification_section_tests()
