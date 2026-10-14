"""``ast_cache mode=index`` 响应的文件明细投影（#1582）。

索引器内部的 ``files`` 明细会逐个列出每个文件，包括内容未变、直接命中缓存的
文件。2417 个文件的仓库上，只改一个文件的增量运行仍然返回约 320 KB，代理要为
每个字节付费。这里只在 MCP/CLI 响应边界做投影，不改动索引器内部统计（发布策略
与快照复核仍依赖完整明细）：

* 默认：省略 ``status=cached`` 的未变文件，只列出变化/出错/跳过/告警的文件，
  错误优先，并以 ``files_cap`` 为上限；截断与省略都用计数如实报告。
* ``include_details=true``：返回完整明细（含未变文件），与旧行为一致。

计数字段（``indexed`` / ``cached`` / ``errors`` / ``skipped``）始终保持原值，
摘要只影响列表本身。
"""

from __future__ import annotations

from typing import Any

# 默认列出的变化文件上限；与 full_index 的 error_details 上限同量级。
INDEX_FILES_CAP = 50

# 未变文件在索引器明细中的状态值。
_UNCHANGED_STATUS = "cached"

# 列表排序优先级：错误与告警永远排在前面，避免被截断隐藏。
_STATUS_PRIORITY = {"error": 0, "warning": 1, "skipped": 2}


def _priority(detail: Any) -> int:
    """返回明细的排序优先级；未知状态排在最后。"""
    status = detail.get("status") if isinstance(detail, dict) else None
    return _STATUS_PRIORITY.get(str(status), len(_STATUS_PRIORITY))


def project_index_files(
    result: dict[str, Any], *, include_details: bool
) -> dict[str, Any]:
    """返回带有限 ``files`` 明细与如实计数的新字典，不修改 ``result``。

    ``result`` 中没有 ``files`` 列表时（单文件索引、类型化失败等）原样返回副本。
    """
    files = result.get("files")
    if not isinstance(files, list):
        return dict(result)
    if include_details:
        return {
            **result,
            "files_total": len(files),
            "files_listed": len(files),
            "files_truncated": False,
            "unchanged_omitted": 0,
        }
    changed = [
        detail
        for detail in files
        if not (isinstance(detail, dict) and detail.get("status") == _UNCHANGED_STATUS)
    ]
    # sorted 是稳定排序：同优先级内保持索引器的原始顺序。
    ordered = sorted(changed, key=_priority)
    listed = ordered[:INDEX_FILES_CAP]
    projected: dict[str, Any] = {
        **result,
        "files": listed,
        "files_total": len(changed),
        "files_listed": len(listed),
        "files_cap": INDEX_FILES_CAP,
        "files_truncated": len(changed) > len(listed),
        "unchanged_omitted": len(files) - len(changed),
    }
    if projected["files_truncated"] or projected["unchanged_omitted"]:
        projected["files_next_step"] = (
            "pass include_details=true (CLI: --ast-cache-include-details) "
            "for the full per-file list including unchanged files"
        )
    return projected
