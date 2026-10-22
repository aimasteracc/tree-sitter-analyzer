"""#1743：Java 经声明类型的调用（虚分派）。

规则：``x.m()`` 中 ``x`` 的静态类型为 ``S`` 时，``S.m``（或 ``S`` 最近的项目祖先上的
``m``）是确定目标；``S`` 的子类型（``extends`` / ``implements``）中的覆写是可能目标
（``name_only_sites`` / ``NAME_ONLY_INBOUND``），从不确定，也从不省略。

dogfood 第 10 轮 gson：经超类型 / 接口接收者的调用 0/11 被列出；经声明类型的调用
（``gson.getDelegateAdapter`` 等）全部只是同名匹配。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

P = "src/main/java/com/ex/"
_FILES = {
    P
    + "Shape.java": "package com.ex;\n\npublic interface Shape {\n  double area();\n}\n",
    P + "AbstractShape.java": (
        "package com.ex;\n\npublic abstract class AbstractShape implements Shape {\n"
        "  public abstract double area();\n\n"
        '  public String describe() {\n    return "a" + area();\n  }\n}\n'
    ),
    P + "Circle.java": (
        "package com.ex;\n\npublic class Circle extends AbstractShape {\n"
        "  @Override\n  public double area() {\n    return 3.14;\n  }\n}\n"
    ),
    P + "Square.java": (
        "package com.ex;\n\npublic class Square extends AbstractShape {\n"
        "  @Override\n  public double area() {\n    return 1;\n  }\n\n"
        "  public double side() {\n    return 1;\n  }\n}\n"
    ),
    P + "Box.java": (
        "package com.ex;\n\npublic class Box<T extends Shape> {\n  private final T item;\n\n"
        "  public Box(T item) {\n    this.item = item;\n  }\n\n"
        "  public T get() {\n    return item;\n  }\n\n"
        "  public double size() {\n    return item.area();\n  }\n}\n"
    ),
    P + "Printer.java": (
        "package com.ex;\n\npublic class Printer {\n"
        "  public void print(int x) {}\n\n  public void print(String s) {}\n\n"
        "  public int size() {\n    return 0;\n  }\n}\n"
    ),
    P + "Use.java": (
        "package com.ex;\n\nimport java.util.List;\n\npublic class Use {\n"
        "  private AbstractShape field;\n  private Printer shadow;\n\n"
        "  double a(Shape s) {\n    return s.area();\n  }\n\n"
        "  double b(Circle c) {\n    return c.area();\n  }\n\n"
        "  double c() {\n    Square sq = new Square();\n    return sq.side();\n  }\n\n"
        "  String d() {\n    this.field.area();\n    return field.describe();\n  }\n\n"
        "  Shape e(Box<Circle> box) {\n    return box.get();\n  }\n\n"
        "  double f(List<Shape> shapes) {\n    double t = 0;\n"
        "    for (Shape s : shapes) {\n      t += s.area();\n    }\n    return t + shapes.size();\n  }\n\n"
        "  void g(Printer p) {\n    p.print(1);\n  }\n\n"
        "  int h() {\n    int n = shadow.size();\n    Square shadow = new Square();\n    return n;\n  }\n}\n"
    ),
}


async def _index(root: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in _FILES.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


@pytest.fixture
async def project(tmp_path) -> str:
    return await _index(tmp_path)


async def _answers(root: str, qual: str, file_name: str) -> list[dict]:
    """限定名与裸名两种问法（#1740）：两者必须一致地遵守规则。"""
    bare = qual.rsplit(".", 1)[-1]
    out = []
    for name in (qual, bare):
        out.append(
            await CodeGraphCallersTool(root).execute(
                {
                    "function_name": name,
                    "file_path": P + file_name,
                    "include_bodies": False,
                }
            )
        )
    return out


def _callers(result: dict) -> set[str]:
    return {c["name"] for c in result.get("callers") or []}


def _possible(result: dict) -> set[str]:
    return {s["caller"].rsplit(".", 1)[-1] for s in result.get("name_only_sites") or []}


