"""nav callers 的“绝对否定”诚实性：0 个调用方何时才能说 ``complete``。

RFC-0028 §1.1 的单向不变式要求：答案不得把无法证明的不存在当作确定的不存在。
调用图只记录调用边，以下两类缺口会让 ``0 callers, complete`` 成为危险的假答案：

* #1593：方法以非调用方式被使用——回调传递（``callback=obj.m``）、属性读取
  （``obj.prop``）、字符串反射（``getattr(obj, "m")``）。索引不存储属性访问或
  名字引用，因此这里在查询时对同语言的已索引源码做一次有预算的扫描；超出预算
  或读取失败即为 ``unknown``，从不退化为 ``complete``。``@property`` 等访问器
  的读取永远不是调用边，因此它们从不凭调用边宣称 ``complete``。
* #1594：答案所依据的索引已落后于源码（RFC-0030 ``source_evidence``）。范围内
  证据为 ``stale`` 或无法复核时，``complete`` 降级，并指向既有的刷新 next_step。

扫描只会让答案更保守：注释与普通字符串被剔除，恰为该名字的字符串字面量保留
（反射）；其余任何同名出现都计为可能的引用。
"""

from __future__ import annotations

import bisect
import os
import re
import sqlite3
import time
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field, replace
from typing import Any

from ...discovery_budget import DISCOVERY_SECONDS_PER_ENTRY
from . import reference_vocab
from .absence_text_kinds import reference_text, text_language
from .absence_text_refs import CONFIG_LANGUAGE, string_code
from .callers_alias_refs import alias_reference_check
from .callers_call_lines import call_edge_lines
from .callers_decorators import (
    DECORATED_REASON,
    UNREADABLE,
    registered_hint,
    registering_decorator,
)
from .callers_excluded import EXCLUDED_REASON, excluded_definition, excluded_hint
from .callers_import_bindings import mask_import_bindings
from .callers_outcomes import Checked, CheckOutcome, NotChecked, Scope, checked
from .callers_reference_freshness import stale_reference_files
from .callers_target import NOT_DEFINED_REASON, not_defined_hint, resolve_target
from .callers_target import UNCHECKED_REASON as TARGET_UNCHECKED_REASON
from .evidence_file_cache import FILE_CACHE, StatKey
from .reference_vocab import ReferenceVocabulary
from .relation_freshness import SCOPED_REASON, STALE_REASON, UNKNOWN_REASON
from .unindexed_sources import FILES_CAP as UNINDEXED_FILES_CAP
from .unindexed_sources import UNCHECKED_REASON as UNINDEXED_UNCHECKED_REASON
from .unindexed_sources import (
    UNINDEXED_REASON,
    project_files,
    unchecked_hint,
    unindexed_hint,
)

#: 找到非调用引用（属性访问、裸名、字符串名）。
NON_CALL_REASON = "NON_CALL_REFERENCES"
#: 非调用引用无法在预算内复核（读取失败或超时）。
UNCHECKED_REASON = "NON_CALL_REFERENCES_UNCHECKED"
#: 目标是 @property 等访问器：读取是属性访问，不是调用边。
ACCESSOR_REASON = "ACCESSOR_NOT_CALL_EDGES"
#: RFC-0040：声明读不到，无法排除访问器（读取不是调用边）。
ACCESSOR_UNCHECKED_REASON = "ACCESSOR_UNCHECKED"

#: 响应中点名的引用位置上限；总数始终与列表并列给出。
_SITES_CAP = 5
#: hint 中内联点名的位置数。
_SITES_NAMED = 3
#: 同语言源码扫描的基础期限；超出即为 unknown，不以部分结果冒充普查。
#: #1609：固定 2 s 在负载下约 3% 的答案随机降级，因此再按文件数线性放宽。
_SCAN_DEADLINE_SECONDS = 2.0
#: 并行读取的线程数。
_READ_WORKERS = 8
#: 每个线程分到的块数（块越少调度越省，块越多期限检查越细）。
_CHUNKS_PER_WORKER = 4

