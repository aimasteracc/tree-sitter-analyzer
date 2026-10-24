"""统一查询引擎所组合的、基于索引的生产者 (RFC-0041 §5)。

这里不会重新推导任何关系。选择由 Hyphae 求值器执行；callers / callees 直接
就是 ``nav`` 工具本身 (``CodeGraphCallersTool`` / ``CodeGraphCalleesTool``)，
因此其完整性与原因码完全按 ``nav action=callers`` 的报告原样采用；索引就绪度、
未索引源文件与源码新鲜度复用 callers 工具所执行的同一套门禁。

引擎通过 :class:`Backends` 协议交互，因此测试可以注入伪生产者，在没有索引的
情况下固定传播规则。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol

from ..hyphae.ast import SelectorList
from .coverage import (
    COMPLETE_COVERAGE,
    INCOMPLETE,
    UNKNOWN,
    Coverage,
    gap,
)

#: 求值器读取路径所需的探测语句 (沿用 RFC 之前的 ``tql_execute``)：
#: 部分旧的缓存读取路径会吞掉 SQL 错误，所以在求值前先检查这些表，
#: 而不是信任空结果。
_READ_PROBES = (
    "SELECT file_path, language, symbols_json FROM ast_index LIMIT 0",
    "SELECT id, name, kind, file_path, language, line FROM ast_symbol_rows LIMIT 0",
    "SELECT kind, caller_name, callee_name, file_path, caller_line, "
    "callee_symbol_id, callee_resolved_file, metadata FROM edges LIMIT 0",
    "SELECT symbol_id, file_path, last_modified_at, mod_count_30d "
    "FROM ast_symbol_activation LIMIT 0",
    "SELECT rule_id, caller_file, caller_name FROM ast_constraint_violations LIMIT 0",
)

#: 属于定义的符号种类 (``symbol()`` 源与单一定义检查共用这一份列表)。
DEFINITION_KINDS = (
    "function",
    "method",
    "class",
    "interface",
    "struct",
    "trait",
    "enum",
    "type",
    "variable",
    "constant",
)
#: 求值器每次查询实际物化匹配数的硬上限。
SELECT_CAP = 10_000
#: 每次生产者调用请求的关系行数 (nav callers 最多列出这么多)。
RELATION_LIST_CAP = 10_000


@dataclass(frozen=True)
class IndexState:
    """``ready`` / ``empty`` / ``missing`` / ``unavailable`` 状态及详情。"""

    state: str
    indexed_files: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class Selection:
    rows: list[dict[str, Any]]
    total: int
    truncated: bool


class Backends(Protocol):
    def index_state(self) -> IndexState: ...

    def select(self, selector: SelectorList, cap: int) -> Selection: ...

    def source_gate(self, files: list[str], languages: frozenset[str]) -> Coverage: ...

    def definitions(
        self, name: str, *, cls: str | None, file: str | None
    ) -> list[dict[str, Any]]: ...

    def definition_count(self, name: str) -> int | None: ...

    def definition_kinds(
        self, coordinates: list[tuple[str, int, str]]
    ) -> dict[tuple[str, int, str], str]: ...

    async def callers(self, name: str, file: str | None) -> dict[str, Any]: ...

    async def callees(self, name: str, file: str | None) -> dict[str, Any]: ...

    def generation(self) -> str | None: ...


class IndexBackends:
    """基于单个项目 AST 缓存的生产环境 :class:`Backends` 实现。"""

    def __init__(self, project_root: str, cache: Any = None) -> None:
        self.project_root = project_root
        self._cache = cache
        self._nav_facade: Any = None
        self._callers_tool: Any = None

    @property
    def cache(self) -> Any:
        if self._cache is None:
            from ..ast_cache import ASTCache

            self._cache = ASTCache(self.project_root)
        return self._cache

    # -- 索引 -------------------------------------------------------------
    def index_state(self) -> IndexState:
        try:
            conn = self.cache.get_conn()
            for probe in _READ_PROBES:
                conn.execute(probe)
        except Exception as exc:  # noqa: BLE001 — 任何读取失败都视为 "unavailable"
            return IndexState("unavailable", 0, str(exc))
        try:
            stats = self.cache.get_stats() or {}
            total = int(stats.get("total_files", 0) or 0)
        except Exception:  # noqa: BLE001
            return IndexState("missing")
        return IndexState("ready", total) if total > 0 else IndexState("empty")

    def select(self, selector: SelectorList, cap: int) -> Selection:
        from ..hyphae import Evaluator

        evaluator = Evaluator(self.cache, max_results=cap)
        rows = _with_class(self.cache, evaluator.eval(selector))
        return Selection(rows, evaluator.total_matches(), evaluator.was_truncated())

    def source_gate(self, files: list[str], languages: frozenset[str]) -> Coverage:
        """未索引源文件门禁与新鲜度门禁，与 ``nav action=callers`` 的执行方式一致。

        门禁失败时，非空答案只是下界 (``incomplete``)；
        空答案则不能作为不存在的证据 (``unknown``)。
        """
        from ..mcp.tools.callers_absence import _freshness_gap
        from ..mcp.tools.relation_freshness import relation_source_evidence
        from ..mcp.tools.unindexed_sources import (
            UNCHECKED_REASON,
            UNINDEXED_REASON,
            unindexed_source_files,
        )

        failed = INCOMPLETE if files else UNKNOWN
        langs = languages or self._indexed_languages()
        if langs is None:
            return gap(UNKNOWN, UNCHECKED_REASON)
        unindexed = unindexed_source_files(self.cache, self.project_root, langs)
        if unindexed is None:
            return gap(failed, UNCHECKED_REASON)
        if unindexed:
            return gap(failed, UNINDEXED_REASON)
        evidence, _changed = relation_source_evidence(
            # 有结果也复核全部已索引文件（Codex #1802 P1）：只复核结果所在文件时，
            # 未列出的文件里已改名出来的同名定义会被漏掉而仍报 complete。
            self.cache,
            self.project_root,
            files,
            absence=True,
        )
        reason = _freshness_gap(evidence)
        return gap(failed, reason) if reason else COMPLETE_COVERAGE

    def _indexed_languages(self) -> frozenset[str] | None:
        try:
            rows = self.cache.get_conn().execute(
                "SELECT DISTINCT language FROM ast_index"
            )
            return frozenset(str(r[0]) for r in rows if r[0])
        except (sqlite3.Error, AttributeError):
            return None

    def definitions(
        self, name: str, *, cls: str | None, file: str | None
    ) -> list[dict[str, Any]]:
        """名称精确匹配的定义 (``symbol()`` 源)。

        结果行与 Hyphae ``#name[class=..][file=..]`` 相同，但省去了其模糊搜索
        层级：这些层级在 TSA 自身索引上约耗时 0.9 s，且结果随后会被精确名称
        过滤丢弃。
        """
        placeholders = ", ".join("?" for _ in DEFINITION_KINDS)
        rows = (
            self.cache.get_conn()
            .execute(
                "SELECT name, kind, file_path, line, end_line, language "
                f"FROM ast_symbol_rows WHERE name = ? AND kind IN ({placeholders}) "
                "ORDER BY file_path, line",
                (name, *DEFINITION_KINDS),
            )
            .fetchall()
        )
        found = [
            {
                "name": r["name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "line": r["line"],
                "end_line": r["end_line"],
                "language": r["language"],
            }
            for r in rows
            if not file or file in str(r["file_path"])
        ]
        found = _with_class(self.cache, found)
        return [r for r in found if not cls or r.get("class") == cls]

    def definition_kinds(
        self, coordinates: list[tuple[str, int, str]]
    ) -> dict[tuple[str, int, str], str]:
        """``(file, line, name) -> kind``：关系行的种类取自已索引定义（Codex #1802）。"""
        out: dict[tuple[str, int, str], str] = {}
        if not coordinates:
            return out
        try:
            conn = self.cache.get_conn()
            for file, line, name in coordinates:
                row = conn.execute(
                    "SELECT kind FROM ast_symbol_rows WHERE file_path = ? AND line = ? "
                    "AND name = ? LIMIT 1",
                    (file, line, name),
                ).fetchone()
                if row is not None and row[0]:
                    out[(file, line, name)] = str(row[0])
        except (sqlite3.Error, AttributeError):
            return {}
        return out

    def definition_count(self, name: str) -> int | None:
        """已索引的名为 ``name`` 的定义数；无法读取时返回 ``None``。"""
        try:
            row = (
                self.cache.get_conn()
                .execute(
                    "SELECT COUNT(*) FROM ast_symbol_rows WHERE name = ? AND kind IN "
                    "('function', 'method', 'class', 'enum', 'variable', 'constant')",
                    (name,),
                )
                .fetchone()
            )
        except (sqlite3.Error, AttributeError):
            return None
        return int(row[0]) if row else None

    # -- 关系 -------------------------------------------------------------
    def _nav(self) -> Any:
        if self._nav_facade is None:
            from ..mcp.tools.nav_facade import build_nav_facade

            self._nav_facade = build_nav_facade(self.project_root)
        return self._nav_facade

    async def _relation(
        self, action: str, name: str, file: str | None
    ) -> dict[str, Any]:
        # 经由公开的 ``nav`` facade 而非内部工具调用：payload 就是
        # ``nav action=callers`` 契约本身，并且与它共享 facade 按 generation
        # 键控的答案缓存 (RFC-0027 L6.1)。
        args: dict[str, Any] = {
            "action": action,
            "function_name": name,
            "include_bodies": False,
            "limit": RELATION_LIST_CAP,
        }
        if file:
            args["file_path"] = file
        result = await self._nav().execute(args)
        return result if isinstance(result, dict) else {"success": False}

    async def callers(self, name: str, file: str | None) -> dict[str, Any]:
        return (await self.callers_many([(name, file)]))[0]

    async def callers_many(
        self, pairs: list[tuple[str, str | None]]
    ) -> list[dict[str, Any]]:
        """一次批量的 ``nav action=callers``：共享认证读与调用图，逐输入答复不变。

        直接调用 callers 工具的 ``execute_batch``（与 nav 门面背后的同一工具、
        同一参数投影），每个输入的 payload 与单次调用逐字节相同。
        """
        if self._callers_tool is None:
            from ..mcp.tools.callers_tool import CodeGraphCallersTool

            self._callers_tool = CodeGraphCallersTool(self.project_root)
        requests = []
        for name, file in pairs:
            args: dict[str, Any] = {
                "function_name": name,
                "include_bodies": False,
                "limit": RELATION_LIST_CAP,
            }
            if file:
                args["file_path"] = file
            requests.append(args)
        return await self._callers_tool.execute_batch(requests)  # type: ignore[no-any-return]

    async def callees(self, name: str, file: str | None) -> dict[str, Any]:
        return await self._relation("callees", name, file)

    def generation(self) -> str | None:
        from ..cache.answer_cache_policy import current_generation

        return current_generation(self.project_root)


def _with_class(cache: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """返回 ``rows`` 的副本，并补齐求值器缺失的 ``class`` 字段。

    ``#name`` 行来自级联搜索，没有 class 列；按文件的函数行则有。每个不同的
    文件只读取一次；求值器返回的行可能是共享的缓存对象，因此复制而不是原地修改。
    """
    missing = {r.get("file") for r in rows if not r.get("class") and r.get("file")}
    getter = getattr(cache, "get_functions_by_file", None)
    owners: dict[tuple[Any, Any, Any], Any] = {}
    if missing and callable(getter):
        for file in missing:
            try:
                for fn in getter(file) or []:
                    owners[(file, fn.get("name"), fn.get("line"))] = fn.get("class")
            except Exception:  # noqa: BLE001 — 补全的只是展示用数据
                continue
    out: list[dict[str, Any]] = []
    for row in rows:
        cls = row.get("class") or owners.get(
            (row.get("file"), row.get("name"), row.get("line"))
        )
        out.append({**row, "class": cls})
    return out
