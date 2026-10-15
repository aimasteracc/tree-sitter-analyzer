"""#1624：绝对否定不得弱于 grep——字符串里的点号/冒号名与配置文件中的名字。

#1598 的非调用引用扫描只看同语言的已索引源码，且丢弃一切非“恰为标识符”的
字符串。于是入口点（``"pkg.mod:func"``）、``importlib`` 解析串、``exec("o.m()")``
与 ``.github/workflows/*.yml`` 里点名的方法都被漏掉，``0 callers, complete``
反而比 grep 更弱。这里通过公开的 callers 工具在已索引的夹具上复核。
"""

from __future__ import annotations

import re

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_JOBS = (
    "class Jobs:\n"
    "    def launch(self):\n"
    "        return 1\n\n"
    "    def resolved(self):\n"
    "        return 2\n\n"
    "    def executed(self):\n"
    "        return 3\n\n"
    "    def from_workflow(self):\n"
    "        return 4\n\n"
    "    def untouched(self):\n"
    '        """untouched 只出现在文档字符串、普通文案与 README 里。"""\n'
    "        return 5\n"
)
_LOADER = (
    "import importlib\n\n\n"
    "def load(spec):\n"
    '    module, _, attr = spec.partition(":")\n'
    "    return importlib.import_module(module), attr\n\n\n"
    'TARGET = "pkg.jobs:Jobs.resolved"\n\n\n'
    "def run(obj):\n"
    '    print("untouched branch is fine")\n'
    '    exec("obj.executed()")\n'
)
_PYPROJECT = (
    '[project]\nname = "pkg"\n\n'
    '[project.entry-points."pkg.plugins"]\n'
    'jobs = "pkg.jobs:Jobs.launch"\n'
)
_WORKFLOW = (
    "name: ci\n"
    "on: [push]\n"
    "jobs:\n"
    "  test:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - run: uv run pytest -k from_workflow\n"
)


@pytest.fixture
async def jobs_root(tmp_path):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "jobs.py").write_text(_JOBS, encoding="utf-8")
    (package / "loader.py").write_text(_LOADER, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / "README.md").write_text("Jobs.untouched is internal.\n", "utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(_WORKFLOW, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "site"),
    [
        ("Jobs.launch", {"file": "pyproject.toml", "line": 5}),
        ("Jobs.resolved", {"file": "pkg/loader.py", "line": 9}),
        ("Jobs.executed", {"file": "pkg/loader.py", "line": 14}),
        ("Jobs.from_workflow", {"file": ".github/workflows/ci.yml", "line": 7}),
    ],
    ids=["entry-point", "importlib-string", "exec-string", "workflow-yml"],
)
async def test_grep_visible_reference_blocks_complete(jobs_root, name, site) -> None:
    # #1624：grep 能找到的名字（入口点、importlib 串、exec 串、workflow）必须降级。
    result = await _callers(jobs_root, name)

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "NON_CALL_REFERENCES"
    assert result["non_call_reference_sites"] == [site]


@pytest.mark.asyncio
async def test_unreferenced_method_stays_complete_despite_prose(jobs_root) -> None:
    # #1624：文档字符串、普通文案字符串与 README 散文都不是引用；仍答 complete。
    result = await _callers(jobs_root, "Jobs.untouched")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert result["non_call_references"] == 0


@pytest.mark.asyncio
async def test_config_scan_over_budget_is_unchecked(jobs_root, monkeypatch) -> None:
    # #1624：配置文件也计入扫描预算；预算用尽只能答 unchecked，不得答 complete。
    from tree_sitter_analyzer.mcp.tools import callers_absence

    monkeypatch.setattr(callers_absence, "_SCAN_DEADLINE_SECONDS", -1.0)

    result = await _callers(jobs_root, "Jobs.untouched")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "NON_CALL_REFERENCES_UNCHECKED",
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("pyproject.toml", True),
        ("setup.cfg", True),
        ("tox.ini", True),
        (".github/workflows/ci.yml", True),
        ("deploy/compose.yaml", True),
        ("scripts/run.sh", True),
        ("scripts/run.ps1", True),
        ("build.bat", True),
        ("Makefile", True),
        ("docker/Dockerfile.dev", True),
        ("README.md", False),
        ("docs/guide.rst", False),
        ("tests/golden/out.json", False),
        ("notes.txt", False),
    ],
)
def test_config_file_set(path, expected) -> None:
    # #1624：配置 / 脚本文件会调用名字；散文文档与 JSON 数据不扫描。
    from tree_sitter_analyzer.mcp.tools.absence_text_refs import is_config_file

    assert is_config_file(path) is expected


def test_code_like_strings_count_but_prose_strings_do_not() -> None:
    # #1624：点号/冒号形式、调用形式与无空白的串计为引用；散文串与文档字符串不计。
    from tree_sitter_analyzer.mcp.tools.callers_absence import (
        _reference_lines,
        _strip_comments_and_prose,
    )

    source = (
        '"""size 出现在模块文档字符串里。"""\n'
        'a = "pkg.mod:size"\n'
        'b = "pkg.mod.size"\n'
        'c = "the size is fine"\n'
        'd = "import m; m.size()"\n'
        "e = '''first line\n"
        "w.size()\n"
        "'''\n"
        'g = "resize"\n'
    )
    text = _strip_comments_and_prose(source, "python", "size")
    lines = _reference_lines(text, re.compile(r"(?<![\w$])size(?![\w$])"), set())

    assert lines == [2, 3, 5, 7]


def test_string_mention_keeps_line_numbers() -> None:
    # #1624：多行串只在命中行留下名字，其余行保持换行，行号不漂移。
    from tree_sitter_analyzer.mcp.tools.absence_text_refs import string_mention

    assert string_mention("a\nx.size()\nb", "size") == "\n size \n"
    assert string_mention("plain size words", "size") is None
    assert string_mention("pkg:size", "size") == " size "
