"""Element construction helpers for the Python language extractor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...models import Class, Function, Variable
from ...utils import log_warning


def node_line_range(node: Any) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


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
        return Variable(
            name=attr_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
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
        modifiers=data.decorators,
        is_static=has_staticmethod,
        is_staticmethod=has_staticmethod,
        is_private=visibility == "private",
        is_public=visibility == "public",
        framework_type=data.framework_type,
        is_property="property" in data.decorators,
        is_classmethod="classmethod" in data.decorators,
        is_constructor=data.is_constructor,
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
    return Class(
        name=data.name,
        start_line=data.start_line,
        end_line=data.end_line,
        raw_text=data.raw_text,
        language="python",
        class_type="class",
        superclass=data.superclasses[0] if data.superclasses else None,
        interfaces=data.superclasses[1:] if len(data.superclasses) > 1 else [],
        docstring=data.docstring,
        modifiers=data.decorators,
        full_qualified_name=_class_full_qualified_name(data.current_module, data.name),
        package_name=data.current_module,
        framework_type=data.framework_type,
        is_dataclass="dataclass" in data.decorators,
        is_abstract="ABC" in data.superclasses or "abstractmethod" in data.raw_text,
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
