"""#1676：``edit action=impact`` 的验证命令只完整出现一次；queue_ledger 缺席要说明原因。

dogfood 第 8 轮（8 个文件的 diff）：默认响应 31.9 KB，其中约 8 KB 是同一条验证命令
出现在 ``verification_command`` / ``local_verification_command`` /
``agent_summary.verification_command`` 等字段里的逐字副本；``queue_ledger`` 在默认与
``include_details`` 两种响应中都缺席，却没有任何字段说明原因。

夹具 ``dogfood_impact_result`` 复现该形状（长命令、低影响档位的 4 个验证步骤、
无 scope_paths），经由真实的 ``ChangeImpactTool.execute``。
"""

from __future__ import annotations

import json

from tests.unit._impact_summary_support import dogfood_impact_result, run_impact_tool
from tree_sitter_analyzer.mcp.tools.utils.change_impact_detail_view import (
    IMPACT_SUMMARY_BUDGET_BYTES,
)

#: 默认与 include_details 两种响应中必须逐字相同的决策字段（#1617 + #1676）。
_DECISION_KEYS = (
    "verdict",
    "risk_level",
    "verification_command",
    "ci_verification_command",
    "verification_steps",
    "verification_hint",
    "risk_factors",
    "constraint_violations",
    "queue_ledger",
    "queue_ledger_absent_reason",
    "scope_paths_invalid",
    "agent_summary",
    "summary_line",
    "changed_count",
    "affected_count",
    "tests_to_run_count",
    "tests_to_run_truncated",
)


def _run(tmp_path, monkeypatch, **arguments) -> dict:
    return run_impact_tool(
        tmp_path,
        monkeypatch,
        factory=dogfood_impact_result,
        scope_paths=(),
        **arguments,
    )


def test_verification_command_appears_once_at_full_length(
    tmp_path, monkeypatch
) -> None:
    response = _run(tmp_path, monkeypatch)
    command = response["verification_command"]
    text = json.dumps(response, ensure_ascii=False)

    # 与 dogfood 同量级的长命令（PowerShell 形式的 40 个测试目标）。
    assert len(command) == 1684
    assert text.count(command) == 1
    # 其他字段按名字引用它。
    assert response["command_aliases"] == {
        "pytest_command": "verification_command",
        "test_command": "verification_command",
        "local_verification_command": "verification_command",
    }
    summary = response["agent_summary"]
    assert summary["verification_command"] == (
        f"`verification_command` ({len(command)} chars)"
    )
    assert summary["next_step"].startswith(
        "Run low-impact local verification: `local_verification_command` "
        f"({len(command)} chars); keep `ci_verification_command` "
    )
    # CI 命令是另一条命令（多出 ruff 与全量步骤），同样只完整出现一次。
    assert text.count(response["ci_verification_command"]) == 1


def test_decision_fields_are_identical_with_and_without_details(
    tmp_path, monkeypatch
) -> None:
    summary = _run(tmp_path, monkeypatch)
    details = _run(tmp_path, monkeypatch, include_details=True)

    assert {key: summary.get(key) for key in _DECISION_KEYS} == {
        key: details.get(key) for key in _DECISION_KEYS
    }
    # include_details 仍返回每个命令字段的完整原值。
    assert details["local_verification_command"] == details["verification_command"]
    assert details["pytest_command"] == details["verification_command"]


def test_queue_ledger_absence_is_explained(tmp_path, monkeypatch) -> None:
    for arguments in ({}, {"include_details": True}):
        response = _run(tmp_path, monkeypatch, **arguments)
        assert "queue_ledger" not in response
        assert response["queue_ledger_absent_reason"] == "NO_SCOPE_PATHS"


def test_scoped_impact_carries_the_ledger_without_an_absence_reason(
    tmp_path, monkeypatch
) -> None:
    response = run_impact_tool(
        tmp_path, monkeypatch, factory=dogfood_impact_result, scope_paths=("src",)
    )

    ledger = response["queue_ledger"]
    assert (ledger["scope_paths"], ledger["scoped_changed_count"]) == (["src"], 8)
    assert "queue_ledger_absent_reason" not in response
    # handoff 同样按名字引用命令。
    command = response["verification_command"]
    assert ledger["handoff"].endswith(
        f"verification=`verification_command` ({len(command)} chars)"
    )


def test_realistic_diff_default_reply_size_is_pinned(tmp_path, monkeypatch) -> None:
    """#1676 字节不变量：dogfood 形状的默认响应。

    实测 2026-10-18：修复前默认 16515 B（1684 字符的命令有 3 份逐字副本），
    修复后 13250 B（1 份；-19.8%）。
    """
    summary = _run(tmp_path, monkeypatch)
    details = _run(tmp_path, monkeypatch, include_details=True)
    summary_bytes = len(json.dumps(summary, ensure_ascii=False))
    details_bytes = len(json.dumps(details, ensure_ascii=False))

    assert summary_bytes <= IMPACT_SUMMARY_BUDGET_BYTES
    assert summary_bytes < details_bytes
    assert summary_bytes == 13250


def test_summary_reference_rules_without_mutation() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_command_refs import (
        reference_summary_command,
    )

    long_command = "uv run pytest " + "x" * 300
    response = {
        "verification_command": long_command,
        "agent_summary": {"verification_command": long_command, "risk": "low"},
    }

    referenced = reference_summary_command(response)

    assert referenced["agent_summary"] == {
        "verification_command": f"`verification_command` ({len(long_command)} chars)",
        "risk": "low",
    }
    assert response["agent_summary"]["verification_command"] == long_command
    # 短命令照旧内联；摘要与顶层不同、或没有摘要时原样返回。
    short = {
        "verification_command": "uv run pytest -q",
        "agent_summary": {"verification_command": "uv run pytest -q"},
    }
    assert reference_summary_command(short) == short
    differs = {
        "verification_command": long_command,
        "agent_summary": {"verification_command": "git diff --check"},
    }
    assert reference_summary_command(differs) is differs
    bare = {"verification_command": long_command}
    assert reference_summary_command(bare) is bare


def test_compact_view_passes_the_absence_reason_through() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
        attach_queue_ledger,
        build_agent_summary_only_response,
    )

    result = attach_queue_ledger(
        dogfood_impact_result(),
        mode="diff",
        scope_paths=[],
        scoped_changed_files=[],
        workspace_changed_files=[],
    )
    compact = build_agent_summary_only_response(result)

    assert compact["queue_ledger"] == {}
    assert compact["queue_ledger_absent_reason"] == "NO_SCOPE_PATHS"
