"""#1706：原因码背后的证据要能把 Agent 引到缺失的调用方。

dogfood 第 9 轮的三个缺口，经公开的 ``nav callers``（``CodeGraphCallersTool``）
在已索引的夹具上验证：

1. ``UNRESOLVED_INBOUND`` 只有计数：答复现在带 ``unresolved_inbound_sites``
   （``{file, line, caller, callee}``，有上限，总数与是否截断并列），``next_step``
   先点名它们，再点名同名调用点；
2. ``name_only_sites`` 按路径字母序截断：现在先按接近程度排序（声明文件、导入了
   目标的文件、其余），同档内生产代码在测试之前；
3. 主因为 ``NON_CALL_REFERENCES`` 且已列出调用方的答案拿到通用 ``next_step``：现在
   点名非调用引用的位置并说明要检查什么。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_GENERIC = "Review callers above"


async def _index_files(root: Path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 80}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str, file_path: str | None = None) -> dict:
    arguments: dict = {"function_name": name, "include_bodies": False}
    if file_path:
        arguments["file_path"] = file_path
    return await CodeGraphCallersTool(root).execute(arguments)


# ---------------------------------------------------------------------------
# 1. UNRESOLVED_INBOUND：调用点，而不只是计数
# ---------------------------------------------------------------------------

_PING = {
    "a.py": "class A:\n    def ping(self):\n        return 1\n",
    "b.py": "class B:\n    def ping(self):\n        return 2\n",
    "use.py": "def use(x):\n    return x.ping()\n",
}


@pytest.mark.asyncio
async def test_unresolved_inbound_names_its_sites(tmp_path) -> None:
    root = await _index_files(tmp_path, _PING)

    result = await _callers(root, "A.ping")

    assert result["completeness_reasons"][0] == "UNRESOLVED_INBOUND"
    assert result["unresolved_inbound"] == 1
    assert result["unresolved_inbound_sites"] == [
        {"file": "use.py", "line": 2, "caller": "use", "callee": "x.ping"}
    ]
    assert result["unresolved_inbound_sites_total"] == 1
    assert result["unresolved_inbound_sites_truncated"] is False
    assert "use.py:2 (use: `x.ping`)" in result["next_step"]


@pytest.mark.asyncio
async def test_unresolved_sites_lead_the_next_step_when_callers_are_listed(
    tmp_path,
) -> None:
    files = {
        **_PING,
        "direct.py": "from a import A\n\n\ndef direct():\n    return A().ping()\n",
    }
    root = await _index_files(tmp_path, files)

    result = await _callers(root, "A.ping")

    assert {entry["name"] for entry in result["callers"]} == {"direct"}
    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"][0] == "UNRESOLVED_INBOUND"
    step = result["next_step"]
    assert _GENERIC not in step
    assert "use.py:2 (use: `x.ping`)" in step
    assert step.index("unresolved_inbound_sites") < step.index("name_only_sites")


@pytest.mark.asyncio
async def test_unresolved_inbound_sites_are_capped_with_an_honest_total(
    tmp_path,
) -> None:
    calls = "".join(
        f"def use_{index}(x):\n    return x.ping()\n\n\n" for index in range(25)
    )
    root = await _index_files(tmp_path, {**_PING, "use.py": calls})

    result = await _callers(root, "A.ping")

    assert result["unresolved_inbound"] == 25
    assert result["unresolved_inbound_sites_total"] == 25
    assert len(result["unresolved_inbound_sites"]) == 20
    assert result["unresolved_inbound_sites_truncated"] is True


# ---------------------------------------------------------------------------
# 2. name_only_sites：先排序再截断
# ---------------------------------------------------------------------------

_BASE = (
    "from external_pkg import Mixin\n\n\n"
    "class Base(Mixin):\n"
    "    def _reset(self):\n"
    "        return 1\n\n\n"
    "def nearby(obj):\n"
    "    return obj._reset()\n"
)
#: 字母序在 `pkg/` 之前的 25 个同名调用点（无关文件）。
_EARLY = "".join(
    f"def early_{index}(obj):\n    return obj._reset()\n\n\n" for index in range(25)
)
_IMPORTER = (
    "from pkg.base import Base\n\n\ndef via_importer(obj):\n    return obj._reset()\n"
)
_TEST_IMPORTER = (
    "from pkg.base import Base\n\n\ndef test_reset(obj):\n    return obj._reset()\n"
)


@pytest.mark.asyncio
async def test_name_only_sites_rank_declaring_file_and_importers_first(
    tmp_path,
) -> None:
    files = {
        "aaa/early.py": _EARLY,
        "pkg/__init__.py": "",
        "pkg/base.py": _BASE,
        "tests/test_reset.py": _TEST_IMPORTER,
        "zzz/importer.py": _IMPORTER,
    }
    root = await _index_files(tmp_path, files)

    result = await _callers(root, "Base._reset", "pkg/base.py")

    assert result["name_only_sites_total"] == 28
    assert result["name_only_sites_truncated"] is True
    head = [(site["file"], site["caller"]) for site in result["name_only_sites"][:3]]
    assert head == [
        ("pkg/base.py", "nearby"),
        ("zzz/importer.py", "via_importer"),
        ("tests/test_reset.py", "test_reset"),
    ]
    # 其余按路径与行号：无关文件排在最后，仍可见总数。
    assert result["name_only_sites"][3]["file"] == "aaa/early.py"
    assert "pkg/base.py:10 (nearby)" in result["next_step"]


def test_test_paths_are_recognised() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_site_rank import is_test_path

    assert is_test_path("tests/unit/test_x.py")
    assert is_test_path("pkg/test/helpers.py")
    assert is_test_path("pkg/x_test.py")
    assert is_test_path("conftest.py")
    assert not is_test_path("pkg/testing_utils.py")
    assert not is_test_path("benchmarks/bench_runner.py")


def test_ranking_without_a_readable_index_keeps_every_site() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_site_rank import rank_sites

    class _Broken:
        def get_conn(self):
            raise AttributeError("no index")

    sites = [
        {"file": "tests/test_b.py", "line": 1},
        {"file": "b.py", "line": 9},
        {"file": "a.py", "line": 3},
    ]

    ranked = rank_sites(_Broken(), sites, "f", None)

    assert ranked == [
        {"file": "a.py", "line": 3},
        {"file": "b.py", "line": 9},
        {"file": "tests/test_b.py", "line": 1},
    ]


# ---------------------------------------------------------------------------
# 3. NON_CALL_REFERENCES 且有调用方：点名位置的 next_step
# ---------------------------------------------------------------------------

_HOOKS = (
    "def target():\n    return 1\n\n\n"
    "def caller():\n    return target()\n\n\n"
    "def register(hooks):\n    hooks.append(target)\n"
)


@pytest.mark.asyncio
async def test_non_call_references_with_callers_name_their_sites(tmp_path) -> None:
    root = await _index_files(tmp_path, {"mod.py": _HOOKS})

    result = await _callers(root, "target", "mod.py")

    assert {entry["name"] for entry in result["callers"]} == {"caller"}
    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    step = result["next_step"]
    assert "mod.py:10" in step
    assert "non_call_reference_sites" in step
    assert "callback" in step
    assert result["agent_summary"]["next_step"] == step


def test_listed_callers_hint_rewrites_the_absence_wording() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_reason_steps import reason_step

    hint = (
        "No resolved caller for 'f', but it is decorated with `app.route`, which "
        "may register it, so this is not evidence of absence."
    )

    step = reason_step(
        "DECORATOR_MAY_REGISTER",
        "f",
        {"caller_count": 2},
        unresolved_sites=None,
        declaring_sites=None,
        absence_hint=hint,
    )

    assert step == (
        "2 caller(s) are listed for 'f', but it is decorated with `app.route`, "
        "which may register it, so the list may be incomplete."
    )
    assert (
        reason_step(
            "SOURCE_INDEX_MISMATCH",
            "f",
            {},
            unresolved_sites=None,
            declaring_sites=None,
            absence_hint=hint,
        )
        is None
    )


def test_reason_steps_for_reasons_without_a_dedicated_fixture() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_reason_steps import reason_step

    def step(primary: str, result: dict, hint: str | None = None) -> str | None:
        return reason_step(
            primary,
            "C.size",
            result,
            unresolved_sites=None,
            declaring_sites=None,
            absence_hint=hint,
        )

    sites = [{"file": "a.py", "line": 3}, {"file": "b.py", "line": 4}]
    accessor = step(
        "ACCESSOR_NOT_CALL_EDGES",
        {"non_call_reference_sites": sites, "non_call_references": 5},
    )
    assert accessor is not None
    assert "`.size` reads" in accessor
    assert "a.py:3; b.py:4; and 3 more" in accessor
    assert "Non-call references" not in str(step("ACCESSOR_NOT_CALL_EDGES", {}))
    unattributed = step("UNATTRIBUTED_CALL_SITES", {"unattributed_call_sites": 2})
    assert unattributed is not None
    assert unattributed.startswith("2 module-level call site(s) reach 'C.size'")
    # 无主因或无提示时不给出步骤；不以 “No resolved caller” 开头的提示原样保留。
    assert step("UNINDEXED_SOURCE_FILES", {}, None) is None
    assert step("UNINDEXED_SOURCE_FILES", {"caller_count": 1}, "Run refresh.") == (
        "Run refresh."
    )
    assert step(
        "UNINDEXED_SOURCE_FILES",
        {"caller_count": 1},
        "No resolved caller for 'C.size', and files were added.",
    ) == ("1 caller(s) are listed for 'C.size', and files were added.")


def test_unresolved_reader_falls_back_to_the_count() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_reason_steps import (
        read_unresolved_inbound,
    )

    class _CountOnly:
        def count_unresolved_callers(self, name, file_path, bound_targets=None):
            return 3 if bound_targets else 2

    class _Unreadable:
        def unresolved_caller_sites(self, name, file_path, bound_targets=None):
            return None

    assert read_unresolved_inbound(None, "f", None, None) == (None, None)
    assert read_unresolved_inbound(_CountOnly(), "f", None, None) == (2, None)
    assert read_unresolved_inbound(_CountOnly(), "f", None, {("a.py", 1)}) == (
        3,
        None,
    )
    assert read_unresolved_inbound(_Unreadable(), "f", None, None) == (None, None)


def test_ranking_helpers_cover_packages_and_unreadable_declarations() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools import callers_site_rank as rank

    class _Broken:
        def get_conn(self):
            raise sqlite3.OperationalError("locked")

    assert rank.declaring_files(_Broken(), "f", None) == []
    assert rank._module_name("pkg/__init__.py") == "pkg"
    assert rank._module_name("pkg/mod.py") == "mod"


def test_cache_wrappers_report_unreadable_sites_as_none() -> None:
    import sqlite3

    from tree_sitter_analyzer._ast_cache_graph_mixin import ASTCacheGraphMixin

    class _Cache(ASTCacheGraphMixin):
        def _get_conn(self):
            conn = sqlite3.connect(":memory:")
            return conn  # 没有 edges 表：读取失败

    assert _Cache().unresolved_caller_sites("f") is None


def test_unresolved_sites_clause_is_empty_without_sites() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_reason_steps import (
        unresolved_sites_clause,
    )

    site = {"file": "use.py", "line": 2, "caller": "use", "callee": "x.ping"}

    assert unresolved_sites_clause(None) == ""
    assert unresolved_sites_clause([]) == ""
    assert unresolved_sites_clause([site]) == (
        " Sites (`unresolved_inbound_sites`): use.py:2 (use: `x.ping`)."
    )
