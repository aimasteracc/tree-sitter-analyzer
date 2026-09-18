"""task-outcome/v1 路由输出与调用日志的精确字节护栏。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable

import pytest

from tests.unit.task.test_task_router import (
    INDEX_OK,
    NAV_OK,
    FakeExecutor,
    _clock,
)
from tree_sitter_analyzer.task import (
    AssessChangeRequest,
    Budget,
    DiffInput,
    PlanChangeRequest,
    TaskOutcome,
    UnderstandRequest,
)
from tree_sitter_analyzer.task import router as router_module
from tree_sitter_analyzer.task.router import assess_change, plan_change, understand
from tree_sitter_analyzer.task.serializers import serialize_json

EXPECTED_SCENARIO_SHA256 = {
    "assess_diff_success": "11eb1966114839879937577642aa6a9a0a359a382266dbbd7d9a1f1eb17ce710",  # pragma: allowlist secret -- 固定公开测试摘要
    "budget_truncation": "dfd949d50bac5833532e8ba6549cbf7f5ba45aaf3146dac6d9ed78714aad8feb",  # pragma: allowlist secret -- 固定公开测试摘要
    "cleanup_failure": "9bc29242679b52877ed766ea104589c429701761094cbf8cdbc48efa6e391fd3",  # pragma: allowlist secret -- 固定公开测试摘要
    "internal_error": "7faa657f77a4040a900e8f28044a326ce7fa49513d618238619ab0f65b7a0c1e",  # pragma: allowlist secret -- 固定公开测试摘要
    "missing_oracle": "86db686b68a3a23b06071e7c94ba1cd979ba3dae39a36ededce6a6509b204d87",  # pragma: allowlist secret -- 固定公开测试摘要
    "plan_task_success": "47b3c4e8ea049dc2f10c159d15145e2b078994fa5b38ce7b1296689ed7e98f7a",  # pragma: allowlist secret -- 固定公开测试摘要
    "snapshot_mismatch": "0e7ec4893c0f0651be2699672eccd4b8a2135600125af4c69e39d8dab9afcabe",  # pragma: allowlist secret -- 固定公开测试摘要
    "understand_success": "971021e23a83fe01249c433ff81b785c898fdc7132aac430eb0810d675d7a8ab",  # pragma: allowlist secret -- 固定公开测试摘要
}


class CleanupFailureExecutor(FakeExecutor):
    """仅让差分快照释放失败的确定性执行器。"""

    async def call(self, facade, action, arguments):
        if action == "release_snapshot":
            self.calls.append((facade, action, dict(arguments)))
            raise RuntimeError("redacted")
        return await super().call(facade, action, arguments)


def _run(coro: Awaitable[TaskOutcome]) -> TaskOutcome:
    return asyncio.run(coro)


def _wire_digest(outcome: TaskOutcome, executor: FakeExecutor) -> str:
    payload = json.dumps(
        {"wire": serialize_json(outcome), "calls": executor.calls},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _run_scenario(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[TaskOutcome, FakeExecutor]:
    if name == "understand_success":
        executor = FakeExecutor()
        outcome = _run(
            understand(UnderstandRequest(task="x"), executor, _clock(executor))
        )
    elif name == "plan_task_success":
        executor = FakeExecutor()
        outcome = _run(
            plan_change(PlanChangeRequest(task="x"), executor, _clock(executor))
        )
    elif name == "assess_diff_success":
        executor = FakeExecutor()
        outcome = _run(
            assess_change(
                AssessChangeRequest(diff=DiffInput("workspace")),
                executor,
                _clock(executor),
            )
        )
    elif name == "budget_truncation":
        executor = FakeExecutor()
        request = UnderstandRequest(task="x", budget=Budget(max_primitive_calls=1))
        outcome = _run(understand(request, executor, _clock(executor)))
    elif name == "cleanup_failure":
        executor = CleanupFailureExecutor()
        outcome = _run(
            assess_change(
                AssessChangeRequest(diff=DiffInput("workspace")),
                executor,
                _clock(executor),
            )
        )
    elif name == "snapshot_mismatch":
        nav_mismatch = dict(NAV_OK)
        nav_mismatch["snapshot_id"] = "idx_other"
        executor = FakeExecutor(responses={("nav", "context"): nav_mismatch})
        outcome = _run(
            plan_change(PlanChangeRequest(task="x"), executor, _clock(executor))
        )
    elif name == "internal_error":
        executor = FakeExecutor()

        def boom(_fragments):
            raise RuntimeError("redacted")

        with monkeypatch.context() as context:
            context.setattr(router_module, "project_plan_steps", boom)
            outcome = _run(
                plan_change(PlanChangeRequest(task="x"), executor, _clock(executor))
            )
    elif name == "missing_oracle":
        missing = dict(INDEX_OK)
        missing.update(
            {
                "snapshot_id": None,
                "source_generation": None,
                "completeness": "unknown",
                "access_state": "missing",
                "access_reason": "MISSING_INDEX",
            }
        )
        executor = FakeExecutor(responses={("index", "status"): missing})
        outcome = _run(
            understand(UnderstandRequest(task="x"), executor, _clock(executor))
        )
    else:  # pragma: no cover - 参数集合由本文件固定
        raise AssertionError(f"unknown scenario: {name}")
    return outcome, executor


@pytest.mark.parametrize(
    ("scenario", "expected_sha256"),
    sorted(EXPECTED_SCENARIO_SHA256.items()),
)
def test_router_wire_bytes_and_calls_are_stable(
    scenario: str,
    expected_sha256: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome, executor = _run_scenario(scenario, monkeypatch)

    assert _wire_digest(outcome, executor) == expected_sha256
