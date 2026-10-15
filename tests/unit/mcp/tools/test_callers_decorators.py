"""#1623：装饰器从 AST 读取，豁免只给经导入解析到的已知包装器。

#1614 第一版逐行扫描 ``@`` 行并按裸名豁免：多行 / 夹注释的装饰器不可见，项目
自己的 ``@cache`` 登记器被当作 ``functools.cache``（dogfood 第 5 轮）。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_decorators import (
    UNREADABLE,
    Decorator,
    declaration_decorators,
    registered_hint,
    registering_decorator,
)

_BODY = "def target():\n    return 1\n"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        # 多行装饰器：旧的逐行扫描只看到 `@register(`。
        ('@register(\n    "multi",\n)\n', [Decorator('@register( "multi", )', None)]),
        # 装饰器与 def 之间夹注释：旧扫描在注释行停下。
        ("@register\n# 说明\n", [Decorator("@register", None)]),
        (
            "import functools\n@functools.lru_cache(maxsize=1)\n",
            [Decorator("@functools.lru_cache(maxsize=1)", "functools.lru_cache")],
        ),
        (
            "from functools import cache\n@cache\n",
            [Decorator("@cache", "functools.cache")],
        ),
        (
            "import functools as ft\n@ft.wraps(x)\n",
            [Decorator("@ft.wraps(x)", "functools.wraps")],
        ),
        ("@staticmethod\n", [Decorator("@staticmethod", "builtins.staticmethod")]),
        # 项目自己的 `cache`：本文件绑定了该名字，不是 functools.cache。
        ("def cache(fn):\n    return fn\n@cache\n", [Decorator("@cache", None)]),
        # 未导入、也不是内建包装器的裸名：无法解析。
        ("@cache\n", [Decorator("@cache", None)]),
        # `import *` 之后的裸名可能来自任何模块。
        ("from x import *\n@staticmethod\n", [Decorator("@staticmethod", None)]),
        # 相对导入是项目代码。
        ("from .util import lru_cache\n@lru_cache\n", [Decorator("@lru_cache", None)]),
        # 同一名字两处来源（try/except 回退）：无法确定是哪一个。
        (
            "try:\n    from functools import cache\nexcept ImportError:\n"
            "    from .compat import cache\n@cache\n",
            [Decorator("@cache", None)],
        ),
        (
            "@pytest.mark.parametrize(\n    'x', [1],\n)\n",
            [Decorator("@pytest.mark.parametrize( 'x', [1], )", None)],
        ),
        ("", []),
    ],
)
def test_python_decorators_come_from_the_ast(header: str, expected: list) -> None:
    # #1623：声明行取 def 所在行。
    text = header + _BODY
    line = text.splitlines().index("def target():") + 1

    assert declaration_decorators(text, line, "python") == expected


def test_declaration_line_on_the_first_decorator_also_matches() -> None:
    # #1623：索引可能把声明记在第一个装饰器所在行。
    text = '@register(\n    "x",\n)\n' + _BODY

    assert declaration_decorators(text, 1, "python") == [
        Decorator('@register( "x", )', None)
    ]


def test_line_without_definition_has_no_decorators() -> None:
    # #1623：同名变量等非定义行没有装饰器。
    assert declaration_decorators("target = 1\n", 1, "python") == []


def test_syntax_error_is_unreadable() -> None:
    # #1623：无法解析不等于没有装饰器。
    assert declaration_decorators("@register\ndef target(:\n", 2, "python") is None


#: Java：方法上的多行注解，以及另一方法的参数注解。
_JAVA = (
    "class A {\n"
    "    @Override\n"
    "    @Handler(\n"
    '        "x")\n'
    "    void target() {}\n"
    "    void other(@Named String s) {}\n"
    "}\n"
)
#: TS：方法装饰器挂在 class_body 中、位于方法之前，中间夹注释。
_TS = (
    "class A {\n"
    "  @Get(\n"
    "    '/x')\n"
    "  // note\n"
    "  target() { return 1; }\n"
    "  plain() { return 2; }\n"
    "}\n"
)


def test_java_annotations_are_never_exempt() -> None:
    # #1623：非 Python 声明的注解无法经导入解析，一律视为可能登记。
    assert declaration_decorators(_JAVA, 5, "java") == [
        Decorator("@Override", None),
        Decorator('@Handler( "x")', None),
    ]


def test_java_parameter_annotation_does_not_decorate_the_method() -> None:
    # #1623：参数注解不登记所在方法。
    assert declaration_decorators(_JAVA, 6, "java") == []


def test_typescript_method_decorator_is_read_across_a_comment() -> None:
    # #1623：装饰器与方法之间夹注释仍可见。
    assert declaration_decorators(_TS, 5, "typescript") == [
        Decorator("@Get( '/x')", None)
    ]


def test_typescript_undecorated_method_has_no_decorators() -> None:
    # #1623：上一个方法的装饰器不会算到下一个方法上。
    assert declaration_decorators(_TS, 6, "typescript") == []


def test_language_without_grammar_is_unreadable() -> None:
    # #1623：grammar 不可用时无法读取装饰器，不当作“没有装饰器”。
    assert declaration_decorators("@x\nfun target() {}\n", 2, "no-such-lang") is None


def test_typescript_exported_class_decorator_is_read() -> None:
    # #1623：`@dec export class` 的装饰器挂在 export_statement 上。
    text = "@Component({})\nexport class Target {}\n"

    assert declaration_decorators(text, 2, "typescript") == [
        Decorator("@Component({})", None)
    ]


def test_registering_decorator_reports_first_non_wrapper(tmp_path) -> None:
    # #1623：已知包装器之后的登记器仍被报告。
    (tmp_path / "m.py").write_text(
        "import functools\n\n\n@functools.wraps(f)\n@register\n" + _BODY,
        encoding="utf-8",
    )

    assert registering_decorator(str(tmp_path), [("m.py", 6, "python")]) == (
        "@register"
    )


def test_unreadable_declaration_reports_unreadable(tmp_path) -> None:
    # #1623：读取失败不等于没有装饰器。
    assert registering_decorator(str(tmp_path), [("gone.py", 1, "python")]) == (
        UNREADABLE
    )


def test_unreadable_hint_names_the_gap() -> None:
    # #1623：不可读时 hint 不假装点名某个装饰器。
    assert registered_hint("target", UNREADABLE) == (
        "No resolved caller for 'target', and the decorators on its declaration "
        "could not be read, so a registering decorator cannot be ruled out and "
        "this is not evidence of absence."
    )
