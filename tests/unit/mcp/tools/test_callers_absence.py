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
    (tmp_path / "gadget.py").write_text(
        "class Gadget:\n    def spin(self):\n        return 2\n"
    )
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


@pytest.mark.parametrize(
    ("completeness", "callers"),
    [("unknown", 0), ("incomplete", 3), ("complete", 3)],
)
def test_only_an_edge_complete_absence_is_rechecked(completeness, callers) -> None:
    # #1593：非 complete 的答案与非空列表都原样返回，不做额外扫描。
    from tree_sitter_analyzer.mcp.tools.callers_absence import assess_completeness

    scoped = {"freshness": "unknown", "reason": "SOURCE_REVALIDATION_SCOPED"}
    verdict = assess_completeness(None, ".", "f", None, completeness, callers, scoped)

    assert (verdict.completeness, verdict.reason, verdict.fields) == (
        completeness,
        None,
        {},
    )


def test_unreadable_definition_is_unchecked_not_complete() -> None:
    # #1606：定义行读取失败时存在性未知，不是“已定义且无人调用”。
    from tree_sitter_analyzer.mcp.tools.callers_absence import assess_completeness

    scoped = {"freshness": "unknown", "reason": "SOURCE_REVALIDATION_SCOPED"}
    verdict = assess_completeness(object(), ".", "W.f", None, "complete", 0, scoped)

    assert (verdict.completeness, verdict.reason) == (
        "unknown",
        "SYMBOL_DEFINITION_UNCHECKED",
    )
    assert verdict.fields == {"target_defined": None, "close_matches": []}
    assert verdict.hint == (
        "Whether 'W.f' is defined in the index could not be read, so 0 callers "
        "is not evidence of absence."
    )


def test_unreadable_declarations_are_unchecked_not_complete(monkeypatch) -> None:
    # #1593：目标已定义但声明行读取失败，仍不是“没有引用”。
    from tree_sitter_analyzer.mcp.tools import callers_absence
    from tree_sitter_analyzer.mcp.tools.callers_target import TargetResolution

    monkeypatch.setattr(
        callers_absence, "resolve_target", lambda *_args: TargetResolution(True)
    )
    scoped = {"freshness": "unknown", "reason": "SOURCE_REVALIDATION_SCOPED"}
    verdict = callers_absence.assess_completeness(
        object(), ".", "W.f", None, "complete", 0, scoped
    )

    assert (verdict.completeness, verdict.reason) == (
        "unknown",
        "NON_CALL_REFERENCES_UNCHECKED",
    )
    assert verdict.fields == {
        "target_defined": True,
        "close_matches": [],
        "non_call_references": None,
        "non_call_reference_sites": None,
    }


@pytest.mark.asyncio
async def test_named_file_keeps_the_reference_check(widget_root) -> None:
    # #1593：点名声明文件只收窄声明范围，不跳过非调用引用扫描。
    result = await CodeGraphCallersTool(widget_root).execute(
        {
            "function_name": "Widget._style",
            "file_path": "widget.py",
            "include_bodies": False,
        }
    )

    assert (result["completeness"], result["non_call_references"]) == ("unknown", 1)


def test_unreadable_source_file_is_not_an_empty_scan(tmp_path) -> None:
    # #1593：任一同语言文件不可读时，扫描结果为 None 而不是部分结果。
    import time

    from tree_sitter_analyzer.mcp.tools.callers_absence import _files_containing

    (tmp_path / "a.py").write_text("x = w.size\n", encoding="utf-8")
    files = [("a.py", "python"), ("gone.py", "python")]

    assert (
        _files_containing(str(tmp_path), files, b"size", time.monotonic() + 5) is None
    )


def test_attribute_writes_count_but_bare_assignments_do_not() -> None:
    # #1593：`w.size = 1` 是对属性的使用；局部变量赋值与关键字实参不是。
    import re

    from tree_sitter_analyzer.mcp.tools.callers_absence import (
        _reference_lines,
        _strip_comments_and_prose,
    )

    source = "w.size = 1\nsize = 2\nf(size=3)\nok = a.size + b.size\n"
    text = _strip_comments_and_prose(source, "ruby")

    assert text == source
    assert _reference_lines(text, re.compile(r"(?<![\w$])size(?![\w$])")) == [1, 4]


def test_accessor_check_reads_decorators_on_either_side(tmp_path) -> None:
    # #1593：声明行可能指向装饰器行本身；缺失文件与越界行号不判为访问器。
    from tree_sitter_analyzer.mcp.tools.callers_absence import _is_accessor

    (tmp_path / "p.py").write_text(
        "class P:\n    @x.setter\n    def x(self, v):\n        pass\n", encoding="utf-8"
    )

    assert _is_accessor(str(tmp_path), [("p.py", 2, "python")], "x") is True
    assert _is_accessor(str(tmp_path), [("p.py", 99, "python")], "x") is False
    assert _is_accessor(str(tmp_path), [("gone.py", 1, "python")], "x") is False


