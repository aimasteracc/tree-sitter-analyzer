"""#1790：死代码分析里“不是调用、却在使用函数”的引用。

调用图只记录 ``f(...)`` 形式的调用。函数作为值被使用时不会成为边：存进
dict / list / tuple / set 的分发表、作为参数传入（``Thread(target=worker)``、
``json.loads(..., parse_constant=reject)``）、按属性取出（``@property``、
``self.handler``）、装饰器 ``@register``、或按名字字符串取出（``getattr``）。
把这些函数报告为“死代码”会诱导 agent 删除活代码。

这里用一次轻量的词法扫描补上这些引用：

- 只关心当前仍被判为死的候选函数名，扫描成本与候选数成比例。
- 名字后紧跟 ``(`` 的出现视为调用（交给调用图），后跟单个 ``=`` 的视为赋值
  目标或关键字实参名；``def`` / ``function`` 等定义处也跳过。其余出现都算引用。
- 引用位于某个函数体内时，记为“该函数 → 被引用函数”的边，死函数里的引用
  不会让目标复活；位于模块作用域（无外围函数、或文件里没有函数）时，被引用
  函数直接成为根。
- 带登记型装饰器（``@app.route`` 等，非 ``staticmethod`` / ``property`` 这类）的
  Python 函数由框架调用，同样是根。
- 字符串和注释里的名字同样算引用。这是有意的过近似：宁可漏报死代码，也不
  把活代码报告为死代码（Trust first）。
"""

from __future__ import annotations

import ast
import os
import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .call_graph import FunctionRef
from .constants import EXCLUDE_DIRS
from .project_graph import _language_from_ext

_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
# 定义关键字紧挨在名字前：``def name`` / ``function name`` / ``fn name`` ...
_DEFINITION_PREFIX = re.compile(
    r"(?:^|[^\w$])(?:def|function|func|fn|fun|sub)\s+$", re.MULTILINE
)
# 名字前是这些记号时按属性 / 成员访问处理：``obj.name`` / ``Cls::name`` / ``p->name``。
_MEMBER_ACCESS_SUFFIXES = (".", "::", "->")
# Python 的 ``*.py`` 模块路径里每一段都必须是合法标识符才能按点分路径导入。
_PY_SUFFIXES = (".py", ".pyi")
# 只改变调用方式、不把函数登记到别处的装饰器；其余装饰器视为“登记”（路由、
# 钩子、插件表），被装饰的函数由框架调用。
_NON_REGISTERING_DECORATORS = frozenset(
    {
        "abstractmethod",
        "asynccontextmanager",
        "cache",
        "cached_property",
        "classmethod",
        "contextmanager",
        "deprecated",
        "final",
        "lru_cache",
        "overload",
        "override",
        "property",
        "staticmethod",
        "wraps",
    }
)


@dataclass(frozen=True)
class ReferenceIndex:
    """候选函数被“作为值”引用的情况。

    ``module_targets``：在模块作用域被引用的函数（导入时就会执行，直接是根）。
    ``edges``：函数体内的引用，键为外围函数，值为被引用的函数。
    """

    module_targets: frozenset[FunctionRef] = frozenset()
    edges: Mapping[FunctionRef, tuple[FunctionRef, ...]] = field(default_factory=dict)
    #: 被装饰器登记、由框架调用的函数（同样是根）。
    registered: frozenset[FunctionRef] = frozenset()

    def referenced(self) -> frozenset[FunctionRef]:
        """被任何位置引用或登记过的函数（不区分来源是否存活）。"""
        targets: set[FunctionRef] = set(self.module_targets) | set(self.registered)
        for refs in self.edges.values():
            targets.update(refs)
        return frozenset(targets)


def normalize_rel_path(path: str) -> str:
    """统一相对路径的分隔符，内存图与缓存图的写法不同。"""
    return path.replace("\\", "/")


def module_path_unresolvable(file_path: str) -> bool:
    """Python 文件的点分模块路径是否无法解析（如目录名 ``agent-tasks``）。

    这类文件只能靠 ``sys.path`` 改写或脚本方式加载，调用图无法把其他文件里的
    ``from scenarios import ...`` 连到它们，跨文件的调用 / 引用会缺失。
    """
    normalized = normalize_rel_path(file_path)
    if not normalized.endswith(_PY_SUFFIXES):
        return False
    # 以 ``.py`` 结尾保证至少有一段非空的文件名。
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    stem = parts[-1].rsplit(".", 1)[0]
    return any(not part.isidentifier() for part in (*parts[:-1], stem))


def _iter_source_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            if filename.startswith("."):
                continue
            if _language_from_ext(filename) is not None:
                yield Path(dirpath) / filename


def _next_non_space(text: str, index: int) -> str:
    length = len(text)
    while index < length and text[index] in " \t":
        index += 1
    return text[index : index + 2] if index < length else ""


