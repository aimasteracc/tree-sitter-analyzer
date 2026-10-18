"""#1617 edit action=impact 摘要测试的确定性夹具（非测试模块）。

供 test_output_cost_invariants（字节不变量）与
test_change_impact_tool_execute_and_mapping（决策字段与 include_details 行为）共用。
"""

from __future__ import annotations

import asyncio
import shlex

IMPACT_CHANGED = [f"src/pkg/mod_{i}.py" for i in range(10)]


def _impact_caller(i: int, j: int, *, name_only: bool) -> dict:
    """一个确定性的跨文件调用方；name_only 调用方带 #1559 的 match 标记。"""
    caller = {
        "file": f"src/app/user_{j}.py",
        "name": f"use_{i}_{j}",
        "line": 10 + j,
        "end_line": 20 + j,
        "language": "python",
    }
    return {**caller, "match": "name_only"} if name_only else caller


def _impact_call_graph() -> dict:
    """10 个文件 × 3 个函数；fan_in 各不相同，每个函数 12 个调用方（3 个仅同名）。"""
    from tree_sitter_analyzer.mcp.tools.utils.call_graph_impact import (
        CallGraphImpactResult,
        FunctionImpact,
    )

    result = CallGraphImpactResult()
    for f, path in enumerate(IMPACT_CHANGED):
        for k in range(3):
            i = f * 3 + k
            callers = [_impact_caller(i, j, name_only=j < 3) for j in range(12)]
            callees = [
                {"file": f"src/lib/dep_{j}.py", "name": f"dep_{j}", "line": j}
                for j in range(8)
            ]
            impact = FunctionImpact(
                name=f"func_{i}",
                file=path,
                line=k * 30 + 1,
                upstream_callers=callers,
                downstream_callees=callees,
                fan_in=12 + (i * 7) % 30,
                fan_out=8,
            )
            result.functions_analyzed += 1
            result.total_upstream += 12
            result.total_downstream += 8
            result.total_possible_upstream += 3
            result.cross_file_callers.setdefault(path, []).extend(callers[:10])
            result.cross_file_callees.setdefault(path, []).extend(callees[:10])
            for c in callers:
                result.affected_functions_by_file.setdefault(c["file"], []).append(
                    f"{c['name']} -> func_{i}"
                )
            result.high_risk_functions.append(
                f"{path}:func_{i} (fan_in={impact.fan_in}, name_only=3)"
            )
            result.function_impacts.append(impact.to_dict())
    return result.to_dict()


def impact_full_result() -> dict:
    """确定性的完整 diff 响应：真实的响应组装 + 真实的 CallGraphImpactResult。"""
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
        AgentSummaryContext,
        ChangeImpactResponseContext,
        build_agent_summary,
        build_change_impact_response,
    )

    tests = [f"tests/unit/test_mod_{i}.py" for i in range(10)]
    local = "uv run pytest " + " ".join(tests) + " -n 2 -q"
    ci = "uv run pytest " + " ".join(tests) + " -q"
    verification = {
        "test_required": True,
        "test_runner": "pytest",
        "default_test_command": "uv run pytest -q",
        "pytest_required": True,
        "verification_command": ci,
        "verification_reason": "changed Python source",
    }
    strategy = {
        "focused_test_command": ci,
        "low_impact_focused_test_command": local,
        "local_verification_command": local,
        "ci_verification_command": ci,
        "resource_profile": "local_low_impact",
        "verification_strategy": "local_low_impact_focused_then_ci",
        "verification_steps": [local],
        "verification_hint": "run the focused tests",
    }
    affected = {f"src/app/user_{j}.py" for j in range(12)}
    summary = build_agent_summary(
        AgentSummaryContext(
            risk="high",
            changed_files=IMPACT_CHANGED,
            scope_paths=["src"],
            verification=verification,
            strategy=strategy,
            affected_count=len(affected),
            tests_to_run_count=len(tests),
        )
    )
    symbols = [
        {"name": f"sym_{s}", "kind": "function", "line": s + 1} for s in range(50)
    ]
    file_impacts = [
        {
            "file": path,
            "direct_dependents": sorted(affected),
            "total_affected": len(affected),
            "symbols": symbols[:10],
            "symbol_count": 60,
        }
        for path in IMPACT_CHANGED
    ]
    request = SimpleNamespace(
        mode="diff", scope_paths=["src"], changed_files=IMPACT_CHANGED, diff_stat=""
    )
    result = build_change_impact_response(
        ChangeImpactResponseContext(
            request=request,
            risk="high",
            affected=affected,
            file_impacts=file_impacts,
            visible_tests=tests,
            all_tests=tests,
            verification=verification,
            strategy=strategy,
            test_mapping=dict.fromkeys(IMPACT_CHANGED, tests[:1]),
            agent_summary=summary,
        )
    )
    result["call_graph_impact"] = _impact_call_graph()
    result["changed_symbols"] = [
        {"file": path, "symbol_count": 60, "symbols": symbols}
        for path in IMPACT_CHANGED
    ]
    result["changed_symbol_count"] = 600
    result["affected_symbols"] = [
        {
            "file": f"src/app/user_{n % 12}.py",
            "name": f"s_{n}",
            "kind": "function",
            "line": n,
        }
        for n in range(200)
    ]
    result["affected_symbol_count"] = 200
    result["risk_factors"] = [
        {
            "factor": "hot_zone",
            "reason": "hot zone: src/pkg/mod_0.py",
            "severity": "warn",
        }
    ]
    result["constraint_violations"] = []
    result["activation_diagnostic"] = {"available": True, "reason": None}
    result["agent_summary"]["activation_diagnostic"] = result["activation_diagnostic"]
    return result


