"""基于 ``nav`` 生产者的关系阶段 (RFC-0041 §3, §5)。

每个关系阶段对其检查过的每个输入，都直接采用生产者自身的覆盖度
(``coverage.from_producer``)；只有当所有输入都是 ``complete`` 时，阶段才是
``complete``。各行保留来源 (``via``)，使详细视图能显示由哪个输入产生；
每个被检查的输入都作为证据记录，并附带可直接调用的 ``nav`` 请求。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .backends import Backends
from .coverage import (
    CALLEE_UNRESOLVED,
    CALLEES_COVERAGE_UNREPORTED,
    COMPLETE_COVERAGE,
    INCOMPLETE,
    RELATION_DEPTH_LIMIT,
    RELATION_NODE_BUDGET,
    TEST_HELPER_DEPTH,
    UNKNOWN,
    Coverage,
    combine_or_complete,
    from_producer,
    gap,
)

#: 单个关系阶段可消耗的生产者调用次数；超出后该阶段结果为下界
#: (``RELATION_NODE_BUDGET``)，绝不静默截断。
NODE_BUDGET = 400
MODULE_SCOPE = "<module>"


@dataclass(frozen=True)
class Row:
    name: str
    file: str
    line: int | None
    cls: str | None = None
    kind: str | None = None
    language: str | None = None
    depth: int | None = None
    via: str | None = None
    role: str | None = None
    membership: str | None = None

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}:{self.name}"

    def as_symbol(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "class": self.cls,
            "kind": self.kind,
            "language": self.language,
        }


@dataclass
class RelationResult:
    rows: list[Row]
    coverage: Coverage
    evidence: list[dict[str, Any]] = field(default_factory=list)


def row_from_symbol(sym: dict[str, Any]) -> Row:
    line = sym.get("line")
    return Row(
        name=str(sym.get("name") or ""),
        file=str(sym.get("file") or ""),
        line=int(line) if isinstance(line, int) else None,
        cls=sym.get("class") or None,
        kind=sym.get("kind") or None,
        language=sym.get("language") or None,
    )


def _evidence(
    op: str,
    send: str,
    row: Row,
    scope: str | None,
    cov: Coverage,
    listed: int,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # 该句柄就是实际发送的请求，重放它即可看到本阶段所采用的生产者证据。
    request: dict[str, Any] = {"action": op, "function_name": send}
    if scope:
        request["file_path"] = scope
    item: dict[str, Any] = {
        "input": row.key,
        "completeness": cov.status,
        "listed": listed,
        "nav": request,
    }
    if cov.reasons:
        item["reasons"] = list(cov.reasons)
    # RFC-0040：生产者给出的有界逐项检查证明，原样携带，
    # 使 detail="full" 能显示对该输入检查了哪些内容。
    checks = (response or {}).get("completeness_checks")
    if checks is not None:
        item["checks"] = checks
    return item


def _related_rows(
    response: dict[str, Any], key: str, parent: Row, depth: int
) -> list[Row]:
    rows: list[Row] = []
    for entry in response.get(key) or []:
        name = str(entry.get("name") or "")
        if not name:
            continue
        line = entry.get("line")
        rows.append(
            Row(
                name=name,
                file=str(entry.get("file") or ""),
                line=int(line) if isinstance(line, int) else None,
                language=entry.get("language") or None,
                depth=depth,
                via=parent.key,
            )
        )
    return rows


def _target(backends: Backends, row: Row) -> tuple[str, str | None]:
    """针对 ``row`` 的生产者请求所用的 ``(function_name, file_path)``。

    行有文件时总是带上范围：callers 工具对项目里唯一定义的名字，带不带范围
    经同一目标集回答、答案相同 (#1798)，不再为唯一名字改发不带范围的请求。
    已知所属类的行以 ``Class.method`` 发送：若用裸名称加上含两个同名方法的
    文件，callers 工具会返回二者的并集 (#1801 上的 Codex)。
    """
    if not row.file:
        return row.name, None
    if row.cls:
        return f"{row.cls}.{row.name}", row.file
    return row.name, row.file


def _requests(backends: Backends, rows: list[Row]) -> list[tuple[Row, str, str | None]]:
    """对 ``rows`` 的每个不同问题只发一次生产者请求。

    当这些行包含某名称的全部已索引定义时，不带范围的裸名称恰好就是在问这个
    集合 (callers 工具对有多个定义的裸名称返回其并集，置信度不会高于其中
    任何一个，#1740)，因此只发一次请求，而不是每个定义各发一次。
    """
    by_name: dict[str, list[Row]] = {}
    for row in rows:
        group = by_name.setdefault(row.name, [])
        # 按定义身份去重：两条遍历分支到达同一定义不能被数成两个定义（Codex #1802）。
        if all(existing.key != row.key for existing in group):
            group.append(row)
    out: list[tuple[Row, str, str | None]] = []
    for name, group in by_name.items():
        count = backends.definition_count(name)
        if len(group) > 1 and count is not None and len(group) >= count:
            out.append((group[0], name, None))
            continue
        out.extend((row, *_target(backends, row)) for row in group)
    return out


class _Budget:
    def __init__(self) -> None:
        self.spent = 0

    def take(self) -> bool:
        if self.spent >= NODE_BUDGET:
            return False
        self.spent += 1
        return True


async def callers(
    backends: Backends, inputs: list[Row], *, depth: int, closure: bool = False
) -> RelationResult:
    """最多 ``depth`` 跳的 callers (BFS，每个展开节点调用一次生产者)。

    ``closure=True`` (``impact()``) 表示问题是完整的传递闭包：在深度上限处
    仍未展开的前沿是一个缺口 (``RELATION_DEPTH_LIMIT``)。而对
    ``callers(depth=N)`` 而言，深度界限就是问题本身，因此不算缺口。
    """
    budget = _Budget()
    covs: list[Coverage] = []
    evidence: list[dict[str, Any]] = []
    out: dict[str, Row] = {}
    expanded: set[str] = set()
    frontier = [r for r in inputs if r.name != MODULE_SCOPE]
    for level in range(1, depth + 1):
        nxt: list[Row] = []
        pending = [r for r in frontier if r.key not in expanded]
        expanded.update(r.key for r in pending)
        requests = _requests(backends, pending)
        await prefetch(backends, [(s, f) for _, s, f in requests], budget)
        for row, send, scope in requests:
            if not budget.take():
                covs.append(gap(INCOMPLETE, RELATION_NODE_BUDGET))
                return RelationResult(
                    list(out.values()), combine_or_complete(covs), evidence
                )
            response = await backends.callers(send, scope)
            cov = from_producer(response)
            covs.append(cov)
            found = _related_rows(response, "callers", row, level)
            evidence.append(
                _evidence("callers", send, row, scope, cov, len(found), response)
            )
            for item in found:
                if item.key not in out:
                    out[item.key] = item
                if item.name != MODULE_SCOPE and item.key not in expanded:
                    nxt.append(item)
        frontier = nxt
    if closure and frontier:
        covs.append(gap(INCOMPLETE, RELATION_DEPTH_LIMIT))
    return RelationResult(list(out.values()), combine_or_complete(covs), evidence)


async def prefetch(
    backends: Backends, pairs: list[tuple[str, str | None]], budget: _Budget
) -> None:
    """把一个阶段将要发出的 callers 请求合并成一次批量（不超出剩余预算）。

    只是预取：随后逐个读取时命中查询内记忆，答复与逐个请求完全相同。
    """
    fetch = getattr(backends, "prefetch_callers", None)
    if callable(fetch) and pairs:
        await fetch(pairs[: max(0, NODE_BUDGET - budget.spent)])


def _is_test_entry(row: Row) -> bool:
    from ..mcp.tools.nav_facade import _is_collectible_caller
    from ..utils.test_detection import is_test_file

    return bool(is_test_file(row.file)) and _is_collectible_caller(
        row.file, row.name, row.language or ""
    )


def _in_test_file(row: Row) -> bool:
    from ..utils.test_detection import is_test_file

    return bool(is_test_file(row.file))


async def tests(
    backends: Backends, inputs: list[Row], budget: _Budget | None = None
) -> RelationResult:
    """直接或经由一个测试辅助函数到达各输入的测试入口。

    定义与 ``nav action=test_map`` (RFC-0014 Phase B) 相同，但由
    ``nav action=callers`` 推导，因此带有 callers 的覆盖度：只有当输入的
    callers 是完整普查、且所经过的每个辅助函数的 callers 也是完整普查时，
    该输入的测试才是完整普查。
    """
    budget = budget or _Budget()
    covs: list[Coverage] = []
    evidence: list[dict[str, Any]] = []
    out: dict[str, Row] = {}
    candidates = [r for r in inputs if r.name != MODULE_SCOPE]
    requests = _requests(backends, candidates)
    await prefetch(backends, [(s, f) for _, s, f in requests], budget)
    helpers: list[tuple[Row, Row]] = []
    for row, send, scope in requests:
        if not budget.take():
            covs.append(gap(INCOMPLETE, RELATION_NODE_BUDGET))
            break
        response = await backends.callers(send, scope)
        cov = from_producer(response)
        covs.append(cov)
        direct = _related_rows(response, "callers", row, 1)
        evidence.append(
            _evidence("callers", send, row, scope, cov, len(direct), response)
        )
        for caller in direct:
            if not _in_test_file(caller):
                continue
            if _is_test_entry(caller):
                out.setdefault(caller.key, _as_test(caller, row))
                continue
            helpers.append((caller, row))
    # 测试文件辅助函数的上一跳同样合并成一次批量。
    await prefetch(backends, [_target(backends, h) for h, _ in helpers], budget)
    for helper, row in helpers:
        covs.append(await _walk_helper(backends, helper, row, budget, out, evidence))
    return RelationResult(list(out.values()), combine_or_complete(covs), evidence)


def _as_test(test: Row, target: Row) -> Row:
    return Row(
        name=test.name,
        file=test.file,
        line=test.line,
        language=test.language,
        depth=test.depth,
        via=target.key,
        role="test",
    )


async def _walk_helper(
    backends: Backends,
    helper: Row,
    target: Row,
    budget: _Budget,
    out: dict[str, Row],
    evidence: list[dict[str, Any]],
) -> Coverage:
    if not budget.take():
        return gap(INCOMPLETE, RELATION_NODE_BUDGET)
    send, scope = _target(backends, helper)
    response = await backends.callers(send, scope)
    cov = from_producer(response)
    parents = _related_rows(response, "callers", helper, 2)
    evidence.append(
        _evidence("callers", send, helper, scope, cov, len(parents), response)
    )
    nested = False
    for parent in parents:
        if not _in_test_file(parent):
            continue
        if _is_test_entry(parent):
            out.setdefault(parent.key, _as_test(parent, target))
        else:
            nested = True
    if nested:
        return combine_or_complete([cov, gap(INCOMPLETE, TEST_HELPER_DEPTH)])
    return cov


#: ``nav callees`` 中解析到项目内定义的被调方（跨文件 ``project`` 与同文件 ``local``）。
_RESOLVED_CALLEES = frozenset({"project", "local"})


async def callees(backends: Backends, inputs: list[Row]) -> RelationResult:
    """通过 ``nav action=callees`` 获取项目内的 callees（跨文件与同文件）。

    ``nav callees`` 不做覆盖度声明，因此本阶段永远不是 ``complete``：若有
    callees 未解析到项目内定义则为 ``incomplete`` (列出的集合是下界)，
    否则为 ``unknown``。
    """
    budget = _Budget()
    covs: list[Coverage] = []
    evidence: list[dict[str, Any]] = []
    out: dict[str, Row] = {}
    for row in inputs:
        if row.name == MODULE_SCOPE:
            continue
        # 与其他关系阶段同一生产者调用上限（Codex #1802）。
        if not budget.take():
            covs.append(gap(INCOMPLETE, RELATION_NODE_BUDGET))
            break
        send, scope = _target(backends, row)
        response = await backends.callees(send, scope)
        unresolved = 0
        listed = 0
        for entry in response.get("callees") or []:
            target = str(entry.get("callee_resolved_file") or "")
            # #1814：同文件被调方（``local``）同样解析到了项目内定义；只有带解析文件的
            # 才算——``self.x`` 的 local 推测没有解析文件，仍是未解析。
            if entry.get("callee_resolution") not in _RESOLVED_CALLEES or not target:
                unresolved += 1
                continue
            name = str(entry.get("name") or "")
            listed += 1
            out.setdefault(
                f"{target}::{name}",
                Row(
                    name=name,
                    file=target,
                    line=None,
                    language=entry.get("language") or None,
                    depth=1,
                    via=row.key,
                ),
            )
        cov = (
            gap(INCOMPLETE, CALLEE_UNRESOLVED)
            if unresolved
            else gap(UNKNOWN, CALLEES_COVERAGE_UNREPORTED)
        )
        if response.get("success") is False:
            cov = from_producer(response)
        covs.append(cov)
        item = _evidence("callees", send, row, scope, cov, listed, response)
        item["unresolved"] = unresolved
        evidence.append(item)
    return RelationResult(list(out.values()), combine_or_complete(covs), evidence)


def new_budget() -> _Budget:
    """一个阶段共享的生产者调用预算（``untested()`` 逐行调用 ``tests()`` 时共用）。"""
    return _Budget()


def target(backends: Backends, row: Row) -> tuple[str, str | None]:
    return _target(backends, row)


def is_test_entry(row: Row) -> bool:
    return _is_test_entry(row)


__all__ = [
    "COMPLETE_COVERAGE",
    "NODE_BUDGET",
    "RelationResult",
    "Row",
    "callees",
    "callers",
    "is_test_entry",
    "row_from_symbol",
    "tests",
]
