"""候选发现的墙钟预算：随已计入的目录项数线性放宽（#1597、#1601）。

首次捕获曾用固定 5 s。Windows 上 2,800 个目录项空闲时就要 2.6–3.9 s
（``realpath`` 与逐项句柄打开占大头），负载下两次冷全量索引越界，只发现了
2,614 / 2,334 项，索引因此无法认证（#1601）。#1597 已为发布前复核采用
30 s + 10 ms/项（约实测成本 10 倍）；首次捕获与复核共用此唯一公式。

首次捕获事先不知道总项数，因此按“到目前为止已计入的项数”判定：处理第 n 项时
允许的累计耗时为 ``discovery_budget_seconds(n)``。仍越界时照旧失败关闭为
``INDEX_CANDIDATE_DISCOVERY_BUDGET``；条目预算（100,000 项）继续封顶总时长。
"""

from __future__ import annotations

DISCOVERY_BASE_SECONDS = 30.0
DISCOVERY_SECONDS_PER_ENTRY = 0.01


def discovery_budget_seconds(entries: int) -> float:
    """``entries`` 个目录项的总发现预算（秒）。"""
    return DISCOVERY_BASE_SECONDS + DISCOVERY_SECONDS_PER_ENTRY * entries


def discovery_deadline(
    started: float, entries: int, fixed_seconds: float | None
) -> float:
    """处理第 `entries` 项时的单调时钟截止点；给定 `fixed_seconds` 则不放宽。"""
    if fixed_seconds is not None:
        return started + fixed_seconds
    return started + discovery_budget_seconds(entries)
