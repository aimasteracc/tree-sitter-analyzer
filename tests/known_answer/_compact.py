"""#1853 紧凑答复的独立解析器与等价判定（测试侧，不复用产品代码）。

紧凑答复是完整答复的投影：调用方集合（名字、文件、行、解析方式）与完整性判定
必须与完整答复相同。这里从紧凑文本**解析回**结构，再与完整答复直接读出的结构
比较，所以产品侧的渲染与这里的解析是两份独立实现。

#1854：紧凑答复按置信层级排序（proven → inferred → unconfirmed_receiver，同层
保持原顺序），默认把 unconfirmed_receiver 调用方折叠为一行计数。层级映射在这里
另写一份（:func:`tier_rank`），与产品侧的映射表互相校验。折叠绝不改变判定：
列出的与折叠的合起来正是完整答复的调用方。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_HEADER = re.compile(r"^callers of (?P<function>.*): (?P<total>\d+)$")
_CALLER = re.compile(
    r"^(?P<name>\S(?:.*?\S)?)  (?P<file>.+):(?P<line>-?\d+)  (?P<kind>\S+)$"
)
_MORE = re.compile(r"^\+(?P<hidden>\d+) more \(raise limit\)$")
_COLLAPSED = re.compile(
    r"^\+(?P<collapsed>\d+) unconfirmed-receiver candidates "
    r"\(include_unconfirmed=true to list\)$"
)
_VERDICT = re.compile(
    r"^verdict: (?P<label>complete|incomplete|unknown)"
    r"(?: \((?P<reasons>[^)]*)\))?(?P<details>; details: format=verbose)?$"
)
_EXTRA = re.compile(r"^\+(\d+)$")
#: PR-4: the exhaustive open-site bound, just before the verdict line.
_OPEN = re.compile(
    r"^open: (?P<total>\d+) sites \(exhaustive\)  (?P<sites>.+?)"
    r"(?:; \+(?P<more>\d+) more \(format=verbose\))?$"
)
#: #1923: a bound that failed because a review gate could not run on this call.
_OPEN_UNCHECKED = re.compile(
    r"^open: unchecked \((?P<code>[A-Z_]+)\); re-ask or format=verbose$"
)
#: PR-4: sites named inline on the ``open:`` line.
OPEN_SHOWN = 10

CallerRow = tuple[str, str, int, str]


@dataclass(frozen=True)
class CompactShape:
    """紧凑答复里可比较的部分。"""

    completeness: str
    reasons: tuple[str, ...]
    extra_reasons: int
    callers: tuple[CallerRow, ...]
    total: int
    hidden: int
    #: #1854：默认折叠、未逐行列出的 unconfirmed_receiver 调用方个数。
    collapsed: int = 0
    #: PR-4: ``(total, named sites, more)`` of an exhaustive bound, else None.
    open_bound: tuple[int, tuple[str, ...], int] | None = None
    #: #1923: the gate code of a bound that could not be checked, else None.
    open_unchecked: str | None = None


def _must_match(pattern: re.Pattern[str], line: str) -> re.Match[str]:
    """``line`` 必须整行符合紧凑格式的某一行形态。"""
    match = pattern.match(line)
    if match is None:
        raise AssertionError(f"not a compact line ({pattern.pattern}): {line!r}")
    return match


def parse_compact(answer: Mapping[str, Any]) -> CompactShape:
    """把 ``format=compact`` 的答复解析回结构；格式不符即断言失败。"""
    assert answer.get("format") == "compact", answer
    lines = str(answer["answer"]).split("\n")
    header = _must_match(_HEADER, lines[0])
    verdict = _must_match(_VERDICT, lines[-1])
    body = lines[1:-1]
    open_bound = None
    open_unchecked = None
    if body and (gap := _OPEN_UNCHECKED.match(body[-1])) is not None:
        open_unchecked = gap["code"]
        body = body[:-1]
        assert answer.get("open_sites") == {
            "enumerated": False,
            "reason": "REVIEW_UNCHECKED",
            "unchecked": open_unchecked,
        }, answer
    elif body and (opened := _OPEN.match(body[-1])) is not None:
        named = tuple(opened["sites"].split("; "))
        open_bound = (int(opened["total"]), named, int(opened["more"] or 0))
        body = body[:-1]
        assert answer.get("open_sites") == {
            "total": open_bound[0],
            "enumerated": True,
        }, answer
    else:
        assert "open_sites" not in answer, answer
    hidden = 0
    if body and (more := _MORE.match(body[-1])) is not None:
        hidden = int(more["hidden"])
        body = body[:-1]
    collapsed = 0
    if body and (folded := _COLLAPSED.match(body[-1])) is not None:
        collapsed = int(folded["collapsed"])
        body = body[:-1]
    # 机器可读的折叠数与文本行一致（没有折叠时不出现该字段）。
    assert answer.get("unconfirmed_collapsed", 0) == collapsed, answer
    assert collapsed or "unconfirmed_collapsed" not in answer, answer
    callers: list[CallerRow] = []
    for line in body:
        row = _must_match(_CALLER, line)
        callers.append((row["name"], row["file"], int(row["line"]), row["kind"]))
    raw = [r.strip() for r in (verdict["reasons"] or "").split(",") if r.strip()]
    extra = 0
    if raw and (tail := _EXTRA.match(raw[-1])) is not None:
        extra = int(tail.group(1))
        raw = raw[:-1]
    label = verdict["label"]
    # 非 complete 必须指向完整答复；complete 不带原因也不带指引。
    assert (label != "complete") == bool(verdict["details"]), lines[-1]
    assert answer.get("completeness") == label, answer
    return CompactShape(
        completeness=label,
        reasons=tuple(raw),
        extra_reasons=extra,
        callers=tuple(callers),
        total=int(header["total"]),
        hidden=hidden,
        collapsed=collapsed,
        open_bound=open_bound,
        open_unchecked=open_unchecked,
    )


# #1854：置信层级的测试侧独立实现。0 = proven，1 = registration（PR-4），
# 2 = inferred，3 = unconfirmed_receiver；表外取值、缺失或非字符串一律 3。
_PROVEN_RESOLUTIONS = ("local", "project")
_KIND_RANK = {"import_alias": 0, "registration": 1, "annotated_receiver": 2}
UNCONFIRMED_RANK = 3


def tier_rank(caller: Mapping[str, Any]) -> int:
    """完整答复里一个调用方的层级序号（两个字段中较不确定者）。"""
    resolution = caller.get("callee_resolution")
    rank = (
        0
        if isinstance(resolution, str) and resolution in _PROVEN_RESOLUTIONS
        else UNCONFIRMED_RANK
    )
    kind = caller.get("resolution_kind")
    if kind is not None:
        kind_rank = (
            _KIND_RANK.get(kind, UNCONFIRMED_RANK)
            if isinstance(kind, str)
            else UNCONFIRMED_RANK
        )
        rank = max(rank, kind_rank)
    return rank


def _kind(caller: Mapping[str, Any]) -> str:
    return str(
        caller.get("resolution_kind") or caller.get("callee_resolution") or "unknown"
    )


def _row(caller: Mapping[str, Any]) -> CallerRow:
    name = caller.get("name") or "?"
    if _kind(caller) == "registration" and caller.get("via"):
        name = caller["via"]  # PR-4: a registration shows its decorator text
    return (
        str(name),
        str(caller.get("file") or "?"),
        int(caller.get("line") or 0),
        _kind(caller),
    )


def expected_shape(
    full: Mapping[str, Any], top: int = 3, *, include_unconfirmed: bool = False
) -> CompactShape:
    """完整答复应投影出的结构（直接读完整答复的字段）。"""
    completeness = full.get("completeness")
    label = completeness if completeness in ("complete", "incomplete") else "unknown"
    reasons = list(full.get("completeness_reasons") or [])
    if not reasons and full.get("completeness_reason"):
        reasons = [str(full["completeness_reason"])]
    if label == "complete":
        reasons = []
    page = [c for c in full.get("callers") or [] if isinstance(c, Mapping)]
    ordered = sorted(page, key=tier_rank)
    listed = [
        c for c in ordered if include_unconfirmed or tier_rank(c) < UNCONFIRMED_RANK
    ]
    callers = tuple(_row(c) for c in listed)
    total = int(full.get("caller_count", len(page)) or 0)
    return CompactShape(
        completeness=label,
        reasons=tuple(str(r) for r in reasons[:top]),
        extra_reasons=max(0, len(reasons) - top),
        callers=callers,
        total=total,
        hidden=max(0, total - len(page)),
        collapsed=len(page) - len(listed),
        open_bound=_expected_open(full, label),
        open_unchecked=_expected_unchecked(full, label),
    )


def _expected_unchecked(full: Mapping[str, Any], label: str) -> str | None:
    """#1923: the gate code an ``unknown`` full answer's unchecked bound names."""
    bound = full.get("open_sites")
    if label != "unknown" or not isinstance(bound, Mapping):
        return None
    if bound.get("enumerated") is not False or bound.get("reason") != (
        "REVIEW_UNCHECKED"
    ):
        return None
    return str(bound.get("unchecked") or "REVIEW_UNCHECKED")