#: #1676：dogfood 第 8 轮形状——8 个改动文件、40 个测试目标、低影响档位的
#: 4 步验证。命令按 PowerShell 引用形式渲染（Windows 上的真实形状），与平台无关。
DOGFOOD_CHANGED = [f"src/pkg/core_{i}.py" for i in range(8)]
DOGFOOD_TESTS = [f"tests/unit/test_area_{i:02d}_behaviour.py" for i in range(40)]


def _powershell(steps: list[str]) -> str:
    """把 POSIX 步骤渲染为 ``& { & 'a' 'b'; if (-not $?) { throw ... } }``。"""
    rendered = [
        "& "
        + " ".join(f"'{token}'" for token in shlex.split(step))
        + "; if (-not $?) { throw 'Verification failed' }"
        for step in steps
    ]
    return "& { " + "; ".join(rendered) + " }"


def dogfood_impact_result() -> dict:
    """确定性的“真实形状”diff 响应：长命令、4 个验证步骤、无 scope_paths。"""
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.utils.change_impact_command_refs import (
        command_ref,
    )
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
        AgentSummaryContext,
        ChangeImpactResponseContext,
        build_agent_summary,
        build_change_impact_response,
    )

    marker = "-m 'not network and not benchmark' "
    steps = [
        "uv run pytest " + marker + " ".join(DOGFOOD_TESTS) + " -n 2 -q",
        "uv run pytest " + marker + " ".join(DOGFOOD_TESTS) + " -q",
        "uv run ruff check " + " ".join(DOGFOOD_CHANGED),
        "uv run pytest -q",
    ]
    local = _powershell(steps[:1])
    ci = _powershell(steps[1:])
    verification = {
        "test_required": True,
        "test_runner": "pytest",
        "default_test_command": "uv run pytest -q",
        "pytest_required": True,
        "verification_command": ci,
        "verification_reason": "changed Python source",
    }
    strategy = {
        "focused_test_command": steps[1],
        "low_impact_focused_test_command": steps[0],
        "local_verification_command": local,
        "ci_verification_command": ci,
        "resource_profile": "local_low_impact",
        "verification_strategy": "local_low_impact_focused_then_ci",
        "verification_steps": steps,
        "verification_hint": (
            "Run the low-impact local verification command while iterating; keep "
            f"{command_ref('ci_verification_command', ci)} as the CI or "
            "queue-boundary verification command."
        ),
    }
    affected = {f"src/app/user_{j}.py" for j in range(6)}
    summary = build_agent_summary(
        AgentSummaryContext(
            risk="medium",
            changed_files=DOGFOOD_CHANGED,
            scope_paths=None,
            verification=verification,
            strategy=strategy,
            affected_count=len(affected),
            tests_to_run_count=len(DOGFOOD_TESTS),
        )
    )
    request = SimpleNamespace(
        mode="diff", scope_paths=None, changed_files=DOGFOOD_CHANGED, diff_stat=""
    )
    result = build_change_impact_response(
        ChangeImpactResponseContext(
            request=request,
            risk="medium",
            affected=affected,
            file_impacts=[
                {"file": path, "direct_dependents": sorted(affected)}
                for path in DOGFOOD_CHANGED
            ],
            visible_tests=DOGFOOD_TESTS[:20],
            all_tests=DOGFOOD_TESTS,
            verification=verification,
            strategy=strategy,
            test_mapping=dict.fromkeys(DOGFOOD_CHANGED, DOGFOOD_TESTS[:3]),
            agent_summary=summary,
        )
    )
    result["risk_factors"] = []
    result["constraint_violations"] = []
    return result


def run_impact_tool(
    tmp_path, monkeypatch, *, factory=None, scope_paths=("src",), **arguments
) -> dict:
    """经由真实的 ChangeImpactTool.execute（diff 模式）返回响应，只替换分析计算。"""
    from tree_sitter_analyzer.mcp.tools import change_impact_tool as tool_module

    build = factory or impact_full_result
    changed = DOGFOOD_CHANGED if build is dogfood_impact_result else IMPACT_CHANGED
    (tmp_path / "src").mkdir(exist_ok=True)
    monkeypatch.setattr(
        tool_module, "_get_changed_files", lambda *_a, **_k: list(changed)
    )
    monkeypatch.setattr(tool_module, "_get_diff_stat", lambda *_a, **_k: "")
    monkeypatch.setattr(
        tool_module, "_build_change_impact_result", lambda _req: build()
    )
    tool = tool_module.ChangeImpactTool(project_root=str(tmp_path))
    return asyncio.run(
        tool.execute({"mode": "diff", "scope_paths": list(scope_paths), **arguments})
    )
