"""Response-size and node-body budget coverage for AST diff."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool

_OLD_SRC = "def foo():\n    pass\n"
_NEW_SRC = "def foo():\n    pass\n\ndef bar():\n    pass\n"
_LANG = "python"


@pytest.fixture
def tool():
    return ASTDiffTool(project_root="/tmp/test_project")


class TestASTDiffNodeBudget:
    """Issue #552 — default response must NOT contain children; opt-in adds them."""

    @pytest.mark.asyncio
    async def test_default_response_has_no_children_key(self, tool):
        """Hunk nodes must NOT contain a 'children' key when include_node_bodies is omitted."""
        result = await tool.execute(
            {
                "mode": "diff_strings",
                "old_source": _OLD_SRC,
                "new_source": _NEW_SRC,
                "language": _LANG,
                "output_format": "json",
            }
        )
        hunks = result.get("hunks", [])
        assert len(hunks) == 1  # exactly one added hunk
        hunk = hunks[0]
        new_node = hunk.get("new")
        assert new_node is not None, "hunk must have 'new' node"
        assert "children" not in new_node, (
            "default response must NOT inline children — issue #552"
        )

    @pytest.mark.asyncio
    async def test_default_response_has_child_count(self, tool):
        """Hunk nodes MUST have child_count (exact pin) when include_node_bodies is omitted."""
        result = await tool.execute(
            {
                "mode": "diff_strings",
                "old_source": _OLD_SRC,
                "new_source": _NEW_SRC,
                "language": _LANG,
                "output_format": "json",
            }
        )
        hunks = result.get("hunks", [])
        assert len(hunks) == 1
        new_node = hunks[0].get("new", {})
        assert "child_count" in new_node, "child_count must be present in default mode"
        # Grammar-pinned exact assertion: function_definition has 5 children
        # (def keyword, name identifier, parameters, colon, body block).
        # If a grammar bump shifts this, the test MUST go red.
        assert new_node["child_count"] == 5

    @pytest.mark.asyncio
    async def test_schema_has_include_node_bodies_param(self, tool):
        """Schema must expose include_node_bodies boolean param."""
        schema = tool.get_tool_schema()
        props = schema.get("properties", {})
        assert "include_node_bodies" in props, (
            "include_node_bodies param must be in the tool schema"
        )
        assert props["include_node_bodies"].get("type") == "boolean"
        # Must NOT be in required (runtime-resolved param convention)
        assert "include_node_bodies" not in schema.get("required", [])

    @pytest.mark.asyncio
    async def test_default_bytes_smaller_than_include_bodies_bytes(self, tool):
        """DOCUMENTED RELATIONSHIP: default response < include_node_bodies=True response."""
        import json

        args_base = {
            "mode": "diff_strings",
            "old_source": _OLD_SRC,
            "new_source": _NEW_SRC,
            "language": _LANG,
            "output_format": "json",
        }
        default_result = await tool.execute(args_base)
        bodies_result = await tool.execute({**args_base, "include_node_bodies": True})

        # Strip volatile envelope fields (timing varies run-to-run) so the
        # byte counts are deterministic and can be pinned EXACTLY (CLAUDE.md
        # locked rule: no loose </> assertions — a grammar bump SHOULD go red
        # and force a conscious re-pin).
        _volatile = {
            "elapsed_ms",
            "cache_age_s",
            "from_cache",
            "cache_invalidated_reason",
        }

        def _stable_bytes(d):
            return len(json.dumps({k: v for k, v in d.items() if k not in _volatile}))

        default_bytes = _stable_bytes(default_result)
        bodies_bytes = _stable_bytes(bodies_result)

        # Cost invariant (CLAUDE.md rule 11) pinned exactly: 746 < 1877 — the
        # default is dramatically smaller than the full-body opt-in.
        # Re-pinned after Codex P2 made agent_summary a dict (next_step+verdict).
        # RFC-0022 P0.5: +38 bytes for the action_version echo.
        assert default_bytes == 784
        # RFC-0022 P0.5: +38 bytes for the action_version echo.
        assert bodies_bytes == 1915

    @pytest.mark.asyncio
    async def test_include_node_bodies_true_has_children(self, tool):
        """When include_node_bodies=True, hunk nodes MUST contain 'children' key."""
        result = await tool.execute(
            {
                "mode": "diff_strings",
                "old_source": _OLD_SRC,
                "new_source": _NEW_SRC,
                "language": _LANG,
                "output_format": "json",
                "include_node_bodies": True,
            }
        )
        hunks = result.get("hunks", [])
        assert len(hunks) == 1
        new_node = hunks[0].get("new", {})
        assert "children" in new_node, (
            "include_node_bodies=True must inline children in hunk nodes"
        )
        # Exact pin: function_definition has 5 children (grammar-pinned)
        assert len(new_node["children"]) == 5

    @pytest.mark.asyncio
    async def test_over_budget_sets_children_truncated(self, tool):
        """When include_node_bodies=True and response exceeds budget, set children_truncated."""
        # Patch the budget constant to 1 byte to guarantee truncation
        with patch(
            "tree_sitter_analyzer.mcp.tools.ast_diff_tool.NODE_BODIES_BUDGET", 1
        ):
            result = await tool.execute(
                {
                    "mode": "diff_strings",
                    "old_source": _OLD_SRC,
                    "new_source": _NEW_SRC,
                    "language": _LANG,
                    "output_format": "json",
                    "include_node_bodies": True,
                }
            )
        # Must set the transparency flag when budget is exceeded
        assert result.get("children_truncated") is True, (
            "children_truncated must be True when budget is exceeded"
        )
        assert "bytes_omitted" in result, "bytes_omitted must be present when truncated"
        # Exact pin (deterministic for this fixture at budget=1): the omitted
        # bytes equal full-body minus compact = 1627 - 496 = 1131.
        assert result["bytes_omitted"] == 1131