_PY_LANGUAGES = frozenset({"python"})
_C_LANGUAGES = frozenset(
    {
        "c",
        "cpp",
        "csharp",
        "go",
        "java",
        "javascript",
        "kotlin",
        "scala",
        "swift",
        "typescript",
        "tsx",
    }
)
#: 注释或字符串。左起最先匹配者胜出，因此字符串中的 ``#`` 不会被当作注释；
#: 以引号开头的是字符串，其余（``#`` / ``/``）是注释。
#: #1691：每个分支都以字面字符开头（不包进分组），``re`` 因而能按首字符集跳过
#: 其余位置；串体与块注释写成展开循环（unrolled loop）。匹配的位置与长度与
#: 原写法 ``(#…)|("""[\s\S]*?"""|…|"(?:\\.|[^"\\\n])*"|…)`` 完全相同，实测约快 4 倍。
_PY_LEXEME = re.compile(
    r"#[^\n]*"
    r"|\"\"\"[^\"]*(?:\"(?!\"\")[^\"]*)*\"\"\"|'''[^']*(?:'(?!'')[^']*)*'''"
    r"|\"[^\"\\\n]*(?:\\.[^\"\\\n]*)*\"|'[^'\\\n]*(?:\\.[^'\\\n]*)*'"
)
_C_LEXEME = re.compile(
    r"//[^\n]*|/\*[^*]*\*+(?:[^/*][^*]*\*+)*/"
    r"|\"[^\"\\\n]*(?:\\.[^\"\\\n]*)*\"|'[^'\\\n]*(?:\\.[^'\\\n]*)*'"
)
_QUOTES = "\"'"
_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
#: 名字之后的前两个非空白字符（区分调用 ``(``、赋值 ``=`` 与比较 ``==``）。
_FOLLOWING = re.compile(r"[ \t]*(\S{0,2})")
#: Python 访问器装饰器：@property、@x.setter、@functools.cached_property 等。
_ACCESSOR_DECORATOR = re.compile(
    r"^@\s*(?:[\w.]+\.)?(?:\w*property|setter|getter|deleter)\b"
)


@dataclass(frozen=True)
class AbsenceVerdict:
    """completeness 复核结果：最终取值、原因、提示与附加响应字段。"""

    completeness: str
    reason: str | None = None
    hint: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    #: 主因之后仍成立的原因（#1672：MISMATCH 之后，未变文件里的非调用引用）。
    also: tuple[str, ...] = ()
    #: 引用扫描发现已与索引不一致的文件（#1672）；非空时答案的证据为 stale。
    stale_files: tuple[str, ...] = ()
    #: RFC-0040：本次运行过（或未能运行）的复核门 ``(检查名, 结果)``，按运行顺序。
    #: ``complete`` 由 ``callers_checks.prove`` 依据它们构成，而不是依据 ``completeness``。
    checks: tuple[tuple[str, CheckOutcome], ...] = ()


def assess_completeness(
    cache: Any,
    project_root: str | None,
    func_name: str,
    file_path: str | None,
    completeness: str,
    total_callers: int,
    evidence: dict[str, Any],
) -> AbsenceVerdict:
    """在调用边已给出 ``complete`` 时，复核新鲜度与非调用引用两道门。"""
    if completeness != "complete":
        return AbsenceVerdict(completeness)
    scope: Scope = (func_name, file_path)
    downgraded = "incomplete" if total_callers else "unknown"
    freshness_reason = _freshness_gap(evidence)
    freshness = _freshness_outcome(scope, evidence, freshness_reason)
    if freshness_reason is not None:
        return AbsenceVerdict(
            downgraded,
            freshness_reason,
            _freshness_hint(func_name, evidence),
            checks=(("freshness", freshness),),
        )
    if not project_root:
        # RFC-0040：没有项目根就读不到源码，其余复核门都无法运行——不是 complete。
        return AbsenceVerdict(
            downgraded,
            TARGET_UNCHECKED_REASON,
            _no_root_hint(func_name),
            checks=(("freshness", freshness),),
        )
    # #1643：调用方列表同样须通过这些门才是普查——别名、回调、登记型装饰器、
    # 未入索引的新文件都可能是列表之外的调用方。有调用方时降级为 incomplete。
    verdict = _assess_absence(
        cache, project_root, func_name, file_path, with_callers=bool(total_callers)
    )
    verdict = replace(verdict, checks=(("freshness", freshness), *verdict.checks))
    if total_callers and verdict.completeness != "complete":
        return replace(verdict, completeness=downgraded)
    return verdict


