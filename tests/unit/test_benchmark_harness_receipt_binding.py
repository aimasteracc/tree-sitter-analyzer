"""Issue #1376：test_benchmark_harness_receipt_binding 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

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


def test_strict_validator_accepts_complete_plan_bound_e0_receipt(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)

    assert (
        _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == ()
    )


def test_strict_validator_rejects_source_eligibility_mutation(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    mutated = copy.deepcopy(receipt)
    mutated["eligibility"]["eligible_paths"] = []
    _resign_qualification_receipt(mutated)

    assert _validate_qualification_receipt(
        mutated,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "SOURCE_ELIGIBILITY_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_raw_stdout_mutation(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "raw/0-stdout").write_bytes(b"mutated")

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RAW_EXECUTION_EVIDENCE_MISSING",)


def test_strict_validator_rejects_scalar_execution_without_crashing(tmp_path: Path):
    # PR #1247: 畸形的直接 receipt 必须在 schema 边界失败关闭。

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["raw_executions"].append(7)
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RECEIPT_SCHEMA_MISMATCH",
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_unplanned_explicit_exclusion(tmp_path: Path):
    # PR #1247: 排除项是独立且绑定计划的分区类别。
    from benchmarks.codegraph_compare.integrity import _sha256

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    partition = receipt["index_partition"]
    partition["indexed_paths"] = []
    partition["indexed_paths_hash"] = _sha256([])
    partition["excluded_paths"] = ["main.ts"]
    partition["excluded_paths_hash"] = _sha256(["main.ts"])
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PARTITION_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_accepts_exact_plan_bound_explicit_exclusion(tmp_path: Path):
    # PR #1247: 显式排除项必须与解析错误分开冻结。
    from dataclasses import replace

    base_plan = _qualification_plans(tmp_path)[0]
    plan = replace(base_plan, explicit_excluded_allowlist=("main.ts",))
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)

    assert (
        _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == ()
    )


def test_strict_validator_rejects_execution_cwd_mutation(tmp_path: Path):
    # PR #1247: receipt 不能把原本精确的冻结命令移到其他位置。
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][0]["cwd"] = plan.source_checkout_path
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


def test_strict_validator_rejects_execution_environment_mutation(tmp_path: Path):
    # PR #1247: receipt 中的环境证据必须等于冻结计划的摘要。
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][0]["environment_digest"] = "0" * 64
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


def test_strict_validator_rejects_index_root_symlink(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "index.bin").write_bytes(b"frozen index")
    for child in (cell_root / "index").iterdir():
        child.unlink()
    (cell_root / "index").rmdir()
    (cell_root / "index").symlink_to(outside, target_is_directory=True)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "SNAPSHOT_AUDIT_MISSING",
        "INDEX_BYTES_MISMATCH",
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_harness_config_byte_mutation(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    Path(plan.config.path).write_bytes(b"mutated config")

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("HARNESS_BYTES_MISMATCH",)


def test_strict_validator_rejects_network_audit_mutation(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    mutated = copy.deepcopy(receipt)
    mutated["os_audit"]["network_denied"] = False
    _resign_qualification_receipt(mutated)

    assert _validate_qualification_receipt(
        mutated,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    (
        (
            ("repo_id",),
            "django",
            (
                "CELL_IDENTITY_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("attempt",),
            2,
            (
                "RECEIPT_SCHEMA_MISMATCH",
                "CELL_IDENTITY_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (("plan_hash",), "0" * 64, "PLAN_BINDING_MISMATCH"),
        (
            ("artifact_path",),
            "cells/foreign/cell-receipt.json",
            (
                "PLAN_BINDING_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("counters", "model_calls"),
            1,
            (
                "FORBIDDEN_COUNTER_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("resource_plan_hash",),
            "0" * 64,
            (
                "RESOURCE_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("resource_observation", "cpu_seconds"),
            21,
            (
                "RESOURCE_LIMIT_VIOLATION",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("raw_executions", 0, "id"),
            "foreign",
            (
                "RECEIPT_SCHEMA_MISMATCH",
                "RAW_EXECUTION_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("raw_executions", 0, "exit_code"),
            1,
            (
                "RAW_EXECUTION_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("raw_executions", 0, "argv"),
            [],
            (
                "RECEIPT_SCHEMA_MISMATCH",
                "RAW_EXECUTION_EVIDENCE_MISSING",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("os_audit", "credentials_stripped"),
            False,
            (
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (
            ("os_audit", "descendants_observed"),
            False,
            (
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
        (("human_oracle_approval", "approved"), False, "HUMAN_ORACLE_APPROVAL_MISSING"),
        (
            ("human_oracle_approval", "key_id"),
            "",
            ("RECEIPT_SCHEMA_MISMATCH", "HUMAN_ORACLE_APPROVAL_MISSING"),
        ),
        (
            ("index_content_hash",),
            "0" * 64,
            (
                "INDEX_BYTES_MISMATCH",
                "INDEX_PROVENANCE_MISSING",
                "OS_AUDIT_MISSING",
                "HUMAN_ORACLE_APPROVAL_MISSING",
            ),
        ),
    ),
)
def test_strict_validator_rejects_one_receipt_boundary_mutation(
    tmp_path: Path, path, value, expected
):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    mutated = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    target = mutated
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    _resign_qualification_receipt(mutated)

    wanted = expected if isinstance(expected, tuple) else (expected,)
    assert (
        _validate_qualification_receipt(
            mutated,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == wanted
    )


_mark_posix_qualification_section_tests()