def test_describe_names_three_sites_then_counts_the_rest() -> None:
    # #1593：提示点名前三个位置，其余以数量给出。
    from tree_sitter_analyzer.mcp.tools.callers_absence import _describe

    sites = [{"file": "a.py", "line": n} for n in range(1, 6)]

    assert _describe(sites) == "a.py:1; a.py:2; a.py:3; and 2 more"


# --- #1606：目标必须解析到索引中的定义，否则 0 不是“不存在”的证据 ---

_REFRESH = "`index action=cache mode=index` (CLI: `--ast-cache --ast-cache-mode index`)"


@pytest.mark.asyncio
async def test_unknown_class_qualifier_is_not_defined(widget_root) -> None:
    # #1606：`NoSuchClass.unused` 不存在；不得答 complete，也不得说“已在索引中定义”。
    result = await _callers(widget_root, "NoSuchClass.unused")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "SYMBOL_NOT_DEFINED"
    assert result["target_defined"] is False
    assert result["close_matches"] == ["Widget.unused"]
    assert result["next_step"] == (
        "Symbol 'NoSuchClass.unused' is not in the index (no indexed definition "
        "matches it), so 0 callers is not evidence of absence. Close matches: Widget.unused. Retry with one of "
        "them; if the symbol was added since the last index, run "
        "`index action=cache mode=index` (CLI: `--ast-cache --ast-cache-mode "
        "index`) first."
    )


@pytest.mark.asyncio
async def test_real_class_without_the_method_is_not_defined(widget_root) -> None:
    # #1606：`Gadget` 真实存在但没有定义 `unused`，同样不是确定的不存在。
    result = await _callers(widget_root, "Gadget.unused")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "SYMBOL_NOT_DEFINED",
    )
    assert result["close_matches"] == ["Widget.unused"]


@pytest.mark.asyncio
async def test_unknown_bare_name_is_not_defined(widget_root) -> None:
    # #1606：完全不存在的名字与真正的 0 不能是同一个答案。
    result = await _callers(widget_root, "no_such_function_xyz")

    assert (result["verdict"], result["completeness"]) == ("NOT_FOUND", "unknown")
    assert result["completeness_reason"] == "SYMBOL_NOT_DEFINED"
    assert result["close_matches"] == []
    # #1606：拼写相近的已索引符号作为候选给出。
    misspelled = await _callers(widget_root, "unusd")
    assert (misspelled["completeness_reason"], misspelled["close_matches"]) == (
        "SYMBOL_NOT_DEFINED",
        ["unused"],
    )


# --- #1607：索引之后新增的同语言源码可能就是调用方 ---


@pytest.mark.asyncio
async def test_new_unindexed_file_blocks_complete(widget_root) -> None:
    # #1607：新文件调用了 `Widget.unused`，但尚未入索引；不得答 complete。
    from pathlib import Path

    (Path(widget_root) / "late.py").write_text(
        "def late(w):\n    return w.unused()\n", encoding="utf-8"
    )

    result = await _callers(widget_root, "Widget.unused")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "UNINDEXED_SOURCE_FILES"
    assert result["unindexed_source_files"] == ["late.py"]
    assert result["unindexed_source_files_total"] == 1
    assert result["next_step"] == (
        "No resolved caller for 'Widget.unused', but 1 python source file(s) "
        "were added since the last index and were not checked: late.py. Run "
        "`index action=cache mode=index` (CLI: `--ast-cache --ast-cache-mode "
        "index`) to index them, then retry."
    )


@pytest.mark.asyncio
async def test_new_file_of_another_language_keeps_complete(widget_root) -> None:
    # #1607：另一种语言的新文件不可能调用 Python 方法；被忽略的目录也不计入。
    # #1606：存在且无人引用的方法仍为 complete，并标明目标已定义。
    from pathlib import Path

    root = Path(widget_root)
    (root / "late.js").write_text("function f(w) { return w.unused(); }\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "vendored.py").write_text("x = w.unused()\n")

    result = await _callers(widget_root, "Widget.unused")

    assert (result["completeness"], result["completeness_reason"]) == (
        "complete",
        None,
    )
    assert (result["target_defined"], result["close_matches"]) == (True, [])
    assert result["unindexed_source_files"] == []


@pytest.mark.asyncio
async def test_new_file_listing_over_budget_is_unknown(
    widget_root, monkeypatch
) -> None:
    # #1607：预算内列不完目录时只能答 unknown，不得假定没有新文件。
    from tree_sitter_analyzer.mcp.tools import unindexed_sources

    monkeypatch.setattr(unindexed_sources, "_ENTRY_BUDGET", 1)

    result = await _callers(widget_root, "Widget.unused")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "UNINDEXED_SOURCE_UNCHECKED",
    )
    assert result["unindexed_source_files"] is None
    assert result["next_step"] == (
        "No resolved caller for 'Widget.unused', but whether source files were "
        "added since the last index could not be checked within budget, so this "
        f"is not evidence of absence. Run {_REFRESH}, then retry."
    )


