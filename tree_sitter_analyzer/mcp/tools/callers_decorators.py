"""#1596 / #1623：从 AST 读取声明上的装饰器，判断它是否可能把目标登记到别处。

RFC-0028 §1.2 的守卫在 0 调用方时按名收窄（#1596），注册表分发（``@app.route``、
``@register``）因此不再由声明文件守卫兜底：被登记的函数之后以名字不同的
``handler()`` 调用，调用图里没有边。登记门要求“可能登记它的装饰器”不存在，才允许
``complete``。

#1614 的第一版逐行扫描以 ``@`` 开头的连续行，并按裸名豁免包装器；dogfood 第 5 轮
（#1623）发现两处缺口：

* 多行装饰器（``@register(\\n"x",\\n)``）与装饰器和 def 之间夹注释的写法不可见
  （真实仓库中有 353 个测试函数带多行 ``@pytest.mark...``）；
* 项目自己的 ``def cache(fn): HANDLERS.append(fn)`` 以 ``@cache`` 使用时，被当作
  ``functools.cache`` 豁免。

现在的做法：

* Python 用 ``ast`` 的 ``decorator_list``；其他语言用 tree-sitter 节点
  （decorator / annotation / attribute），与换行和注释无关；
* 只有经导入解析到已知标准库 / 第三方包装器的装饰器才豁免（``functools.lru_cache``、
  内建 ``staticmethod`` 等）；名字在本文件被重新绑定、来自 ``import *`` 或相对导入
  的一律不豁免；
* 无法解析（语法错误、读取失败、grammar 不可用）时视为“可能登记”——只会更保守。
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from typing import Any

from .evidence_file_cache import FILE_CACHE

#: completeness 原因：目标带有可能登记它的装饰器（注册表分发不产生调用边）。
DECORATED_REASON = "DECORATOR_MAY_REGISTER"
#: 无法读取装饰器时 hint 中使用的占位文本。
UNREADABLE = "<decorators unreadable>"
#: 只包装或标注、不把函数登记到别处的装饰器（完全限定名，经导入解析后比较）。
KNOWN_WRAPPERS = frozenset(
    {
        "builtins.classmethod",
        "builtins.property",
        "builtins.staticmethod",
        "abc.abstractclassmethod",
        "abc.abstractmethod",
        "abc.abstractproperty",
        "abc.abstractstaticmethod",
        "contextlib.asynccontextmanager",
        "contextlib.contextmanager",
        "dataclasses.dataclass",
        "functools.cache",
        "functools.cached_property",
        "functools.lru_cache",
        "functools.total_ordering",
        "functools.wraps",
        "typing.final",
        "typing.no_type_check",
        "typing.overload",
        "typing.override",
        "typing.runtime_checkable",
        "typing_extensions.deprecated",
        "typing_extensions.final",
        "typing_extensions.overload",
        "typing_extensions.override",
        "typing_extensions.runtime_checkable",
        "warnings.deprecated",
    }
)
#: 未绑定时可解析为内建的名字。
_BUILTIN_WRAPPERS = frozenset({"classmethod", "property", "staticmethod"})
#: tree-sitter 中表示装饰器 / 注解的节点类型。
_TS_DECORATOR_TYPES = frozenset(
    {
        "decorator",
        "annotation",
        "marker_annotation",
        "attribute",
        "attribute_item",
        "attribute_list",
    }
)
#: 装饰器可能嵌套其中、不构成“被装饰声明”的中间节点。
_TS_WRAPPER_TYPES = frozenset({"modifiers", "annotations"})
#: 声明节点类型的后缀（method_declaration、method_definition、function_item 等）；
#: 参数等其他节点上的注解不会登记所在函数。
_TS_DECLARATION_SUFFIXES = ("declaration", "definition", "_item", "signature")
_WHITESPACE = re.compile(r"\s+")


def registering_decorator(
    project_root: str, declarations: list[tuple[str, int, str]]
) -> str | None:
    """声明上第一个可能登记目标的装饰器文本；没有则为 None。

    读取或解析失败的声明返回 :data:`UNREADABLE`——无法读取不等于没有装饰器。
    """
    for rel_path, line, language in declarations:
        text = FILE_CACHE.read_text(os.path.join(project_root, rel_path))
        if text is None:
            return UNREADABLE
        decorators = declaration_decorators(text, line, language)
        if decorators is None:
            return UNREADABLE
        for decorator in decorators:
            if decorator.qualified not in KNOWN_WRAPPERS:
                return decorator.text
    return None


def registered_hint(func_name: str, decorator: str) -> str:
    """装饰器登记门的 next_step。"""
    if decorator == UNREADABLE:
        return (
            f"No resolved caller for {func_name!r}, and the decorators on its "
            "declaration could not be read, so a registering decorator cannot be "
            "ruled out and this is not evidence of absence."
        )
    return (
        f"No resolved caller for {func_name!r}, but it is decorated with "
        f"`{decorator}`, which may register it for dispatch the call graph does "
        "not record, so this is not evidence of absence."
    )


@dataclass(frozen=True)
class Decorator:
    """一个装饰器：源码文本（空白折叠）与解析出的完全限定名（无法解析为 None）。"""

    text: str
    qualified: str | None


def declaration_decorators(
    text: str, line: int, language: str
) -> list[Decorator] | None:
    """声明行 ``line`` 所在定义的装饰器；无法解析为 None。

    ``line`` 可以落在装饰器起始行到定义头（``def`` / 名字所在行）之间的任意一行。
    该行没有定义（例如同名变量）时返回空列表。
    """
    if language == "python":
        return _python_decorators(text, line)
    return _tree_sitter_decorators(text, line, language)


def _parsed_python(text: str) -> tuple[ast.Module, dict[str, set[str]]] | None:
    """The module tree and its bindings; one parse per text inside a query scope.

    RFC-0041: a pipeline asks callers about several symbols declared in the
    same file; outside a scope every call parses live, as before.
    """
    from ...query_scope import scoped

    def compute() -> tuple[ast.Module, dict[str, set[str]]] | None:
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return None
        return tree, _python_bindings(tree)

    return scoped(("callers_decorators.parse", text), compute)


def _python_decorators(text: str, line: int) -> list[Decorator] | None:
    parsed = _parsed_python(text)
    if parsed is None:
        return None
    tree, bindings = parsed
    found: list[Decorator] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        starts = [node.lineno, *(item.lineno for item in node.decorator_list)]
        if not min(starts) <= line <= node.lineno:
            continue
        for item in node.decorator_list:
            segment = ast.get_source_segment(text, item) or ast.unparse(item)
            found.append(
                Decorator(
                    "@" + _WHITESPACE.sub(" ", segment).strip(),
                    _qualify(item, bindings),
                )
            )
    return found


def _python_bindings(tree: ast.Module) -> dict[str, set[str]]:
    """文件中每个名字的绑定来源：导入给出模块路径，其他绑定记为 ``<local>``。

    ``import *`` 记在 ``*`` 下：此后任何未显式导入的名字都无法解析。
    """
    bindings: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.partition(".")[0]
                origin = alias.name if alias.asname else local
                bindings.setdefault(local, set()).add(origin)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                local = alias.asname or alias.name
                bindings.setdefault(local, set()).add(f"{module}.{alias.name}")
        elif isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        ) or (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)):
            name = node.id if isinstance(node, ast.Name) else node.name
            bindings.setdefault(name, set()).add("<local>")
    return bindings


def _qualify(expr: ast.expr, bindings: dict[str, set[str]]) -> str | None:
    """装饰器表达式的完全限定名；项目内绑定、冲突或无法解析时为 None。"""
    if isinstance(expr, ast.Call):
        expr = expr.func
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name):
        return None
    origins = bindings.get(expr.id)
    if origins is None:
        if "*" in bindings or expr.id not in _BUILTIN_WRAPPERS or parts:
            return None
        return f"builtins.{expr.id}"
    if len(origins) != 1:
        return None
    origin = next(iter(origins))
    if origin == "<local>" or origin.startswith("."):
        return None
    return ".".join([origin, *reversed(parts)])


def _tree_sitter_decorators(
    text: str, line: int, language: str
) -> list[Decorator] | None:
    """非 Python：tree-sitter 中挂在该声明上的装饰器 / 注解，一律不豁免。"""
    from ...language_loader import create_parser_safely

    try:
        parser = create_parser_safely(language)
        if parser is None:
            return None
        source = text.encode("utf-8")
        root = parser.parse(source).root_node
    except Exception:  # noqa: BLE001 — grammar 故障即“无法解析”，保守处理
        return None
    found: list[Decorator] = []
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        if node.type in _TS_DECORATOR_TYPES:
            owner = _ts_owner(node)
            if owner is not None and _ts_header_holds(node, owner, line):
                raw = source[node.start_byte : node.end_byte].decode("utf-8", "replace")
                found.append(Decorator(_WHITESPACE.sub(" ", raw).strip(), None))
            continue
        # 逆序压栈，使装饰器按源码顺序出现。
        stack.extend(reversed(node.children))
    return found


def _ts_owner(node: Any) -> Any | None:
    """装饰器所修饰的声明节点：跳过 modifiers 等中间层；挂在容器里时取其后继兄弟。

    修饰的不是声明（参数注解等）时为 None。
    """
    current = node
    while current.parent is not None and current.parent.type in _TS_WRAPPER_TYPES:
        current = current.parent
    parent = current.parent
    if parent is None:
        return None
    owner = parent
    if not _ts_is_declaration(parent) and parent.child_by_field_name("name") is None:
        owner = current.next_named_sibling
        while owner is not None and (
            owner.type in _TS_DECORATOR_TYPES or "comment" in str(owner.type)
        ):
            owner = owner.next_named_sibling
    if owner is not None and owner.type == "export_statement":
        owner = owner.child_by_field_name("declaration") or owner
    if owner is None or not _ts_is_declaration(owner):
        return None
    return owner


def _ts_is_declaration(node: Any) -> bool:
    return str(node.type).endswith(_TS_DECLARATION_SUFFIXES)


def _ts_header_holds(decorator: Any, owner: Any, line: int) -> bool:
    """``line`` 是否落在装饰器起始行到声明名字所在行之间（均为 1 起）。"""
    name = owner.child_by_field_name("name")
    end = int((name or owner).start_point[0]) + 1
    start = int(min(decorator.start_point[0], owner.start_point[0])) + 1
    return start <= line <= end