@pytest.mark.asyncio
async def test_interface_receiver_binds_the_interface_method(project) -> None:
    for result in await _answers(project, "Shape.area", "Shape.java"):
        assert {"a", "f"} <= _callers(result)
        assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_override_lists_supertype_receivers_as_possible_never_certain(
    project,
) -> None:
    for result in await _answers(project, "Circle.area", "Circle.java"):
        assert _callers(result) == {"b"}
        # Shape / AbstractShape receivers and the implicit this.area() in describe()
        # may dispatch to Circle.area: possible, never omitted.
        assert {"a", "d", "f", "describe"} <= _possible(result)
        assert "NAME_ONLY_INBOUND" in result["completeness_reasons"]
        assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_abstract_class_receiver_and_implicit_this(project) -> None:
    for result in await _answers(project, "AbstractShape.area", "AbstractShape.java"):
        assert {"describe", "d"} <= _callers(result)
    for result in await _answers(
        project, "AbstractShape.describe", "AbstractShape.java"
    ):
        assert _callers(result) == {"d"}
        assert result["completeness"] == "complete"


@pytest.mark.asyncio
async def test_local_and_generic_typed_receivers_bind(project) -> None:
    for result in await _answers(project, "Square.side", "Square.java"):
        assert _callers(result) == {"c"}
        assert result["completeness"] == "complete"
    # ``Box<Circle> box`` is a Box: the type argument is dropped.
    for result in await _answers(project, "Box.get", "Box.java"):
        assert _callers(result) == {"e"}
        assert result["completeness"] == "complete"


@pytest.mark.asyncio
async def test_type_variable_receiver_is_not_bound(project) -> None:
    # ``T item`` with ``<T extends Shape>``: the type variable is not a project class.
    for result in await _answers(project, "Shape.area", "Shape.java"):
        assert "size" not in _callers(result)
    for result in await _answers(project, "Circle.area", "Circle.java"):
        assert "size" not in _callers(result)
        assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_overloaded_method_is_not_bound(project) -> None:
    for result in await _answers(project, "Printer.print", "Printer.java"):
        assert "g" not in _callers(result)
        assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_external_type_and_shadowed_field_are_not_bound(project) -> None:
    # ``shapes.size()`` is java.util.List.size; ``shadow.size()`` before a local
    # ``Square shadow`` refers to the Printer field but cannot be told apart by name.
    for result in await _answers(project, "Printer.size", "Printer.java"):
        assert "f" not in _callers(result)
        assert "h" not in _callers(result)


_ANON = {
    P + "Adapter.java": (
        "package com.ex;\n\npublic abstract class Adapter<T> {\n  abstract long[] values(T t);\n\n"
        "  public long first(T t) {\n    return values(t)[0];\n  }\n}\n"
    ),
    P + "Adapters.java": (
        "package com.ex;\n\npublic final class Adapters {\n"
        "  static final Adapter<String> STRING =\n      new Adapter<String>() {\n"
        "        @Override\n        long[] values(String s) {\n          return new long[] {s.length()};\n        }\n      };\n}\n"
    ),
    P + "Client.java": (
        'package com.ex;\n\npublic class Client {\n  long a(Adapter<String> ad) {\n    return ad.values("x")[0];\n  }\n}\n'
    ),
}


@pytest.mark.asyncio
async def test_anonymous_subclass_override_lists_base_class_dispatch(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in _ANON.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True

    result = await CodeGraphCallersTool(str(tmp_path)).execute(
        {
            "function_name": "values",
            "file_path": P + "Adapters.java",
            "include_bodies": False,
        }
    )

    # gson ``IntegerFieldsTypeAdapter.write`` calls the abstract ``integerValues(value)``;
    # the anonymous ``new IntegerFieldsTypeAdapter<Period>() {...}`` override may run.
    assert {"first", "a"} <= _possible(result)
    assert result["completeness"] != "complete"
