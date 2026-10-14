"""已发布索引的部分结果发布规则：稳定单文件失败不冻结其余文件（#1554 风险 4）。

稳定失败是环境或源码字节的确定性性质：缺少可选语法、同一字节解析失败。重试同一
字节只会得到同一失败，因此不能阻塞其余文件的发布；发布前 ``GenerationStore.publish``
仍逐字节复核捕获的源码，失败绑定的正是未变的字节。读失败、写失败等临时失败仍
失败闭合，父版本保持不变。失败文件不写行、不认证，清单与调用图标记保持撤销，
``completeness`` 因而始终不是 complete。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

FAILURE_KIND = "failure_kind"
STABLE = "stable"


def stable_failure(rel_path: str, reason: str) -> dict[str, Any]:
    """解析器拒绝这份字节时的单文件错误项。"""
    return {"file": rel_path, "status": "error", "reason": reason, FAILURE_KIND: STABLE}


def stable_failures_only(details: Iterable[Mapping[str, Any]], errors: int) -> bool:
    """每个错误计数都对应一条带文件的稳定失败项；无明细的错误一律视为临时。"""
    failures = [detail for detail in details if detail.get("status") == "error"]
    return (
        bool(failures)
        and errors == len(failures)
        and all(
            detail.get(FAILURE_KIND) == STABLE and detail.get("file")
            for detail in failures
        )
    )


def publishable_result(result: Any) -> bool:
    """显式写入口（index_file/index_project）的结果能否替换父版本。"""
    if not isinstance(result, Mapping):
        return True
    if result.get("backfill_errors"):
        return False
    if result.get("status") == "error":
        return result.get(FAILURE_KIND) == STABLE and bool(result.get("file"))
    errors = result.get("errors") or 0
    return not errors or stable_failures_only(result.get("files", ()), errors)


def publishable_sync(result: Any, *, permanent_cleanup: bool) -> bool:
    """增量同步结果能否替换父版本；稳定失败外的范围条件仍须精确。"""
    if result.backfill_errors or result.manifest_certification_failed:
        return False
    if not result.errors:
        return bool(result.scope_complete or permanent_cleanup)
    return (
        stable_failures_only(result.details, result.errors)
        and not result.truncated_by_max_files
        and result.changed_during_run == 0
    )
