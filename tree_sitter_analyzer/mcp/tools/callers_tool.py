#!/usr/bin/env python3
"""
CodeGraph Callers MCP Tool

Dedicated tool for finding all functions that call a given function.
CodeGraph parity: equivalent to codegraph_callers.

Simpler and more discoverable than the monolithic codegraph_call_graph tool.
"""

import os
import sqlite3
from typing import Any

from ...module_scope_caller import module_caller_entry
from ...receiver_proof import has_unproven_receiver
from ...utils import setup_logger
from . import certification_timeouts
from ._response_builder import build_response
from .base_tool import BaseMCPTool
from .callers_absence import assess_completeness
from .callers_annotated import (
    alias_provenance,
    annotated_provenance,
    drop_bound_sites,
    graph_bound_targets,
    name_bound_targets,
)
from .callers_call_lines import call_edge_lines
from .callers_dispatch import narrow_to_target
from .callers_name_only import name_only_fields, name_only_sites, name_only_step
from .callers_reasons import EdgeEvidence, edge_completeness, final_reasons
from .codegraph_relation_tool import (
    _STALE_CACHE_WARNING,
    CodeGraphRelationToolMixin,
    _is_stale_resolution,
    classify_callee_resolution,
    label_graph_relations,
)
from .index_rebuild_signal import (
    is_index_rebuilding,
    rebuild_in_progress_next_step,
)
from .relation_freshness import (
    STALE_REASON,
    apply_source_evidence,
    not_in_index_hint,
    relation_files,
    relation_source_evidence,
)

logger = setup_logger(__name__)

#: How many unresolved sites the response carries. The total is reported beside
#: it, so a capped list is never mistaken for the whole set — the same
#: honest-truncation pattern the caller list itself uses.
_UNRESOLVED_SITES_CAP = 20

#: RFC-0038 caller-entry fields of an edge bound only through an annotation.
_PROVENANCE_FIELDS = ("resolution_kind", "receiver_type", "type_source", "confidence")

#: How many sites the next_step names inline. Small on purpose: the hint is there
#: to make the work bounded, not to duplicate the payload.
_UNRESOLVED_SITES_NAMED = 3


def _declaring_file_unresolved(
    cache: Any,
    func_name: str,
    file_path: str | None,
    limit: int | None = None,
) -> list[dict[str, Any]] | None:
    """Unresolved CALLS sites inside the files that declare ``func_name``.

    The RFC-0028 §1.2 scope guard: a computed dispatch site records its own
    source text as the callee, so no per-symbol lookup can see it, and the only
    place it can be counted from is the file it sits in.  A symbol this project
    does not declare contributes ``[]`` — there is no file scope to check, which
    is different from a scope that could not be read.

    ``file_path`` narrows the scope when the caller named one.  Without it, a
    symbol declared in several files inherits every sibling's unresolved calls:
    measured, `run` declared in a clean file and a noisy one answered `unknown`
    for a query that named the clean file, contradicting §1.2's guard that a
    symbol in a fully-resolved file answers ``complete``.

    ``None`` means the question could not be answered — including a failed read of
    the declaring files, which must never degrade to "nothing unresolved here".

    This reads the cache directly and is therefore answerable on every data
    source, not only the SQL one.  Gating it on ``data_source == "sql"`` returned
    ``None`` for a query that took the in-memory graph path, which the caller then
    reported as "its inbound edges could not be read" — a claim of ignorance where
    the answer was available, and measured to mislabel a genuinely absent symbol
    as an unreadable one.

    RFC-0028 §1.3: this returns the sites, not a count of them.  The count is
    ``len(...)`` at the call site, so the number the response reports and the
    sites it names come from one derivation and cannot drift apart.
    """
    if cache is None:
        return None
    declaring = _declaring_files(cache, func_name, file_path)
    if declaring is None:
        return None
    return _collect_sites(cache, declaring, "unresolved_call_sites_in_file", limit)


