"""#1706：非 ``complete`` 答案的 ``next_step`` 点名主因背后的证据，有无调用方都一样。

dogfood 第 9 轮：

* ``UNRESOLVED_INBOUND`` 只有计数（15 个答案），答复从不说那些入边在哪里；
* 主因为 ``NON_CALL_REFERENCES`` 且已列出调用方的 53 个答案拿到的是通用的
  “Review callers above…”，非调用引用的位置只出现在 0 调用方的答案里。

这里给出 ``unresolved_inbound_sites``（与 ``name_only_sites`` 同形：有上限的列表，
总数与是否截断并列），以及按主因点名证据位置的 ``next_step``。
"""

from __future__ import annotations

from typing import Any

from .callers_absence import ACCESSOR_REASON, NON_CALL_REASON
from .callers_reasons import (
    DECLARING_FILE_REASON,
    UNATTRIBUTED_REASON,
    UNRESOLVED_INBOUND_REASON,
)
from .relation_freshness import STALE_REASON

#: 响应中列出的未解析入边调用点上限（与 ``name_only_sites`` 相同）。
SITES_CAP = 20
#: next_step 中内联点名的位置数。
_SITES_NAMED = 3


def unresolved_inbound_fields(sites: list[dict[str, Any]] | None) -> dict[str, Any]:
    """``unresolved_inbound`` 背后的调用点；读不到时三个字段都是 None。"""
    if sites is None:
        return {
            "unresolved_inbound_sites": None,
            "unresolved_inbound_sites_total": None,
            "unresolved_inbound_sites_truncated": None,
        }
    return {
        "unresolved_inbound_sites": sites[:SITES_CAP],
        "unresolved_inbound_sites_total": len(sites),
        "unresolved_inbound_sites_truncated": len(sites) > SITES_CAP,
    }


def read_unresolved_inbound(
    cache: Any,
    name: str,
    file_path: str | None,
    bound_targets: Any,
) -> tuple[int | None, list[dict[str, Any]] | None]:
    """``(未解析入边数, 调用点)``；数目由调用点得出，读取失败为 ``(None, None)``。

    缓存没有调用点读取接口时退回只读计数（调用点为 None）。
    """
    if cache is None:
        return None, None
    extra = {"bound_targets": bound_targets} if bound_targets else {}
    reader = getattr(cache, "unresolved_caller_sites", None)
    if reader is None:
        return cache.count_unresolved_callers(name, file_path, **extra), None
    sites = reader(name, file_path, **extra)
    return (None, None) if sites is None else (len(sites), list(sites))


def unresolved_sites_named(sites: list[dict[str, Any]]) -> str:
    """``a.py:3 (run: `x.open`); …; and N more``。"""
    named = [
        f"{site['file']}:{site['line']} ({site['caller']}: `{site['callee']}`)"
        for site in sites[:_SITES_NAMED]
    ]
    return _join(named, len(sites))


def unresolved_sites_clause(sites: list[dict[str, Any]] | None) -> str:
    """0 调用方提示后附加的 ` Sites (…): …`；没有调用点时为空串。"""
    if not sites:
        return ""
    return " Sites (`unresolved_inbound_sites`): " + unresolved_sites_named(sites) + "."


def unresolved_inbound_step(func_name: str, sites: list[dict[str, Any]]) -> str:
    """点名未解析入边的调用点，并说明怎样判断它是不是调用方。"""
    return (
        f"{len(sites)} call edge(s) into {func_name!r} are unresolved "
        f"(`unresolved_inbound_sites`): {unresolved_sites_named(sites)}. The index "
        "could not bind them to a definition; read each site and check what its "
        f"receiver or name refers to: if it is {func_name!r}, it is a caller "
        "missing from the list."
    )


