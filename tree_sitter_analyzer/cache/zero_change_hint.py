"""零变化快路径提示（dogfood 2026-11-10 §11）。

实测（同一台机器、本仓库 2921 文件）：缺收敛记录的 no-op 索引要 9.08 s，
有记录时 0.72–0.86 s。记录只在「完整刷新 + 只差稳定失败 + 回填零错误」时签发，
所以遗留缓存需要一次 ``--ast-cache-force`` 才能进入快路径；没有提示时，agent
只看到慢，却猜不到一次 force 就能永久修好。
"""

from __future__ import annotations

from typing import Any


def zero_change_fast_path_hint(stats: dict[str, Any]) -> str | None:
    """没有收敛记录的零变化运行：告诉 agent 一次 force 就能永久提速。

    实测（2026-11-10，本仓库 2921 文件）：缺记录的 no-op 是 9.08 s，有记录的
    no-op 是 0.72–0.86 s。记录只在「完整刷新 + 只差稳定失败 + 回填零错误」时
    签发，所以遗留缓存需要一次 ``--ast-cache-force`` 才会进入快路径。
    没有这个提示时，agent 只能看到 9 s 的耗时，猜不到一次 force 就能修好。
    """
    if stats.get("stable_failures_recorded"):
        return None
    if stats.get("backfill_skipped"):
        return None
    if int(stats.get("indexed", 0) or 0) != 0:
        return None
    if int(stats.get("errors", 0) or 0) <= 0:
        return None
    return (
        "This index has stable failures but no convergence record, so every "
        "unchanged run re-runs the backfill (measured 9.08 s vs 0.72-0.86 s). "
        "Run once with --ast-cache-force to record them; unchanged indexes then "
        "take the zero-change fast path."
    )
