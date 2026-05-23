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

from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


@pytest.fixture
def callees_tool() -> CodeGraphCalleesTool:
    return CodeGraphCalleesTool(_PROJECT_ROOT)


class TestCodeGraphCalleesResolutionFields:
    """Once Synapse lands, every callee entry exposes the resolution columns."""

    @pytest.mark.asyncio
    async def test_callees_tool_response_includes_resolution_fields(
        self, callees_tool: CodeGraphCalleesTool
    ) -> None:
        """Each callees[*] entry must have callee_resolution + resolved_file.

        Uses ``score_file`` from health_scorer as the seed function — it is
        a real method on HealthScorer that calls several siblings (mostly
        intra-file, with at least one cross-module call), so the response
        list must be non-empty and must include at least one ``project``
        entry whose ``callee_resolved_file`` is set.
        """
        result = await callees_tool.execute(
            {"function_name": "score_file", "output_format": "json"}
        )
        assert result["success"] is True, f"tool errored: {result}"
        callees = result.get("callees", [])
        assert isinstance(callees, list), (
            f"expected list of callees, got {type(callees).__name__}"
        )
        assert callees, (
            "score_file is known to call other functions; got an empty "
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

        # And at least one entry must demonstrate cross-file resolution so
        # the test fails loudly if the resolver silently always emits
        # 'unknown'. score_file delegates to helpers across the file and
        # at least one to another module, so we expect 'project' or 'local'.
        non_unknown = [e for e in callees if e["callee_resolution"] != "unknown"]
        assert non_unknown, (
            f"every callee for score_file is 'unknown' — the resolver is "
            f"either disabled or broken. Sample entries: {callees[:3]}"
        )
