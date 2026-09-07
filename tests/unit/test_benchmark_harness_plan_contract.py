"""Issue #1376：plan_contract 行为组，原测试 AST 保持不变。"""

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
    _qualification_verifier_config,
    _resign_qualification_receipt,
    _validate_qualification_receipt,
    _write_valid_qualification_receipt,
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
    # PR #1247: an oracle must not replace a built-in execution in frozen argv.
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
    # PR #1247: frozen dataclasses must not retain caller-owned command lists.
    from benchmarks.codegraph_compare.setup_qualification import ExecutionSpecV1

    with pytest.raises(ValueError, match="argv"):
        ExecutionSpecV1(
            "build",
            ["tool", "build"],  # type: ignore[arg-type]
            "/tmp",
            "0" * 64,
        )


def test_oracle_spec_rejects_mutable_query():
    # PR #1247: oracle query allowlists use exact immutable tuples.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="immutable string pairs"):
        OracleSpecV1("main.symbol", "symbol", [("name", "Main")], {})  # type: ignore[arg-type]


def test_oracle_expected_result_is_copied_to_canonical_bytes():
    # PR #1247: later caller mutations cannot alter a signed oracle expectation.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    supplied = {"matches": [{"line": 1, "path": "main.ts"}]}
    spec = OracleSpecV1("main.symbol", "symbol", (("name", "Main"),), supplied)
    supplied["matches"][0]["line"] = 99

    assert spec.expected_result == b'{"matches":[{"line":1,"path":"main.ts"}]}'


def test_oracle_spec_rejects_duplicate_query_key():
    # PR #1247: dict conversion must not discard an earlier frozen query value.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="parameter keys"):
        OracleSpecV1(
            "duplicate.query",
            "symbol",
            (("name", "A"), ("name", "B")),
            {"path": "main.ts"},
        )


@pytest.mark.parametrize(
    "query_key",
    ("config", "--INDEX", "source_path", "cwd", "tool-path"),
)
def test_oracle_spec_rejects_harness_owned_query_flags(query_key: str):
    # PR #1247: query expansion cannot override harness-selected execution inputs.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="harness-owned flags"):
        OracleSpecV1(
            "reserved.query",
            "symbol",
            ((query_key, "decoy"),),
            {"matches": []},
        )


def test_oracle_spec_rejects_query_flag_normalization_collision():
    # PR #1247: syntactic aliases must not produce duplicate parser options.
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="collide after normalization"):
        OracleSpecV1(
            "alias.query",
            "symbol",
            (("foo-bar", "one"), ("foo_bar", "two")),
            {"matches": []},
        )


def test_cell_plan_rejects_noncanonical_execution_cwd(tmp_path: Path):
    # PR #1247: every frozen command is bound to an authenticated working directory.
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
    # PR #1247: index output cannot overlap retained evidence or control documents.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]

    with pytest.raises(ValueError, match="Index path"):
        replace(plan, index_path=index_path)


def test_resource_plan_rejects_each_missing_ceiling():
    from dataclasses import fields

    import pytest

    from benchmarks.codegraph_compare.setup_qualification import ResourcePlanV1

    valid = {
        "wall_timeout_seconds": 30,
        "max_cpu_seconds": 20,
        "max_index_bytes": 1024,
        "max_disk_write_bytes": 4096,
        "min_free_disk_bytes": 1,
        "max_rss_bytes": 1024,
        "max_processes": 2,
        "max_open_files": 8,
        "max_concurrency": 1,
    }
    rejected = []
    for field in fields(ResourcePlanV1):
        values = dict(valid)
        values[field.name] = 0 if field.name != "max_concurrency" else 2
        with pytest.raises(ValueError, match="resource ceiling"):
            ResourcePlanV1(**values)
        rejected.append(field.name)

    assert tuple(rejected) == tuple(valid)


@pytest.mark.parametrize("value", (float("nan"), float("inf"), True))
def test_resource_plan_rejects_nonfinite_or_boolean_ceiling(value):
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import ResourcePlanV1

    values = {
        "wall_timeout_seconds": value,
        "max_cpu_seconds": 20,
        "max_index_bytes": 1024,
        "max_disk_write_bytes": 4096,
        "min_free_disk_bytes": 1,
        "max_rss_bytes": 1024,
        "max_processes": 2,
        "max_open_files": 8,
        "max_concurrency": 1,
    }
    with pytest.raises(ValueError, match="resource ceiling"):
        ResourcePlanV1(**values)


def test_resource_plan_accepts_arbitrarily_large_exact_integer_ceiling():
    # PR #1247: math.isfinite used to overflow while converting this JSON integer.
    from benchmarks.codegraph_compare.setup_qualification import ResourcePlanV1

    plan = ResourcePlanV1(10**400, 20, 1024, 4096, 1, 1024, 2, 8, 1)

    assert plan.wall_timeout_seconds == 10**400


