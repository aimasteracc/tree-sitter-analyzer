from __future__ import annotations

import asyncio
import os


def test_search_facade_routes_text_without_an_index(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    (tmp_path / "a.py").write_text("needle\nneedle\n", encoding="utf-8")
    facade = build_search_facade(str(tmp_path))

    assert type(facade.action_map["text"]).__name__ == "TextSearchTool"
    result = asyncio.run(
        facade.execute({"action": "text", "query": "needle", "limit": 1})
    )

    assert result["success"] is True
    assert result["total_count"] == 2
    assert result["displayed_count"] == 1
    assert result["truncated"] is True
    assert result["source_evidence"] == {
        "consistency": "per_file_live",
        "index_used": False,
        "scan_complete": True,
    }
    assert not (tmp_path / ".ast-cache").exists()


def test_search_text_complete_miss_is_not_found(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.text_search_tool import TextSearchTool

    (tmp_path / "a.py").write_text("haystack\n", encoding="utf-8")
    result = asyncio.run(TextSearchTool(str(tmp_path)).execute({"query": "needle"}))

    assert result["success"] is True
    assert result["verdict"] == "NOT_FOUND"
    assert result["total_count"] == 0
    assert result["results"] == []


def test_search_text_worker_failure_is_an_error(tmp_path, monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools import text_search_tool
    from tree_sitter_analyzer.mcp.tools.text_search_tool import TextSearchTool
    from tree_sitter_analyzer.text_search import TextSearchError

    def fail(_request):
        raise TextSearchError("SOURCE_SCAN_BUDGET_EXCEEDED")

    monkeypatch.setattr(text_search_tool, "search_text_bounded", fail)
    result = asyncio.run(TextSearchTool(str(tmp_path)).execute({"query": "needle"}))

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert result["error_code"] == "SOURCE_SCAN_BUDGET_EXCEEDED"
    assert result["results"] == []
    assert result["source_evidence"]["scan_complete"] is False


def test_search_text_typo_is_rejected_before_scan(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    result = asyncio.run(
        build_search_facade(str(tmp_path)).execute(
            {"action": "text", "query": "needle", "limt": 2}
        )
    )

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert result["suggestions"] == {"limt": "limit"}


def test_search_text_rejects_symlink_scope_at_the_mcp_boundary(tmp_path) -> None:
    if os.name == "nt":
        return

    from tree_sitter_analyzer.mcp.tools.text_search_tool import TextSearchTool

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.py").write_text("needle\n", encoding="utf-8")
    os.symlink(source, tmp_path / "linked-src")

    result = asyncio.run(
        TextSearchTool(str(tmp_path)).execute({"query": "needle", "root": "linked-src"})
    )

    assert result["success"] is False
    assert result["error_code"] == "SOURCE_ROOT_SYMLINK"


def test_search_facade_returns_error_envelope_for_missing_scope(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    result = asyncio.run(
        build_search_facade(str(tmp_path)).execute(
            {"action": "text", "query": "needle", "root": "missing"}
        )
    )

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert result["error_code"] == "SOURCE_ROOT_UNAVAILABLE"
    assert result["results"] == []
    assert result["source_evidence"]["scan_complete"] is False


def test_search_facade_returns_error_envelope_for_outside_scope(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    result = asyncio.run(
        build_search_facade(str(tmp_path)).execute(
            {"action": "text", "query": "needle", "root": "../outside"}
        )
    )

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert result["results"] == []


def test_search_facade_returns_error_envelope_for_external_symlink(tmp_path) -> None:
    if os.name == "nt":
        return

    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    os.symlink(outside, tmp_path / "outside-link")

    result = asyncio.run(
        build_search_facade(str(tmp_path)).execute(
            {"action": "text", "query": "needle", "root": "outside-link"}
        )
    )

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert result["error_code"] == "SOURCE_ROOT_OUTSIDE_PROJECT"
    assert result["results"] == []


def test_search_facade_rejects_symlink_project_root(tmp_path) -> None:
    if os.name == "nt":
        return

    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("needle\n", encoding="utf-8")
    link = tmp_path / "project-link"
    os.symlink(project, link)

    result = asyncio.run(
        build_search_facade(str(link)).execute({"action": "text", "query": "needle"})
    )

    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert result["error_code"] == "SOURCE_ROOT_SYMLINK"
    assert result["results"] == []
