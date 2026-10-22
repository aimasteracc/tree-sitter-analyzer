"""#1743：Java 调用 ``x.m()`` 的接收者声明类型（交给 Synapse 按静态类型绑定）。

Java 的变量都有声明类型：形参、局部变量、增强 for 变量、catch 参数与外围类的字段。
这里在提取时为接收者是 ``x`` 或 ``this.x`` 的调用写下 ``receiver_hint``
（``{"type": "Gson", "source": "param"}``），解析阶段再把类型名解析为项目类、在
类及其项目祖先上找方法（``synapse_resolver/_java_typed.py``）。

只记录能确定的类型：

* 基本类型、数组、``var``、通配与类型变量以外的引用类型；泛型去掉类型实参
  （``TypeAdapter<T>`` 记为 ``TypeAdapter``），限定名保留（``JsonReader.Token``）；
* 同一方法里同名变量以不同类型声明（不同块中的同名局部）时不记录；
* 局部 / 形参遮蔽字段；``this.x`` 只看字段；
* 外围类由内到外：内部类与匿名类的字段遮蔽外层类的同名字段。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: 不是引用类型的类型节点。
_NON_REFERENCE_TYPES = frozenset(
    {
        "integral_type",
        "floating_point_type",
        "boolean_type",
        "void_type",
        "array_type",
    }
)
#: 不进入的嵌套作用域（它们的方法各自是函数定义）。
_NESTED_SCOPES = frozenset({"class_body", "interface_body", "enum_body"})
#: 可以声明字段的类型声明。
_CLASS_DECLS = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }
)
_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")
_THIS_FIELD = re.compile(r"^this\.([A-Za-z_$][\w$]*)$")
#: 冲突标记：同名变量有多个不同的声明类型。
_CONFLICT = ""

Hint = dict[str, str]


def _text(node: Any) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)


def declared_type(type_node: Any) -> str | None:
    """类型节点的规范名；不可作为接收者类型（基本类型、数组、``var``）时为 None。"""
    if type_node is None or type_node.type in _NON_REFERENCE_TYPES:
        return None
    node = type_node
    if node.type == "generic_type":
        node = next(
            (
                child
                for child in node.children
                if child.type in ("type_identifier", "scoped_type_identifier")
            ),
            None,
        )
        if node is None:
            return None
    if node.type not in ("type_identifier", "scoped_type_identifier"):
        return None
    name = re.sub(r"<[^<>]*>", "", _text(node)).replace(" ", "")
    if name == "var" or not all(_IDENT.match(part) for part in name.split(".")):
        return None
    return name


def _record(names: dict[str, str], name: str, type_name: str | None) -> None:
    if not name or type_name is None:
        if name:
            names[name] = _CONFLICT
        return
    previous = names.get(name)
    names[name] = type_name if previous in (None, type_name) else _CONFLICT


def _declarators(node: Any) -> list[str]:
    return [
        _text(name)
        for declarator in node.children_by_field_name("declarator")
        if (name := declarator.child_by_field_name("name")) is not None
    ]


def method_variables(func_node: Any) -> tuple[dict[str, str], dict[str, str]]:
    """``(形参, 局部)``：名字 -> 声明类型（冲突为空串）。"""
    params: dict[str, str] = {}
    params_node = func_node.child_by_field_name("parameters")
    for child in params_node.children if params_node is not None else ():
        if child.type in ("formal_parameter", "spread_parameter"):
            name = child.child_by_field_name("name")
            if name is None:
                name = next(
                    (
                        c.child_by_field_name("name")
                        for c in child.children
                        if c.type == "variable_declarator"
                    ),
                    None,
                )
            type_node = child.child_by_field_name("type")
            if child.type == "spread_parameter":
                type_node = None  # ``T... xs`` 是数组
            if name is not None:
                _record(params, _text(name), declared_type(type_node))
    locals_: dict[str, str] = {}
    body = func_node.child_by_field_name("body")
    if body is not None:
        _collect_locals(body, locals_)
    return params, locals_


def _collect_locals(node: Any, out: dict[str, str]) -> None:
    for child in node.children:
        kind = child.type
        if kind in _NESTED_SCOPES:
            continue
        if kind == "local_variable_declaration":
            type_name = declared_type(child.child_by_field_name("type"))
            for name in _declarators(child):
                _record(out, name, type_name)
        elif kind == "enhanced_for_statement":
            name = child.child_by_field_name("name")
            if name is not None:
                _record(out, _text(name), declared_type(child.child_by_field_name("type")))
        elif kind == "catch_formal_parameter":
            name = child.child_by_field_name("name")
            catch_types = [c for c in child.children if c.type == "catch_type"]
            type_name = None
            if len(catch_types) == 1 and len(catch_types[0].named_children) == 1:
                type_name = declared_type(catch_types[0].named_children[0])
            if name is not None:
                _record(out, _text(name), type_name)
        elif kind == "lambda_expression":
            params = child.child_by_field_name("parameters")
            for param in params.children if params is not None else ():
                if param.type == "identifier":
                    _record(out, _text(param), None)  # 推断类型：未知
                elif param.type == "formal_parameter":
                    pname = param.child_by_field_name("name")
                    if pname is not None:
                        _record(out, _text(pname), declared_type(param.child_by_field_name("type")))
            if params is not None and params.type == "identifier":
                _record(out, _text(params), None)
        _collect_locals(child, out)


def class_fields(class_body: Any) -> dict[str, str]:
    """类体中直接声明的字段：名字 -> 声明类型（冲突为空串）。"""
    fields: dict[str, str] = {}
    for child in class_body.children:
        if child.type in ("field_declaration", "constant_declaration"):
            type_name = declared_type(child.child_by_field_name("type"))
            for name in _declarators(child):
                _record(fields, name, type_name)
    return fields


def enclosing_fields(func_node: Any) -> list[dict[str, str]]:
    """由内到外每个外围类体（含匿名类）的字段表。"""
    scopes: list[dict[str, str]] = []
    node = func_node.parent
    while node is not None:
        if node.type in _NESTED_SCOPES:
            scopes.append(class_fields(node))
        node = node.parent
    return scopes


@dataclass(frozen=True)
class JavaReceiverHintScope:
    """``_extract_recursive`` 的接收者线索作用域（与 Python 的 ``_ReceiverHintScope`` 同接口）。"""

    params: dict[str, str] = field(default_factory=dict)
    locals: dict[str, str] = field(default_factory=dict)
    fields: tuple[dict[str, str], ...] = ()

    def for_function(self, func_node: Any) -> JavaReceiverHintScope:
        params, locals_ = method_variables(func_node)
        return JavaReceiverHintScope(params, locals_, tuple(enclosing_fields(func_node)))

    def hint_for(self, receiver: str | None, enclosing_class: str | None) -> Hint | None:
        if not receiver:
            return None
        this_field = _THIS_FIELD.match(receiver)
        if this_field is not None:
            return self._field(this_field.group(1))
        if not _IDENT.match(receiver):
            return None
        for source, names in (("local", self.locals), ("param", self.params)):
            if receiver in names:
                type_name = names[receiver]
                if not type_name:
                    return None
                shadowed = self._field(receiver)
                if source == "local" and shadowed and shadowed["type"] != type_name:
                    # 声明之前的 ``x`` 指向同名字段：无法按位置区分时不记录。
                    return None
                return {"type": type_name, "source": source}
        return self._field(receiver)

    def _field(self, name: str) -> Hint | None:
        for scope in self.fields:
            if name in scope:
                type_name = scope[name]
                return {"type": type_name, "source": "field"} if type_name else None
        return None


__all__ = [
    "JavaReceiverHintScope",
    "class_fields",
    "declared_type",
    "enclosing_fields",
    "method_variables",
]
