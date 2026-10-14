"""change-impact 响应中验证命令的去重规则（#1582）。

dogfood round 2 实测：``edit action=impact`` 的完整响应约 100 KB，其中同一条
约 2.2 KB 的 pytest 命令出现了 17 次（顶层别名字段、``agent_summary`` 镜像、
``next_step`` / ``stop_condition`` 文案内联）。代理要为每个字节付费。

规则：

* 顶层命令字段（``verification_command`` / ``test_command`` / ``pytest_command`` /
  ``focused_test_command`` / ``local_verification_command`` / ``ci_verification_command``
  等）是可直接复制执行的契约字段，取值不变。
* ``agent_summary.verification_command`` 是摘要块中唯一的规范命令，保留原值。
* ``agent_summary`` 中与顶层同名同值的其他命令镜像被移除——顶层就是唯一来源。
* ``next_step`` / ``stop_condition`` / ``queue_ledger.handoff`` 等文案：命令不超过
  ``INLINE_COMMAND_LIMIT`` 字符时照旧内联（短命令可直接复制）；更长时改为按字段名
  引用，并注明长度，不再整段重复。
"""

from __future__ import annotations

from typing import Any

# 文案中内联命令的长度上限；超过时只引用字段名。
INLINE_COMMAND_LIMIT = 200

# agent_summary 中会被顶层同名字段完整覆盖的命令镜像键。
MIRRORED_COMMAND_KEYS = (
    "focused_test_command",
    "local_verification_command",
    "low_impact_focused_test_command",
    "ci_verification_command",
)


def command_ref(field: str, command: str) -> str:
    """短命令原样返回；长命令返回指向顶层字段的引用文本。"""
    if len(command) <= INLINE_COMMAND_LIMIT:
        return command
    return f"`{field}` ({len(command)} chars)"


def steps_ref(steps: list[str]) -> str:
    """多步验证：总长不超过上限时按序内联，否则引用 ``verification_steps``。"""
    joined = "; ".join(steps)
    if len(joined) <= INLINE_COMMAND_LIMIT:
        return joined
    return f"the {len(steps)} `verification_steps` ({len(joined)} chars)"


def drop_mirrored_commands(
    summary: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    """返回去掉与顶层同名同值命令镜像后的新摘要，不修改入参。"""
    return {
        key: value
        for key, value in summary.items()
        if not (key in MIRRORED_COMMAND_KEYS and response.get(key) == value)
    }
