"""每个调用方的置信层级（#1854），只由解析器已写在条目上的字段推出。

调用方条目上有两个解析字段：

* ``callee_resolution`` —— :func:`classify_callee_resolution` 写入
  ``local`` / ``project`` / ``stdlib`` / ``unknown``；边表里另有解析器写入的
  ``external`` / ``builtin``。
* ``resolution_kind`` —— ``callers_annotated.py`` 写入 ``annotated_receiver``
  （RFC-0038：接收者类型只经注解得出，``confidence`` 0.8）或 ``import_alias``
  （#1670：经改名导入解析）；普通的已解析边不带此字段。

映射表（两字段各给出一个层级，取其中**较不确定**的一个）：

=====================  ======================  ====================
字段                     值                      层级
=====================  ======================  ====================
callee_resolution       local, project          proven
callee_resolution       stdlib, external,       unconfirmed_receiver
                        builtin, unknown
resolution_kind         （无）, import_alias      proven
resolution_kind         annotated_receiver      inferred
resolution_kind         registration            registration（PR-4）
任一字段                其他任何值、缺失、非字符串  unconfirmed_receiver
=====================  ======================  ====================

``proven``：解析器把这条调用边绑定到了项目内的定义（self/cls、导入、同文件、
唯一全局函数、类名或构造得到的接收者及其 MRO）。``inferred``：绑定依赖一次
类型注解推断。``unconfirmed_receiver``：同名调用点，但边未绑定到项目内定义——
接收者类型未被证明。层级只影响排序与紧凑答复的折叠，从不参与完整性判定；
这类调用点照旧作为未解析证据计入 RFC-0040 的检查。

本模块只依赖标准库，可在离线脚本里对已存的答复做同一推导（用于测量）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

PROVEN = "proven"
#: PR-4：登记型装饰器（``resolution_kind: "registration"``）——确定的入向使用，
#: 但不是调用边：框架经由登记调用目标，那些调用方列不出来。单列一层，
#: 不与调用边混淆；紧凑答复照常列出（不折叠）。
REGISTRATION = "registration"
INFERRED = "inferred"
UNCONFIRMED = "unconfirmed_receiver"
#: 从最确定到最不确定。
TIERS = (PROVEN, REGISTRATION, INFERRED, UNCONFIRMED)
#: 调用方条目上的字段名。``confidence`` 已被 RFC-0038 的数值占用，故另起一名。
CONFIDENCE_FIELD = "confidence_tier"

_RANK = {tier: rank for rank, tier in enumerate(TIERS)}

#: ``callee_resolution`` 的取值 → 层级；表外取值一律最不确定。
CALLEE_RESOLUTION_TIERS: dict[str, str] = {
    "local": PROVEN,
    "project": PROVEN,
    "stdlib": UNCONFIRMED,
    "external": UNCONFIRMED,
    "builtin": UNCONFIRMED,
    "unknown": UNCONFIRMED,
}
#: ``resolution_kind`` 的取值 → 层级；字段缺失即普通已解析边。
RESOLUTION_KIND_TIERS: dict[str, str] = {
    "import_alias": PROVEN,
    "registration": REGISTRATION,
    "annotated_receiver": INFERRED,
}

ORDER_INDEX = "index"
ORDER_CONFIDENCE = "confidence"
#: ``nav action=callers`` 接受的 ``order`` 值；默认 ``index`` 即原有顺序。
ORDERS = (ORDER_INDEX, ORDER_CONFIDENCE)

ORDER_PROPERTY: dict[str, Any] = {
    "type": "string",
    "enum": list(ORDERS),
    "default": ORDER_INDEX,
    "description": (
        "index (default) = existing order; confidence = proven callers first, "
        "then registration, inferred, unconfirmed_receiver (stable within a tier), "
        "applied before the limit cut. Each caller carries confidence_tier."
    ),
}


def tier_rank(tier: str) -> int:
    """层级的序号（0 最确定）；未知层级按最不确定处理。"""
    return _RANK.get(tier, _RANK[UNCONFIRMED])


def _lookup(table: Mapping[str, str], value: Any) -> str:
    return table.get(value, UNCONFIRMED) if isinstance(value, str) else UNCONFIRMED


def caller_confidence(caller: Any) -> str:
    """一个调用方条目的层级：两字段各自的层级中较不确定者。"""
    if not isinstance(caller, Mapping):
        return UNCONFIRMED
    tier = _lookup(CALLEE_RESOLUTION_TIERS, caller.get("callee_resolution"))
    if "resolution_kind" in caller and caller["resolution_kind"] is not None:
        kind_tier = _lookup(RESOLUTION_KIND_TIERS, caller["resolution_kind"])
        tier = max(tier, kind_tier, key=tier_rank)
    return tier


def with_confidence(callers: Iterable[Any]) -> list[Any]:
    """返回新列表：每个条目复制并带上 ``confidence_tier``（不改原条目）。"""
    return [
        {**caller, CONFIDENCE_FIELD: caller_confidence(caller)}
        if isinstance(caller, Mapping)
        else caller
        for caller in callers
    ]


def order_by_confidence(callers: Iterable[Any]) -> list[Any]:
    """按层级稳定排序（同层保持原顺序），返回新列表。"""
    return sorted(callers, key=lambda caller: tier_rank(caller_confidence(caller)))


def invalid_order(value: Any) -> dict[str, Any] | None:
    """``order`` 不在允许值内时的错误答复；合法时为 ``None``。"""
    if value in ORDERS:
        return None
    return {
        "success": False,
        "error_code": "INVALID_ARGUMENT",
        "error": (
            f"order={value!r} is not supported for action=callers; "
            f"use one of: {', '.join(ORDERS)}"
        ),
    }