def _freshness_gap(evidence: dict[str, Any]) -> str | None:
    """范围内证据不能支撑普查时返回其原因；SCOPED 表示范围内已复核一致。"""
    freshness = evidence.get("freshness")
    reason = evidence.get("reason")
    if freshness == "stale" or (freshness != "fresh" and reason != SCOPED_REASON):
        return str(reason or "SOURCE_SCOPE_UNKNOWN")
    return None


def _freshness_outcome(
    scope: Scope, evidence: dict[str, Any], gap: str | None
) -> CheckOutcome:
    """新鲜度门：stale 是复核后发现的问题；无法复核则是未能运行。"""
    if gap is None:
        return checked(scope)
    if evidence.get("freshness") == "stale":
        return checked(scope, gap)
    return NotChecked(gap)


def _freshness_hint(func_name: str, evidence: dict[str, Any]) -> str:
    if evidence.get("freshness") == "stale":
        state = "the index is stale for this answer"
    else:
        state = "the source could not be revalidated against the index"
    return (
        f"No resolved caller for {func_name!r}, but {state}, so this is not "
        "evidence of absence."
    )


def _no_root_hint(func_name: str) -> str:
    return (
        f"No resolved caller for {func_name!r}, and no project root is set, so "
        "its definition and non-call references could not be checked; this is "
        "not evidence of absence."
    )


def _budget_hint(func_name: str) -> str:
    return (
        f"No resolved caller for {func_name!r}, and its non-call references "
        "(attribute access, bare name, or string name) could not be checked "
        "within budget, so this is not evidence of absence."
    )