def _is_member_access(text: str, start: int) -> bool:
    before = text[max(0, start - 8) : start].rstrip(" \t")
    return before.endswith(_MEMBER_ACCESS_SUFFIXES)


def _is_value_reference(text: str, start: int, end: int) -> bool:
    """名字的这次出现是否是“作为值”的使用。"""
    following = _next_non_space(text, end)
    if following.startswith("("):
        return False  # 调用：由调用图负责
    if following.startswith("=") and not following.startswith(("==", "=>")):
        return False  # 赋值目标 / 关键字实参名
    line_start = text.rfind("\n", 0, start) + 1
    return not _DEFINITION_PREFIX.search(text, line_start, start)


@dataclass(frozen=True)
class _Occurrence:
    name: str
    line: int
    member_access: bool


def _value_occurrences(text: str, names: Collection[str]) -> list[_Occurrence]:
    occurrences: list[_Occurrence] = []
    line = 1
    cursor = 0
    for match in _IDENTIFIER.finditer(text):
        name = match.group(0)
        if name not in names:
            continue
        start, end = match.span()
        if not _is_value_reference(text, start, end):
            continue
        line += text.count("\n", cursor, start)
        cursor = start
        occurrences.append(_Occurrence(name, line, _is_member_access(text, start)))
    return occurrences


def _enclosing(funcs: list[FunctionRef], line: int) -> FunctionRef | None:
    best: FunctionRef | None = None
    for ref in funcs:
        if ref.start_line <= line <= ref.end_line and (
            best is None
            or (ref.end_line - ref.start_line) < (best.end_line - best.start_line)
        ):
            best = ref
    return best


def _targets_for(
    occurrence: _Occurrence,
    file_funcs: list[FunctionRef],
    by_name: Mapping[str, list[FunctionRef]],
) -> list[FunctionRef]:
    """同文件定义优先；属性访问或文件内无定义时按名字匹配全项目。"""
    candidates = by_name.get(occurrence.name, [])
    if occurrence.member_access:
        return list(candidates)
    local = [ref for ref in file_funcs if ref.name == occurrence.name]
    return local or list(candidates)


def _decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return ""


def _registering_decorated_lines(source: str) -> set[tuple[str, int]]:
    """带登记型装饰器的 Python 函数的 ``(名字, def 行号)``。"""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    found: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(
            _decorator_name(dec) not in _NON_REGISTERING_DECORATORS
            for dec in node.decorator_list
        ):
            found.add((node.name, node.lineno))
    return found


def python_registered_functions(
    project_root: str | os.PathLike[str], candidates: Iterable[FunctionRef]
) -> set[FunctionRef]:
    """Python 候选里被装饰器登记的函数（``@app.route`` / ``@server.list_tools()``
    ...）：框架按登记表调用它们，源码里没有调用点。"""
    by_file: dict[str, list[FunctionRef]] = defaultdict(list)
    for ref in candidates:
        if ref.language == "python":
            by_file[ref.file_path].append(ref)
    root = Path(project_root)
    registered: set[FunctionRef] = set()
    for rel, refs in by_file.items():
        try:
            source = (root / rel).read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        decorated = _registering_decorated_lines(source)
        registered.update(r for r in refs if (r.name, r.start_line) in decorated)
    return registered


def build_reference_index(
    project_root: str | os.PathLike[str],
    functions: Iterable[FunctionRef],
    candidates: Collection[FunctionRef],
) -> ReferenceIndex:
    """扫描项目源文件，收集 ``candidates`` 作为值被引用或被装饰器登记的位置。"""
    candidate_list = list(candidates)
    names = frozenset(ref.name for ref in candidate_list)
    if not names:
        return ReferenceIndex()

    by_name: dict[str, list[FunctionRef]] = defaultdict(list)
    by_file: dict[str, list[FunctionRef]] = defaultdict(list)
    for ref in functions:
        by_file[normalize_rel_path(ref.file_path)].append(ref)
        if ref.name in names:
            by_name[ref.name].append(ref)

    root = Path(project_root)
    module_targets: set[FunctionRef] = set()
    edges: dict[FunctionRef, set[FunctionRef]] = defaultdict(set)
    for path in _iter_source_files(root):
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        occurrences = _value_occurrences(text, names)
        if not occurrences:
            continue
        rel = normalize_rel_path(str(path.relative_to(root)))
        file_funcs = by_file.get(rel, [])
        for occurrence in occurrences:
            targets = _targets_for(occurrence, file_funcs, by_name)
            if not targets:
                continue
            source = _enclosing(file_funcs, occurrence.line)
            if source is None:
                module_targets.update(targets)
            else:
                edges[source].update(t for t in targets if t != source)

    return ReferenceIndex(
        module_targets=frozenset(module_targets),
        edges={src: tuple(dst) for src, dst in edges.items() if dst},
        registered=frozenset(python_registered_functions(root, candidate_list)),
    )
