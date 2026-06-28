"""Element construction helpers for the Python language extractor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tree_sitter_analyzer.cache.extraction import _PY_SCOPE_BODY_NODES, _python_module_constant
from ...models import Class, Function, Variable
from ...utils import log_warning
from ..shared.traversal import node_range


def node_line_range(node: Any) -> tuple[int, int]:
    return node_range(node)


def node_raw_text(node: Any, source_code: str) -> str:
    # ``node.start_byte``/``end_byte`` are UTF-8 byte offsets, not codepoint
    # offsets. Slice the bytes form and decode so multibyte source code stays
    # aligned. ``end_byte`` is clamped because some legacy callers pass nodes
    # whose offsets exceed the source — matches the original lenient behavior.
    source_bytes = source_code.encode("utf-8")
    start_byte = max(0, min(getattr(node, "start_byte", 0), len(source_bytes)))
    end_byte = max(start_byte, min(getattr(node, "end_byte", 0), len(source_bytes)))
    if start_byte < end_byte:
        return source_bytes[start_byte:end_byte].decode("utf-8", errors="replace")
    return source_code


def function_raw_text(content_lines: list[str], start_line: int, end_line: int) -> str:
    start_line_idx = max(0, start_line - 1)
    end_line_idx = min(len(content_lines), end_line)
    return "\n".join(content_lines[start_line_idx:end_line_idx])


def extract_class_attribute_info(node: Any, source_code: str) -> Variable | None:
    """Extract class attribute information from an assignment node."""
    try:
        assignment_text = node_raw_text(node, source_code)
        if "=" not in assignment_text:
            return None

        left_part = assignment_text.split("=")[0].strip()
        attr_name, attr_type = _class_attribute_name_and_type(left_part)
        _start, _end = node_line_range(node)
        return Variable(
            name=attr_name,
            start_line=_start,
            end_line=_end,
            raw_text=assignment_text,
            language="python",
            variable_type=attr_type,
        )
    except Exception as exc:
        log_warning(f"Could not extract class attribute info: {exc}")
        return None


def _class_attribute_name_and_type(left_part: str) -> tuple[str, str | None]:
    if ":" not in left_part:
        return left_part, None

    name_part, type_part = left_part.split(":", 1)
    return name_part.strip(), type_part.strip()


def extract_module_constants(tree: Any, source_code: str) -> list[Variable]:
    """Extract module-level constants as Variable elements (issue #639).

    Plugin-path parity with the #612 ast_cache scope rule (shared via
    :func:`tree_sitter_analyzer._ast_extraction._python_module_constant`):
    an ``assignment`` not enclosed by any function/class body whose target
    is a plain identifier matching const-style ∪ annotated-with-value ∪
    dunder. Only ``function_definition``/``class_definition`` close module
    scope — if/try-wrapped module assignments stay captured, and chained
    targets (``A = B = 1``) yield one row per nested assignment.
    """
    constants: list[Variable] = []
    if tree is None or tree.root_node is None:
        return constants
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in _PY_SCOPE_BODY_NODES:
            continue
        if node.type == "assignment":
            sym = _python_module_constant(node, source_code)
            if sym is not None:
                constants.append(_build_module_constant(node, sym, source_code))
        stack.extend(reversed(node.children))
    return constants


def _build_module_constant(
    node: Any, sym: dict[str, Any], source_code: str
) -> Variable:
    type_node = node.child_by_field_name("type")
    vtype = node_raw_text(type_node, source_code) if type_node is not None else None
    return Variable(
        name=sym["name"],
        start_line=sym["line"],
        end_line=sym["end_line"],
        raw_text=node_raw_text(node, source_code),
        language="python",
        variable_type=vtype,
        field_type=vtype,
        is_constant=True,
        visibility=_function_visibility(sym["name"]),
    )


@dataclass(slots=True)
class FunctionBuildInput:
    name: str
    start_line: int
    end_line: int
    raw_text: str
    parameters: list[str]
    return_type: str | None
    is_async: bool
    decorators: list[str]
    docstring: str
    complexity_score: int
    framework_type: str
    is_constructor: bool = False
    is_method: bool = False
    parent_class: str | None = None


def build_function_element(data: FunctionBuildInput) -> Function:
    visibility = _function_visibility(data.name)
    has_staticmethod = "staticmethod" in data.decorators

    return Function(
        name=data.name,
        start_line=data.start_line,
        end_line=data.end_line,
        raw_text=data.raw_text,
        language="python",
        parameters=data.parameters,
        return_type=data.return_type or "Any",
        is_async=data.is_async,
        is_generator="yield" in data.raw_text,
        docstring=data.docstring,
        complexity_score=data.complexity_score,
        decorators=data.decorators,
        modifiers=data.decorators,
        is_static=has_staticmethod,
        is_staticmethod=has_staticmethod,
        is_private=visibility == "private",
        is_public=visibility == "public",
        framework_type=data.framework_type,
        is_property="property" in data.decorators,
        is_classmethod="classmethod" in data.decorators,
        is_constructor=data.is_constructor,
        is_method=data.is_method,
        parent_class=data.parent_class,
    )


def _function_visibility(name: str) -> str:
    if name.startswith("__") and name.endswith("__"):
        return "magic"
    if name.startswith("_"):
        return "private"
    return "public"


@dataclass(slots=True)
class DetailedFunctionBuildInput:
    name: str
    start_line: int
    end_line: int
    raw_text: str
    parameters: list[str]
    return_type: str | None
    decorators: list[str]


def build_detailed_function_element(data: DetailedFunctionBuildInput) -> Function:
    visibility = _function_visibility(data.name)
    return Function(
        name=data.name,
        start_line=data.start_line,
        end_line=data.end_line,
        raw_text=data.raw_text,
        language="python",
        parameters=data.parameters,
        return_type=data.return_type or "Any",
        decorators=data.decorators,
        modifiers=data.decorators,
        is_static="staticmethod" in data.decorators,
        is_private=visibility == "private",
        is_public=visibility == "public",
    )


@dataclass(slots=True)
class ClassBuildInput:
    name: str
    start_line: int
    end_line: int
    raw_text: str
    superclasses: list[str]
    decorators: list[str]
    docstring: str | None
    current_module: str
    framework_type: str


def build_class_element(data: ClassBuildInput) -> Class:
    # Accept both bare ABC and qualified abc.ABC (Codex P2 on #583)
    is_abstract = (
        any(s == "ABC" or s.endswith(".ABC") for s in data.superclasses)
        or "abstractmethod" in data.raw_text
    )
    return Class(
        name=data.name,
        start_line=data.start_line,
        end_line=data.end_line,
        raw_text=data.raw_text,
        language="python",
        class_type="abstract_class" if is_abstract else "class",
        superclass=data.superclasses[0] if data.superclasses else None,
        interfaces=data.superclasses[1:] if len(data.superclasses) > 1 else [],
        docstring=data.docstring,
        modifiers=data.decorators,
        full_qualified_name=_class_full_qualified_name(data.current_module, data.name),
        package_name=data.current_module,
        framework_type=data.framework_type,
        is_dataclass="dataclass" in data.decorators,
        is_abstract=is_abstract,
        is_exception=_is_exception_class(data.superclasses),
    )


def _class_full_qualified_name(current_module: str, class_name: str) -> str:
    if current_module:
        return f"{current_module}.{class_name}"
    return class_name


def _is_exception_class(superclasses: list[str]) -> bool:
    return any(
        "Exception" in superclass or "Error" in superclass
        for superclass in superclasses
    )
