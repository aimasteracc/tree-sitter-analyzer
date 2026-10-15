"""#1596：``imports dependents`` 按文件计数，并给出真实的 import 行号。

实测（dogfood 第 3 轮）：38 个依赖文件报告为 54 条、12 个报告为 14 条——计数的是
import 语句而不是文件；且每条的 ``line`` 都是 0。响应改为每个依赖文件一条，
语句与行号作为明细保留在 ``statements`` 中。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.import_dependents import group_dependents_by_file
from tree_sitter_analyzer.mcp.tools.import_graph_tool import CodeGraphImportGraphTool


@pytest.fixture
async def project(tmp_path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "c.py").write_text("def x():\n    return 1\n", encoding="utf-8")
    (tmp_path / "a.py").write_text(
        '"""两条语句都导入 c。"""\n\nimport c\nfrom c import x\n', encoding="utf-8"
    )
    (tmp_path / "b.py").write_text("from c import x\n", encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


@pytest.mark.asyncio
async def test_dependents_counts_files_not_statements(project) -> None:
    # #1596：a.py 两条语句 + b.py 一条 → 2 个依赖文件、3 条语句。
    result = await CodeGraphImportGraphTool(project).execute(
        {"mode": "dependents", "file_path": "c.py"}
    )

    assert result["dependent_count"] == 2
    assert result["import_statement_count"] == 3
    assert result["dependents"] == [
        {
            "source": "a.py",
            "target": "c.py",
            "import": "import c",
            "line": 3,
            "statements": [
                {"import": "import c", "line": 3},
                {"import": "from c import x", "line": 4},
            ],
        },
        {
            "source": "b.py",
            "target": "c.py",
            "import": "from c import x",
            "line": 1,
            "statements": [{"import": "from c import x", "line": 1}],
        },
    ]
    assert result["agent_summary"]["summary_line"] == (
        "imports dependents: 'c.py' ← 2 dependent file(s) (3 import statement(s))"
    )


@pytest.mark.asyncio
async def test_deps_reports_real_import_lines(project) -> None:
    # #1596：正向依赖同样带真实行号，而不是 0。
    result = await CodeGraphImportGraphTool(project).execute(
        {"mode": "deps", "file_path": "a.py"}
    )

    assert [(d["import"], d["line"]) for d in result["dependencies"]] == [
        ("import c", 3),
        ("from c import x", 4),
    ]


def test_group_dependents_keeps_first_seen_order_and_sorts_by_file() -> None:
    # #1596：分组按文件排序，文件内语句按行号排序；不修改输入。
    edges = [
        {"source": "z.py", "target": "c.py", "import": "import c", "line": 9},
        {"source": "a.py", "target": "c.py", "import": "from c import y", "line": 5},
        {"source": "a.py", "target": "c.py", "import": "import c", "line": 2},
    ]

    grouped = group_dependents_by_file(edges)

    assert [(g["source"], g["line"], len(g["statements"])) for g in grouped] == [
        ("a.py", 2, 2),
        ("z.py", 9, 1),
    ]
    assert grouped[0]["import"] == "import c"
    assert edges[0] == {
        "source": "z.py",
        "target": "c.py",
        "import": "import c",
        "line": 9,
    }