def _assess_absence(
    cache: Any,
    project_root: str,
    func_name: str,
    file_path: str | None,
    *,
    with_callers: bool = False,
) -> AbsenceVerdict:
    """目标已定义、无新文件、访问器与非调用引用都不存在时才保留 complete。

    ``with_callers``（#1643）：已有调用方时，未改名的导入行只是绑定，不计为引用。
    0 调用方时导入行仍计入——``__init__`` 中的再导出可能是仓库外调用的公开 API，
    “0 个调用方、complete”会被当作可删除的死代码。

    RFC-0040：每道门把结果记入 ``checks``，门的顺序与 ``callers_checks`` 的登记表
    一致；首个未通过（或未能运行）的门决定原因。
    """
    scope: Scope = (func_name, file_path)
    checks: list[tuple[str, CheckOutcome]] = []
    fields: dict[str, Any] = {}

    def verdict(
        completeness: str, reason: str | None, hint: str | None
    ) -> AbsenceVerdict:
        return AbsenceVerdict(completeness, reason, hint, fields, checks=tuple(checks))

    # #1606：精确（限定）目标必须解析到已索引定义，否则 0 不是不存在的证据。
    target = resolve_target(cache, project_root, func_name, file_path)
    fields.update(
        {"target_defined": target.defined, "close_matches": list(target.close_matches)}
    )
    if not target.defined:
        if target.defined is False:
            # #1635：定义在被索引排除的文件里时，刷新无济于事，须点名文件与规则。
            excluded = excluded_definition(cache, project_root, func_name, file_path)
            if excluded is not None:
                fields["excluded_definition"] = excluded.to_dict()
                checks.append(("target_defined", checked(scope, EXCLUDED_REASON)))
                return verdict(
                    "unknown", EXCLUDED_REASON, excluded_hint(func_name, excluded)
                )
            checks.append(("target_defined", checked(scope, NOT_DEFINED_REASON)))
            reason = NOT_DEFINED_REASON
        else:
            checks.append(("target_defined", NotChecked(TARGET_UNCHECKED_REASON)))
            reason = TARGET_UNCHECKED_REASON
        return verdict("unknown", reason, not_defined_hint(func_name, target))
    checks.append(("target_defined", checked(scope)))
    bare = func_name.rpartition(".")[2]
    owner = func_name.rpartition(".")[0]
    declarations = _declarations(cache, bare, owner, file_path)
    if not declarations:
        # 声明行读不到（或一行也没有）：没有可扫描的语言与文件，其后各门都无从运行。
        fields["non_call_references"] = None
        fields["non_call_reference_sites"] = None
        checks.append(("unindexed_sources", NotChecked(UNCHECKED_REASON)))
        return verdict("unknown", UNCHECKED_REASON, _budget_hint(func_name))
    new_files_verdict, config_files, unindexed = _new_files_gap(
        cache, project_root, scope, declarations, fields
    )
    checks.append(("unindexed_sources", unindexed))
    if new_files_verdict is not None:
        return replace(new_files_verdict, checks=tuple(checks))
    scan = _reference_scan(
        cache,
        project_root,
        bare,
        declarations,
        config_files,
        mask_imports=with_callers,
    )
    sites = None if scan is None else scan[0]
    fields["non_call_references"] = None if sites is None else len(sites)
    fields["non_call_reference_sites"] = None if sites is None else sites[:_SITES_CAP]
    if scan is None or sites is None:
        checks.append(("reference_freshness", NotChecked(UNCHECKED_REASON)))
        return verdict("unknown", UNCHECKED_REASON, _budget_hint(func_name))
    accessor = _is_accessor(project_root, declarations, bare)
    stale, freshness = _stale_verdict(
        cache, project_root, scope, scan, accessor is True, fields
    )
    checks.append(("reference_freshness", freshness))
    if stale is not None:
        return replace(stale, checks=tuple(checks))
    if accessor is None:
        checks.append(("accessor", NotChecked(ACCESSOR_UNCHECKED_REASON)))
        hint = (
            f"No resolved caller for {func_name!r}, and its declaration could not "
            "be read to rule out a property/accessor (whose reads are not call "
            "edges), so this is not evidence of absence."
        )
        return verdict("unknown", ACCESSOR_UNCHECKED_REASON, hint)
    if accessor:
        checks.append(("accessor", checked(scope, ACCESSOR_REASON)))
        hint = (
            f"{func_name!r} is a property/accessor: it is read by attribute "
            "access, which the call graph does not record, so 0 callers is not "
            "evidence of absence."
        )
        if sites:
            hint += f" Non-call references: {_describe(sites)}."
        return verdict("unknown", ACCESSOR_REASON, hint)
    checks.append(("accessor", checked(scope)))
    if sites:
        checks.append(("non_call_references", checked(scope, NON_CALL_REASON)))
        hint = (
            f"No resolved caller for {func_name!r}, but {len(sites)} non-call "
            "reference(s) (attribute access, bare name, or string name) could "
            f"reach it: {_describe(sites)}. Read those sites before treating "
            "this as absence."
        )
        return verdict("unknown", NON_CALL_REASON, hint)
    checks.append(("non_call_references", checked(scope)))
    # #1596：守卫按名收窄后，注册表分发须由装饰器登记门兜底。
    decorator = registering_decorator(project_root, declarations)
    if decorator == UNREADABLE:
        checks.append(("registering_decorator", NotChecked(DECORATED_REASON)))
        return verdict(
            "unknown", DECORATED_REASON, registered_hint(func_name, decorator)
        )
    if decorator is not None:
        checks.append(("registering_decorator", checked(scope, DECORATED_REASON)))
        return verdict(
            "unknown", DECORATED_REASON, registered_hint(func_name, decorator)
        )
    checks.append(("registering_decorator", checked(scope)))
    return verdict("complete", None, None)