def _declaring_file_excluded(
    cache: Any,
    func_name: str,
    file_path: str | None,
    limit: int | None = None,
) -> list[dict[str, Any]] | None:
    """Sites in the declaring files that were ruled out, and on what grounds.

    The complement of :func:`_declaring_file_unresolved`, over the same scope.
    RFC-0028 §1.3: a caller told only "this file is not a census" cannot tell a
    file gated by one genuine dispatch site from one gated by three hundred
    builtin attribute calls. Reporting the exclusions makes that checkable, and
    the reasons are the raw material for widening the exclusion set with proofs
    rather than with a bound.
    """
    if cache is None:
        return None
    declaring = _declaring_files(cache, func_name, file_path)
    if declaring is None:
        return None
    return _collect_sites(cache, declaring, "excluded_call_sites_in_file", limit)


def _declaring_files(
    cache: Any,
    func_name: str,
    file_path: str | None,
) -> tuple[str, ...] | None:
    """The files declaring ``func_name``, narrowed to the one the caller named.

    ``None`` when the read fails: a failed read is not an empty scope.  Computed
    once and shared by the unresolved and excluded accessors, so the two lists a
    response reports side by side always describe the same files.
    """
    declaring = cache.symbol_declaring_files(func_name)
    if declaring is None:
        return None
    if file_path:
        normalized = file_path.replace("\\", "/")
        narrowed = tuple(
            path for path in declaring if path.replace("\\", "/") == normalized
        )
        declaring = narrowed or declaring
    return tuple(declaring)


def _collect_sites(
    cache: Any,
    declaring: tuple[str, ...],
    accessor: str,
    limit: int | None,
) -> list[dict[str, Any]] | None:
    """Gather one kind of site across ``declaring``, ordered and optionally capped.

    ``None`` from any file means the whole answer is unknown rather than partial:
    a readable sibling must not stand in for an unreadable one.
    """
    sites: list[dict[str, Any]] = []
    for path in declaring:
        found = getattr(cache, accessor)(path)
        if found is None:
            return None
        sites.extend(found)
    sites.sort(key=lambda site: (site["file"], site["line"]))
    return sites[:limit] if limit is not None else sites


def _unbound_receiver_call(edge: dict[str, Any]) -> bool:
    """边未绑定到任何文件，且接收者未被证明（#1669）：只是同名匹配。"""
    return not edge.get("callee_resolved_file") and has_unproven_receiver(
        str(edge.get("callee_full") or "")
    )


def _certification_ruled_out(project_root: str) -> bool:
    """Whether a certified read of the live index is certain to yield no owner.

    A certified snapshot is ``complete`` only when its private copy of the
    index carries the exact call-graph marker; a copy of an index whose marker
    is not exact always publishes ``CALL_GRAPH_INCOMPLETE`` and the read falls
    back to the uncertified cache.  dogfood round 7 measured that capture —
    copying the database and WAL, an in-memory ``backup`` and a projection
    check — at 1.5-3.5 s on every call, only to be discarded.

    The marker is read from the same database in one read-only transaction; the
    answer then reflects the index as of that read, exactly as if the capture
    had run at that instant.  An unreadable probe never rules certification out
    (the full capture still runs).
    """
    from ...cache.live_index_probe import probe_live_index

    probe = probe_live_index(project_root)
    return probe is not None and not probe.call_graph_exact


def _symbol_indexed(cache: Any, func_name: str) -> bool:
    """#1578：目标符号是否在索引中有定义行（读取失败按"未知"处理为 False）。"""
    if cache is None:
        return False
    declaring = cache.symbol_declaring_files(func_name.rpartition(".")[2])
    return bool(declaring)


