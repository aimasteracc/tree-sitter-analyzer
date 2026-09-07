"""Issue #1376：test_benchmark_harness_plan_oracles 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

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
    _qualification_inventories,
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


def test_oracle_spec_rejects_mutable_query():
    # PR #1247: oracle 查询白名单使用精确的不可变元组。
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="immutable string pairs"):
        OracleSpecV1("main.symbol", "symbol", [("name", "Main")], {})  # type: ignore[arg-type]


def test_oracle_expected_result_is_copied_to_canonical_bytes():
    # PR #1247: 调用方后续修改不能改变已签名的 oracle 预期值。
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    supplied = {"matches": [{"line": 1, "path": "main.ts"}]}
    spec = OracleSpecV1("main.symbol", "symbol", (("name", "Main"),), supplied)
    supplied["matches"][0]["line"] = 99

    assert spec.expected_result == b'{"matches":[{"line":1,"path":"main.ts"}]}'


def test_oracle_spec_rejects_duplicate_query_key():
    # PR #1247: 转换为 dict 不能丢弃更早的冻结查询值。
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
    # PR #1247: 查询展开不能覆盖 harness 选择的执行输入。
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="harness-owned flags"):
        OracleSpecV1(
            "reserved.query",
            "symbol",
            ((query_key, "decoy"),),
            {"matches": []},
        )


def test_oracle_spec_rejects_query_flag_normalization_collision():
    # PR #1247: 语法别名不能生成重复的解析器选项。
    from benchmarks.codegraph_compare.setup_qualification import OracleSpecV1

    with pytest.raises(ValueError, match="collide after normalization"):
        OracleSpecV1(
            "alias.query",
            "symbol",
            (("foo-bar", "one"), ("foo_bar", "two")),
            {"matches": []},
        )


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
    # PR #1247: math.isfinite 曾在转换这个 JSON 整数时溢出。
    from benchmarks.codegraph_compare.setup_qualification import ResourcePlanV1

    plan = ResourcePlanV1(10**400, 20, 1024, 4096, 1, 1024, 2, 8, 1)

    assert plan.wall_timeout_seconds == 10**400


def test_plan_set_rejects_cross_arm_oracle_spec_difference(tmp_path: Path):
    # PR #1247: 两个比较组必须使用完全相同的 oracle 契约。
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
    # PR #1247: Python 相等比较会把 JSON true 与整数 1 视为相等。
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
    # PR #1247: 各比较组必须索引完全相同的合格源文件集合。
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
    # PR #1247 review 3743050574: 各比较组共享同一份精确资源预算。
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


_mark_posix_qualification_section_tests()
