"""#1899: a supertype dispatch gap with listed callers is never ``complete``.

.. code-block:: java

    interface I { void m(); default void run() { m(); } }
    class A { public void m() {} }
    class B extends A implements I {}
    class Main { void go(A a) { a.m(); } }   // a listed caller of A.m

#1894 / #1895 made ``A.m`` answer ``OVERRIDE_DISPATCH`` with 0 callers. With a
listed caller the dispatch site (``m()`` in ``I.run``) is still not listed, so
the answer must be ``incomplete`` with the same reason. The ``supertype_dispatch``
check runs whatever the caller count (``assess_completeness`` passes listed
answers through the same gates and downgrades them to ``incomplete``); these
tests guard that for every supertype path: the Java subtype proof (#1894), the
Java override proof with and without ``@Override`` (PR-2 / #1884), the Python
unfollowable base (#1883) and subclass (#1896, in ``test_callers_py_subtypes``),
and the JS/TS unfollowable ``extends`` (#1882, in
``test_callers_dynamic_supertype``).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_py_supertypes
from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_supertypes import (
    DYNAMIC_SUPERTYPE_REASON,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

#: The #1894 repro.
_REPRO = {
    "p/I.java": (
        "package p;\n"
        "public interface I {\n"
        "  void m();\n"
        "  default void run() { m(); }\n"
        "}\n"
    ),
    "p/A.java": "package p;\npublic class A {\n  public void m() {}\n}\n",
    "p/B.java": "package p;\npublic class B extends A implements I {}\n",
}


def _caller(cls: str, body: str, package: str = "p") -> str:
    imports = "" if package == "p" else "import p.A;\n"
    return f"package {package};\n{imports}public class {cls} {{\n{body}}}\n"


_ONE = {"p/Main.java": _caller("Main", "  void go(A a) { a.m(); }\n")}
_SEVERAL = {
    "p/Main.java": _caller(
        "Main", "  void go(A a) { a.m(); }\n  void again(A a) { a.m(); }\n"
    ),
    "p/Other.java": _caller("Other", "  void use(A a) { a.m(); }\n"),
}
_OTHER_PACKAGE = {"r/Use.java": _caller("Use", "  void go(A a) { a.m(); }\n", "r")}
#: A subtype that adds no type declaring ``m``: the listed answer stays complete.
_PLAIN = {
    "p/J.java": "package p;\npublic interface J {\n  void other();\n}\n",
    "p/B.java": (
        "package p;\npublic class B extends A implements J {\n"
        "  public void other() {}\n}\n"
    ),
}

#: The override paths (#1884: ``A<String>`` has no ``extends`` edge, so the
#: call in ``A.run`` is bound to ``A.make`` and is not a name-only site).
_OVERRIDE = {
    "o/A.java": (
        "package o;\n"
        "public abstract class A<T> {\n"
        "  public T run() { return make(); }\n"
        "  protected abstract T make();\n"
        "}\n"
    ),
    "o/B.java": (
        "package o;\n"
        "public class B extends A<String> {\n"
        '  protected String make() { return "b"; }\n'
        "}\n"
    ),
    "o/C.java": (
        "package o;\n"
        "public class C extends A<String> {\n"
        "  @Override\n"
        '  protected String make() { return "c"; }\n'
        "}\n"
    ),
}

#: #1883: a Python member under a base the index cannot follow, with a caller.
_PY_MIXIN = {
    "a.py": "class Proc:\n    def run(self):\n        return 0\n",
    "b.py": (
        "from a import Proc\n\n\n"
        "def mix(base):\n    return base\n\n\n"
        "class V1(mix(Proc)):\n"
        "    def only(self):\n        return 1\n\n"
        "    def use(self):\n        return self.only()\n"
    ),
}


async def _answer(tmp_path, files: dict[str, str], name: str) -> dict:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    callers_py_supertypes.clear_parsed()
    for rel_path, text in files.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return await CodeGraphCallersTool(str(tmp_path)).execute(
        {"function_name": name, "include_bodies": False}
    )


def _incomplete(result: dict, count: int, reason: str) -> None:
    assert result["caller_count"] == count, result
    assert result["completeness"] == "incomplete", result
    assert result["completeness_reasons"] == [reason], result


# --- Java subtype dispatch (#1894) ---------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("callers", "count"),
    [(_ONE, 1), (_SEVERAL, 3), (_OTHER_PACKAGE, 1)],
    ids=["one-direct-caller", "several-callers", "caller-in-another-package"],
)
async def test_subtype_dispatch_with_listed_callers_is_incomplete(
    tmp_path, callers, count
) -> None:
    result = await _answer(tmp_path, {**_REPRO, **callers}, "A.m")

    _incomplete(result, count, OVERRIDE_REASON)
    assert "`B`" in result["next_step"], result["next_step"]
    assert "`I.m`" in result["next_step"], result["next_step"]
    assert "p/I.java:4" in result["next_step"], result["next_step"]


@pytest.mark.asyncio
async def test_listed_callers_without_a_dispatch_site_stay_complete(
    tmp_path,
) -> None:
    result = await _answer(tmp_path, {**_REPRO, **_ONE, **_PLAIN}, "A.m")

    assert result["caller_count"] == 1, result
    assert result["completeness"] == "complete", result


# --- Java override dispatch (PR-2 / #1884) --------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", ["B", "C"], ids=["unannotated", "override"])
async def test_override_dispatch_with_a_listed_caller_is_incomplete(
    tmp_path, cls: str
) -> None:
    files = {
        "o/A.java": _OVERRIDE["o/A.java"],
        f"o/{cls}.java": _OVERRIDE[f"o/{cls}.java"],
        "o/Main.java": (
            "package o;\npublic class Main {\n"
            f"  String go({cls} x) {{ return x.make(); }}\n}}\n"
        ),
    }

    result = await _answer(tmp_path, files, f"{cls}.make")

    _incomplete(result, 1, OVERRIDE_REASON)
    assert "o/A.java:3" in result["next_step"], result["next_step"]


# --- Python unfollowable base (#1883) -------------------------------------------


@pytest.mark.asyncio
async def test_python_dynamic_base_with_a_listed_caller_is_incomplete(
    tmp_path,
) -> None:
    result = await _answer(tmp_path, _PY_MIXIN, "V1.only")

    _incomplete(result, 1, DYNAMIC_SUPERTYPE_REASON)
    assert "`mix(Proc)`" in result["next_step"], result["next_step"]
