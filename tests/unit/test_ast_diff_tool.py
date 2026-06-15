"""Tests for tree_sitter_analyzer.mcp.tools.ast_diff_tool — previously ZERO coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool


@pytest.fixture
def tool():
    return ASTDiffTool(project_root="/tmp/test_project")


class TestASTDiffToolInit:
    def test_default_project_root(self):
        t = ASTDiffTool()
        assert t.project_root is None

    def test_custom_project_root(self):
        t = ASTDiffTool(project_root="/src")
        assert t.project_root == "/src"


class TestASTDiffToolDefinition:
    def test_get_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert isinstance(defn, dict)
        assert "name" in defn
        assert defn["name"] == "ast_diff"

    def test_get_tool_schema(self, tool):
        schema = tool.get_tool_schema()
        assert isinstance(schema, dict)
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_schema_has_file_path_property(self, tool):
        schema = tool.get_tool_schema()
        assert "file_path" in schema["properties"]


class TestASTDiffToolValidation:
    def test_validate_with_file_path(self, tool):
        # diff_git mode requires file_path — valid call returns True
        assert (
            tool.validate_arguments({"mode": "diff_git", "file_path": "/src/main.py"})
            is True
        )

    def test_validate_missing_file_path(self, tool):
        # diff_git mode raises ValueError when file_path is absent
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "diff_git"})

    def test_validate_empty_file_path(self, tool):
        # falsy file_path also raises
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "diff_git", "file_path": ""})

    def test_validate_diff_files_missing_new_file(self, tool):
        # diff_files with old_file but no new_file → raises (line 145-146)
        with pytest.raises(ValueError, match="old_file and new_file are required"):
            tool.validate_arguments({"mode": "diff_files", "old_file": "/a.py"})

    def test_validate_diff_strings_missing_new_source(self, tool):
        # diff_strings with old_source but no new_source → raises (line 154)
        with pytest.raises(ValueError, match="old_source and new_source are required"):
            tool.validate_arguments(
                {"mode": "diff_strings", "old_source": "x = 1", "language": "python"}
            )

    def test_validate_diff_strings_missing_language(self, tool):
        # diff_strings with both sources but no language → raises (line 158)
        with pytest.raises(ValueError, match="language is required"):
            tool.validate_arguments(
                {
                    "mode": "diff_strings",
                    "old_source": "x = 1",
                    "new_source": "x = 2",
                }
            )

    def test_validate_diff_files_valid(self, tool):
        # diff_files with both file paths → True
        assert (
            tool.validate_arguments(
                {
                    "mode": "diff_files",
                    "old_file": "/a.py",
                    "new_file": "/b.py",
                }
            )
            is True
        )

    def test_validate_diff_strings_valid(self, tool):
        # diff_strings fully specified → True
        assert (
            tool.validate_arguments(
                {
                    "mode": "diff_strings",
                    "old_source": "x = 1",
                    "new_source": "x = 2",
                    "language": "python",
                }
            )
            is True
        )


class TestASTDiffToolExecution:
    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tool):
        # diff_git gracefully falls back to empty string for missing git objects
        # — returns a result dict (no raise), success may be True or False
        result = await tool.execute(
            {"mode": "diff_git", "file_path": "/nonexistent/file.py"}
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_diff_files_mode(self, tool):
        # diff_files path (line 181) — mock differ.diff_files
        mock_differ = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"hunks": [{"kind": "signature_change"}]}
        mock_differ.diff_files.return_value = mock_result

        with patch.object(tool, "_get_differ", return_value=mock_differ):
            result = await tool.execute(
                {
                    "mode": "diff_files",
                    "old_file": "/tmp/a.py",
                    "new_file": "/tmp/b.py",
                }
            )
        assert isinstance(result, dict)
        mock_differ.diff_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_git_mode(self, tool):
        # The correct mode name is "diff_git"
        with patch.object(tool, "_diff_git") as mock_git:
            mock_result = MagicMock()
            mock_result.to_dict.return_value = {"changes": []}
            mock_git.return_value = mock_result
            result = await tool.execute(
                {
                    "file_path": "/src/main.py",
                    "mode": "diff_git",
                }
            )
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_git_timeout_fallback(self, tool):
        """_diff_git falls back to empty string on subprocess TimeoutExpired (lines 234-235, 247-248)."""
        import subprocess

        def _subprocess_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=10)

        with patch("subprocess.run", side_effect=_subprocess_timeout):
            # Should not raise — returns a result dict (empty diff)
            result = await tool.execute(
                {
                    "mode": "diff_git",
                    "file_path": "src/main.py",
                }
            )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_with_invalid_mode(self, tool):
        # An unrecognized explicit mode still raises ValueError — updated to
        # enumerate all three valid mode signatures (issue #529 Leg E).
        with pytest.raises(ValueError, match="diff_files|diff_strings|diff_git"):
            await tool.execute(
                {
                    "file_path": "/src/main.py",
                    "mode": "invalid_mode",
                }
            )


class TestASTDiffModeInference:
    """Leg A+B — mode is inferred from argument shape when omitted."""

    def test_infer_diff_git_from_refs(self, tool):
        # Leg A: old_ref+new_ref present, no mode → inferred as diff_git
        # validate_arguments returns True (file_path is not required for diff_git
        # when old_ref/new_ref fully specify the refs; validate just needs file_path)
        result = tool._resolve_mode(
            {"old_ref": "HEAD~1", "new_ref": "HEAD", "file_path": "src/main.py"}
        )
        assert result == "diff_git"

    def test_infer_diff_strings_from_sources(self, tool):
        # Leg B: old_source+new_source present, no mode → inferred as diff_strings
        result = tool._resolve_mode(
            {
                "old_source": "def f(): pass",
                "new_source": "def g(): pass",
                "language": "python",
            }
        )
        assert result == "diff_strings"

    def test_infer_diff_files_default(self, tool):
        # old_file+new_file → diff_files
        result = tool._resolve_mode({"old_file": "/a.py", "new_file": "/b.py"})
        assert result == "diff_files"

    def test_default_refs_do_not_steal_string_diff(self, tool):
        # Codex P2 on #551: the CLI bridge materializes old_ref/new_ref
        # defaults on EVERY call — sources must win over bare ref fields.
        result = tool._resolve_mode(
            {
                "old_source": "def f(): pass",
                "new_source": "def g(): pass",
                "language": "python",
                "old_ref": "HEAD~1",
                "new_ref": "HEAD",
            }
        )
        assert result == "diff_strings"

    def test_refs_without_file_path_do_not_infer_git(self, tool):
        # The git signature requires its file_path discriminator; bare
        # default refs match nothing (validate raises the enumerating error).
        result = tool._resolve_mode({"old_ref": "HEAD~1", "new_ref": "HEAD"})
        assert result == ""

    def test_explicit_mode_wins_over_inference(self, tool):
        # Explicit mode always wins — even if old_source/new_source present,
        # explicit mode=diff_files is honored
        result = tool._resolve_mode(
            {
                "mode": "diff_files",
                "old_source": "x = 1",
                "new_source": "x = 2",
                "language": "python",
            }
        )
        assert result == "diff_files"

    def test_validate_git_mode_inferred_no_explicit_mode(self, tool):
        # Leg A (validate path): {file_path, old_ref, new_ref} without mode → validates OK
        assert (
            tool.validate_arguments(
                {
                    "file_path": "src/main.py",
                    "old_ref": "HEAD~1",
                    "new_ref": "HEAD",
                }
            )
            is True
        )

    def test_validate_strings_mode_inferred_no_explicit_mode(self, tool):
        # Leg B (validate path): {old_source, new_source, language} without mode → validates OK
        assert (
            tool.validate_arguments(
                {
                    "old_source": "def f(): pass",
                    "new_source": "def g(): pass",
                    "language": "python",
                }
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_execute_git_inferred_no_explicit_mode(self, tool):
        # Leg A (execute path): {file_path, old_ref, new_ref} without mode
        # must reach _diff_git (not fail with Unknown mode)
        with patch.object(tool, "_diff_git") as mock_git:
            mock_result = MagicMock()
            mock_result.to_dict.return_value = {"changes": []}
            mock_git.return_value = mock_result
            result = await tool.execute(
                {
                    "file_path": "src/main.py",
                    "old_ref": "HEAD~1",
                    "new_ref": "HEAD",
                }
            )
        assert isinstance(result, dict)
        mock_git.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_strings_inferred_no_explicit_mode(self, tool):
        # Leg B (execute path): {old_source, new_source, language} without mode
        # must call differ.diff_strings (not fail with Unknown mode)
        from unittest.mock import MagicMock, patch

        mock_differ = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"changes": []}
        mock_differ.diff_strings.return_value = mock_result

        with patch.object(tool, "_get_differ", return_value=mock_differ):
            result = await tool.execute(
                {
                    "old_source": "def f(): pass",
                    "new_source": "def g(): pass",
                    "language": "python",
                }
            )
        assert isinstance(result, dict)
        mock_differ.diff_strings.assert_called_once()


class TestASTDiffSchemaHonesty:
    """Leg C — mode must NOT be in schema required."""

    def test_mode_not_in_required(self, tool):
        # Leg C: mode is runtime-resolved, so required must NOT include it
        schema = tool.get_tool_schema()
        assert "mode" not in schema.get("required", []), (
            "mode must not be in 'required' — it is runtime-resolved from arg shape"
        )


class TestASTDiffErrorQuality:
    """Leg E — no-signature-match error enumerates all three mode signatures."""

    def test_no_match_error_mentions_all_three_modes(self, tool):
        # Leg E: when args match NO mode signature, error must enumerate all three
        with pytest.raises(ValueError) as exc_info:
            tool.validate_arguments({})  # no mode, no recognizable args
        msg = str(exc_info.value)
        # All three mode signatures must appear
        assert "old_file" in msg and "new_file" in msg, "diff_files signature missing"
        assert "old_source" in msg and "new_source" in msg, (
            "diff_strings signature missing"
        )
        assert "old_ref" in msg and "new_ref" in msg, "diff_git signature missing"


# ---------------------------------------------------------------------------
# Issue #552 — node-body budget tests
# ---------------------------------------------------------------------------

# Small deterministic fixture used throughout this section.
# old: one function; new: two functions (bar added).
_OLD_SRC = "def foo():\n    pass\n"
_NEW_SRC = "def foo():\n    pass\n\ndef bar():\n    pass\n"
_LANG = "python"


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
        assert default_bytes == 746
        assert bodies_bytes == 1877

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


class TestAstDiffAgentSummaryEnvelope:
    """#744: ast_diff must include agent_summary and summary_line in response."""

    @pytest.fixture
    def tool(self):
        return ASTDiffTool()

    @pytest.mark.asyncio
    async def test_response_has_agent_summary_with_hunks(self, tool):
        """When diff produces hunks, agent_summary is a dict with count in summary_line."""
        result = await tool.execute(
            {
                "mode": "diff_strings",
                "old_source": _OLD_SRC,
                "new_source": _NEW_SRC,
                "language": _LANG,
                "output_format": "json",
            }
        )
        assert "agent_summary" in result, "agent_summary missing from envelope"
        assert "summary_line" in result, "summary_line missing from envelope"
        # Codex P2: agent_summary must be a dict, not a string
        assert isinstance(result["agent_summary"], dict), "agent_summary must be a dict"
        assert result["agent_summary"]["summary_line"] == result["summary_line"]
        assert "verdict" in result["agent_summary"]
        # There are hunks — summary must mention count, not "No AST changes"
        assert "No AST changes" not in result["agent_summary"]["summary_line"]

    @pytest.mark.asyncio
    async def test_response_has_agent_summary_no_hunks(self, tool):
        """When old == new (no hunks), agent_summary dict says 'No AST changes'."""
        result = await tool.execute(
            {
                "mode": "diff_strings",
                "old_source": _OLD_SRC,
                "new_source": _OLD_SRC,  # identical → no hunks
                "language": _LANG,
                "output_format": "json",
            }
        )
        assert "agent_summary" in result, "agent_summary missing from envelope"
        assert isinstance(result["agent_summary"], dict), "agent_summary must be a dict"
        assert "No AST changes" in result["agent_summary"]["summary_line"]

    @pytest.mark.asyncio
    async def test_response_has_agent_summary_parse_failure(self, tool):
        """When both sources fail to parse (unsupported language), verdict is ERROR."""
        result = await tool.execute(
            {
                "mode": "diff_strings",
                "old_source": "a = 1",
                "new_source": "b = 2",
                # 'cobol' is unsupported → both parse calls return success=False
                # → ASTDiffer emits a single error sentinel hunk with no old/new
                "language": "cobol",
                "output_format": "json",
            }
        )
        assert "agent_summary" in result
        assert isinstance(result["agent_summary"], dict)
        # Parse failure → error hunk → verdict ERROR, not the generic "INFO"
        assert result["verdict"] == "ERROR"
        assert result["agent_summary"]["verdict"] == "ERROR"
        assert result["agent_summary"]["summary_line"] == "Both sources failed to parse"
