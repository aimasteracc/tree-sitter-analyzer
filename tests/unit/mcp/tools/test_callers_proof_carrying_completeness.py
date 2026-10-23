"""RFC-0040：``complete`` 必须由证据构成——跳过的检查不能产出 ``complete``。

#1740 / #1758 / #1759 / #1772 / #1644 同属一类：``complete`` 曾由“没有失败标志”推出，
任何跳过某道门的代码路径都得到计数 0，于是成了 ``complete``。这里证明：

* 每道必需检查漏记、未能运行或在别的范围上运行时，答案都不是 ``complete``，
  且原因码点名该检查（登记表逐项参数化——新增检查自动被覆盖）；
* 登记表新增一道检查而代码尚未接线时，失败即关闭；
* 真实查询中把某道门换成“没有运行”（monkeypatch）时，答案不再是 ``complete``；
* 裸名与限定名对唯一方法给出同一份证明；
* 无索引（全量重建中）的答复同样声明 completeness（#1644）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools import callers_absence, callers_checks, callers_tool
from tree_sitter_analyzer.mcp.tools.callers_checks import (
    REQUIRED_CHECKS,
    CheckSpec,
    Ledger,
    prove,
    prove_edges,
)
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, NotChecked
from tree_sitter_analyzer.mcp.tools.callers_reasons import COMPLETENESS_REASONS
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_SCOPE = ("Service.compute", "pkg/svc.py")


def _all_pass(scope: tuple[str, str | None] = _SCOPE) -> Ledger:
    return Ledger(scope).record_all(
        (spec.name, Checked(scope)) for spec in REQUIRED_CHECKS
    )


def _without(ledger: Ledger, name: str) -> Ledger:
    outcomes = {key: value for key, value in ledger.outcomes.items() if key != name}
    return Ledger(ledger.scope).record_all(outcomes.items())


# ------------------------------------------------------------------ the registry
def test_every_required_check_passing_is_the_only_way_to_complete() -> None:
    proof = prove(_all_pass(), 2)

    assert (proof.completeness, proof.reasons) == ("complete", ())
    assert proof.checks == {
        "required": len(REQUIRED_CHECKS),
        "checked": len(REQUIRED_CHECKS),
    }


def test_an_empty_ledger_is_unknown_never_complete() -> None:
    proof = prove(Ledger(_SCOPE), 0)

    assert proof.completeness == "unknown"
    assert proof.reasons[0] == "UNRESOLVED_INBOUND_UNCHECKED"


@pytest.mark.parametrize("spec", REQUIRED_CHECKS, ids=lambda spec: spec.name)
@pytest.mark.parametrize("callers", [0, 3])
def test_a_check_that_did_not_run_cannot_produce_complete(
    spec: CheckSpec, callers: int
) -> None:
    proof = prove(_without(_all_pass(), spec.name), callers)

    assert proof.completeness == (
        "incomplete" if callers and spec.layer == "review" else "unknown"
    )
    assert proof.reasons == (spec.unchecked_reason,)
    assert proof.checks["not_checked"] == {spec.name: spec.unchecked_reason}


@pytest.mark.parametrize("spec", REQUIRED_CHECKS, ids=lambda spec: spec.name)
def test_a_check_that_could_not_run_names_itself(spec: CheckSpec) -> None:
    ledger = _all_pass().record(spec.name, NotChecked(spec.unchecked_reason))

    proof = prove(ledger, 0)

    assert proof.completeness == "unknown"
    assert proof.reasons == (spec.unchecked_reason,)


@pytest.mark.parametrize("spec", REQUIRED_CHECKS, ids=lambda spec: spec.name)
def test_a_check_run_over_another_target_set_does_not_count(spec: CheckSpec) -> None:
    # #1759：限定名曾按错误的名字查范围——同名而范围不同的检查不是这个目标的证据。
    ledger = _all_pass().record(spec.name, Checked(("compute", "pkg/svc.py")))

    proof = prove(ledger, 0)

    assert proof.completeness == "unknown"
    assert proof.reasons == (spec.unchecked_reason,)


def test_every_unchecked_reason_is_in_the_closed_reason_set() -> None:
    assert {spec.unchecked_reason for spec in REQUIRED_CHECKS} <= COMPLETENESS_REASONS
    assert len({spec.name for spec in REQUIRED_CHECKS}) == len(REQUIRED_CHECKS)


def test_a_newly_registered_check_fails_closed_until_it_is_wired(monkeypatch) -> None:
    new = CheckSpec("future_gate", "review", "NON_CALL_REFERENCES_UNCHECKED")
    monkeypatch.setattr(callers_checks, "REQUIRED_CHECKS", (*REQUIRED_CHECKS, new))
    monkeypatch.setattr(
        callers_checks,
        "CHECK_NAMES",
        frozenset({*callers_checks.CHECK_NAMES, new.name}),
    )

    proof = prove(_all_pass(), 0)

    assert (proof.completeness, proof.reasons) == (
        "unknown",
        ("NON_CALL_REFERENCES_UNCHECKED",),
    )
    assert proof.checks["not_checked"] == {
        "future_gate": "NON_CALL_REFERENCES_UNCHECKED"
    }


def test_an_unregistered_check_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown callers check 'nmae_only'"):
        Ledger(_SCOPE).record("nmae_only", Checked(_SCOPE))


def test_edge_problems_keep_their_contract_order_and_severity() -> None:
    ledger = _all_pass().record_all(
        (
            ("name_only", Checked(_SCOPE, ("NAME_ONLY_INBOUND",))),
            ("unattributed", Checked(_SCOPE, ("UNATTRIBUTED_CALL_SITES",))),
        )
    )

    assert prove_edges(ledger, 2).reasons == (
        "NAME_ONLY_INBOUND",
        "UNATTRIBUTED_CALL_SITES",
    )
    assert (prove(ledger, 2).completeness, prove(ledger, 0).completeness) == (
        "incomplete",
        "unknown",
    )
    # 调用边层已判定时，复核门不运行：摘要只给出个数。
    assert prove(ledger, 2).checks == {"required": 12, "checked": 5, "not_run": 7}


# ------------------------------------------------------------ closed skip paths
def test_no_project_root_runs_no_source_check_and_is_not_complete() -> None:
    scoped = {"freshness": "unknown", "reason": "SOURCE_REVALIDATION_SCOPED"}

    verdict = callers_absence.assess_completeness(
        object(), None, "f", None, "complete", 0, scoped
    )

    assert (verdict.completeness, verdict.reason) == (
        "unknown",
        "SYMBOL_DEFINITION_UNCHECKED",
    )
    assert [name for name, _outcome in verdict.checks] == ["freshness"]


def test_unreadable_declaration_cannot_rule_out_an_accessor(tmp_path) -> None:
    (tmp_path / "p.py").write_text("def x():\n    return 1\n", encoding="utf-8")

    assert (
        callers_absence._is_accessor(
            str(tmp_path), [("p.py", 1, "python"), ("gone.py", 1, "python")], "x"
        )
        is None
    )
    assert (
        callers_absence._is_accessor(str(tmp_path), [("p.py", 1, "python")], "x")
        is False
    )


# --------------------------------------------------------------- real queries
_SVC = (
    "class Service:\n"
    "    def compute(self, x):\n"
    "        return x + 1\n"
    "\n"
    "\n"
    "def helper():\n"
    "    return Service().compute(1)\n"
)
_USE = (
    "from .svc import Service, helper\n"
    "\n"
    "\n"
    "def run():\n"
    "    return Service().compute(2) + helper()\n"
)


async def _index(root: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    files = {"pkg/__init__.py": "", "pkg/svc.py": _SVC, "pkg/use.py": _USE}
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _ask(root: str, name: str, file_path: str = "pkg/svc.py") -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


def _proof_shape(result: dict) -> tuple:
    return (
        result["completeness"],
        tuple(result["completeness_reasons"]),
        result["completeness_checks"],
        tuple(sorted((c["file"], c["name"]) for c in result["callers"])),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Service.compute", "compute", "helper"])
async def test_a_census_carries_its_proof(tmp_path, name: str) -> None:
    indexed = await _index(tmp_path)
    result = await _ask(indexed, name)

    assert result["completeness"] == "complete"
    assert result["completeness_reasons"] == []
    assert result["completeness_checks"] == {"required": 12, "checked": 12}


@pytest.mark.asyncio
async def test_bare_and_qualified_carry_the_same_proof(tmp_path) -> None:
    indexed = await _index(tmp_path)
    # #1759：两种问法在任何检查运行前归一为同一目标集。
    assert _proof_shape(await _ask(indexed, "compute")) == _proof_shape(
        await _ask(indexed, "Service.compute")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Service.compute", "compute"])
async def test_a_review_gate_that_forgets_to_record_cannot_complete(
    tmp_path, name: str, monkeypatch
) -> None:
    indexed = await _index(tmp_path)
    # 模拟一道“忘了”记录检查结果、却声称 complete 的复核门。
    monkeypatch.setattr(
        callers_absence,
        "_assess_absence",
        lambda *_args, **_kwargs: callers_absence.AbsenceVerdict("complete"),
    )

    result = await _ask(indexed, name)

    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["SYMBOL_DEFINITION_UNCHECKED"]
    assert result["completeness_checks"]["not_checked"] == {
        "target_defined": "SYMBOL_DEFINITION_UNCHECKED"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Service.compute", "compute"])
async def test_an_edge_check_left_out_of_the_ledger_cannot_complete(
    tmp_path, name: str, monkeypatch
) -> None:
    indexed = await _index(tmp_path)
    built = callers_tool._edge_ledger

    def forgetful(scope, **kwargs):
        return _without(built(scope, **kwargs), "declaring_file")

    monkeypatch.setattr(callers_tool, "_edge_ledger", forgetful)

    result = await _ask(indexed, name)

    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == ["UNRESOLVED_INBOUND_UNCHECKED"]


@pytest.mark.asyncio
async def test_uncounted_module_level_sites_on_the_qualified_path_are_unchecked(
    tmp_path, monkeypatch
) -> None:
    indexed = await _index(tmp_path)
    # 限定名走调用图路径，此前把模块级调用点固定为 0，从未计数。
    monkeypatch.setattr(callers_tool, "unattributed_sites", lambda *_args: None)

    result = await _ask(indexed, "Service.compute")

    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == ["UNATTRIBUTED_CALL_SITES_UNCHECKED"]


@pytest.mark.asyncio
async def test_unreadable_sibling_methods_leave_the_bare_union_unchecked(
    tmp_path, monkeypatch
) -> None:
    indexed = await _index(tmp_path)

    def unreadable(*_args):
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(callers_tool, "_same_name_definitions", unreadable)

    result = await _ask(indexed, "compute")

    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == ["NAME_ONLY_INBOUND_UNCHECKED"]
    assert "`name_only` (NAME_ONLY_INBOUND_UNCHECKED)" in result["next_step"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Service.compute", "helper"])
async def test_an_unreadable_accessor_check_is_not_complete(
    tmp_path, name: str, monkeypatch
) -> None:
    indexed = await _index(tmp_path)
    monkeypatch.setattr(callers_absence, "_is_accessor", lambda *_args: None)

    result = await _ask(indexed, name)

    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["ACCESSOR_UNCHECKED"]


@pytest.mark.asyncio
async def test_unreadable_reference_stamps_are_not_no_stale_files(
    tmp_path, monkeypatch
) -> None:
    indexed = await _index(tmp_path)
    # 引用命中、但索引戳记读不到：比对没有运行，不是“没有不一致的文件”。
    monkeypatch.setattr(
        callers_absence, "stale_reference_files", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        callers_absence,
        "_reference_scan",
        lambda *_args, **_kwargs: ([{"file": "pkg/use.py", "line": 1}], {}),
    )

    result = await _ask(indexed, "helper")

    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["SOURCE_SCOPE_UNKNOWN"]


@pytest.mark.asyncio
async def test_an_index_rebuild_reply_declares_completeness(
    tmp_path, monkeypatch
) -> None:
    # #1644：没有可用索引的答复同样声明 unknown 与原因码。
    monkeypatch.setattr(callers_tool, "is_index_rebuilding", lambda *_args: True)

    result = await _ask(str(tmp_path), "anything")

    assert result["index_rebuilding"] is True
    assert (
        result["completeness"],
        result["completeness_reason"],
        result["completeness_reasons"],
    ) == ("unknown", "MISSING_INDEX", ["MISSING_INDEX"])
