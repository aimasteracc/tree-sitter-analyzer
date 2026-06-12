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
