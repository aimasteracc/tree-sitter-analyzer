import os
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


# Helper to create a temporary file with specific encoding
def create_temp_file(content: str, encoding: str, tmp_path: str) -> str:
    file_path = os.path.join(tmp_path, f"test_file_{encoding}.txt")
    with open(file_path, "w", encoding=encoding) as f:
        f.write(content)
    return file_path


@pytest.mark.asyncio
async def test_sjis_auto_detection_success(tmp_path):
    """
    Tests if Shift_JIS encoding is auto-detected and the search is successful.
    """
    sjis_content = "これはShift_JISエンコーディングのテストです。"
    sjis_file = create_temp_file(sjis_content, "shift_jis", str(tmp_path))

    tool = SearchContentTool(project_root=str(tmp_path))

    # Mock run_command_capture to check the command
    with patch(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        new_callable=AsyncMock,
    ) as mock_run:
        # Simulate ripgrep finding a match - use proper JSON format
        rg_json = {
            "type": "match",
            "data": {
                "path": {"text": sjis_file},
                "lines": {"text": sjis_content},
                "line_number": 1,
                "submatches": [{"match": {"text": "Shift_JIS"}, "start": 3, "end": 12}],
                "absolute_offset": 0,
            },
        }
        import json

        mock_run.return_value = (
            0,
            (json.dumps(rg_json, ensure_ascii=False) + "\n").encode("utf-8"),
            b"",
        )

        arguments = {
            "query": "Shift_JIS",
            "files": [sjis_file],
        }

        result = await tool.execute(arguments)

        # Check that rg was called with the correct encoding
        called_cmd = mock_run.call_args[0][0]
        assert "--encoding" in called_cmd
        assert "shift-jis" in called_cmd

        # Check that the result is correct
        assert result["success"]
        assert result["count"] > 0


@pytest.mark.asyncio
async def test_utf8_default_handling(tmp_path):
    """
    Tests if UTF-8 files are handled correctly by default.
    """
    utf8_content = "This is a UTF-8 encoding test."
    utf8_file = create_temp_file(utf8_content, "utf-8", str(tmp_path))

    tool = SearchContentTool(project_root=str(tmp_path))

    with patch(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        new_callable=AsyncMock,
    ) as mock_run:
        # Simulate ripgrep finding a match - use proper JSON format
        rg_json = {
            "type": "match",
            "data": {
                "path": {"text": utf8_file},
                "lines": {"text": utf8_content},
                "line_number": 1,
                "submatches": [{"match": {"text": "UTF-8"}, "start": 10, "end": 15}],
                "absolute_offset": 0,
            },
        }
        import json

        mock_run.return_value = (
            0,
            (json.dumps(rg_json, ensure_ascii=False) + "\n").encode("utf-8"),
            b"",
        )

        arguments = {
            "query": "UTF-8",
            "files": [utf8_file],
        }

        result = await tool.execute(arguments)

        mock_run.call_args[0][0]
        # Depending on the system, rg might not need --encoding for utf-8
        # So we just check for success
        assert result["success"]
        assert result["count"] > 0


@pytest.mark.asyncio
async def test_explicit_encoding_overrides_auto_detection(tmp_path):
    """
    Tests that an explicitly provided encoding parameter overrides auto-detection.
    """
    sjis_content = "これはShift_JISエンコーディングのテストです。"
    sjis_file = create_temp_file(sjis_content, "shift_jis", str(tmp_path))

    tool = SearchContentTool(project_root=str(tmp_path))

    with patch(
        "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, b"", b"")  # No match expected

        # Search with a wrong but explicit encoding
        arguments = {
            "query": "Shift_JIS",
            "files": [sjis_file],
            "encoding": "latin1",
            "roots": [str(tmp_path)],  # Pass a valid directory
        }

        await tool.execute(arguments)

        called_cmd = mock_run.call_args[0][0]
        assert "--encoding" in called_cmd
        assert "latin1" in called_cmd
        assert "shift-jis" not in called_cmd


@pytest.mark.asyncio
async def test_encoding_detection_failure_fallback(tmp_path):
    """
    Tests that the tool falls back to UTF-8 when encoding detection fails.
    """
    # Create a file with ambiguous content that might fail detection
    ambiguous_content = "\x81\x40"  # Invalid SJIS
    ambiguous_file = os.path.join(str(tmp_path), "ambiguous.txt")
    with open(ambiguous_file, "wb") as f:
        f.write(ambiguous_content.encode("latin1"))

    tool = SearchContentTool(project_root=str(tmp_path))

    with (
        patch(
            "tree_sitter_analyzer.mcp.tools.fd_rg_utils.run_command_capture",
            new_callable=AsyncMock,
        ) as mock_run,
        patch(
            "tree_sitter_analyzer.encoding_utils.EncodingManager.detect_encoding",
            return_value=None,
        ) as mock_detect,
    ):
        mock_run.return_value = (1, b"", b"")  # Expect no match or error

        arguments = {
            "query": "test",
            "files": [ambiguous_file],
        }

        await tool.execute(arguments)

        mock_detect.assert_called_once()
        called_cmd = mock_run.call_args[0][0]
        # Should not have --encoding flag, letting ripgrep use its default (usually UTF-8)
        assert "--encoding" not in called_cmd
