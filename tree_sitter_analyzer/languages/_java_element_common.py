"""Java 元素构造共用的范围、注解、文档和类模型辅助函数。"""

from collections.abc import Callable
from typing import Any

from ..models import Class

_CLASS_TYPE_MAP = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}

_ANNOTATION_NODE_TYPES = frozenset({"annotation", "marker_annotation"})


def _extract_javadoc_from_node(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """读取相邻 JavaDoc，越过行注释但不越过普通块注释或声明；适配器错误上抛。"""
    prev = node.prev_sibling
    while prev is not None:
        if prev.type == "block_comment":
            text = get_node_text(prev)
            return text if text.strip().startswith("/**") else None
        if prev.type != "line_comment":
            return None
        prev = prev.prev_sibling
    return None


def _node_line_span(node: Any) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _extract_node_annotations(
    node: Any, get_node_text: Callable[..., str]
) -> list[dict[str, Any]]:
    """只读取声明自身 modifiers 下的注解，不按行号邻近关系归属。"""
    annotations: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "modifiers":
            continue
        for modifier in child.children:
            if modifier.type not in _ANNOTATION_NODE_TYPES:
                continue
            ann_text = get_node_text(modifier)
            ann_name = None
            for sub in modifier.children:
                if sub.type == "identifier":
                    ann_name = get_node_text(sub)
                    break
            if not ann_name:
                import re as _re

                m = _re.search(r"@(\w+)", ann_text)
                if m:
                    ann_name = m.group(1)
            if ann_name:
                annotations.append(
                    {
                        "name": ann_name,
                        "line": modifier.start_point[0] + 1,
                        "text": ann_text,
                        "type": "annotation",
                    }
                )
        break  # 每个声明只有一个 modifiers 子节点。
    return annotations


def _qualified_class_name(package_name: str, class_name: str) -> str:
    return f"{package_name}.{class_name}" if package_name else class_name


def _raw_text_for_span(
    content_lines: list[str],
    start_line: int,
    end_line: int,
) -> str:
    start_line_idx = max(0, start_line - 1)
    end_line_idx = min(len(content_lines), end_line)
    return "\n".join(content_lines[start_line_idx:end_line_idx])


def _build_java_class(
    node: Any,
    class_name: str,
    start_line: int,
    end_line: int,
    raw_text: str,
    full_qualified_name: str,
    package_name: str,
    extends_class: str | None,
    implements_interfaces: list[str],
    modifiers: list[str],
    visibility: str,
    annotations: list[dict[str, Any]],
    is_nested: bool,
    parent_class: str | None,
    *,
    docstring: str | None = None,
    class_type: str | None = None,
) -> Class:
    return Class(
        name=class_name,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
        language="java",
        class_type=class_type
        if class_type is not None
        else _CLASS_TYPE_MAP.get(node.type, "class"),
        full_qualified_name=full_qualified_name,
        package_name=package_name,
        superclass=extends_class,
        interfaces=implements_interfaces,
        modifiers=modifiers,
        visibility=visibility,
        annotations=annotations,
        is_nested=is_nested,
        parent_class=parent_class,
        extends_class=extends_class,
        implements_interfaces=implements_interfaces,
        docstring=docstring,
    )
