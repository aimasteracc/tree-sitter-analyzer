#!/usr/bin/env python3
"""无索引时的现场解析预算（#1562）。

调用关系工具在没有任何索引时会退回 ``CallGraph`` 现场解析整个仓库。
小仓库这条退路有价值（几秒内给出答案、无需先建索引），但大仓库上它会
静默阻塞数分钟：2026-10-14 的 dogfood 审计里 ``nav callers`` 在 2415
个文件的仓库上无提示地解析了 346 s。

本模块把退路限制在小仓库内：源文件数超过 ``PARSE_FALLBACK_MAX_FILES``
时不解析，立即返回诚实的 "索引缺失" 答复，并在 ``next_step`` 中给出
应执行的索引动作与其成本量级。

预算依据（实测，Windows 11 开发机，tree-sitter-analyzer 检出，2026-10-14）：
``CallGraph.build`` 在 164 个文件上耗时 3.3 s（20 ms/文件，CPU 3.1 s）；
在 2409 个文件、机器高负载时耗时 182 s（CPU 63 s）。200 个文件的上限
对应空闲时约 4 s 的现场解析，可以接受；超过即应先建索引。
文件计数与 ``CallGraph`` 使用同一遍历规则，2409 个文件的计数耗时 0.16 s。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...call_graph import SUPPORTED_EXTS
from ...constants import EXCLUDE_DIRS
from ._response_builder import build_response

#: 允许现场解析的最大源文件数；超过即返回 INDEX_MISSING（见模块文档的实测依据）。
PARSE_FALLBACK_MAX_FILES = 200

#: 计数的硬上限：只需知道量级，避免在超大目录树上无界遍历。
_COUNT_CAP = 100_000

INDEX_MCP_ROUTE = "index action=cache mode=index"
INDEX_CLI_ROUTE = "tree-sitter-analyzer --ast-cache --ast-cache-mode index"


def count_source_files(project_root: str, limit: int = _COUNT_CAP) -> int:
    """按 ``CallGraph`` 的遍历规则统计源文件数，达到 ``limit`` 即停止。

    与 ``CallGraph._iter_source_files`` 保持一致：跳过 ``EXCLUDE_DIRS``
    与以点开头的目录和文件，只计 ``SUPPORTED_EXTS`` 后缀。
    """
    count = 0
    for _root, dirs, names in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for name in names:
            if name.startswith("."):
                continue
            if Path(name).suffix.lower() in SUPPORTED_EXTS:
                count += 1
                if count >= limit:
                    return count
    return count


def index_missing_next_step(file_count: int) -> str:
    """给出建索引的动作与成本量级；文件数是实测值，不是估计。"""
    return (
        f"No index exists yet, and this project has {file_count} source files — "
        f"more than the {PARSE_FALLBACK_MAX_FILES}-file limit for an on-the-fly "
        "parse, so nothing was parsed. Build the index once: MCP "
        f"`{INDEX_MCP_ROUTE}` (CLI: `{INDEX_CLI_ROUTE}`). It parses every "
        f"source file once — expect minutes, not seconds, for {file_count} "
        "files — and later graph reads are SQL lookups. Then retry this query."
    )


def index_missing_response(
    project_root: str | None, tool_label: str, **subject: Any
) -> dict[str, Any] | None:
    """仓库超出预算时返回 INDEX_MISSING 答复；预算之内返回 ``None`` 允许现场解析。

    ``tool_label`` 用于摘要行（如 ``"callers"``）；``subject`` 是查询主体字段
    （如 ``function="foo"``），原样写入答复。
    """
    if not project_root:
        return None
    file_count = count_source_files(project_root)
    if file_count <= PARSE_FALLBACK_MAX_FILES:
        return None
    next_step = index_missing_next_step(file_count)
    subject_text = ", ".join(repr(v) for v in subject.values())
    return build_response(
        verdict="WARN",
        error_code="INDEX_MISSING",
        data_source="none",
        index_missing=True,
        source_file_count=file_count,
        parse_fallback_max_files=PARSE_FALLBACK_MAX_FILES,
        next_step=next_step,
        agent_summary={
            "summary_line": (
                f"{tool_label}: {subject_text} unavailable — no index for "
                f"{file_count} source files"
            ),
            "verdict": "WARN",
            "next_step": next_step,
        },
        **subject,
    )
