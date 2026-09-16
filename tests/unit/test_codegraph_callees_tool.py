"""RED tests for Feature 1 (Synapse): codegraph_callees tool surface.

The CodeGraphCalleesTool response shape today does NOT include the new
``callee_resolution`` / ``callee_resolved_file`` keys. Once the resolver
ships, every callee entry must carry them.

Harness mirrors ``tests/unit/test_callers_callees_tools.py`` so the
existing project-root + tool fixtures work the same way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit._navigation_test_support import assert_sqlite_deadline_falls_back
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool


@pytest.fixture
def indexed_call_project(tmp_path: Path) -> str:
    (tmp_path / "helper.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "worker.py").write_text(
        "from helper import helper\n\n\ndef build():\n    return helper()\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path)


@pytest.fixture
def callees_tool(indexed_call_project: str) -> CodeGraphCalleesTool:
    return CodeGraphCalleesTool(indexed_call_project)


class TestCodeGraphCalleesResolutionFields:
    """Once Synapse lands, every callee entry exposes the resolution columns."""

    @pytest.mark.asyncio
    async def test_callees_tool_response_includes_resolution_fields(
        self, callees_tool: CodeGraphCalleesTool
    ) -> None:
        """Each callees[*] entry must have callee_resolution + resolved_file.

        Uses a tiny indexed project where worker.build imports helper.helper,
        so the response list must be non-empty and include a resolved
        cross-file project callee without scanning the whole repository.
        """
        result = await callees_tool.execute(
            {"function_name": "build", "output_format": "json"}
        )
        assert result["success"] is True, f"tool errored: {result}"
        callees = result.get("callees", [])
        assert isinstance(callees, list), (
            f"expected list of callees, got {type(callees).__name__}"
        )
        assert callees, (
            "build is known to call helper; got an empty "
            "callees list, which suggests the cache is stale or the index "
            "missed the file"
        )

        # Every entry must carry the two new keys.
        missing_resolution = [
            i for i, e in enumerate(callees) if "callee_resolution" not in e
        ]
        missing_resolved_file = [
            i for i, e in enumerate(callees) if "callee_resolved_file" not in e
        ]
        assert not missing_resolution, (
            f"{len(missing_resolution)} of {len(callees)} callee entries "
            f"are missing 'callee_resolution' (e.g. entry "
            f"{callees[missing_resolution[0]]!r})"
        )
        assert not missing_resolved_file, (
            f"{len(missing_resolved_file)} of {len(callees)} callee entries "
            f"are missing 'callee_resolved_file' (e.g. entry "
            f"{callees[missing_resolved_file[0]]!r})"
        )

        # Values must come from the documented enum.
        allowed = {"local", "project", "stdlib", "third_party", "dynamic", "unknown"}
        for entry in callees:
            res = entry["callee_resolution"]
            assert res in allowed, (
                f"callee_resolution={res!r} not in allowed set {sorted(allowed)}"
            )
            # resolved_file is a string (possibly empty for unknown/stdlib).
            assert isinstance(entry["callee_resolved_file"], str)

        project_edges = [
            e
            for e in callees
            if e["callee_resolution"] == "project"
            and e["callee_resolved_file"] == "helper.py"
        ]
        assert project_edges, (
            "expected build -> helper to resolve across files via the EdgeStore "
            f"read path. Sample entries: {callees[:3]}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_type", [CodeGraphCallersTool, CodeGraphCalleesTool])
async def test_sqlite_deadline_falls_back_to_coordinate_query(
    tmp_path, monkeypatch, tool_type
) -> None:
    await assert_sqlite_deadline_falls_back(
        tmp_path,
        monkeypatch,
        tool_type(str(tmp_path)),
        {"function_name": "target"},
    )


# Issue #1450：关闭正文后必须彻底绕过源码读取路径。
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_type", "function_name"),
    [
        (CodeGraphCallersTool, "Service.target"),
        (CodeGraphCalleesTool, "caller"),
    ],
)
async def test_certified_graph_routes_report_cache_source(
    tmp_path, monkeypatch, tool_type, function_name
) -> None:
    """认证图回退路径必须准确声明缓存证据来源。"""
    (tmp_path / "sample.py").write_text(
        "class Service:\n"
        "    def target(self):\n"
        "        return 1\n\n"
        "def caller(service):\n"
        "    return service.target()\n",
        encoding="utf-8",
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    tool = tool_type(str(tmp_path))
    monkeypatch.setattr(tool, "_cache_call_graph_built", lambda _cache: False)
    result = await tool.execute(
        {"function_name": function_name, "output_format": "json"}
    )

    assert result["data_source"] == "cache"


@pytest.mark.parametrize("tool_type", [CodeGraphCallersTool, CodeGraphCalleesTool])
def test_call_graph_tools_expose_body_opt_out(tool_type) -> None:
    """调用图工具必须声明保留默认行为的正文开关。"""
    schema = tool_type().get_tool_schema()

    assert schema["properties"]["include_bodies"] == {
        "type": "boolean",
        "description": (
            "When false, omit "
            f"{'caller' if tool_type is CodeGraphCallersTool else 'callee'} "
            "source bodies and return only call-graph coordinates and metadata."
        ),
        "default": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_type", "function_name", "list_key", "count_key", "inline_method"),
    [
        (
            CodeGraphCallersTool,
            "helper",
            "callers",
            "caller_count",
            "_inline_caller_bodies",
        ),
        (
            CodeGraphCalleesTool,
            "build",
            "callees",
            "callee_count",
            "_inline_callee_bodies",
        ),
    ],
)
async def test_include_bodies_false_skips_source_enrichment(
    indexed_call_project,
    monkeypatch,
    tool_type,
    function_name,
    list_key,
    count_key,
    inline_method,
) -> None:
    """关闭正文时仍返回完整坐标结果，并且不进入源码读取路径。"""
    tool = tool_type(indexed_call_project)

    def reject_inline(*_args, **_kwargs):
        raise AssertionError("include_bodies=false must skip source enrichment")

    monkeypatch.setattr(tool, inline_method, reject_inline)
    result = await tool.execute(
        {
            "function_name": function_name,
            "include_bodies": False,
            "output_format": "json",
        }
    )

    assert result[count_key] == 1
    assert len(result[list_key]) == 1
    assert "body" not in result[list_key][0]
