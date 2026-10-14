"""源码摘要绑定的预算与类型化失败（#1562）。

``generation_store._bind_source_hashes`` 在路径平台（Windows）上为每个候选
文件计算内容摘要。此前整批共用固定 30 s 截止时间：Windows 打开文件受 I/O
延迟支配（实测 2741 个文件 45.5 s 墙钟、仅 3.1 s CPU，约 17 ms/文件），
约 1800 个文件以上的仓库首次索引必然抛出裸 ``TimeoutError``（#1554 引入）。

总预算改为随文件数线性增长，每文件 0.1 s 约为实测成本的 6 倍余量；单文件
仍限 30 s 以挡住慢读；字节预算保持 512 MiB 不变。
"""

from __future__ import annotations

SOURCE_HASH_BASE_SECONDS = 30.0
SOURCE_HASH_SECONDS_PER_FILE = 0.1
SOURCE_HASH_MAX_SECONDS_ONE_FILE = 30.0
SOURCE_HASH_BYTE_BUDGET = 512 * 1024 * 1024
SOURCE_HASH_BUDGET_EXCEEDED = "INDEX_GENERATION_SOURCE_HASH_BUDGET_EXCEEDED"


class SourceHashBudgetExceeded(RuntimeError):
    """源码摘要绑定超出时间或字节预算；候选不完整，失败关闭、绝不发布。"""

    def __init__(self, selected: int, bound: int) -> None:
        super().__init__(SOURCE_HASH_BUDGET_EXCEEDED)
        self.selected = selected
        self.bound = bound


def source_hash_budget_seconds(selected: int) -> float:
    """``selected`` 个文件的总时间预算（秒）。"""
    return SOURCE_HASH_BASE_SECONDS + SOURCE_HASH_SECONDS_PER_FILE * selected


def source_hash_budget_next_step(exc: SourceHashBudgetExceeded) -> str:
    """预算耗尽时给调用方的可执行下一步。"""
    budget = source_hash_budget_seconds(exc.selected)
    return (
        f"Nothing was published: binding source hashes stopped after {exc.bound} "
        f"of {exc.selected} files because the {budget:.0f} s budget ran out "
        "(usually slow file opens on a loaded machine or an antivirus scan). "
        "Retry the same index call; if it fails again, narrow the scope with "
        "`index action=full exclude_patterns=[...]` or max_files."
    )