def test_cell_plan_rejects_duplicate_oracle_ids(tmp_path: Path):
    from dataclasses import replace

    import pytest

    plan = _qualification_plans(tmp_path)[0]
    duplicate = replace(plan.oracle_specs[1], oracle_id=plan.oracle_specs[0].oracle_id)
    with pytest.raises(ValueError, match="unique symbol and call oracle IDs"):
        replace(plan, oracle_specs=(plan.oracle_specs[0], duplicate))


def test_plan_set_rejects_cross_arm_oracle_spec_difference(tmp_path: Path):
    # PR #1247: both comparison arms must use the exact same oracle contract.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    changed_oracle = replace(
        plans[1].oracle_specs[0], expected_result={"path": "other.ts", "line": 1}
    )
    plans[1] = replace(
        plans[1], oracle_specs=(changed_oracle, plans[1].oracle_specs[1])
    )
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical oracle specifications"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


def test_plan_set_distinguishes_boolean_from_integer_oracle_result(
    tmp_path: Path,
):
    # PR #1247: Python equality aliases JSON true and integer 1.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    first = replace(plans[0].oracle_specs[0], expected_result={"line": True})
    second = replace(plans[1].oracle_specs[0], expected_result={"line": 1})
    plans[0] = replace(plans[0], oracle_specs=(first, plans[0].oracle_specs[1]))
    plans[1] = replace(plans[1], oracle_specs=(second, plans[1].oracle_specs[1]))
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical oracle specifications"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


@pytest.mark.parametrize(
    "field",
    ("parse_error_allowlist", "explicit_excluded_allowlist"),
)
def test_plan_set_rejects_one_cross_arm_allowlist_difference(
    tmp_path: Path, field: str
):
    # PR #1247: comparison arms must index the exact same eligible source workload.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    plans[1] = replace(plans[1], **{field: ("main.ts",)})
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical source allowlists"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


def test_trusted_manifest_rejects_duplicate_id_before_mapping(tmp_path: Path):
    # PR #1247: mapping construction must not silently overwrite a repository pin.
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
    # PR #1247: every lifecycle and oracle command is bound to the same index.
    from dataclasses import replace

    plan = _qualification_plans(tmp_path)[0]
    unbound = replace(plan.executions[2], argv=("health", "without-index"))

    with pytest.raises(ValueError, match="plan-bound index path"):
        replace(plan, executions=(*plan.executions[:2], unbound, *plan.executions[3:]))


def test_cell_plan_build_argv_is_bound_to_exact_source_checkout(tmp_path: Path):
    # PR #1247: a frozen build cannot consume a checkout other than inventory source.
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


def test_oracle_comparison_distinguishes_boolean_from_number(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][3]["stdout_bytes"]
    payload = b'{"line":true,"path":"main.ts"}'
    (cell_root / blob["path"]).write_bytes(payload)
    blob["size_bytes"] = len(payload)
    blob["sha256"] = _bytes_hash(payload)
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


def test_plan_set_rejects_cross_arm_resource_plan_difference(tmp_path: Path):
    # PR #1247 review 3743050574: comparison arms share one exact resource budget.
    from dataclasses import replace

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _trusted_commits,
        _validate_plans,
    )

    plans = list(_qualification_plans(tmp_path))
    plans[1] = replace(
        plans[1],
        resources=replace(
            plans[1].resources,
            wall_timeout_seconds=plans[1].resources.wall_timeout_seconds + 1,
        ),
    )
    trusted = _trusted_commits(Path("benchmarks/codegraph_compare/repos.yaml"))

    with pytest.raises(ValueError, match="exactly identical resource plans"):
        _validate_plans(plans, trusted, _qualification_inventories(plans))


def test_producer_plan_rejects_noncanonical_environment_digest_before_execution():
    # PR #1249 review 3744776130: stale execution digests fail producer preflight.
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
    # PR #1249 review 3744887352: all inventories share the receipt validator.
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
    # PR #1249 review 3744944744: preflight must match published relativePath.
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["eligible_paths"] = [invalid]

    with pytest.raises(ValueError, match="canonical relative path"):
        validate_receipt_inventory({"eligibility": eligibility})


def test_receipt_inventory_accepts_consistent_sha256_git_object_ids():
    # PR #1249 review 3744944747: SHA-256 Git repositories use 64-char OIDs.
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
    # PR #1249 review 3744944747: every OID must match the root-tree algorithm.
    from benchmarks.codegraph_compare.receipt_inventory import (
        validate_receipt_inventory,
    )

    eligibility = dict(_qualification_v3_body()["source"]["eligibility"])
    eligibility["root_tree_id"] = "b" * 64

    with pytest.raises(ValueError, match="match root tree format"):
        validate_receipt_inventory({"eligibility": eligibility})


_mark_posix_qualification_section_tests()
