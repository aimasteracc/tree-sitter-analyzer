"""MCP 写入路由的类型化准入失败答复（RFC-0032 slice 4，#1554）。

CLI 打印同一 MCP 答复，因此两条路由的机器字段天然一致；watcher 使用
:func:`tree_sitter_analyzer.cache.admission.admission_failure_payload` 的同一构造器。
"""

from __future__ import annotations

from typing import Any

from ...cache.admission import admission_failure_of, admission_failure_payload
from .error_sanitizer import bounded_safe_error_message


def admission_error_response(
    exc: BaseException, project_root: str | None, *, prefix: str = ""
) -> dict[str, Any] | None:
    """准入失败返回类型化答复，``error`` 保持该路由原有的净化文本；否则返回 None。"""
    failure = admission_failure_of(exc)
    if failure is None:
        return None
    error, truncated = bounded_safe_error_message(exc, project_root, prefix=prefix)
    return {
        **admission_failure_payload(failure, error),
        "error_truncated": truncated,
    }