def _describe_sites(sites: list[dict[str, Any]] | None) -> str:
    """Name the first few unresolved sites so the hint is actionable.

    "3 unresolved calls sit in a file that declares X" leaves the caller to
    re-read the file to find them.  Naming the sites, their lines and their
    mechanisms makes the remaining work bounded — which is why the evidence is
    carried at all (RFC-0028 §1.3).
    """
    if not sites:
        return "none"
    named = sites[:_UNRESOLVED_SITES_NAMED]
    parts = [
        f"{site['file']}:{site['line']} ({site['mechanism']} `{site['callee']}`)"
        for site in named
    ]
    remaining = len(sites) - len(named)
    if remaining > 0:
        parts.append(f"and {remaining} more")
    return "; ".join(parts)


class CodeGraphCallersTool(CodeGraphRelationToolMixin, BaseMCPTool):
    """MCP Tool for finding callers of a function (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._init_relation_state()
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._reset_relation_state()

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_callers",
            "description": (
                "PRIMARY for 'who calls FUNCTION X' — try this FIRST instead "
                "of grepping for the function name. "
                "Reverse call lookup over the indexed call graph (CodeGraph parity). "
                "Returns caller function name, file, line, and language."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "function_name": {
                    "type": "string",
                    "description": "Target function name to find callers for",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded functions",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of callers to list in the response "
                        "(default 50). Raise for more, or qualify with "
                        "ClassName.method to narrow high-fan-in symbols."
                    ),
                    "default": 50,
                    "minimum": 1,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "description": "Output format: JSON",
                    "default": "json",
                },
                "include_activation": {
                    "type": "boolean",
                    "description": (
                        "When true, embed per-caller git modification "
                        "frequency under the 'activation' key. Off by "
                        "default to preserve token budget."
                    ),
                    "default": False,
                },
                "include_bodies": {
                    "type": "boolean",
                    "description": (
                        "When false, omit caller source bodies and return only "
                        "call-graph coordinates and metadata."
                    ),
                    "default": True,
                },
            },
            "required": ["function_name"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "function_name" not in arguments:
            raise ValueError("function_name is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        if is_index_rebuilding(self.project_root):
            return await self._execute_bound(arguments, None, None)
        if self.project_root and not _certification_ruled_out(self.project_root):
            # #1710：同一索引与源码状态下捕获已在期限内完成不了时，直接走与捕获
            # 超时相同的未认证回退，不再每次白付约 10 s。
            if not certification_timeouts.should_skip(self.project_root):
                from ...index_snapshot import (
                    _certified_index_read_reason,
                    certified_index_read,
                )

                try:
                    with certified_index_read(self.project_root) as owner:
                        certification_timeouts.record(
                            self.project_root,
                            None
                            if owner is not None
                            else _certified_index_read_reason(),
                        )
                        if owner is not None:
                            return await self._execute_bound(
                                arguments, owner.query_cache(), owner.read_source
                            )
                except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError):
                    pass
        return await self._execute_bound(arguments, None, None)

    async def _execute_bound(
        self, arguments: dict[str, Any], bound_cache: Any, source_reader: Any
    ) -> dict[str, Any]:
        func_name = arguments["function_name"]
        file_path = arguments.get("file_path")
        output_format = arguments.get("output_format", "json")
        include_activation = bool(arguments.get("include_activation", False))
        include_bodies = bool(arguments.get("include_bodies", True))
        listed_cap = int(arguments.get("limit", 50))

        if is_index_rebuilding(self.project_root):
            rebuild_next_step = rebuild_in_progress_next_step()
            result = build_response(
                verdict="WARN",
                data_source="cache_rebuilding",
                function=func_name,
                index_rebuilding=True,
                next_step=rebuild_next_step,
                agent_summary={
                    "summary_line": f"callers: {func_name!r} unavailable during full rebuild",
                    "verdict": "WARN",
                    "next_step": rebuild_next_step,
                },
            )
            from ..utils.format_helper import apply_output_format_to_response

            return apply_output_format_to_response(result, output_format)

        # Detect "ClassName.method_name" qualified lookup.  The SQL fast-path
        # stores bare callee names and can't filter by receiver class, so we
        # fall through to the in-memory CallGraph which does handle qualified
        # names via the FunctionRef.receiver field.
        is_qualified = (
            "." in func_name
            and ":" not in func_name
            and "/" not in func_name
            and "\\" not in func_name
            and func_name.rpartition(".")[0]  # non-empty class part
        )

        unattributed_call_sites = 0
        name_only_inbound = 0
        possible_callers: list[dict[str, Any]] = []
        # RFC-0038：本次查询涉及的定义；经注解绑定到它们的边对本查询已解析。
        bound_targets: frozenset[tuple[str, int]] = frozenset()
        cache = bound_cache if bound_cache is not None else self._try_get_cache()
        refusal = self._parse_fallback_refusal(cache, "callers", function=func_name)
        if refusal is not None:
            from ..utils.format_helper import apply_output_format_to_response

            return apply_output_format_to_response(refusal, output_format)
        call_graph_built = (
            self._cache_call_graph_built(cache) if cache is not None else False
        )
        call_graph_indexed = (
            cache is not None and call_graph_built and cache.has_call_edges()
        )
        if call_graph_indexed and not is_qualified:
            callers, unattributed_call_sites = self._sql_native_callers(
                cache, func_name, file_path, include_activation
            )
            bound_targets = name_bound_targets(cache, func_name, file_path)
            data_source = "sql"
            has_any_call_edges = True  # SQL path only runs when edges exist
        else:
            graph: Any
            if bound_cache is not None:
                from ...call_graph import CachedCallGraph

                # #1675：边解析结果落盘，冷进程的首个 callers 不再重新解析。
                graph = CachedCallGraph(
                    self.project_root or ".",
                    cache=bound_cache,
                    fallback=False,
                    persist=True,
                )
                data_source = "cache"
            else:
                graph = self._get_call_graph()
                data_source = self._data_source
            callers = graph.callers_of(func_name, file_path)
            bound_targets = graph_bound_targets(graph, func_name, file_path)
            # #1578：仅同名匹配、无法绑定到目标的入边——它们存在时不能宣称 complete。
            possible_callers = graph.possible_callers_of(func_name, file_path)
            name_only_inbound = len(possible_callers)
            callers = label_graph_relations(
                graph, func_name, file_path, callers, inbound=True
            )
            # #981 defense-in-depth: the built marker can be a false-negative
            # (e.g. cleared while the index actually holds 125K call edges).
            # Trust an actual edge probe in addition to the marker so a missing
            # symbol in a populated index is never mislabelled "index empty".
            has_any_call_edges = call_graph_built or (
                cache is not None and cache.has_call_edges()
            )

        # A graph that holds no CALLS edges at all cannot support an absence
        # claim: a zero read from it is indistinguishable from a graph that was
        # never populated.  This is the counterpart of `has_any_call_edges`
        # above, which trusts the marker; here the marker may be set over an
        # empty table, so the edge probe itself is the evidence.
        empty_evidence_base = cache is not None and not cache.has_call_edges()
        # dogfood 2026-10-14：答案必须声明它所依据的索引是否已落后于源码。
        evidence, stale_files = relation_source_evidence(
            cache,
            self.project_root,
            relation_files(cache, func_name, callers),
            absence=not callers,
        )

        warnings_list: list[str] = []
        if _is_stale_resolution(callers, cache):
            warnings_list.append(_STALE_CACHE_WARNING)

        # Honest-truncation cap: record total before slicing so agents know
        # what was omitted (same pattern as dead_code_tool / hyphae_select_tool).
        total_callers = len(callers)
        truncated = total_callers > listed_cap
        callers = callers[:listed_cap]

        # 默认内联有上限的调用方源码；调用者可只请求坐标和元数据。
        next_step = None
        if include_bodies:
            body_reader = (
                source_reader if call_graph_indexed and not is_qualified else None
            )
            next_step = self._inline_caller_bodies(cache, callers, body_reader)

        # RFC-0028 §1.1: declare the epistemic status of this list.  It is
        # assembled from resolved CALLS edges, so an unresolved inbound edge
        # makes it a lower bound rather than a census.  An unreadable count is
        # unknown, never complete — a failed read is not evidence of absence.
        # #1559：限定名 `Class.method` 的未解析入边按裸方法名计数——
        # `target.publish` 这类接收者未知的调用可能指向任何同名方法。
        count_name = func_name.rpartition(".")[2] if is_qualified else func_name
        unresolved_inbound = (
            cache.count_unresolved_callers(
                count_name,
                file_path,
                **({"bound_targets": bound_targets} if bound_targets else {}),
            )
            if cache is not None
            else None
        )
        # RFC-0028 §1.2 scope guard.  A computed dispatch site is recorded under
        # its source text (`HANDLERS[name]`, `getattr(self, name)`), so it names
        # no symbol and the per-symbol count above cannot see it.  An unresolved
        # call inside a file that declares this symbol could target it, so the
        # claim is gated on the declaring files as well.  A symbol in a
        # fully-resolved file still answers complete.
        #
        # RFC-0028 §1.3: the sites are carried into the response, not just their
        # number.  A caller told only "3 unresolved calls sit in a file that
        # declares this symbol" has to re-read the file to act; a caller given the
        # sites and their mechanisms can go straight to them.
        declaring_sites = _declaring_file_unresolved(cache, func_name, file_path)
        # The complement of the sites above: what was ruled out, and on what
        # grounds. Without it, "this file is not a census" cannot be checked
        # against "this file is a browser asset full of builtin attribute calls".
        excluded_sites = _declaring_file_excluded(cache, func_name, file_path)
        declaring_sites = drop_bound_sites(declaring_sites, bound_targets)
        # #1596 / #1643：非调用引用门（#1593）会扫描别名与回调，守卫只需计入
        # 可能点名目标的调用点（同名或计算式分发）。该门对有无调用方都运行，
        # 因此收窄也不再限于 0 调用方。
        if self.project_root:
            declaring_sites, excluded_sites = narrow_to_target(
                declaring_sites, excluded_sites, count_name
            )
        unresolved_in_declaring_files = (
            None if declaring_sites is None else len(declaring_sites)
        )
        # #1672：同名入边的证据——调用点取自调用边的行号，按调用方范围归属。
        name_only_list = name_only_sites(
            possible_callers,
            call_edge_lines(cache, count_name)
            if possible_callers and cache is not None
            else None,
        )

        # #1632：调用边层的降级（#638 模块级调用点、空证据基等）同时给出原因码。
        completeness, edge_reasons = edge_completeness(
            EdgeEvidence(
                total_callers=total_callers,
                unresolved_inbound=unresolved_inbound,
                unresolved_in_declaring_files=unresolved_in_declaring_files,
                name_only_inbound=name_only_inbound,
                unattributed_call_sites=unattributed_call_sites,
                empty_evidence_base=empty_evidence_base,
            )
        )
        # #1593 / #1594：调用边给出的 complete 还须通过新鲜度与非调用引用两道门。
        absence = assess_completeness(
            cache,
            self.project_root,
            func_name,
            file_path,
            completeness,
            total_callers,
            evidence,
        )
        completeness = absence.completeness
        reasons = final_reasons(
            completeness, absence.reason, edge_reasons, absence.also
        )
        if absence.stale_files:
            # #1672：引用扫描在已与索引不一致的文件里命中——源码与索引不一致，
            # 不是非调用引用；与 0 调用方路径给出同一诊断与刷新步骤。
            evidence = {**evidence, "freshness": "stale", "reason": STALE_REASON}
            stale_files = list(absence.stale_files)

        result = build_response(
            verdict="INFO" if callers or total_callers else "NOT_FOUND",
            warnings=warnings_list or None,
            data_source=data_source,
            function=func_name,
            caller_count=total_callers,
            callers_listed=len(callers),
            listed_cap=listed_cap,
            truncated=truncated,
            completeness=completeness,
            completeness_reason=reasons[0] if reasons else None,
            completeness_reasons=reasons,
            **absence.fields,
            unresolved_inbound=unresolved_inbound,
            unresolved_in_declaring_files=unresolved_in_declaring_files,
            **name_only_fields(name_only_inbound, name_only_list),
            callers=callers,
        )
        if declaring_sites is not None:
            # The evidence behind `unresolved_in_declaring_files`: which sites,
            # and what kind. Capped so the field stays bounded, with the total
            # kept beside it so a capped list is never mistaken for the whole set.
            result["unresolved_sites"] = declaring_sites[:_UNRESOLVED_SITES_CAP]
            result["unresolved_sites_total"] = len(declaring_sites)
            result["unresolved_sites_truncated"] = (
                len(declaring_sites) > _UNRESOLVED_SITES_CAP
            )
        else:
            result["unresolved_sites"] = None
            result["unresolved_sites_total"] = None
        if excluded_sites is not None:
            # The negative space, auditable. `excluded_by_reason` is the summary a
            # caller reads to decide whether "not a census" is alarming; the list
            # is the detail behind it.
            result["excluded_sites"] = excluded_sites[:_UNRESOLVED_SITES_CAP]
            result["excluded_sites_total"] = len(excluded_sites)
            by_reason: dict[str, int] = {}
            for site in excluded_sites:
                reason = str(site.get("reason_code") or "unspecified")
                by_reason[reason] = by_reason.get(reason, 0) + 1
            result["excluded_by_reason"] = by_reason
        else:
            result["excluded_sites"] = None
            result["excluded_sites_total"] = None
            result["excluded_by_reason"] = None
        if unattributed_call_sites:
            # #638: module-level call sites have no enclosing function — they
            # are counted here instead of being emitted as un-navigable ghost
            # rows ({name: '', line: 0}).
            result["unattributed_call_sites"] = unattributed_call_sites
        if name_only_list and result.get("verdict") != "NOT_FOUND":
            # #1672：已列出调用方时同样点名同名入边，而不是通用的“Review callers”。
            name_step = name_only_step(func_name, name_only_list)
            next_step = f"{name_step} {next_step}" if next_step else name_step
        if truncated:
            trunc_note = (
                f"showing {len(callers)} of {total_callers} callers — raise limit, "
                "or qualify with ClassName.method to narrow "
                "(dynamic-dispatch names like 'execute' have huge fan-in)"
            )
            # Combine truncation note with any body-inlining deterrent.
            next_step = f"{trunc_note}. {next_step}" if next_step else trunc_note
        # #548 / #981: split the NOT_FOUND hint by whether the index actually
        # holds call edges.
        #   - truly empty (no edges)  → --full-index hint (build the graph).
        #   - populated (has edges)   → the symbol is just missing; port the
        #     navigate phrasing (check spelling / browse) instead of the
        #     misleading "index empty" message.
        if result.get("verdict") == "NOT_FOUND":
            if not has_any_call_edges:
                index_hint = (
                    "Call-graph index is empty or has not been built yet. "
                    "Build it with MCP `index action=full` (CLI: "
                    "`tree-sitter-analyzer --full-index`), then retry."
                )
            elif completeness != "complete":
                # "Not in the index" may only describe a genuine absence.  Name
                # the reason the list is not a census instead (RFC-0028 §1.1,
                # §1.2).  A successfully-read 0 is not a failure to read, so the
                # branches test `is None` rather than truthiness.
                if absence.hint:
                    index_hint = absence.hint
                elif unresolved_inbound:
                    index_hint = (
                        f"No resolved caller for {func_name!r}, and "
                        f"{unresolved_inbound} call edge(s) into it are "
                        "unresolved, so it may still be called. Read those call "
                        "sites directly rather than treating this as absence."
                    )
                    if name_only_list:
                        # #1672：同一调用点常常既未解析又按同名匹配——点名它们。
                        index_hint += " " + name_only_step(func_name, name_only_list)
                elif unattributed_call_sites:
                    index_hint = (
                        f"{unattributed_call_sites} module-level call site(s) "
                        f"reach {func_name!r}. They have no enclosing function "
                        "and are counted rather than listed, so this is not an "
                        "empty result; read them directly."
                    )
                elif name_only_list:
                    index_hint = name_only_step(func_name, name_only_list)
                elif unresolved_in_declaring_files:
                    index_hint = (
                        f"{unresolved_in_declaring_files} unresolved call(s) sit "
                        f"in a file that declares {func_name!r} and could target "
                        f"it: {_describe_sites(declaring_sites)}. Read those "
                        "sites directly rather than treating this as absence."
                    )
                elif empty_evidence_base:
                    # #705: an index that was built over a project with no calls
                    # must not be told to --full-index again.  The user already
                    # indexed; the graph is simply empty.  What must not happen
                    # is a confident absence, so the hint disclaims rather than
                    # instructs.
                    index_hint = (
                        f"No resolved caller for {func_name!r}, and the call graph "
                        "holds no call edges at all. An empty graph cannot "
                        "distinguish 'nothing calls it' from 'never populated', "
                        "so do not treat this as absence."
                    )
                else:
                    index_hint = (
                        f"No resolved caller for {func_name!r} and its inbound "
                        "edges could not be read. Do not treat this as absence."
                    )
            else:
                index_hint = not_in_index_hint(
                    func_name, evidence, indexed=_symbol_indexed(cache, func_name)
                )
            next_step = f"{index_hint} {next_step}" if next_step else index_hint
        if next_step:
            result["next_step"] = next_step

        # #546 seam 3 / #577 leftover: uniform agent_summary across all nav actions.
        verdict = result.get("verdict", "NOT_FOUND")
        if verdict == "NOT_FOUND":
            # A zero is a fact only when every inbound edge resolved *and* every
            # caller could be listed; otherwise the summary must not restate the
            # absence the verdict already implies (RFC-0028 §1.1, §1.2).
            if completeness == "complete":
                as_summary_line = f"callers: {func_name!r} has 0 caller(s)"
            elif unattributed_call_sites:
                as_summary_line = (
                    f"callers: {func_name!r} has 0 listed caller(s) but "
                    f"{unattributed_call_sites} module-level call site(s)"
                )
            else:
                as_summary_line = (
                    f"callers: {func_name!r} has 0 resolved caller(s); "
                    "this is not evidence of absence"
                )
            as_next_step = result.get("next_step") or (
                f"No callers found for '{func_name}'. "
                "Check spelling, or build the call graph with MCP "
                "`index action=full` (CLI: --full-index)."
            )
        else:
            as_summary_line = f"callers: {func_name!r} has {total_callers} caller(s)"
            as_next_step = result.get("next_step") or (
                "Review callers above, run tests for affected paths, "
                "or use nav action=caller_tree for the full blast-radius."
            )
        result["agent_summary"] = {
            "summary_line": as_summary_line,
            "verdict": verdict,
            "next_step": as_next_step,
        }
        apply_source_evidence(result, evidence, stale_files)

        # RFC-0027 L6.2: this route's cold/warm cliff (24.8 s -> 16 ms in the
        # L5 baseline) is the largest in the product, so a caller choosing
        # between nav actions must see which tier it is about to pay for.
        from ...cache.query_cost import cost_fields, query_cost
        from ..utils.format_helper import apply_output_format_to_response

        result.update(
            cost_fields(query_cost("nav", "callers", self.project_root, arguments))
        )

        return apply_output_format_to_response(result, output_format)

    def _inline_caller_bodies(
        self,
        cache: Any,
        callers: list[dict[str, Any]],
        source_reader: Any = None,
    ) -> str | None:
        """P2: attach a body to the top-N callers (in place). Returns deterrent.

        Best-effort: any failure leaves the bare-coordinate list intact and
        returns ``None`` (no deterrent).
        """
        if not callers or not self.project_root:
            return None
        try:
            from . import symbol_body_inline as sbi

            # cache may be None (graph-parse path with no index yet); the
            # helper only needs it for the end_line fallback, and records on
            # the graph path already carry end_line, so it degrades cleanly.
            enriched = sbi.inline_neighbor_bodies(
                self.project_root, cache, callers, source_reader=source_reader
            )
            if not any("body" in c for c in enriched):
                return None
            callers[:] = enriched
            return sbi.NEIGHBORS_DETERRENT
        except Exception as exc:  # best-effort enrichment
            logger.debug(f"Caller body inlining failed: {exc}")
            return None

    def _sql_native_callers(
        self,
        cache: Any,
        func_name: str,
        file_path: str | None,
        include_activation: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """Use SQL-native callers query — O(k) instead of full graph build.

        Returns ``(callers, unattributed_call_sites)``.  Edges without an
        enclosing function (module-level call sites store
        ``caller_name='' / caller_line=0``) are listed under the ``<module>``
        pseudo-caller at their call line (#1622); only a site without a call
        line is counted instead, never emitted as a ghost row (#638).

        When ``include_activation`` is True, each entry gets an
        ``activation`` sub-dict carrying ``mod_count_30d`` and
        ``last_modified_at`` read from ``ast_symbol_activation``.
        """
        raw = cache.query_callers(func_name, callee_file=file_path)
        results: list[dict[str, Any]] = []
        unattributed = 0
        seen: set[str] = set()
        annotated_entries: dict[str, dict[str, Any]] = {}
        activation_map: dict[tuple[str, int], dict[str, Any]] = {}
        if include_activation:
            activation_map = self._fetch_activation_map(cache)
        for edge in raw:
            # #1622：模块作用域调用点列为 ``<module>`` 伪调用方；缺坐标的才计数。
            base = (
                {
                    "name": edge["caller_name"],
                    "file": edge["caller_file"],
                    "line": edge["caller_line"],
                }
                if edge.get("caller_name")
                else module_caller_entry(edge)
            )
            if base is None:
                unattributed += 1
                continue
            if file_path and _unbound_receiver_call(edge):
                # #1669：限定到定义文件的查询只列出绑定到该文件的调用；同文件里
                # 接收者未知的 `self._entries.append()` 仅按名字匹配，留给未解析计数。
                continue
            key = f"{base['file']}:{base['name']}:{base['line']}"
            provenance = annotated_provenance(edge.get("receiver_binding"))
            if key in seen:
                if not provenance and key in annotated_entries:
                    # 同一调用方另有普通边：不再标注为仅经注解绑定。
                    for field_name in _PROVENANCE_FIELDS:
                        annotated_entries[key].pop(field_name, None)
                    del annotated_entries[key]
                continue
            seen.add(key)
            callee_resolved = edge.get("callee_resolved_file", "")
            caller_file_val = edge["caller_file"]
            resolution, resolved_file = classify_callee_resolution(
                func_name, callee_resolved, caller_file_val
            )
            entry: dict[str, Any] = {
                **base,
                "language": "",
                "callee_resolution": resolution,
                "callee_resolved_file": resolved_file,
                **provenance,
                # #1670：经改名导入（`from m import f as g; g()`）解析的调用点。
                **alias_provenance(edge.get("import_alias")),
            }
            if provenance:
                annotated_entries[key] = entry
            row_data = cache.lookup(
                os.path.join(cache.project_root, edge["caller_file"])
            )
            if row_data:
                entry["language"] = row_data.get("language", "")
            if include_activation:
                entry["activation"] = activation_map.get(
                    (edge["caller_file"], edge["caller_line"]),
                    {"mod_count_30d": 0, "last_modified_at": None},
                )
            results.append(entry)
        return results, unattributed
