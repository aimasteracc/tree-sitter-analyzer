"""P1-4：change-impact 的文本引用补充通道（保守、只做提示）。"""

from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.mcp.tools.utils.change_impact_text_refs import (
    text_reference_tests,
)


def _project(tmp_path: Path) -> Path:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_refs.py").write_text(
        "from tree_sitter_analyzer.cache import search\n", encoding="utf-8"
    )
    (tests / "test_dotted.py").write_text(
        "import tree_sitter_analyzer.cache.search as s\n", encoding="utf-8"
    )
    (tests / "test_other.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    return tmp_path


def test_text_references_find_files_the_graph_misses(tmp_path) -> None:
    root = _project(tmp_path)

    found = text_reference_tests(
        str(root),
        changed_paths=["tree_sitter_analyzer/cache/search.py"],
        selected=[],
    )

    assert [item["file"] for item in found] == [
        "tests/test_dotted.py",
        "tests/test_refs.py",
    ]
    assert {item["changed"] for item in found} == {
        "tree_sitter_analyzer/cache/search.py"
    }


def test_already_selected_files_are_not_repeated(tmp_path) -> None:
    root = _project(tmp_path)

    found = text_reference_tests(
        str(root),
        changed_paths=["tree_sitter_analyzer/cache/search.py"],
        selected=["tests/test_refs.py"],
    )

    assert [item["file"] for item in found] == ["tests/test_dotted.py"]


def test_non_python_and_package_inits_have_no_probes(tmp_path) -> None:
    root = _project(tmp_path)

    assert (
        text_reference_tests(str(root), changed_paths=["README.md"], selected=[]),
        text_reference_tests(
            str(root),
            changed_paths=["tree_sitter_analyzer/cache/__init__.py"],
            selected=[],
        ),
    ) == ([], [])


def test_the_limit_caps_the_advisory_list(tmp_path) -> None:
    root = _project(tmp_path)
    tests = root / "tests"
    for index in range(5):
        (tests / f"test_extra_{index}.py").write_text(
            "from tree_sitter_analyzer.cache import search\n", encoding="utf-8"
        )

    found = text_reference_tests(
        str(root),
        changed_paths=["tree_sitter_analyzer/cache/search.py"],
        selected=[],
        limit=2,
    )

    assert len(found) == 2


def test_the_tool_attaches_the_advisory_field(tmp_path) -> None:
    """工具层把补充文件写进响应；已选中的测试文件不重复。"""
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
        ChangeImpactTool,
    )

    root = _project(tmp_path)
    tool = ChangeImpactTool(str(root))

    missing = tool._text_reference_tests(
        {"tests_to_run": [{"file": "tests/test_refs.py"}]},
        ["tree_sitter_analyzer/cache/search.py"],
    )
    result: dict = {}
    tool._attach_text_reference_tests(result, missing)

    assert (
        result["text_reference_count"],
        result["text_reference_tests"][0]["file"],
    ) == (
        1,
        "tests/test_dotted.py",
    )
    assert "decide whether to run them" in result["text_reference_note"]


def test_no_changed_files_means_no_probe() -> None:
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
        ChangeImpactTool,
    )

    tool = ChangeImpactTool(".")

    assert tool._text_reference_tests({}, []) == []
