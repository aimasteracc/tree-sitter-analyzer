"""Issue #1376：test_benchmark_harness_receipt_retention 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
import sys
from functools import partial
from pathlib import Path

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


def test_validator_rejects_missing_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: 调用方提供的映射不能替代留存证据。
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "cell-receipt.json").unlink()

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_stale_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: 留存哈希与提供的哈希必须完全一致。
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    stale = copy.deepcopy(receipt)
    stale["resource_observation"]["wall_seconds"] = 2
    _resign_qualification_receipt(stale)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(stale, sort_keys=True), encoding="utf-8"
    )

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_type_different_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: JSON true 不能被视为整数 1。
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    type_different = copy.deepcopy(receipt)
    type_different["resource_observation"]["wall_seconds"] = True
    _resign_qualification_receipt(type_different)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(type_different, sort_keys=True), encoding="utf-8"
    )

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_empty_retained_receipt_object(tmp_path: Path):
    # PR #1247 review 3743050577: 留存的空 JSON 对象不是证据。
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "cell-receipt.json").write_bytes(b"{}")

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


_mark_posix_qualification_section_tests()
