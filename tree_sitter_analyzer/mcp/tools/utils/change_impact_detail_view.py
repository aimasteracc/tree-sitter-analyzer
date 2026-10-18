"""``edit action=impact`` 明细列表的默认摘要投影（#1617）。

多文件 diff 的完整 impact 响应约 70-224 KB，主要来自 ``affected_symbols``
（受影响文件的符号清单）、``changed_symbols``（改动文件的符号清单）、
``call_graph_impact``（逐函数的上下游调用方列表）以及逐字重复的验证命令。
代理默认只需要计数与影响最大的少数条目来做决策，因此在响应边界做投影：

* 默认：列表替换为按影响排序的前 N 项，并附带如实的 ``*_total`` /
  ``*_listed`` / ``*_truncated``；逐调用方明细只保留计数与同名匹配计数；
  与 ``verification_command`` 逐字相同的命令字段只保留一份，并在
  ``command_aliases`` 中说明去向。
* ``include_details=true``：原样返回完整列表与全部命令字段，与旧行为一致。

驱动决策的字段（verdict、verification_command、ci_verification_command、
risk_factors、``possible_*`` / name_only 过近似信号、high_risk_functions、
queue_ledger、constraint_violations、完整性与诊断标记）不在这里裁剪。
本模块只读入参，始终返回新字典。
"""

from __future__ import annotations

from typing import Any

#: 默认列出的影响最大的函数 / 受影响符号 / 文件条目数。
IMPACT_DETAIL_CAP = 10

#: ``_find_affected_symbols`` 的扫描上限；达到时总数只是下界。
AFFECTED_SYMBOLS_SCAN_CAP = 200

#: 同名匹配（过近似）调用方的 ``match`` 标记，见 call_graph_possible。
_NAME_ONLY_MATCH = "name_only"

DETAILS_NEXT_STEP = (
    "pass include_details=true (CLI: --change-impact-include-details) for the "
    "full call_graph_impact / affected_symbols / changed_symbols / affected_files "
    "lists and every command field"
)

#: 与规范 verification_command 逐字相同时只保留规范字段的命令字段。
#: #1676：``local_verification_command`` 也在其中——有 local 命令时规范命令就是它
#: （``_effective_verification_command``），next_step / stop_condition 中对它的字段名
#: 引用经 ``command_aliases`` 解析到 ``verification_command``。
_ALIASABLE_COMMANDS = ("pytest_command", "test_command", "local_verification_command")

#: verification_steps 第一步的 focused 子集命令；未被文案引用时默认省略。
_FOCUSED_COMMANDS = ("focused_test_command", "low_impact_focused_test_command")

#: 默认列出的影响最大的函数数（每项含 8 个计数字段，约 240 B）。
FUNCTION_IMPACTS_CAP = 5

#: 默认摘要的上下文预算（#1617）：典型多文件 diff 的默认响应必须不超过此字节数。
#: 依据（2026-10-17 实测，本仓库 ``git diff 2702997c 3362b590``，10 个文件、19 个
#: 测试目标）：修复前 73947 B，摘要后约 20.5 KB。剩余部分约 6.7 KB 是必须逐字保留、
#: 可直接复制执行的命令契约（verification_command 及其摘要镜像、local / ci 命令、
#: verification_steps），约 5 KB 是已有上限的测试计划（test_mapping / tests_to_run）。
#: 16 KB 只能靠裁剪这些决策字段达到，因此预算定为 24 KB（约 6k token）。
IMPACT_SUMMARY_BUDGET_BYTES = 24 * 1024

# 函数条目中按计数代替的调用方 / 被调用方明细列表。
_FUNCTION_DETAIL_LISTS = ("upstream_callers", "downstream_callees")

# 调用图摘要中由计数代替的逐条明细字段。
_CALL_GRAPH_DETAIL_KEYS = (
    "function_impacts",
    "cross_file_callers",
    "cross_file_callees",
    "affected_functions_by_file",
)


def project_impact_details(
    result: dict[str, Any], *, include_details: bool
) -> dict[str, Any]:
    """返回带有限明细与如实计数的新响应字典，不修改 ``result``。"""
    projected = dict(result)
    symbols = result.get("affected_symbols")
    if isinstance(symbols, list):
        # 扫描上限在两种模式下都要如实说明：达到上限时总数只是下界。
        projected["affected_symbols_scan_capped"] = (
            len(symbols) >= AFFECTED_SYMBOLS_SCAN_CAP
        )
    if include_details:
        projected["details_included"] = True
        return projected

    truncated = False
    graph = result.get("call_graph_impact")
    if isinstance(graph, dict):
        projected["call_graph_impact"], graph_truncated = _summarize_call_graph(graph)
        truncated = graph_truncated
    if isinstance(symbols, list):
        truncated = _cap_list(projected, "affected_symbols", symbols) or truncated
    files = result.get("affected_files")
    if isinstance(files, list):
        # 上游已把 affected_files 截到 50 个；总数以 affected_count 为准。
        count = result.get("affected_count")
        total = count if isinstance(count, int) else len(files)
        truncated = _cap_list(projected, "affected_files", files, total) or truncated
    if "changed_symbols" in result:
        # file_impacts 已为每个改动文件注入前 10 个符号与 symbol_count，
        # changed_symbol_count 保留总数；完整清单只在 include_details 时返回。
        projected.pop("changed_symbols")
        projected["changed_symbols_omitted"] = True
        truncated = True
    impacts = result.get("file_impacts")
    if isinstance(impacts, list):
        projected["file_impacts"], impacts_truncated = _cap_file_impacts(impacts)
        truncated = truncated or impacts_truncated
    aliases = _alias_duplicate_commands(projected)
    if aliases:
        projected["command_aliases"] = aliases
        truncated = True
    omitted = _omit_unreferenced_focused_commands(projected)
    if omitted:
        projected["command_fields_omitted"] = omitted
        truncated = True
    projected["details_included"] = False
    projected["details_truncated"] = truncated
    if truncated:
        projected["details_next_step"] = DETAILS_NEXT_STEP
    return projected


