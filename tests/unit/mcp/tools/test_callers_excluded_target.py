"""#1635：目标定义在被索引排除的文件里时，答案须点名该文件与排除规则。

dogfood 第 6、7 轮：``tests/golden/corpus_python.py`` 中确实存在的函数答
``SYMBOL_NOT_DEFINED``，提示却是“刷新索引或改用相近的名字”。默认排除规则
（``tests/golden/corpus_*``）让刷新永远不会把它入索引，因此该提示是错的。
答案本身（``unknown``）是安全的，必须保持非 complete。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_CORPUS = (
    "def corpus_only(x):\n"
    "    return x\n\n\n"
    "class CorpusThing:\n"
    "    def spin(self):\n"
    "        return 1\n"
)
_MAIN = "def other():\n    return corpus_mentioned()\n"
_VENDOR = "def vendored():\n    return 2\n"


async def _index(root, **arguments) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 10, **arguments}
    )
    assert indexed["published"] is True


@pytest.fixture
async def corpus_root(tmp_path):
    (tmp_path / "tests" / "golden").mkdir(parents=True)
    (tmp_path / "tests" / "golden" / "corpus_python.py").write_text(
        _CORPUS, encoding="utf-8"
    )
    (tmp_path / "main.py").write_text(_MAIN, encoding="utf-8")
    await _index(tmp_path)
    return str(tmp_path)


async def _callers(root: str, name: str, file_path: str | None = None) -> dict:
    arguments = {"function_name": name, "include_bodies": False}
    if file_path is not None:
        arguments["file_path"] = file_path
    return await CodeGraphCallersTool(root).execute(arguments)


@pytest.mark.asyncio
async def test_default_excluded_definition_names_file_and_rule(corpus_root) -> None:
    # #1635：定义存在但被默认规则排除——点名文件、行号与规则，答案仍非 complete。
    result = await _callers(corpus_root, "corpus_only")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reason"] == "SYMBOL_IN_EXCLUDED_FILE"
    assert result["completeness_reasons"] == ["SYMBOL_IN_EXCLUDED_FILE"]
    assert result["target_defined"] is False
    assert result["excluded_definition"] == {
        "file": "tests/golden/corpus_python.py",
        "line": 1,
        "exclude_pattern": "tests/golden/corpus_*",
        "default_exclude": True,
    }
    assert result["next_step"] == (
        "Symbol 'corpus_only' is defined in tests/golden/corpus_python.py:1, "
        "which the index excludes (built-in default exclude pattern "
        "'tests/golden/corpus_*'), so 0 callers is not evidence of absence and "
        "refreshing the index will not include it. Read the file directly, or "
        "rebuild the index without the default excludes: `index action=full "
        "no_default_excludes=true` (CLI: `--full-index "
        "--full-index-no-default-excludes`)."
    )


@pytest.mark.asyncio
async def test_excluded_qualified_method_is_found(corpus_root) -> None:
    # #1635：限定名 `Class.method` 同样识别为被排除的定义。
    result = await _callers(corpus_root, "CorpusThing.spin")

    assert result["completeness"] == "unknown"
    assert result["completeness_reason"] == "SYMBOL_IN_EXCLUDED_FILE"
    assert result["excluded_definition"]["line"] == 6


@pytest.mark.asyncio
async def test_excluded_file_named_explicitly(corpus_root) -> None:
    # #1635：调用方点名被排除的文件时，同样给出排除规则而非“刷新”。
    result = await _callers(
        corpus_root, "corpus_only", file_path="tests/golden/corpus_python.py"
    )

    assert result["completeness"] == "unknown"
    assert result["completeness_reason"] == "SYMBOL_IN_EXCLUDED_FILE"


@pytest.mark.asyncio
async def test_user_exclude_pattern_names_the_pattern(tmp_path) -> None:
    # #1635：用户提供的 exclude 模式——下一步是去掉该模式重建，而不是关闭默认规则。
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "lib.py").write_text(_VENDOR, encoding="utf-8")
    (tmp_path / "main.py").write_text(_MAIN, encoding="utf-8")
    await _index(tmp_path, exclude_patterns=["generated/*"])

    result = await _callers(str(tmp_path), "vendored")

    assert result["completeness"] == "unknown"
    assert result["completeness_reason"] == "SYMBOL_IN_EXCLUDED_FILE"
    assert result["excluded_definition"] == {
        "file": "generated/lib.py",
        "line": 1,
        "exclude_pattern": "generated/*",
        "default_exclude": False,
    }
    assert "without the exclude pattern 'generated/*'" in result["next_step"]


# --- 负对照：其余答案不变，且永不变成 complete ---


@pytest.mark.asyncio
async def test_truly_missing_symbol_keeps_not_defined(corpus_root) -> None:
    # 负对照：完全不存在的名字仍为 SYMBOL_NOT_DEFINED，不点名任何排除文件。
    result = await _callers(corpus_root, "no_such_function_xyz")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "SYMBOL_NOT_DEFINED",
    )
    assert "excluded_definition" not in result


@pytest.mark.asyncio
async def test_name_only_called_in_excluded_file_is_not_a_definition(
    tmp_path,
) -> None:
    # 负对照：被排除的文件只调用（未定义）该名字时，不得说“定义在排除文件里”。
    (tmp_path / "tests" / "golden").mkdir(parents=True)
    (tmp_path / "tests" / "golden" / "corpus_calls.py").write_text(
        "def caller():\n    return ghost_fn()\n", encoding="utf-8"
    )
    (tmp_path / "main.py").write_text(_MAIN, encoding="utf-8")
    await _index(tmp_path)

    result = await _callers(str(tmp_path), "ghost_fn")

    assert (result["completeness"], result["completeness_reason"]) == (
        "unknown",
        "SYMBOL_NOT_DEFINED",
    )


@pytest.mark.asyncio
async def test_including_the_file_resolves_the_target(tmp_path) -> None:
    # 负对照：按提示关闭默认排除重建后，目标已定义，不再是排除答案。
    (tmp_path / "tests" / "golden").mkdir(parents=True)
    (tmp_path / "tests" / "golden" / "corpus_python.py").write_text(
        _CORPUS, encoding="utf-8"
    )
    (tmp_path / "main.py").write_text(_MAIN, encoding="utf-8")
    await _index(tmp_path, no_default_excludes=True)

    result = await _callers(str(tmp_path), "corpus_only")

    assert result["target_defined"] is True
    assert result["completeness_reason"] != "SYMBOL_IN_EXCLUDED_FILE"
