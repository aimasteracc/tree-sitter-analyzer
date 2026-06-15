"""Tests for issue #806: per-file error envelope in incremental sync MCP tool.

Regression suite for the bug where a single file raising RecursionError during
AST walking aborted the entire batch and the MCP response reported only a bare
"Sync failed: …" message with no file attribution and no partial-success count.

The fix lives in two layers:
  - incremental_sync.py  — per-file broad exception handling in
    _index_new_file / _reindex_modified so one bad file cannot abort the batch.
  - incremental_sync_tool.py — MCP _sync() must surface error details (file
    paths + error types) from SyncResult.details in the response envelope.

Strategy: patch IncrementalSync.sync to return a controlled SyncResult, then
verify the MCP tool properly surfaces all fields from it.  This isolates the
MCP tool's response-formation logic from the incremental_sync engine (which
has its own test suite in tests/unit/test_incremental_sync.py).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.incremental_sync import IncrementalSync, SyncResult
from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
    CodeGraphIncrementalSyncTool,
)


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "good_a.py").write_text("def alpha():\n    pass\n")
    (src / "good_b.py").write_text("def beta():\n    pass\n")
    (src / "pathological.py").write_text("x = 1 + 2\n")
    return tmp_path


@pytest.fixture
def mcp_tool(project):
    return CodeGraphIncrementalSyncTool(str(project))


def _make_sync_result_with_one_error() -> SyncResult:
    """SyncResult representing 2 successes + 1 RecursionError."""
    result = SyncResult(
        scanned=3,
        new_files=2,
        updated_files=0,
        deleted_files=0,
        unchanged_files=0,
        errors=1,
    )
    result.details = [
        {
            "file": "src/good_a.py",
            "considered": "indexed",
            "action": "indexed",
            "status": "indexed",
        },
        {
            "file": "src/good_b.py",
            "considered": "indexed",
            "action": "indexed",
            "status": "indexed",
        },
        {
            "file": "src/pathological.py",
            "considered": "indexed",
            "action": "indexed",
            "status": "error",
            "error_type": "RecursionError",
            "error_message": "maximum recursion depth exceeded",
        },
    ]
    return result


# ---------------------------------------------------------------------------
# MCP tool layer: response envelope must carry per-file error attribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMCPResponseEnvelopeOnPerFileError:
    """Issue #806: MCP _sync() response must surface per-file errors."""

    async def test_response_success_true_when_partial_success(self, mcp_tool, project):
        """success=True when some files indexed; one file errored (partial success)."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        # Partial sync with at least some successes → success=True
        assert result["success"] is True

    async def test_response_contains_error_count(self, mcp_tool, project):
        """errors field in response must equal exactly 1 (one file failed)."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        # Exactly 1 error must be reported — not swallowed
        assert result["errors"] == 1

    async def test_response_details_include_failing_file_path(self, mcp_tool, project):
        """details list must include the file that raised RecursionError."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        details = result.get("details", [])
        error_details = [d for d in details if d.get("status") == "error"]
        assert len(error_details) == 1
        # Exact path — substring match would pass if only a basename is returned,
        # hiding loss of directory attribution (the core regression in #806).
        assert error_details[0]["file"] == "src/pathological.py"

    async def test_response_error_detail_has_exception_type(self, mcp_tool, project):
        """Error detail must carry error_type=RecursionError (Issue #806)."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        details = result.get("details", [])
        error_details = [d for d in details if d.get("status") == "error"]
        assert len(error_details) == 1
        assert error_details[0].get("error_type") == "RecursionError"

    async def test_response_error_detail_has_error_message(self, mcp_tool, project):
        """Error detail must carry the exception message (Issue #806)."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        details = result.get("details", [])
        error_details = [d for d in details if d.get("status") == "error"]
        assert len(error_details) == 1
        assert (
            error_details[0].get("error_message") == "maximum recursion depth exceeded"
        )

    async def test_sibling_files_still_indexed_after_per_file_error(
        self, mcp_tool, project
    ):
        """good_a.py and good_b.py must be indexed despite pathological.py error."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        # 2 good files indexed, 1 error — counts must be exact
        assert result["new_files"] == 2
        assert result["errors"] == 1

    async def test_response_includes_scanned_count(self, mcp_tool, project):
        """scanned field must report total files examined (for partial-success context)."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        # 3 files scanned total
        assert result["scanned"] == 3


# ---------------------------------------------------------------------------
# Outer catch-all in MCP tool: must not swallow batch for outer exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMCPOuterExceptionSurface:
    """Outer sync.sync() exception must surface as error envelope, not be swallowed."""

    async def test_outer_exception_returns_error_envelope(self, mcp_tool, project):
        """If sync.sync() itself raises (not per-file), MCP layer returns error."""
        with patch.object(
            IncrementalSync,
            "sync",
            side_effect=RuntimeError("unexpected top-level failure"),
        ):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        assert result["success"] is False

    async def test_outer_exception_error_message_includes_exception_type(
        self, mcp_tool, project
    ):
        """Error message must name the exception type (not just a bare message)."""
        with patch.object(
            IncrementalSync,
            "sync",
            side_effect=RuntimeError("unexpected top-level failure"),
        ):
            result = await mcp_tool.execute(
                {"mode": "sync", "max_files": 100, "output_format": "json"}
            )

        error_msg = result.get("error", "")
        assert "RuntimeError" in error_msg


# ---------------------------------------------------------------------------
# TOON default path: error attribution must survive TOON formatting (#806)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMCPResponseEnvelopeOnPerFileErrorToon:
    """Issue #806: per-file error detail must be visible in the default TOON path."""

    async def test_toon_response_toon_content_contains_error_path(
        self, mcp_tool, project
    ):
        """Default TOON format must preserve the failing file path in toon_content."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            # no output_format → defaults to TOON (the MCP default)
            result = await mcp_tool.execute({"mode": "sync", "max_files": 100})

        assert result.get("format") == "toon"
        toon_content = result.get("toon_content", "")
        # The failing file path must appear in the textual TOON summary so MCP
        # callers that read toon_content can identify which file errored.
        assert "pathological.py" in toon_content

    async def test_toon_response_errors_field_surfaced(self, mcp_tool, project):
        """errors=1 must be present in the TOON envelope (not stripped)."""
        controlled_result = _make_sync_result_with_one_error()

        with patch.object(IncrementalSync, "sync", return_value=controlled_result):
            result = await mcp_tool.execute({"mode": "sync", "max_files": 100})

        assert result.get("errors") == 1
