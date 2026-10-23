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


#: #1625：回复中最多点名的已移除文件数；总数始终如实报告。
REMOVED_FILES_CAP = 20

#: 本次运行没有执行删除检测时的下一步。再跑一次增量刷新同样不会清除已删除
#: 文件，因此必须指向强制重建，不能让代理在增量刷新上无限循环。
FORCE_REFRESH_STEP = (
    "deleted-file detection did not run for this refresh (language-scoped run, "
    "truncated or incomplete discovery, or sources changed during the run); "
    "run `index action=cache mode=index force=true` (CLI: `--ast-cache "
    "--ast-cache-mode index --ast-cache-force`) to purge deleted files"
)


def project_removed_files(
    result: dict[str, Any], summary_line: str, next_step: str, *, force: bool
) -> tuple[dict[str, Any], str, str]:
    """如实报告本次刷新从索引移除的文件，返回 (新结果, 摘要, 下一步)。

    ``removed_files`` 缺失表示删除检测没有运行：``removed`` 置为 ``None``
    （未知，而非 0），并在非强制运行时把下一步改为强制重建（#1625）。
    """
    # ``pruned`` 与 ``removed`` 重复；``snapshot_metrics`` 是快照驱动后才出现在
    # 本路由的内部发现证据。二者都不进入回复，保持 #1582 的响应体积契约。
    base = {
        key: value
        for key, value in result.items()
        if key not in ("pruned", "snapshot_metrics", "backfill_scope", "certification")
    }
    # #1696：回填范围的完整统计留在索引器内部；回复只说明范围回填还是全量及原因。
    scope = result.get("backfill_scope")
    if isinstance(scope, dict):
        mode = str(scope.get("mode") or "")
        base["backfill"] = mode if mode == "scoped" else f"{mode}:{scope.get('reason')}"
    # RFC-0039：认证根是增量折叠还是完整重算（及原因），同样只给紧凑形式。
    certification = result.get("certification")
    if isinstance(certification, dict):
        mode = str(certification.get("mode") or "")
        base["certification"] = (
            mode if mode == "incremental" else f"{mode}:{certification.get('reason')}"
        )
    paths = result.get("removed_files")
    if not isinstance(paths, list):
        step = next_step if force else FORCE_REFRESH_STEP
        return {**base, "removed": None}, f"{summary_line} removed=unknown", step
    listed = paths[:REMOVED_FILES_CAP]
    projected = {
        **base,
        "removed": len(paths),
        "removed_files": listed,
        "removed_files_truncated": len(paths) > len(listed),
    }
    return projected, f"{summary_line} removed={len(paths)}", next_step


def project_publication(
    result: dict[str, Any], summary_line: str, next_step: str, *, symbols: int
) -> tuple[dict[str, Any], str, str]:
    """#1635：摘要中的 ``symbols`` 是刷新之后活动索引的计数，并如实说明是否发布。

    运行有非稳定失败（``INDEX_NOT_PUBLISHABLE``）时私有副本被放弃，活动版本没有被
    替换：计数仍属于旧版本，摘要必须说出这一点，不能让它看起来像是本次运行的结果。
    零变化（``INDEX_UNCHANGED``）时旧版本与本次运行内容相同，计数本就准确。
    """
    from ...cache.generation_noop import NOT_PUBLISHABLE_REASON

    projected = dict(result)
    reason = result.get("publication_reason")
    if result.get("published") is not False or reason != NOT_PUBLISHABLE_REASON:
        return projected, summary_line, next_step
    summary_line = f"{summary_line} published=false reason={reason}"
    next_step = (
        "this refresh was not published: the active index was not replaced, so "
        f"symbols={symbols} is the previous index. Read `errors` / `files`, fix "
        "the cause (unreadable files, low disk space), then rerun "
        "`index action=cache mode=index`"
    )
    return projected, summary_line, next_step
