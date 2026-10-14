"""#1593：方法以非调用方式被使用时，``0 callers`` 不得宣称 ``complete``。

RFC-0028 §1.1 的单向不变式：调用图只记录调用边，回调传递（``callback=obj.m``）、
属性读取（``obj.prop``）与反射（``getattr(obj, "m")``）都不产生调用边。
答案为 0 时，必须先确认同语言源码中没有可能指向该名字的非调用引用，
且目标不是 ``@property`` 之类的访问器，才可以说 ``complete``。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_WIDGET = (
    "class Widget:\n"
    "    def _style(self, item):\n"
    "        return item\n\n"
    "    @property\n"
    "    def is_built(self):\n"
    "        return True\n\n"
    "    @property\n"
    "    def never_read(self):\n"
    "        return 0\n\n"
    "    def unused(self):\n"
    "        # unused 只出现在注释里\n"
    '        """unused 也只出现在文档字符串里。"""\n'
    "        return 0\n\n"
    "    def _hidden(self):\n"
    "        return 1\n\n\n"
    "def register(callback):\n"
    "    return callback\n\n\n"
    "def wire(w):\n"
    "    register(callback=w._style)\n"
    "    return getattr(w, '_hidden')\n\n\n"
    "def probe(w):\n"
    "    return 1 if w.is_built else 0\n"
)
#: 另一种语言里同名属性的读取不得影响 Python 方法的答案。
_OTHER_LANGUAGE = "function touch(w) {\n  return w.unused;\n}\n"


@pytest.fixture
async def widget_root(tmp_path):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (tmp_path / "touch.js").write_text(_OTHER_LANGUAGE, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


@pytest.mark.asyncio
async def test_bound_method_passed_as_callback_is_not_complete(widget_root) -> None:
    # #1593：`register(callback=w._style)` 不是调用边，却是真实的使用。
    result = await _callers(widget_root, "Widget._style")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_references"] == 1
    assert result["non_call_reference_sites"] == [{"file": "widget.py", "line": 27}]


@pytest.mark.asyncio
async def test_callback_absence_hint_names_the_reference_site(widget_root) -> None:
    # #1593：提示必须点名非调用引用的位置，而不是“没有调用边到达它”。
    result = await _callers(widget_root, "Widget._style")

    assert result["next_step"] == (
        "No resolved caller for 'Widget._style', but 1 non-call reference(s) "
        "(attribute access, bare name, or string name) could reach it: "
        "widget.py:27. Read those sites before treating this as absence."
    )
    assert result["agent_summary"]["summary_line"] == (
        "callers: 'Widget._style' has 0 resolved caller(s); "
        "this is not evidence of absence"
    )


@pytest.mark.asyncio
async def test_property_read_as_attribute_is_not_complete(widget_root) -> None:
    # #1593：`w.is_built` 是属性读取，调用图里永远不会有它的调用边。
    result = await _callers(widget_root, "Widget.is_built")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "ACCESSOR_NOT_CALL_EDGES"
    assert result["non_call_references"] == 1


@pytest.mark.asyncio
async def test_property_never_answers_complete_from_call_edges(widget_root) -> None:
    # #1593：即使找不到读取点，@property 也不能凭调用边宣称 complete。
    result = await _callers(widget_root, "Widget.never_read")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "ACCESSOR_NOT_CALL_EDGES",
    )
    assert result["non_call_references"] == 0


@pytest.mark.asyncio
async def test_string_named_reflection_counts_as_a_reference(widget_root) -> None:
    # #1593：`getattr(w, '_hidden')` 以字符串名使用方法，同样不是调用边。
    result = await _callers(widget_root, "Widget._hidden")

    assert (result["completeness"], result["non_call_references"]) == ("unknown", 1)
    assert result["non_call_reference_sites"] == [{"file": "widget.py", "line": 28}]


@pytest.mark.asyncio
async def test_truly_unreferenced_method_is_still_complete(widget_root) -> None:
    # #1593：注释、文档字符串与另一种语言里的同名读取都不是引用；真正无人使用的
    # 方法仍然答 complete。
    result = await _callers(widget_root, "Widget.unused")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert result["completeness_reason"] is None
    assert result["non_call_references"] == 0
    assert result["next_step"] == (
        "'Widget.unused' is defined in the index and no resolved call edge reaches it."
    )


@pytest.mark.asyncio
async def test_scan_over_budget_is_unknown_not_complete(
    widget_root, monkeypatch
) -> None:
    # #1593：预算内扫描不完时只能答 unknown，绝不以部分结果冒充 complete。
    from tree_sitter_analyzer.mcp.tools import callers_absence

    monkeypatch.setattr(callers_absence, "_SCAN_DEADLINE_SECONDS", -1.0)

    result = await _callers(widget_root, "Widget.unused")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "NON_CALL_REFERENCES_UNCHECKED",
    )
    assert result["non_call_references"] is None


def test_unrevalidated_scope_downgrades_complete() -> None:
    # #1594：范围复核失败（SOURCE_SCOPE_UNKNOWN）与 stale 一样不能支撑普查。
    from tree_sitter_analyzer.mcp.tools.callers_absence import assess_completeness

    evidence = {"freshness": "unknown", "reason": "SOURCE_SCOPE_UNKNOWN"}
    verdict = assess_completeness(None, None, "f", None, "complete", 2, evidence)

    assert (verdict.completeness, verdict.reason) == (
        "incomplete",
        "SOURCE_SCOPE_UNKNOWN",
    )
    assert verdict.hint == (
        "No resolved caller for 'f', but the source could not be revalidated "
        "against the index, so this is not evidence of absence."
    )


def test_typescript_getter_is_an_accessor(tmp_path) -> None:
    # #1593：TS/JS 的 get 访问器与 @property 一样，读取不产生调用边。
    from tree_sitter_analyzer.mcp.tools.callers_absence import _is_accessor

    (tmp_path / "w.ts").write_text(
        "class W {\n  get size(): number {\n    return 1;\n  }\n}\n", encoding="utf-8"
    )

    assert _is_accessor(str(tmp_path), [("w.ts", 2, "typescript")], "size") is True
    assert _is_accessor(str(tmp_path), [("w.ts", 2, "typescript")], "other") is False


def test_c_family_comments_and_prose_strings_are_not_references() -> None:
    # #1593：C 系语言的注释与普通字符串剔除，恰为名字的字符串保留（反射）。
    import re

    from tree_sitter_analyzer.mcp.tools.callers_absence import (
        _reference_lines,
        _strip_comments_and_prose,
    )

    source = (
        "// size is documented here\n"
        "/* size\n   spans lines */\n"
        'log("the size is fine");\n'
        'const k = "size";\n'
        "const v = w.size;\n"
        "w.size();\n"
    )
    text = _strip_comments_and_prose(source, "javascript")

    assert _reference_lines(text, re.compile(r"(?<![\w$])size(?![\w$])")) == [5, 6]


def test_python_f_string_interpolation_is_kept() -> None:
    # #1593：f-string 插值可以引用名字，必须保留而不是当作普通字符串剔除。
    import re

    from tree_sitter_analyzer.mcp.tools.callers_absence import (
        _reference_lines,
        _strip_comments_and_prose,
    )

    text = _strip_comments_and_prose('x = f"{w.size}"\ny = "size of w"\n', "python")

    assert _reference_lines(text, re.compile(r"(?<![\w$])size(?![\w$])")) == [1]