def _stale_verdict(
    cache: Any,
    project_root: str,
    scope: Scope,
    scan: tuple[list[dict[str, Any]], dict[str, StatKey | None]],
    accessor: bool,
    fields: dict[str, Any],
) -> tuple[AbsenceVerdict | None, CheckOutcome]:
    """#1672：引用命中的文件已与索引不一致时，原因是源码与索引不一致。

    这样的命中可能是刷新前新增的调用（还没有调用边），称它为非调用引用是误诊；
    未变文件里的命中仍是非调用引用，按表序列在主因之后。

    RFC-0040：索引戳记读不到时比对没有运行（``SOURCE_SCOPE_UNKNOWN``），不再当作
    “没有不一致的文件”。
    """
    sites, stamps = scan
    func_name = scope[0]
    stale = stale_reference_files(cache, project_root, sites, stamps)
    fields["stale_reference_files"] = None if stale is None else stale[:_SITES_CAP]
    fields["stale_reference_files_total"] = None if stale is None else len(stale)
    if stale is None:
        hint = (
            f"No resolved caller for {func_name!r}, and the files that reference "
            "it could not be compared with the index, so this is not evidence of "
            "absence."
        )
        unread = AbsenceVerdict("unknown", UNKNOWN_REASON, hint, fields)
        return unread, NotChecked(UNKNOWN_REASON)
    if not stale:
        return None, Checked(scope)
    stale_set = frozenset(stale)
    flags = (
        (NON_CALL_REASON, any(site["file"] not in stale_set for site in sites)),
        (ACCESSOR_REASON, accessor),
    )
    also = tuple(code for code, applies in flags if applies)
    in_stale = [site for site in sites if site["file"] in stale_set]
    hint = (
        f"No resolved caller for {func_name!r}, but it is referenced in file(s) "
        f"that changed since the index was built: {_describe(in_stale)}. The "
        "index may be missing those calls, so this is not evidence of absence."
    )
    found = AbsenceVerdict(
        "unknown",
        STALE_REASON,
        hint,
        fields,
        also=also,
        stale_files=tuple(stale[:_SITES_CAP]),
    )
    return found, Checked(scope, (STALE_REASON, *also))


def _new_files_gap(
    cache: Any,
    project_root: str,
    scope: Scope,
    declarations: list[tuple[str, int, str]],
    fields: dict[str, Any],
) -> tuple[AbsenceVerdict | None, list[str], CheckOutcome]:
    """#1607：同语言中尚未入索引的新文件可能就是调用方；无新文件时判定为 None。

    同一次遍历顺带返回需扫描的配置文件（#1624），以及本门的检查结果（RFC-0040）。
    """
    func_name = scope[0]
    languages = frozenset(language for _file, _line, language in declarations)
    walked = project_files(cache, project_root, languages)
    new_files = None if walked is None else walked.unindexed
    config_files = [] if walked is None else walked.config
    fields["unindexed_source_files"] = (
        None if new_files is None else new_files[:UNINDEXED_FILES_CAP]
    )
    fields["unindexed_source_files_total"] = (
        None if new_files is None else len(new_files)
    )
    if new_files is None:
        hint = unchecked_hint(func_name)
        verdict = AbsenceVerdict("unknown", UNINDEXED_UNCHECKED_REASON, hint, fields)
        return verdict, config_files, NotChecked(UNINDEXED_UNCHECKED_REASON)
    if new_files:
        hint = unindexed_hint(func_name, languages, new_files)
        verdict = AbsenceVerdict("unknown", UNINDEXED_REASON, hint, fields)
        return verdict, config_files, Checked(scope, (UNINDEXED_REASON,))
    return None, config_files, Checked(scope)


def _describe(sites: list[dict[str, Any]]) -> str:
    named = [f"{site['file']}:{site['line']}" for site in sites[:_SITES_NAMED]]
    if len(sites) > _SITES_NAMED:
        named.append(f"and {len(sites) - _SITES_NAMED} more")
    return "; ".join(named)


