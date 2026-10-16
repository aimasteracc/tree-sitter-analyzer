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
from dataclasses import dataclass, field
from typing import Any

from ...discovery_budget import DISCOVERY_SECONDS_PER_ENTRY
from .absence_text_kinds import reference_text, text_language
from .absence_text_refs import CONFIG_LANGUAGE, string_code
from .callers_call_lines import call_edge_lines
from .callers_decorators import (
    DECORATED_REASON,
    registered_hint,
    registering_decorator,
)
from .callers_target import NOT_DEFINED_REASON, not_defined_hint, resolve_target
from .callers_target import UNCHECKED_REASON as TARGET_UNCHECKED_REASON
from .relation_freshness import SCOPED_REASON
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

#: 响应中点名的引用位置上限；总数始终与列表并列给出。
_SITES_CAP = 5
#: hint 中内联点名的位置数。
_SITES_NAMED = 3
#: 同语言源码扫描的基础期限；超出即为 unknown，不以部分结果冒充普查。
#: #1609：固定 2 s 在负载下约 3% 的答案随机降级，因此再按文件数线性放宽。
_SCAN_DEADLINE_SECONDS = 2.0
#: 并行读取的线程数。
_READ_WORKERS = 8

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
#: 注释组 1，字符串组 2。左起最先匹配者胜出，因此字符串中的 ``#`` 不会被当作注释。
_PY_LEXEME = re.compile(
    r"(#[^\n]*)"
    r"|(\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')"
)
_C_LEXEME = re.compile(
    r"(//[^\n]*|/\*[\s\S]*?\*/)" r"|(\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')"
)
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
    downgraded = "incomplete" if total_callers else "unknown"
    freshness_reason = _freshness_gap(evidence)
    if freshness_reason is not None:
        return AbsenceVerdict(
            downgraded, freshness_reason, _freshness_hint(func_name, evidence)
        )
    if total_callers or not project_root:
        return AbsenceVerdict(completeness)
    return _assess_absence(cache, project_root, func_name, file_path)


def _freshness_gap(evidence: dict[str, Any]) -> str | None:
    """范围内证据不能支撑普查时返回其原因；SCOPED 表示范围内已复核一致。"""
    freshness = evidence.get("freshness")
    reason = evidence.get("reason")
    if freshness == "stale" or (freshness != "fresh" and reason != SCOPED_REASON):
        return str(reason or "SOURCE_SCOPE_UNKNOWN")
    return None


def _freshness_hint(func_name: str, evidence: dict[str, Any]) -> str:
    if evidence.get("freshness") == "stale":
        state = "the index is stale for this answer"
    else:
        state = "the source could not be revalidated against the index"
    return (
        f"No resolved caller for {func_name!r}, but {state}, so this is not "
        "evidence of absence."
    )


def _assess_absence(
    cache: Any, project_root: str, func_name: str, file_path: str | None
) -> AbsenceVerdict:
    """0 个调用方：目标已定义、无新文件、访问器与非调用引用都不存在时才保留 complete。"""
    # #1606：精确（限定）目标必须解析到已索引定义，否则 0 不是不存在的证据。
    target = resolve_target(cache, project_root, func_name, file_path)
    fields: dict[str, Any] = {
        "target_defined": target.defined,
        "close_matches": list(target.close_matches),
    }
    if not target.defined:
        reason = (
            TARGET_UNCHECKED_REASON if target.defined is None else NOT_DEFINED_REASON
        )
        return AbsenceVerdict(
            "unknown", reason, not_defined_hint(func_name, target), fields
        )
    bare = func_name.rpartition(".")[2]
    owner = func_name.rpartition(".")[0]
    declarations = _declarations(cache, bare, owner, file_path)
    sites = None
    if declarations is not None:
        new_files_verdict, config_files = _new_files_gap(
            cache, project_root, func_name, declarations, fields
        )
        if new_files_verdict is not None:
            return new_files_verdict
        sites = _non_call_sites(cache, project_root, bare, declarations, config_files)
    fields["non_call_references"] = None if sites is None else len(sites)
    fields["non_call_reference_sites"] = None if sites is None else sites[:_SITES_CAP]
    if declarations and _is_accessor(project_root, declarations, bare):
        hint = (
            f"{func_name!r} is a property/accessor: it is read by attribute "
            "access, which the call graph does not record, so 0 callers is not "
            "evidence of absence."
        )
        if sites:
            hint += f" Non-call references: {_describe(sites)}."
        return AbsenceVerdict("unknown", ACCESSOR_REASON, hint, fields)
    if sites is None:
        hint = (
            f"No resolved caller for {func_name!r}, and its non-call references "
            "(attribute access, bare name, or string name) could not be checked "
            "within budget, so this is not evidence of absence."
        )
        return AbsenceVerdict("unknown", UNCHECKED_REASON, hint, fields)
    if sites:
        hint = (
            f"No resolved caller for {func_name!r}, but {len(sites)} non-call "
            "reference(s) (attribute access, bare name, or string name) could "
            f"reach it: {_describe(sites)}. Read those sites before treating "
            "this as absence."
        )
        return AbsenceVerdict("unknown", NON_CALL_REASON, hint, fields)
    # #1596：守卫按名收窄后，注册表分发须由装饰器登记门兜底。
    decorator = registering_decorator(project_root, declarations or [])
    if decorator is not None:
        hint = registered_hint(func_name, decorator)
        return AbsenceVerdict("unknown", DECORATED_REASON, hint, fields)
    return AbsenceVerdict("complete", None, None, fields)