def test_unindexed_hint_names_three_files_then_counts_the_rest() -> None:
    # #1607：next_step 点名前三个新文件，其余以数量给出。
    from tree_sitter_analyzer.mcp.tools.unindexed_sources import unindexed_hint

    hint = unindexed_hint("f", frozenset({"python"}), ["a.py", "b.py", "c.py", "d"])
    assert hint == (
        "No resolved caller for 'f', but 4 python source file(s) were added since "
        "the last index and were not checked: a.py, b.py, c.py and 1 more. Run "
        f"{_REFRESH} to index them, then retry."
    )


def test_reference_scan_budget_scales_with_file_count() -> None:
    # #1609：固定 2 s 在负载下随机降级；期限按扫描文件数线性放宽，空集仍为 2 s。
    from tree_sitter_analyzer.mcp.tools.callers_absence import scan_budget_seconds

    assert (scan_budget_seconds(0), scan_budget_seconds(1700)) == (2.0, 19.0)


def test_defined_lookup_requires_the_method_inside_the_class(tmp_path) -> None:
    # #1606：限定名的所有者既可以是类，也可以是声明该符号的模块名。
    from tree_sitter_analyzer.mcp.tools.callers_target import _defined, _relative

    conn = type("C", (), {"execute": lambda *_a: [("a.py", 1, 10)]})()
    outside = [("a.py", 30, 31, "python")]
    assert [
        _defined(conn, [("a.py", 3, 4, "python")], "Widget"),
        _defined(conn, outside, "Widget"),
        _defined(conn, outside, "a"),
        _defined(conn, [("b.go", 30, 31, "go")], "Widget"),
        _defined(conn, [], ""),
    ] == [True, False, True, True, False]
    assert _relative(str(tmp_path), str(tmp_path / "x" / "y.py")) == "x/y.py"


def test_call_position_is_skipped_only_on_a_line_with_a_call_edge() -> None:
    # #1622：`name(` 只有在该行确有调用边时才可跳过；无边的调用位置计为引用。
    import re

    from tree_sitter_analyzer.mcp.tools.callers_absence import _reference_lines

    text = "a = size(1)\nb = size(2)\nc = w.size\n"
    pattern = re.compile(r"(?<![\w$])size(?![\w$])")

    assert _reference_lines(text, pattern, frozenset({1})) == [2, 3]
    assert _reference_lines(text, pattern, frozenset()) == [1, 2, 3]


@pytest.mark.asyncio
async def test_call_site_without_a_counted_edge_blocks_complete(tmp_path) -> None:
    # #1622：调用点若没有任何调用边，扫描不得假定“已有边”而跳过它。
    import os
    import sqlite3
    import stat

    from tree_sitter_analyzer.ast_cache import ASTCache

    (tmp_path / "lone.py").write_text(
        "def lonely():\n    return 1\n\n\ndef user():\n    return lonely()\n\n\n"
        "def helper():\n    return 2\n\n\ndef other():\n    return helper()\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
        db_path = cache.db_path
    finally:
        cache.close()
    # 模拟“调用点没有任何调用边”：删去指向 lonely 的边（索引封存为只读，先解封）。
    os.chmod(db_path, stat.S_IREAD | stat.S_IWRITE)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM edges WHERE kind = 'calls' AND callee_name = ?", ("lonely",)
        )

    result = await _callers(str(tmp_path), "lonely")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_reference_sites"] == [{"file": "lone.py", "line": 6}]


def test_unreadable_call_edges_make_the_scan_unknown(tmp_path) -> None:
    # #1622：读不到调用边时无法判断哪些 `name(` 已被覆盖，扫描结果为 None（unknown）。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.callers_absence import _non_call_sites
    from tree_sitter_analyzer.mcp.tools.callers_call_lines import call_edge_lines

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
    conn.execute("CREATE TABLE ast_symbol_rows (file_path TEXT, line INT, name TEXT)")

    class _Cache:
        def get_conn(self) -> sqlite3.Connection:
            return conn

    assert call_edge_lines(_Cache(), "size") is None
    declarations = [("a.py", 1, "python")]
    assert _non_call_sites(_Cache(), str(tmp_path), "size", declarations) is None