def _declarations(
    cache: Any, bare: str, owner: str, file_path: str | None
) -> list[tuple[str, int, str]] | None:
    """目标的声明行 ``(file, line, language)``；读取失败为 None。

    限定名 ``Class.method`` 收窄到声明该类的文件；调用方点名文件时再收窄到该
    文件。收窄后为空则退回全部同名声明——只会更保守。
    """
    try:
        conn = cache.get_conn()
        rows = [
            (str(row[0]), int(row[1]), str(row[2]))
            for row in conn.execute(
                "SELECT file_path, line, language FROM ast_symbol_rows WHERE name = ?",
                (bare,),
            )
        ]
        owner_files = (
            {
                str(row[0])
                for row in conn.execute(
                    "SELECT file_path FROM ast_symbol_rows "
                    "WHERE name = ? AND kind = 'class'",
                    (owner.rpartition(".")[2],),
                )
            }
            if owner
            else set()
        )
    except (sqlite3.Error, AttributeError):
        return None
    narrowed = [row for row in rows if row[0] in owner_files] or rows
    if file_path:
        wanted = file_path.replace("\\", "/")
        narrowed = [row for row in narrowed if row[0] == wanted] or narrowed
    return narrowed


def scan_budget_seconds(files: int) -> float:
    """#1609：扫描 ``files`` 个文件的总期限，按 discovery_budget 的每项成本放宽。"""
    return _SCAN_DEADLINE_SECONDS + DISCOVERY_SECONDS_PER_ENTRY * files


def _non_call_sites(
    cache: Any,
    project_root: str,
    bare: str,
    declarations: list[tuple[str, int, str]],
    config_files: Sequence[str] = (),
    *,
    mask_imports: bool = False,
) -> list[dict[str, Any]] | None:
    """同语言已索引文件与配置文件（#1624）中名字的非调用出现位置；超时或读取失败为 None。"""
    scan = _reference_scan(
        cache, project_root, bare, declarations, config_files, mask_imports=mask_imports
    )
    return None if scan is None else scan[0]


def _reference_scan(
    cache: Any,
    project_root: str,
    bare: str,
    declarations: list[tuple[str, int, str]],
    config_files: Sequence[str] = (),
    *,
    mask_imports: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, StatKey | None]] | None:
    """非调用出现位置，及每个命中文件读取时的 stat 证据（#1672 据此比对索引戳记）。"""
    languages = sorted({language for _file, _line, language in declarations})
    if not languages:
        return [], {}
    started = time.monotonic()
    try:
        conn = cache.get_conn()
        marks = ",".join("?" * len(languages))
        files = sorted(
            (str(row[0]), str(row[1]))
            for row in conn.execute(
                "SELECT file_path, language FROM ast_index "  # nosec B608
                f"WHERE language IN ({marks})",
                languages,
            )
        ) + [(path, text_language(path) or CONFIG_LANGUAGE) for path in config_files]
        declared_lines = {
            (str(row[0]), int(row[1]))
            for row in conn.execute(
                "SELECT file_path, line FROM ast_symbol_rows WHERE name = ?", (bare,)
            )
        }
    except (sqlite3.Error, AttributeError):
        return None
    # #1622：调用位置只有在确有调用边时才可跳过；读不到边即无法复核。
    edge_lines = call_edge_lines(cache, bare)
    if edge_lines is None:
        return None
    deadline = started + scan_budget_seconds(len(files))
    hits = _files_containing(project_root, files, bare.encode("utf-8"), deadline)
    if hits is None:
        return None
    pattern = re.compile(r"(?<![\w$])" + re.escape(bare) + r"(?![\w$])")
    declaration_files = {file for file, _line, _language in declarations}
    sites: list[dict[str, Any]] = []
    foreign: list[dict[str, Any]] = []
    stamps: dict[str, StatKey | None] = {}
    texts = [
        (
            rel_path,
            language,
            _strip_comments_and_prose(data.decode("utf-8", "replace"), language, bare),
        )
        for rel_path, language, data, _stamp in hits
    ]
    # #1709：别名在其余文件里的出现（再导出的使用）须与本文件的导入行一并核对。
    python_texts = {
        rel_path: text
        for rel_path, language, text in texts
        if language in _PY_LANGUAGES
    }
    for (rel_path, language, text), (_path, _language, _data, stamp) in zip(
        texts, hits, strict=True
    ):
        stamps[rel_path] = stamp
        alias_lines: list[int] = []
        if language in _PY_LANGUAGES:
            # #1670：别名的每次使用都已核对时，改名导入行也只是绑定。
            check = alias_reference_check(
                cache,
                rel_path,
                text,
                bare,
                declaration_files,
                _reference_lines,
                python_texts,
            )
            foreign.extend(check.foreign)
            if mask_imports:
                alias_lines = check.lines
                text = mask_import_bindings(text, bare, check.masked)
        covered = edge_lines.get(rel_path, frozenset())
        lines = sorted({*_reference_lines(text, pattern, covered), *alias_lines})
        for line in lines:
            if (rel_path, line) not in declared_lines:
                sites.append({"file": rel_path, "line": line})
    return _with_foreign(sites, foreign), stamps


