"""Hypothesis 生成器：小型多文件 Python 项目（``nav callers`` 判定器属性测试用）。

生成的项目只用独立判定器（``scripts.wrong_complete.py_oracle``）能精确判定的
构造：类与继承、``typing.Protocol``、``@overload``、模块级 / 导入别名、分派表、
``getattr``、未类型化接收者、多个类里的同名方法、``self`` / ``super()`` 调用、
构造实例、注解形参、``Cls.m(obj)``，以及模块级函数的直接 / 改名 / 模块属性调用。

``ProjectSpec`` 是纯数据；``render(spec, names)`` 把它渲染成源码，``names`` 控制
所有别名与局部变量的拼写——同一 spec 用两套 ``names`` 渲染即“不改变调用语义的
改名”（不变量 d）。
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import strategies as st

from scripts.wrong_complete.sites import Target

#: 目标方法名与干扰方法名。
METHOD = "handle"
OTHER_METHOD = "reset"
#: 模块级目标函数名。
FUNCTION = "tool"
CLASS_MODULES = ("app/m0.py", "app/m1.py")
#: ``test_module`` 为真时第二个类模块放在测试文件里（#1772：测试里的结构实现）。
TEST_CLASS_MODULE = "tests/test_impl.py"
CALLER_MODULES = ("app/c0.py", "app/c1.py")

#: 调用模板（在调用方模块的函数里）。
CLASS_TEMPLATES = (
    "ctor",
    "local",
    "annotated",
    "untyped",
    "static",
    "module_alias",
    "import_alias",
    "table",
    "getattr",
)
#: 调用模板（在类体里，作为该类的方法）。
METHOD_TEMPLATES = ("self", "super")
FUNCTION_TEMPLATES = ("direct", "alias", "module_attr", "untyped_attr")

#: 两套拼写：``render(spec, NAMES_A)`` 与 ``render(spec, NAMES_B)`` 调用语义相同。
NAMES_A = {
    "local": "obj",
    "param": "item",
    "alias": "Alias",
    "imported": "Kind",
    "table": "TABLE",
    "fn_alias": "use_tool",
    "module": "m0mod",
}
NAMES_B = {
    "local": "inst",
    "param": "thing",
    "alias": "Renamed",
    "imported": "Sort",
    "table": "HANDLERS",
    "fn_alias": "apply_tool",
    "module": "zeromod",
}


@dataclass(frozen=True)
class ClassSpec:
    """一个类：所在模块、基类（``None`` / ``"Protocol"`` / 更早的类下标）、方法。"""

    module: int
    base: int | str | None
    methods: tuple[str, ...]
    overload: bool


@dataclass(frozen=True)
class CallSpec:
    """一个调用点：模板、涉及的类下标、调用的方法名、所在调用方模块。"""

    template: str
    cls: int
    method: str
    caller_module: int


@dataclass(frozen=True)
class ProjectSpec:
    """一个生成的项目与它的查询目标（``target_class`` 为 ``None`` 时目标是 ``tool``）。"""

    classes: tuple[ClassSpec, ...]
    calls: tuple[CallSpec, ...]
    target_class: int | None
    test_module: bool = False

    def module_path(self, index: int) -> str:
        """第 ``index`` 个类模块的相对路径。"""
        return (
            TEST_CLASS_MODULE
            if index == 1 and self.test_module
            else CLASS_MODULES[index]
        )

    def module_dotted(self, index: int) -> str:
        """第 ``index`` 个类模块的点分模块名。"""
        return self.module_path(index)[:-3].replace("/", ".")


@st.composite
def _class_specs(draw: st.DrawFn) -> tuple[ClassSpec, ...]:
    count = draw(st.integers(min_value=1, max_value=4))
    specs: list[ClassSpec] = []
    for index in range(count):
        base_choices: list[int | str | None] = [None, "Protocol", *range(index)]
        base = draw(st.sampled_from(base_choices))
        methods = draw(
            st.sets(
                st.sampled_from((METHOD, OTHER_METHOD)),
                min_size=1 if base == "Protocol" else 0,
            )
        )
        overload = METHOD in methods and base != "Protocol" and draw(st.booleans())
        specs.append(ClassSpec(index % 2, base, tuple(sorted(methods)), overload))
    return tuple(specs)


@st.composite
def projects(draw: st.DrawFn) -> ProjectSpec:
    """生成一个项目规格（目标是某个声明了 ``handle`` 的类，或模块级函数 ``tool``）。"""
    classes = list(draw(_class_specs()))
    target: int | None = None
    if draw(st.integers(min_value=0, max_value=3)):
        # 3/4 的样例以方法为目标；没有类声明 handle 时让第 0 个类声明它。
        holders = [
            i
            for i, c in enumerate(classes)
            if METHOD in c.methods and c.base != "Protocol"
        ]
        if not holders:
            first = classes[0]
            classes[0] = ClassSpec(
                first.module,
                None,
                tuple(sorted({*first.methods, METHOD})),
                first.overload,
            )
            holders = [0]
        target = draw(st.sampled_from(holders))
    call_count = draw(st.integers(min_value=2, max_value=7))
    calls: list[CallSpec] = []
    for _ in range(call_count):
        # 偏向目标类与目标方法：让多数样例里 complete 回答确有必须覆盖的调用点。
        cls_pool = list(range(len(classes))) + (
            [target] * len(classes) if target is not None else []
        )
        cls = draw(st.sampled_from(cls_pool))
        if target is None:
            pool = list(FUNCTION_TEMPLATES) * 3 + list(CLASS_TEMPLATES)
        else:
            pool = list(CLASS_TEMPLATES) + list(FUNCTION_TEMPLATES[:1])
            if classes[cls].base != "Protocol":
                pool += (
                    list(METHOD_TEMPLATES) * 2
                    if isinstance(classes[cls].base, int)
                    else ["self", "self"]
                )
        template = draw(st.sampled_from(pool))
        method = draw(st.sampled_from((METHOD, METHOD, METHOD, OTHER_METHOD)))
        calls.append(
            CallSpec(template, cls, method, draw(st.integers(min_value=0, max_value=1)))
        )
    return ProjectSpec(tuple(classes), tuple(calls), target, draw(st.booleans()))


def class_name(index: int) -> str:
    """第 ``index`` 个类的名字。"""
    return f"C{index}"


def _class_source(spec: ProjectSpec, index: int, body_calls: list[str]) -> list[str]:
    cls = spec.classes[index]
    if cls.base == "Protocol":
        header = f"class {class_name(index)}(Protocol):"
    elif isinstance(cls.base, int):
        header = f"class {class_name(index)}({class_name(cls.base)}):"
    else:
        header = f"class {class_name(index)}:"
    lines = [header]
    for method in cls.methods:
        if cls.base == "Protocol":
            lines.append(f"    def {method}(self): ...")
            continue
        if method == METHOD and cls.overload:
            lines += [
                "    @overload",
                f"    def {method}(self, x: int) -> int: ...",
                "    @overload",
                f"    def {method}(self, x: str) -> str: ...",
            ]
        lines += [f"    def {method}(self, x=None):", "        return x"]
    lines += body_calls
    if len(lines) == 1:
        lines.append("    pass")
    return lines + ["", ""]


def _method_call(call: CallSpec, number: int) -> list[str]:
    """类体里的 ``self.m()`` / ``super().m()`` 调用方法 ``use{number}``。"""
    if call.template == "self":
        expr = f"self.{call.method}()"
    else:
        expr = f"super().{call.method}()"
    return [f"    def use{number}(self):", f"        return {expr}"]


def _function_call(
    spec: ProjectSpec, call: CallSpec, number: int, names: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """``(imports, module_level, function_lines)``。"""
    cname = class_name(call.cls)
    module = spec.module_dotted(spec.classes[call.cls].module)
    m = call.method
    imports = [f"from {module} import {cname}"]
    top: list[str] = []
    params = ""
    t = call.template
    if t == "ctor":
        body = f"return {cname}().{m}()"
    elif t == "local":
        body = f"{names['local']} = {cname}()\n    return {names['local']}.{m}()"
    elif t == "annotated":
        params, body = f"{names['param']}: {cname}", f"return {names['param']}.{m}()"
    elif t == "untyped":
        params, body = names["param"], f"return {names['param']}.{m}()"
    elif t == "static":
        body = f"return {cname}.{m}({cname}())"
    elif t == "module_alias":
        alias = f"{names['alias']}{number}"
        top, body = [f"{alias} = {cname}"], f"return {alias}().{m}()"
    elif t == "import_alias":
        alias = f"{names['imported']}{number}"
        imports, body = (
            [f"from {module} import {cname} as {alias}"],
            f"return {alias}().{m}()",
        )
    elif t == "table":
        table = f"{names['table']}{number}"
        top, body = [f'{table} = {{"k": {cname}().{m}}}'], f'return {table}["k"]()'
    elif t == "getattr":
        body = f'return getattr({cname}(), "{m}")()'
    elif t == "direct":
        imports, body = [f"from app.m0 import {FUNCTION}"], f"return {FUNCTION}(1)"
    elif t == "alias":
        alias = f"{names['fn_alias']}{number}"
        imports, body = (
            [f"from app.m0 import {FUNCTION} as {alias}"],
            f"return {alias}(1)",
        )
    elif t == "module_attr":
        imports, body = (
            [f"import app.m0 as {names['module']}"],
            f"return {names['module']}.{FUNCTION}(1)",
        )
    else:
        params, body = names["param"], f"return {names['param']}.{FUNCTION}(1)"
    return imports, top, [f"def call{number}({params}):", f"    {body}", "", ""]


def render(spec: ProjectSpec, names: dict[str, str]) -> dict[str, str]:
    """渲染成 ``{相对路径: 源码}``。"""
    class_bodies: dict[int, list[str]] = {i: [] for i in range(len(spec.classes))}
    callers: dict[int, tuple[list[str], list[str], list[str]]] = {
        0: ([], [], []),
        1: ([], [], []),
    }
    for number, call in enumerate(spec.calls):
        if call.template in METHOD_TEMPLATES:
            class_bodies[call.cls] += _method_call(call, number)
            continue
        imports, top, lines = _function_call(spec, call, number, names)
        bucket = callers[call.caller_module]
        bucket[0].extend(i for i in imports if i not in bucket[0])
        bucket[1].extend(top)
        bucket[2].extend(lines)
    files = {"app/__init__.py": ""}
    if spec.test_module:
        files["tests/__init__.py"] = ""
    for module_index in range(len(CLASS_MODULES)):
        path = spec.module_path(module_index)
        head = ["from typing import Protocol, overload", ""]
        for cls in spec.classes:
            if cls.module == module_index and isinstance(cls.base, int):
                base_module = spec.classes[cls.base].module
                if base_module != module_index:
                    head.insert(
                        1,
                        f"from {spec.module_dotted(base_module)} import {class_name(cls.base)}",
                    )
        body: list[str] = ["", ""]
        if module_index == 0:
            body += [f"def {FUNCTION}(x):", "    return x", "", ""]
        for i, cls in enumerate(spec.classes):
            if cls.module == module_index:
                body += _class_source(spec, i, class_bodies[i])
        files[path] = "\n".join(head + body).rstrip() + "\n"
    for module_index, path in enumerate(CALLER_MODULES):
        imports, top, lines = callers[module_index]
        text = "\n".join([*imports, "", "", *top, "", "", *lines]).strip()
        files[path] = (text + "\n") if text else ""
    return files


def target_of(spec: ProjectSpec, files: dict[str, str]) -> Target:
    """查询目标：类 ``C{i}.handle`` 的实现定义行，或 ``app/m0.py`` 的 ``tool``。"""
    if spec.target_class is None:
        lines = files["app/m0.py"].splitlines()
        line = next(
            n for n, text in enumerate(lines, 1) if text.startswith(f"def {FUNCTION}(")
        )
        return Target("app/m0.py", FUNCTION, None, line)
    path = spec.module_path(spec.classes[spec.target_class].module)
    lines = files[path].splitlines()
    header = next(
        n
        for n, text in enumerate(lines, 1)
        if text.startswith(f"class {class_name(spec.target_class)}")
    )
    impl = next(
        n
        for n, text in enumerate(lines, 1)
        if n > header and text == f"    def {METHOD}(self, x=None):"
    )
    return Target(path, METHOD, class_name(spec.target_class), impl)


def with_unrelated(files: dict[str, str]) -> dict[str, str]:
    """不变量 c：加一个从未被调用、与任何类都无关的同名方法。"""
    extra = f"class Unrelated:\n    def {METHOD}(self, x=None):\n        return x\n\n\ndef {FUNCTION}(x):\n    return x\n"
    return {**files, "app/zz_unrelated.py": extra}