def _new_files_gap(
    cache: Any,
    project_root: str,
    func_name: str,
    declarations: list[tuple[str, int, str]],
    fields: dict[str, Any],
) -> tuple[AbsenceVerdict | None, list[str]]:
    """#1607：同语言中尚未入索引的新文件可能就是调用方；无新文件时判定为 None。

    同一次遍历顺带返回需扫描的配置文件（#1624）。
    """
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
        return verdict, config_files
    if new_files:
        hint = unindexed_hint(func_name, languages, new_files)
        return AbsenceVerdict("unknown", UNINDEXED_REASON, hint, fields), config_files
    return None, config_files


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
) -> list[dict[str, Any]] | None:
    """同语言已索引文件与配置文件（#1624）中名字的非调用出现位置；超时或读取失败为 None。"""
    languages = sorted({language for _file, _line, language in declarations})
    if not languages:
        return []
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
    sites: list[dict[str, Any]] = []
    for rel_path, language, data in hits:
        decoded = data.decode("utf-8", "replace")
        text = _strip_comments_and_prose(decoded, language, bare)
        covered = edge_lines.get(rel_path, frozenset())
        for line in _reference_lines(text, pattern, covered):
            if (rel_path, line) not in declared_lines:
                sites.append({"file": rel_path, "line": line})
    return sites


def _read_if_contains(path: str, needle: bytes) -> bytes | None:
    """读取文件；不含 ``needle`` 时返回空串，读取失败返回 None。"""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    return data if needle in data else b""


def _files_containing(
    project_root: str,
    files: list[tuple[str, str]],
    needle: bytes,
    deadline: float,
) -> list[tuple[str, str, bytes]] | None:
    """并行读取并按字节预筛；超时或任一文件不可读即为 None（不以部分结果冒充）。

    实测（Windows，约 1,700 个 Python 文件）：串行打开读取约 2 s，打开文件的
    开销主导耗时且会释放 GIL，因此用线程池并行读取。
    """
    hits: list[tuple[str, str, bytes]] = []
    executor = ThreadPoolExecutor(max_workers=_READ_WORKERS)
    try:
        futures = [
            executor.submit(
                _read_if_contains, os.path.join(project_root, rel_path), needle
            )
            for rel_path, _language in files
        ]
        for (rel_path, language), future in zip(files, futures, strict=True):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                data = future.result(timeout=remaining)
            except FutureTimeout:
                return None
            if data is None:
                return None
            if data:
                hits.append((rel_path, language, data))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return hits


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
        if match.group(2) is not None:
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
) -> bool:
    """声明是否为访问器：Python 访问器装饰器，或 JS/TS 的 get/set 访问器。"""
    getter = re.compile(r"\b(?:get|set)\s+" + re.escape(bare) + r"\s*\(")
    for rel_path, line, _language in declarations:
        try:
            with open(
                os.path.join(project_root, rel_path), encoding="utf-8", errors="replace"
            ) as handle:
                source = handle.read().splitlines()
        except OSError:
            continue
        if not 0 < line <= len(source):
            continue
        if getter.search(source[line - 1]):
            return True
        if any(_ACCESSOR_DECORATOR.match(text) for text in _decorators(source, line)):
            return True
    return False


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