def _with_foreign(
    sites: list[dict[str, Any]], foreign: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """并入别的文件里按别名点名的位置（同一位置只列一次，按文件与行排序）。"""
    if not foreign:
        return sites
    merged = {(site["file"], site["line"]): site for site in foreign}
    merged.update({(site["file"], site["line"]): site for site in sites})
    return [merged[key] for key in sorted(merged)]


#: 一次读取的结果：字节（不含 needle 时为空串）及读取时的 stat 证据。
_Read = tuple[bytes, StatKey | None]


def _read_if_contains(
    path: str, needle: bytes, vocab: ReferenceVocabulary | None = None
) -> _Read | None:
    """读取文件；不含 ``needle`` 时字节为空串，读取失败返回 None。

    字节经 :data:`FILE_CACHE` 按 stat 证据复用（每次重新 stat，变即重读）；
    同一份证据随结果返回，供 #1672 与索引戳记比对。
    #1691：``vocab`` 的 stat 证据仍成立且证明不含 ``needle`` 时不打开文件。
    """
    if vocab is not None and vocab.lacks(path, needle):
        return b"", None
    found = FILE_CACHE.read_stamped(path)
    if found is None:
        return None
    data, stamp = found
    if vocab is not None:
        vocab.learn(path, data, stamp)
    return (data if needle in data else b""), stamp


def _files_containing(
    project_root: str,
    files: list[tuple[str, str]],
    needle: bytes,
    deadline: float,
) -> list[tuple[str, str, bytes, StatKey | None]] | None:
    """并行读取并按字节预筛；超时或任一文件不可读即为 None（不以部分结果冒充）。

    实测（Windows，约 1,700 个 Python 文件）：串行打开读取约 2 s，打开文件的
    开销主导耗时且会释放 GIL，因此用线程池并行读取。
    """
    hits: list[tuple[str, str, bytes, StatKey | None]] = []
    # dogfood 第 7 轮：逐文件提交 future 的调度开销与（已缓存的）读取相当；
    # 改为按块提交、块内顺序读取。期限与“任一不可读即 None”的判定不变。
    size = max(1, -(-len(files) // (_READ_WORKERS * _CHUNKS_PER_WORKER)))
    chunks = [files[start : start + size] for start in range(0, len(files), size)]
    vocab = reference_vocab.for_root(project_root)
    executor = ThreadPoolExecutor(max_workers=_READ_WORKERS)
    try:
        futures = [
            executor.submit(_read_chunk, project_root, chunk, needle, vocab)
            for chunk in chunks
        ]
        for chunk, future in zip(chunks, futures, strict=True):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                results = future.result(timeout=remaining)
            except FutureTimeout:
                return None
            # 块在首个不可读文件处停止，结果可能短于块，因此不用 strict。
            for (rel_path, language), read in zip(chunk, results, strict=False):
                if read is None:
                    return None
                if read[0]:
                    hits.append((rel_path, language, read[0], read[1]))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        vocab.flush()
    return hits


def _read_chunk(
    project_root: str,
    chunk: list[tuple[str, str]],
    needle: bytes,
    vocab: ReferenceVocabulary | None = None,
) -> list[_Read | None]:
    """顺序读取一块文件；遇到不可读文件即停止（其后的结果已不再需要）。"""
    results: list[_Read | None] = []
    for rel_path, _language in chunk:
        data = _read_if_contains(os.path.join(project_root, rel_path), needle, vocab)
        results.append(data)
        if data is None:
            break
    return results


def _strip_comments_and_prose(text: str, language: str, bare: str | None = None) -> str:
    """剔除注释与普通字符串，保留行号；恰为标识符的字符串保留（反射用名）。

    #1624：给定 ``bare`` 时，以代码形态提到它的字符串（``"pkg.mod:bare"``、
    ``"o.bare()"``）也保留为一次引用；Python 独立成句的三引号串（文档字符串）除外。
    #1633：`exec`/`eval`/`compile` 的串实参与 doctest 行按代码保留；JSON、
    Notebook 与模板交给 `absence_text_kinds.reference_text`。
    """
    if language in _PY_LANGUAGES:
        lexeme = _PY_LEXEME
    elif language in _C_LANGUAGES:
        lexeme = _C_LEXEME
    else:
        return reference_text(text, language, bare, _strip_comments_and_prose)

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token[0] in _QUOTES:
            quote = 3 if token[:3] in ('"""', "'''") else 1
            body = token[quote:-quote]
            if _IDENTIFIER.fullmatch(body):
                return f" {body} "
            # f-string 的插值可以引用名字；前缀为 f 时保留原文，只会更保守。
            prefix = text[max(0, match.start() - 2) : match.start()]
            if "f" in prefix.lower():
                return token
            docstring = quote == 3 and language in _PY_LANGUAGES
            kept = string_code(text, match.span(), body, docstring, bare)
            if kept is not None:
                return kept
        return "\n" * token.count("\n")

    return lexeme.sub(_replace, text)


def _reference_lines(
    text: str,
    pattern: re.Pattern[str],
    call_lines: AbstractSet[int] | None = None,
) -> list[int]:
    """名字不处于已覆盖的调用位置、也不是裸名赋值 / 关键字实参的出现行（去重、有序）。

    ``call_lines`` 为该文件中确有调用边的行（#1622）：调用位置 ``name(`` 只在
    这些行上跳过。为 None 时信任所有调用位置（仅供纯文本单元测试使用）。
    """
    newlines = [found.start() for found in re.finditer("\n", text)]
    lines: list[int] = []
    for match in pattern.finditer(text):
        after = _FOLLOWING.match(text, match.end())
        following = after.group(1) if after else ""
        line = bisect.bisect_right(newlines, match.start()) + 1
        if following.startswith("("):
            if call_lines is None or line in call_lines:
                continue
        elif following.startswith("=") and not following.startswith("=="):
            start = match.start() - 1
            while start >= 0 and text[start] in " \t":
                start -= 1
            if start < 0 or text[start] != ".":
                continue
        if not lines or lines[-1] != line:
            lines.append(line)
    return lines


def _is_accessor(
    project_root: str, declarations: list[tuple[str, int, str]], bare: str
) -> bool | None:
    """声明是否为访问器：Python 访问器装饰器，或 JS/TS 的 get/set 访问器。

    RFC-0040：读不到的声明（文件不可读，或声明行已不在文件内）无法排除访问器；
    其余声明也都不是访问器时返回 ``None``——读不到不是“不是访问器”的证据。
    """
    getter = re.compile(r"\b(?:get|set)\s+" + re.escape(bare) + r"\s*\(")
    unread = False
    for rel_path, line, _language in declarations:
        text = FILE_CACHE.read_text(os.path.join(project_root, rel_path))
        source = None if text is None else text.splitlines()
        if source is None or not 0 < line <= len(source):
            unread = True
            continue
        if getter.search(source[line - 1]):
            return True
        if any(_ACCESSOR_DECORATOR.match(text) for text in _decorators(source, line)):
            return True
    return None if unread else False


def _decorators(source: list[str], line: int) -> list[str]:
    """声明行上方（及声明行本身起始处）连续的装饰器行，已去除缩进。"""
    found: list[str] = []
    index = line - 1
    while index < len(source) and source[index].lstrip().startswith("@"):
        found.append(source[index].strip())
        index += 1
    index = line - 2
    while index >= 0 and source[index].lstrip().startswith("@"):
        found.append(source[index].strip())
        index -= 1
    return found