def _cap_list(
    projected: dict[str, Any], key: str, items: list[Any], total: int | None = None
) -> bool:
    """把 ``key`` 列表截到上限并写入如实计数，返回是否截断。"""
    listed = items[:IMPACT_DETAIL_CAP]
    full = len(items) if total is None else max(total, len(items))
    projected[key] = listed
    projected[f"{key}_total"] = full
    projected[f"{key}_listed"] = len(listed)
    projected[f"{key}_truncated"] = full > len(listed)
    return bool(projected[f"{key}_truncated"])


def _alias_duplicate_commands(projected: dict[str, Any]) -> dict[str, str]:
    """移除与 verification_command 逐字相同的命令字段，返回字段到规范字段的映射。"""
    canonical = projected.get("verification_command")
    if not isinstance(canonical, str) or not canonical:
        return {}
    aliases: dict[str, str] = {}
    for key in _ALIASABLE_COMMANDS:
        if projected.get(key) == canonical:
            projected.pop(key)
            aliases[key] = "verification_command"
    return aliases


def _omit_unreferenced_focused_commands(projected: dict[str, Any]) -> list[str]:
    """移除未被文案按字段名引用的 focused 子集命令，返回被移除的字段名。

    focused 命令只是 verification_steps 第一步的另一种拼写；当 next_step /
    stop_condition / verification_hint 都没有指向它时，它不驱动任何决策。
    被文案引用时（例如 default 资源档位的 "Run focused verification first"）保留。
    """
    summary = projected.get("agent_summary")
    texts = [projected.get("verification_hint")]
    if isinstance(summary, dict):
        texts += [summary.get("next_step"), summary.get("stop_condition")]
    referenced = " ".join(text for text in texts if isinstance(text, str))
    omitted = []
    for key in _FOCUSED_COMMANDS:
        value = projected.get(key)
        if isinstance(value, str) and value and f"`{key}`" not in referenced:
            projected.pop(key)
            omitted.append(key)
    return omitted


def _cap_file_impacts(
    impacts: list[Any],
) -> tuple[list[Any], bool]:
    """每个改动文件的直接依赖方只列前 N 个，并给出截断前的总数。"""
    rows: list[Any] = []
    truncated = False
    for row in impacts:
        dependents = row.get("direct_dependents") if isinstance(row, dict) else None
        if not isinstance(dependents, list) or len(dependents) <= IMPACT_DETAIL_CAP:
            rows.append(row)
            continue
        # 上游已截到 20 个；total_affected 仍是完整的传递影响数。
        rows.append(
            {
                **row,
                "direct_dependents": dependents[:IMPACT_DETAIL_CAP],
                "direct_dependents_listed": IMPACT_DETAIL_CAP,
                "direct_dependents_truncated": True,
            }
        )
        truncated = True
    return rows, truncated


def _summarize_call_graph(graph: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """把逐函数调用明细收敛为计数与前 N 个影响最大的函数。"""
    summary = {
        key: value for key, value in graph.items() if key not in _CALL_GRAPH_DETAIL_KEYS
    }
    impacts = [i for i in graph.get("function_impacts") or [] if isinstance(i, dict)]
    # 稳定排序：fan_in 降序，同 fan_in 保持原始（文件、行号）顺序。
    ranked = sorted(impacts, key=lambda item: -int(item.get("fan_in") or 0))
    listed = [_compact_function_impact(item) for item in ranked[:FUNCTION_IMPACTS_CAP]]
    total = summary.get("function_impacts_total", len(impacts))
    summary["function_impacts"] = listed
    summary["function_impacts_total"] = total
    summary["function_impacts_listed"] = len(listed)
    summary["function_impacts_truncated"] = total > len(listed)
    truncated = bool(summary["function_impacts_truncated"])

    for key in ("cross_file_callers", "cross_file_callees"):
        per_file = graph.get(key)
        if isinstance(per_file, dict) and per_file:
            summary[f"{key}_by_file"] = {
                file: len(rows) for file, rows in per_file.items()
            }
            truncated = True

    by_file = graph.get("affected_functions_by_file")
    if isinstance(by_file, dict) and by_file:
        ranked_files = sorted(
            by_file.items(), key=lambda kv: (-len(kv[1] or []), str(kv[0]))
        )
        top = [
            {"file": file, "affected_functions": len(edges or [])}
            for file, edges in ranked_files[:IMPACT_DETAIL_CAP]
        ]
        summary["affected_function_files"] = top
        summary["affected_function_files_total"] = len(by_file)
        summary["affected_function_files_truncated"] = len(by_file) > len(top)
        summary["affected_functions_total"] = sum(
            len(edges or []) for edges in by_file.values()
        )
        truncated = True
    return summary, truncated


def _compact_function_impact(item: dict[str, Any]) -> dict[str, Any]:
    """去掉逐调用方明细列表，保留计数与同名匹配（name_only）计数。"""
    compact = {
        key: value for key, value in item.items() if key not in _FUNCTION_DETAIL_LISTS
    }
    upstream = item.get("upstream_callers") or []
    compact.setdefault("upstream_callers_total", len(upstream))
    compact.setdefault(
        "possible_upstream_callers",
        sum(
            1
            for caller in upstream
            if isinstance(caller, dict) and caller.get("match") == _NAME_ONLY_MATCH
        ),
    )
    compact.setdefault(
        "downstream_callees_total", len(item.get("downstream_callees") or [])
    )
    return compact