def _expected_open(
    full: Mapping[str, Any], label: str
) -> tuple[int, tuple[str, ...], int] | None:
    """PR-4: the bound an ``unknown`` full answer projects, read from its fields."""
    bound = full.get("open_sites")
    if label != "unknown" or not isinstance(bound, Mapping):
        return None
    if bound.get("enumerated") is not True:
        return None
    refs: list[str] = []
    for field in bound["fields"]:
        for site in full[field]:
            ref = f"{site['file']}:{site['line']}"
            if ref not in refs:
                refs.append(ref)
    assert len(refs) == bound["total"], full
    return len(refs), tuple(refs[:OPEN_SHOWN]), max(0, len(refs) - OPEN_SHOWN)


def assert_equivalent(
    full: Mapping[str, Any],
    compact: Mapping[str, Any],
    *,
    include_unconfirmed: bool = False,
) -> None:
    """紧凑答复与完整答复的调用方集合、判定一致；紧凑判定绝不更乐观。"""
    shape = parse_compact(compact)
    expected = expected_shape(full, include_unconfirmed=include_unconfirmed)
    assert shape == expected, (full, compact)
    # #1854：列出的 + 折叠的 = 完整答复本页的全部调用方（多重集合相等）。
    page = [c for c in full.get("callers") or [] if isinstance(c, Mapping)]
    folded = [_row(c) for c in page if tier_rank(c) == UNCONFIRMED_RANK]
    union = sorted(shape.callers) + (sorted(folded) if shape.collapsed else [])
    assert sorted(union) == sorted(_row(c) for c in page), (full, compact)
    assert shape.collapsed == (0 if include_unconfirmed else len(folded))
    if shape.completeness == "complete":
        assert full["completeness"] == "complete", (full, compact)
    # 机器可读字段：原因码逐项等于完整答复（complete 时为空），verdict 相同。
    full_reasons = list(full.get("completeness_reasons") or [])
    if not full_reasons and full.get("completeness_reason"):
        full_reasons = [str(full["completeness_reason"])]
    expected_reasons = [] if shape.completeness == "complete" else full_reasons
    assert list(compact.get("completeness_reasons") or []) == expected_reasons
    assert compact.get("verdict") == full.get("verdict"), (full, compact)
