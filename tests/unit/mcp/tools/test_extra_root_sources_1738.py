"""#1738：索引从不入库的源码不是“索引之后新增”的文件。

dogfood 第 10 轮（pydantic）：仓库跟踪 ``.github/actions/people/people.py``。全量索引
跳过点目录，但未入索引源码检查（#1607）把 ``.github`` 作为额外根目录（#1624）遍历，
把其中的 ``.py`` 列为 ``UNINDEXED_SOURCE_FILES``。建议的刷新入库 0 个文件，答案
永远不能 ``complete``。

额外根目录下的源码仍按文本扫描非调用引用（只会降级，从不升级），但不计入未入索引
源码；索引本会入库的目录里真正新增的 ``.py`` 照旧阻止 ``complete``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_WIDGET = (
    "class Widget:\n"
    "    def unused(self):\n"
    "        return 0\n\n"
    "    def spin(self):\n"
    "        return 1\n\n\n"
    "def helper():\n"
    "    return 2\n\n\n"
    "def run():\n"
    "    return helper()\n"
)
_PEOPLE = "def main():\n    return 'people'\n"


@pytest.fixture
async def github_root(tmp_path):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "widget.py").write_text(_WIDGET, encoding="utf-8")
    people = tmp_path / ".github" / "actions" / "people"
    people.mkdir(parents=True)
    (people / "people.py").write_text(_PEOPLE, encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  test:\n    steps:\n      - run: pytest\n", encoding="utf-8"
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return tmp_path


async def _callers(root: Path, name: str) -> dict:
    return await CodeGraphCallersTool(str(root)).execute(
        {"function_name": name, "include_bodies": False}
    )


@pytest.mark.asyncio
async def test_github_source_the_indexer_skips_is_not_unindexed(github_root) -> None:
    # 复现：索引跳过 `.github`，检查却把其中的 `.py` 当作新增文件。
    result = await _callers(github_root, "Widget.unused")

    assert (result["completeness"], result["completeness_reason"]) == (
        "complete",
        None,
    )
    assert result["unindexed_source_files"] == []
    assert result["unindexed_source_files_total"] == 0


@pytest.mark.asyncio
async def test_github_source_mentioning_the_name_is_a_reference(github_root) -> None:
    # #1624 的用意不变：`.github` 下脚本里的名字仍阻止 complete，并点名位置。
    (github_root / ".github" / "actions" / "people" / "bump.py").write_text(
        "def bump(w):\n    return w.unused()\n", encoding="utf-8"
    )

    result = await _callers(github_root, "Widget.unused")

    assert result["completeness"] != "complete"
    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert "UNINDEXED_SOURCE_FILES" not in result["completeness_reasons"]
    assert result["non_call_reference_sites"] == [
        {"file": ".github/actions/people/bump.py", "line": 2}
    ]
    assert result["unindexed_source_files"] == []


@pytest.mark.asyncio
async def test_github_config_is_still_scanned(github_root) -> None:
    # #1624：`.github` 工作流里点名的函数仍是非调用引用。
    (github_root / ".github" / "workflows" / "spin.yml").write_text(
        "jobs:\n  lint:\n    steps:\n      - run: python -c 'spin'\n",
        encoding="utf-8",
    )

    result = await _callers(github_root, "Widget.spin")

    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_reference_sites"] == [
        {"file": ".github/workflows/spin.yml", "line": 4}
    ]


@pytest.mark.asyncio
async def test_default_excluded_source_is_not_unindexed(github_root) -> None:
    # 默认 exclude 模式下的源码同样永远不会入库。
    corpus = github_root / "tests" / "golden" / "corpus_python"
    corpus.mkdir(parents=True)
    (corpus / "sample.py").write_text("def sample():\n    return 1\n")

    result = await _callers(github_root, "Widget.unused")

    assert (result["completeness"], result["unindexed_source_files"]) == (
        "complete",
        [],
    )


@pytest.mark.asyncio
async def test_new_source_in_an_indexed_directory_is_still_unindexed(
    github_root,
) -> None:
    # 对照：索引会入库的目录里真正新增的 `.py` 仍阻止 complete，且只点名它。
    (github_root / "late.py").write_text("def late():\n    return 2\n")

    result = await _callers(github_root, "Widget.unused")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "UNINDEXED_SOURCE_FILES",
    )
    assert result["unindexed_source_files"] == ["late.py"]
    assert result["unindexed_source_files_total"] == 1


def _fake_cache(indexed: list[str]):
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT)")
    conn.executemany("INSERT INTO ast_index VALUES (?)", [(p,) for p in indexed])

    class _Cache:
        def get_conn(self):
            return conn

    return _Cache()


@pytest.mark.parametrize(
    ("indexed", "config"),
    [
        # 未入库：只进入文本引用扫描列表。
        (["widget.py"], [".github/scripts/tool.py", ".github/workflows/ci.yml"]),
        # 已手工入库（#1738 的单文件绕行）：按语言扫描，不在文本列表中重复。
        (["widget.py", ".github/scripts/tool.py"], [".github/workflows/ci.yml"]),
    ],
)
def test_extra_root_sources_are_never_unindexed(
    tmp_path: Path, indexed: list[str], config: list[str]
) -> None:
    from tree_sitter_analyzer.mcp.tools.project_walk_cache import WALK_CACHE
    from tree_sitter_analyzer.mcp.tools.unindexed_sources import project_files

    (tmp_path / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (tmp_path / "late.py").write_text("x = 1\n", encoding="utf-8")
    scripts = tmp_path / ".github" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "tool.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir()
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("jobs: {}\n")
    WALK_CACHE.clear()

    files = project_files(_fake_cache(indexed), str(tmp_path), frozenset({"python"}))

    assert files is not None
    assert (files.unindexed, files.config) == (["late.py"], config)
