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

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool


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
