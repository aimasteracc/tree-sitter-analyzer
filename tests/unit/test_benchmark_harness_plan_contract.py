"""Issue #1376：test_benchmark_harness_plan_contract 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import os as os
import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_qualification_helpers import (
    _qualification_inventories,
    _qualification_plans,
)
from tests.unit._benchmark_harness_service_helpers import _qualification_v3_body

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


@pytest.mark.parametrize("reserved_id", ("delete", "build", "health"))
def test_cell_plan_rejects_reserved_oracle_execution_ids(
    tmp_path: Path, reserved_id: str
):
    # PR #1247: oracle 不能替换冻结 argv 中的内置执行项。
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification import ExecutionSpecV1

    plan = _qualification_plans(tmp_path)[0]
    oracles = (
        replace(plan.oracle_specs[0], oracle_id=reserved_id),
        plan.oracle_specs[1],
    )
    executions = (*plan.executions[:3],) + tuple(
        ExecutionSpecV1(
            spec.oracle_id,
            ("oracle", spec.oracle_id, plan.index_path),
            plan.executions[0].cwd,
            plan.executions[0].environment_digest,
        )
        for spec in oracles
    )

    with pytest.raises(ValueError, match="reserved execution IDs"):
        replace(plan, oracle_specs=oracles, executions=executions)


def test_cell_plan_allows_oracle_id_that_only_contains_reserved_word(tmp_path: Path):
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    oracles = (
        replace(plan.oracle_specs[0], oracle_id="delete.oracle"),
        plan.oracle_specs[1],
    )
    executions = (
        *plan.executions[:3],
        replace(plan.executions[3], execution_id="delete.oracle"),
        plan.executions[4],
    )

    replaced = replace(plan, oracle_specs=oracles, executions=executions)

    assert tuple(item.execution_id for item in replaced.executions) == (
        "delete",
        "build",
        "health",
        "delete.oracle",
        "main.call",
    )


def test_execution_spec_rejects_mutable_argv():
    # PR #1247: 冻结 dataclass 不能保留调用方持有的可变命令列表。
    from benchmarks.codegraph_compare.setup_qualification import ExecutionSpecV1

    with pytest.raises(ValueError, match="argv"):
        ExecutionSpecV1(
            "build",
            ["tool", "build"],  # type: ignore[arg-type]
            "/tmp",
            "0" * 64,
        )


def test_cell_plan_rejects_noncanonical_execution_cwd(tmp_path: Path):
    # PR #1247: 每条冻结命令都绑定到经过认证的工作目录。
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    changed = replace(plan.executions[2], cwd=plan.source_checkout_path)

    with pytest.raises(ValueError, match="trusted experiment root"):
        replace(plan, executions=(*plan.executions[:2], changed, *plan.executions[3:]))


@pytest.mark.parametrize(
    "index_path",
    (
        "cells/vscode/tsa-warm",
        "cells/vscode/tsa-warm/index/shard",
        "cells/vscode/tsa-warm/raw",
        "cells/vscode/tsa-warm/raw/index",
        "cells/vscode/tsa-warm/cell-receipt.json",
        "plan.json",
        "manifest/index",
    ),
)
def test_cell_plan_rejects_nonexact_or_reserved_index_path(
    tmp_path: Path, index_path: str
):
    # PR #1247: 索引输出不能与留存证据或控制文档重叠。
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]

    with pytest.raises(ValueError, match="Index path"):
        replace(plan, index_path=index_path)


def test_cell_plan_rejects_duplicate_oracle_ids(tmp_path: Path):
    from dataclasses import replace

    import pytest

    plan = _qualification_plans(tmp_path)[0]
    duplicate = replace(plan.oracle_specs[1], oracle_id=plan.oracle_specs[0].oracle_id)
    with pytest.raises(ValueError, match="unique symbol and call oracle IDs"):
        replace(plan, oracle_specs=(plan.oracle_specs[0], duplicate))


def test_trusted_manifest_rejects_duplicate_id_before_mapping(tmp_path: Path):
    # PR #1247: 构建映射不能静默覆盖仓库的固定提交值。
    import yaml

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
    )

    source = yaml.safe_load(
        Path("benchmarks/codegraph_compare/repos.yaml").read_text(encoding="utf-8")
    )
    source["repos"][-1]["id"] = source["repos"][0]["id"]
    manifest = tmp_path / "repos.yaml"
    manifest.write_text(yaml.safe_dump(source), encoding="utf-8")

    with pytest.raises(ValueError, match="IDs must be unique"):
        _trusted_commits(manifest)


def test_e0_orchestrator_never_invokes_producer_or_creates_receipts(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        orchestrate_qualification,
    )

    plans = _qualification_plans(tmp_path)
    experiment = tmp_path / "experiment"
    verdict = orchestrate_qualification(
        experiment_root=experiment,
        plans=plans,
        trusted_inventories=_qualification_inventories(plans),
    )

    assert verdict == {
        "schema_version": 2,
        "evaluation_stage": "E0",
        "status": "NOT_EVALUATED",
        "reason": "ISOLATED_EXTERNAL_PRODUCER_AND_FRESH_TRUSTED_VERIFIER_ARTIFACT_REQUIRED",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "unlock_allowed": False,
        "expected_cells": 14,
        "observed_receipts": 0,
        "attempts_per_cell": 0,
        "failures": [],
        "counters": None,
    }
    assert tuple(sorted(path.name for path in experiment.iterdir())) == (
        "plan.json",
        "verdict.json",
    )


def test_e0_orchestrator_rejects_untrusted_complete_inventory(tmp_path: Path):
    from dataclasses import replace

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        orchestrate_qualification,
    )

    plans = _qualification_plans(tmp_path)
    inventories = _qualification_inventories(plans)
    inventories["vscode"] = replace(
        inventories["vscode"], eligible_paths=(), eligible_paths_hash="0" * 64
    )
    with pytest.raises(ValueError, match="complete trusted inventory"):
        orchestrate_qualification(
            experiment_root=tmp_path / "experiment",
            plans=plans,
            trusted_inventories=inventories,
        )


def test_cell_plan_requires_each_execution_to_reference_index_path(tmp_path: Path):
    # PR #1247: 所有生命周期和 oracle 命令都绑定同一个索引。
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    unbound = replace(plan.executions[2], argv=("health", "without-index"))

    with pytest.raises(ValueError, match="plan-bound index path"):
        replace(plan, executions=(*plan.executions[:2], unbound, *plan.executions[3:]))


def test_cell_plan_build_argv_is_bound_to_exact_source_checkout(tmp_path: Path):
    # PR #1247: 冻结构建不能使用清单来源以外的工作副本。
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    other_source = (tmp_path / "other-source").resolve()
    other_source.mkdir()

    with pytest.raises(ValueError, match="canonical source checkout"):
        replace(plan, source_checkout_path=other_source.as_posix())


def test_cell_plan_requires_delete_build_health_and_all_oracles(tmp_path: Path):
    from dataclasses import replace

    import pytest

    plan = _qualification_plans(tmp_path)[0]
    with pytest.raises(ValueError, match="ordered delete/build/health"):
        replace(plan, executions=plan.executions[1:])


def test_producer_plan_rejects_noncanonical_environment_digest_before_execution():
    # PR #1249 review 3744776130: 过期的执行摘要必须在生产者预检阶段失败。
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.setup_qualification_executor import (
        validate_producer_plan,
    )

    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin",
    }
    ceilings = {
        "wall_ns": 1,
        "cpu_usec": 1,
        "io_bytes": 1,
        "memory_peak_bytes": 1,
        "pids_peak": 1,
    }
    resource_digest = hashlib.sha256(
        canonical_json_bytes({"wall_timeout_seconds": 1, "resource_ceilings": ceilings})
    ).hexdigest()
    plan = {
        "schema_version": 1,
        "cell": {"repo_id": "repo", "arm_id": "arm", "attempt": 1},
        "executions": [
            {
                "id": execution_id,
                "argv": ["/bin/tool"],
                "cwd": "/source",
                "environment_digest": "0" * 64,
                "query": {},
                "expected_result": {},
            }
            for execution_id in ("delete", "build", "health", "symbol", "call")
        ],
        "wall_timeout_seconds": 1,
        "environment": environment,
        "artifact_path": "artifact",
        "plan_hash": "a" * 64,
        "plan_set_hash": "b" * 64,
        "tool_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "image_digest": "sha256:" + "e" * 64,
        "seccomp_sha256": "f" * 64,
        "resource_plan_digest": resource_digest,
        "resource_ceilings": ceilings,
        "index_partition": {
            "indexed_paths": [],
            "excluded_paths": [],
            "parse_error_paths": [],
        },
        "oracle_statement": "exact",
    }

    with pytest.raises(ValueError, match="environment digest is not canonical"):
        validate_producer_plan(plan)


def test_receipt_inventory_rejects_missing_commit_before_signing():
    # PR #1249 review 3744887352: 所有清单共享 receipt validator。
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    del eligibility["commit"]

    with pytest.raises(ValueError, match="unknown or missing fields"):
        validate_receipt_inventory({"eligibility": eligibility})


@pytest.mark.parametrize(
    "invalid",
    (
        "src,bad.py",
        "src/control\x1f.py",
        "src\\bad.py",
        "/src/bad.py",
        "src/./bad.py",
        "a" * 4097,
    ),
)
def test_receipt_inventory_enforces_published_relative_path(invalid: str):
    # PR #1249 review 3744944744: 预检必须匹配已发布的 relativePath 规则。
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["eligible_paths"] = [invalid]

    with pytest.raises(ValueError, match="canonical relative path"):
        validate_receipt_inventory({"eligibility": eligibility})


def test_receipt_inventory_accepts_consistent_sha256_git_object_ids():
    # PR #1249 review 3744944747: SHA-256 Git 仓库使用 64 字符 OID。
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["commit"] = "a" * 64
    eligibility["root_tree_id"] = "b" * 64
    eligibility["tracked_entries"] = [
        [path, mode, "c" * 64]
        for path, mode, _object_id in eligibility["tracked_entries"]
    ]
    eligibility["tracked_files"] = [
        [path, mode, "c" * 64, size, digest]
        for path, mode, _object_id, size, digest in eligibility["tracked_files"]
    ]

    validated = validate_receipt_inventory({"eligibility": eligibility})

    assert validated["root_tree_id"] == "b" * 64


def test_receipt_inventory_rejects_mixed_git_object_formats():
    # PR #1249 review 3744944747: 每个 OID 都必须匹配根树的算法。
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["root_tree_id"] = "b" * 64

    with pytest.raises(ValueError, match="match root tree format"):
        validate_receipt_inventory({"eligibility": eligibility})


_mark_posix_qualification_section_tests()