def reason_step(
    primary: str | None,
    func_name: str,
    result: dict[str, Any],
    *,
    unresolved_sites: list[dict[str, Any]] | None,
    declaring_sites: list[dict[str, Any]] | None,
    absence_hint: str | None,
) -> str | None:
    """已列出调用方、答案非 complete 时，点名主因证据的 next_step。

    ``NAME_ONLY_INBOUND`` 已由 ``name_only_step`` 点名；``SOURCE_INDEX_MISMATCH`` 等
    新鲜度原因由刷新步骤（``apply_source_evidence``）给出，这里返回 None。
    """
    if primary == UNRESOLVED_INBOUND_REASON and unresolved_sites:
        return unresolved_inbound_step(func_name, unresolved_sites)
    if primary == DECLARING_FILE_REASON and declaring_sites:
        return _declaring_step(func_name, declaring_sites)
    if primary == NON_CALL_REASON and result.get("non_call_reference_sites"):
        return _non_call_step(func_name, result)
    if primary == ACCESSOR_REASON:
        return _accessor_step(func_name, result)
    if primary == UNATTRIBUTED_REASON:
        return (
            f"{result.get('unattributed_call_sites')} module-level call site(s) "
            f"reach {func_name!r} without a call line, so they are counted rather "
            "than listed; read the module-level code of the files that import it."
        )
    if primary in (None, STALE_REASON) or not absence_hint:
        return None
    return _listed_callers_hint(
        func_name, int(result.get("caller_count") or 0), absence_hint
    )


def _non_call_step(func_name: str, result: dict[str, Any]) -> str:
    sites = result["non_call_reference_sites"]
    total = int(result.get("non_call_references") or len(sites))
    named = [f"{site['file']}:{site['line']}" for site in sites[:_SITES_NAMED]]
    return (
        f"{total} non-call reference(s) to {func_name!r} are not call edges "
        f"(`non_call_reference_sites`): {_join(named, total)}. At each, check "
        f"whether {func_name!r} is passed as a callback, rebound, or re-exported "
        "under another name (for an `import ... as` line, check that name's uses): "
        "a call through any of them is missing from the caller list."
    )


def _accessor_step(func_name: str, result: dict[str, Any]) -> str:
    step = (
        f"{func_name!r} is a property/accessor: it is read by attribute access, "
        "which the call graph does not record, so the listed callers are not all "
        f"of its uses; search for `.{func_name.rpartition('.')[2]}` reads."
    )
    sites = result.get("non_call_reference_sites") or []
    if sites:
        named = [f"{site['file']}:{site['line']}" for site in sites[:_SITES_NAMED]]
        total = int(result.get("non_call_references") or len(sites))
        step += f" Non-call references: {_join(named, total)}."
    return step


def _declaring_step(func_name: str, sites: list[dict[str, Any]]) -> str:
    named = [f"{site['file']}:{site['line']}" for site in sites[:_SITES_NAMED]]
    return (
        f"{len(sites)} unresolved call(s) sit in a file that declares {func_name!r} "
        f"and could target it (`unresolved_sites`): {_join(named, len(sites))}. "
        "Read those sites; any that reaches it is a caller missing from the list."
    )


def _listed_callers_hint(func_name: str, callers: int, hint: str) -> str:
    """把 0 调用方措辞的复核门提示改写为“已列出调用方、但列表可能不全”。"""
    for joint in (", but ", ", and "):
        prefix = f"No resolved caller for {func_name!r}{joint}"
        if hint.startswith(prefix):
            hint = (
                f"{callers} caller(s) are listed for {func_name!r}{joint}"
                + hint[len(prefix) :]
            )
            break
    return hint.replace(
        "this is not evidence of absence", "the list may be incomplete"
    ).replace("treating this as absence", "treating the list as complete")


def _join(named: list[str], total: int) -> str:
    if total > len(named):
        named = [*named, f"and {total - len(named)} more"]
    return "; ".join(named)


__all__ = [
    "SITES_CAP",
    "read_unresolved_inbound",
    "reason_step",
    "unresolved_inbound_fields",
    "unresolved_inbound_step",
    "unresolved_sites_clause",
    "unresolved_sites_named",
]
