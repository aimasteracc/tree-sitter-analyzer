"""Issue #1376：test_benchmark_harness_receipt_json 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
import os as os
import sys
from functools import partial
from pathlib import Path
from unittest.mock import patch

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


def test_direct_receipt_rejects_excessive_nesting_without_recursion_error(
    tmp_path: Path,
):
    # PR #1247: 直接传入的对象必须在递归规范哈希之前受到界限约束。

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    nested: object = "leaf"
    for _ in range(130):
        nested = [nested]
    receipt["eligibility"]["eligible_paths"] = nested

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RECEIPT_SCHEMA_MISMATCH",)


def test_direct_receipt_rejects_excessive_node_count_before_hash(tmp_path: Path):
    # PR #1247: 直接对象的节点上限独立于解析器上限，由可信配置决定。
    import benchmarks.codegraph_compare.setup_qualification_schema as schema

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["eligibility"]["eligible_paths"] = ["main.ts", "extra.ts"]

    with patch.object(schema, "_MAX_STRICT_JSON_NODES", 10):
        failures = _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )

    assert failures == ("RECEIPT_SCHEMA_MISMATCH",)


def test_direct_json_bounds_rejects_string_above_utf8_ceiling():
    # PR #1247: 直接 receipt 与字节输入使用相同的标量分配界限。
    from benchmarks.codegraph_compare.setup_qualification_schema import (
        validate_direct_json_bounds,
    )

    with pytest.raises(ValueError, match="UTF-8 byte ceiling"):
        validate_direct_json_bounds("x" * (1024 * 1024 + 1))


def test_direct_json_bounds_rejects_integer_above_bit_ceiling():
    # PR #1247: 哈希处理绝不能格式化攻击者控制大小的直接整数。
    from benchmarks.codegraph_compare.setup_qualification_schema import (
        validate_direct_json_bounds,
    )

    with pytest.raises(ValueError, match="bit ceiling"):
        validate_direct_json_bounds(1 << 16_384)


def test_direct_json_bounds_rejects_integer_above_digit_ceiling():
    # PR #1247: 十进制转换的界限必须独立于整数位数限制。
    from benchmarks.codegraph_compare.setup_qualification_schema import (
        validate_direct_json_bounds,
    )

    with pytest.raises(ValueError, match="digit ceiling"):
        validate_direct_json_bounds(10**4096)


def test_direct_json_bounds_rejects_aggregate_scalar_budget():
    # PR #1247: 多个单独合法的字符串也必须共享同一编码字节预算。
    import benchmarks.codegraph_compare.setup_qualification_schema as schema

    with patch.object(schema, "_MAX_DIRECT_ENCODED_SCALAR_BYTES", 15):
        with pytest.raises(ValueError, match="aggregate encoded scalar budget"):
            schema.validate_direct_json_bounds(["123456", "abcdef"])


def test_direct_receipt_scalar_bounds_run_before_hashing(tmp_path: Path):
    # PR #1247: 直接 receipt 的界限检查先于规范哈希和十六进制解码。
    import benchmarks.codegraph_compare.setup_qualification_validation as validation

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    receipt["receipt_hash"] = "x" * (1024 * 1024 + 1)

    with patch.object(validation, "_sha256", side_effect=AssertionError("hashed")):
        failures = validation.validate_cell_receipt(
            receipt,
            plan=plan,
            cell_root=tmp_path / "cell",
            verifier_config=_qualification_verifier_config(),
        )

    assert failures == ("RECEIPT_SCHEMA_MISMATCH",)


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_receipt_parser_recursively_rejects_nonfinite_json_constants(
    tmp_path: Path, constant: str
):
    # PR #1247: Python 的 JSON 扩展不属于严格的 receipt 语法。

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    payload = json.dumps(receipt, sort_keys=True).replace(
        '"wall_seconds": 1', f'"wall_seconds": {constant}'
    )

    with pytest.raises(ValueError, match="Non-finite JSON number"):
        _parse_receipt(payload.encode("utf-8"))


@pytest.mark.parametrize(
    ("path", "value", "raw_failure"),
    (
        (("attempt",), True, ()),
        (
            ("raw_executions", 0, "stderr_bytes", "size_bytes"),
            False,
            ("RAW_EXECUTION_EVIDENCE_MISSING",),
        ),
        (("resource_observation", "peak_processes"), 1.5, ()),
    ),
)
def test_receipt_schema_rejects_non_exact_scalar_types(
    tmp_path: Path, path, value, raw_failure
):
    # PR #1247: 布尔值不能与整数相等，计数必须保持整数类型。
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    target = receipt
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RECEIPT_SCHEMA_MISMATCH",
        *raw_failure,
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_receipt_parser_rejects_exponent_overflow(tmp_path: Path):
    # PR #1247: parse_constant 看不到转换为浮点数时溢出的有限数值 token。

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    payload = json.dumps(receipt, sort_keys=True).replace(
        '"wall_seconds": 1', '"wall_seconds": 1e400'
    )

    with pytest.raises(ValueError, match="Non-finite JSON number"):
        _parse_receipt(payload.encode("utf-8"))


@pytest.mark.parametrize(
    "path",
    (
        (),
        ("eligibility",),
        ("tool",),
        ("config",),
        ("counters",),
        ("resource_observation",),
        ("index_partition",),
        ("raw_executions", 0),
        ("raw_executions", 0, "stdout_bytes"),
        ("index_provenance",),
        ("index_provenance", "payload"),
        ("os_audit",),
        ("os_audit", "payload"),
        ("os_audit", "audit_bytes"),
        ("human_oracle_approval",),
        ("human_oracle_approval", "payload"),
        ("human_oracle_approval", "approval_bytes"),
    ),
)
def test_receipt_parser_rejects_extension_at_every_object_schema(
    tmp_path: Path, path: tuple[object, ...]
):
    # PR #1247: 未签名的扩展成员不能通过严格加载。
    import copy

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = copy.deepcopy(_write_valid_qualification_receipt(tmp_path / "cell", plan))
    target = receipt
    for component in path:
        target = target[component]
    target["extension"] = "unsigned"
    _resign_qualification_receipt(receipt)

    with pytest.raises(ValueError, match="exactly the schema-v2 keys"):
        _parse_receipt(json.dumps(receipt, sort_keys=True).encode("utf-8"))


def test_strict_receipt_json_rejects_excessive_depth_before_loading():
    # PR #1247: 生产者 JSON 深度超限应是验证失败，而非 verifier 递归错误。
    import pytest

    from benchmarks.codegraph_compare.setup_qualification import strict_json_loads

    payload = b"[" * 129 + b"0" + b"]" * 129

    with pytest.raises(ValueError, match="trusted nesting limit"):
        strict_json_loads(payload)


def test_receipt_parser_preserves_valid_canonical_hash_roundtrip(tmp_path: Path):
    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    payload = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8")

    assert _parse_receipt(payload) == json.loads(payload)


def test_receipt_parser_rejects_stale_canonical_receipt_hash(tmp_path: Path):
    # PR #1247: 严格加载必须把完整的封闭 receipt 绑定到其哈希。

    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    plan = _qualification_plans(tmp_path)[0]
    receipt = _write_valid_qualification_receipt(tmp_path / "cell", plan)
    receipt["resource_observation"]["wall_seconds"] = 2

    with pytest.raises(ValueError, match="Receipt hash does not match"):
        _parse_receipt(json.dumps(receipt, sort_keys=True).encode("utf-8"))


def test_receipt_parser_rejects_duplicate_members_at_nested_depth():
    import pytest

    from benchmarks.codegraph_compare.setup_qualification_orchestration import (
        _parse_receipt,
    )

    with pytest.raises(ValueError, match="Duplicate JSON member: exit_code"):
        _parse_receipt(b'{"run":{"exit_code":1,"exit_code":0}}')


_mark_posix_qualification_section_tests()
