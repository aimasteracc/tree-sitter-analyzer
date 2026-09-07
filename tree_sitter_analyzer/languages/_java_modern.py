"""Java lambda、初始化器、匿名类、record 构造器和 module 的唯一构造入口。"""

from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Package
from ._java_element_common import (
    _build_java_class,
    _extract_javadoc_from_node,
    _extract_node_annotations,
    _node_line_span,
    _qualified_class_name,
    _raw_text_for_span,
)

_JAVA_MODIFIER_KEYWORDS = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "final",
        "abstract",
        "synchronized",
        "volatile",
        "transient",
    }
)


def extract_lambda_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Function | None:
    """提取真实 lambda 节点；Node 或文本适配器的协议错误交由插件边界处理。"""
    start_line, end_line = _node_line_span(node)
    if node.child_by_field_name("parameters").has_error:
        return None
    parameters = _extract_lambda_parameters(node, get_node_text)
    return Function(
        name="<lambda>",
        start_line=start_line,
        end_line=end_line,
        raw_text=_raw_text_for_span(content_lines, start_line, end_line),
        language="java",
        parameters=parameters,
        return_type=None,
        modifiers=[],
        is_method=True,
    )


def extract_static_initializer(
    node: Any,
    content_lines: list[str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Function:
    """从已分派的静态初始化器生成函数；多个初始化器以行号区分。"""
    start_line, end_line = _node_line_span(node)
    return Function(
        name="<static_initializer>",
        start_line=start_line,
        end_line=end_line,
        raw_text=_raw_text_for_span(content_lines, start_line, end_line),
        language="java",
        modifiers=["static"],
        is_static=True,
        is_method=True,
    )


def extract_anonymous_class(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    current_package: str,
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Class:
    """从已由父节点验证的匿名 class_body 构造匿名类元素。"""
    start_line, end_line = _node_line_span(node)
    return _build_java_class(
        node,
        "<anonymous>",
        start_line,
        end_line,
        _raw_text_for_span(content_lines, start_line, end_line),
        _qualified_class_name(current_package, "<anonymous>"),
        current_package,
        None,
        [],
        [],
        "package",
        [],
        True,
        None,
        class_type="anonymous",
    )


def extract_compact_constructor(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Function:
    """已分派的紧凑构造器必有 name 字段；保留 record 隐式参数，协议错误上抛。"""
    start_line, end_line = _node_line_span(node)
    ctor_name = get_node_text(node.child_by_field_name("name"))

    modifiers = _extract_inline_modifiers(node, get_node_text)
    record = node.parent.parent if node.parent is not None else None
    header = record.child_by_field_name("parameters") if record is not None else None
    parameters = [
        get_node_text(parameter)
        for parameter in (header.named_children if header is not None else ())
        if parameter.type in ("formal_parameter", "spread_parameter")
    ]
    return Function(
        name=ctor_name,
        start_line=start_line,
        end_line=end_line,
        raw_text=_raw_text_for_span(content_lines, start_line, end_line),
        language="java",
        parameters=parameters,
        return_type="void",
        modifiers=modifiers,
        is_constructor=True,
        is_static="static" in modifiers,
        is_private="private" in modifiers,
        is_public="public" in modifiers,
        visibility=_determine_visibility_inline(modifiers),
        docstring=_extract_javadoc_from_node(node, get_node_text),
        annotations=_extract_node_annotations(node, get_node_text),
        throws=[],
        complexity_score=1,
        is_abstract=False,
        is_final=False,
        is_method=True,
    )


def extract_module_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
) -> Package | None:
    """模块元素的唯一构造入口；缺失名称返回 None，协议错误上抛。"""
    start_line, end_line = _node_line_span(node)
    name_node = node.child_by_field_name("name")
    module_name = get_node_text(name_node)
    if not module_name or name_node.has_error:
        return None
    return Package(
        name=module_name,
        start_line=start_line,
        end_line=end_line,
        language="java",
    )


def _extract_lambda_parameters(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    """读取 grammar 必需的 parameters 字段，保留推断、显式类型及 varargs 参数。"""
    parameters = node.child_by_field_name("parameters")
    if parameters.type == "identifier":
        return [get_node_text(parameters)]
    return [
        get_node_text(p)
        for p in parameters.named_children
        if p.type in ("identifier", "formal_parameter", "spread_parameter")
    ]


def _extract_inline_modifiers(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    """从声明自身的 modifiers 子节点读取修饰符关键字。"""
    for child in node.children:
        if child.type == "modifiers":
            return [
                get_node_text(gc)
                for gc in child.children
                if get_node_text(gc) in _JAVA_MODIFIER_KEYWORDS
            ]
    return []


def _determine_visibility_inline(modifiers: list[str]) -> str:
    """按显式修饰符确定可见性，缺省为包内可见。"""
    if "public" in modifiers:
        return "public"
    if "private" in modifiers:
        return "private"
    if "protected" in modifiers:
        return "protected"
    return "package"
