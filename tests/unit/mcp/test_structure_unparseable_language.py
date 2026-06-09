"""Structure tools must NOT mask an unparseable-language parse failure
as an empty-success result.

Regression for the Theme-D dogfood finding (2026-06-09): a ``.scala`` file
is extension-mapped to language ``scala`` by ``language_detector`` but no
``tree-sitter-scala`` grammar is installed, so the parse fails. The analysis
engine correctly returns ``AnalysisResult(success=False, ...)``, but the MCP
structure tools only checked ``result is None`` and then fabricated a
``{"success": True, "total_lines": 0, ... "0 classes, 0 methods"}`` envelope.

That lies to an AI agent: it reports a real, non-empty Scala file as a healthy
empty file and even suggests ``extract_code_section`` for non-existent methods.
The CLI errors honestly on the same file (``Unsupported language: scala``), so
this is also a CLI<->MCP parity violation.

The fix: both structure tools must honor ``analysis_result.success`` and
propagate the failure so the MCP boundary maps it to a ``language_unsupported``
error envelope (the same path Bash already gets).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool

# A real, non-empty golden corpus file whose language (scala) is detected but
# whose tree-sitter grammar is not installed -> parse fails.
UNPARSEABLE_FILE = "tests/golden/corpus_scala.scala"


@pytest.mark.asyncio
async def test_outline_does_not_mask_unparseable_language() -> None:
    """get_code_outline must not report a failed parse as empty-success."""
    tool = GetCodeOutlineTool(project_root=".")
    with pytest.raises(Exception) as exc_info:
        await tool.execute({"file_path": UNPARSEABLE_FILE, "output_format": "json"})
    # The propagated message must let the boundary classify it as
    # ``language_unsupported`` (substring match in error_recovery).
    assert "unsupported language" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_analyze_structure_does_not_mask_unparseable_language() -> None:
    """analyze (structure) must not report a failed parse as empty-success."""
    tool = AnalyzeCodeStructureTool(project_root=".")
    with pytest.raises(Exception) as exc_info:
        await tool.execute({"file_path": UNPARSEABLE_FILE, "output_format": "json"})
    assert "unsupported language" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_structure_boundary_classifies_as_language_unsupported() -> None:
    """The MCP boundary must surface an honest ``language_unsupported`` ERROR
    envelope (verdict=ERROR, success=False) — not a masked empty-success — for
    every structure action on an unparseable-language file.

    This exercises the true client surface (``_dispatch_tool`` + the canonical
    envelope normalizers), so it catches both the masking regression AND any
    error_type misclassification the per-tool ``pytest.raises`` checks miss.
    """
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
    from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
        build_agent_friendly_error,
        ensure_canonical_error_envelope,
        ensure_canonical_success_envelope,
    )
    from tree_sitter_analyzer.mcp.server_utils.tool_registration import (
        _dispatch_tool,
    )

    server = TreeSitterAnalyzerMCPServer(project_root=".")
    server._ensure_registry()
    server._initialization_complete = True

    async def boundary(name: str, args: dict) -> dict:
        try:
            result = await _dispatch_tool(server, name, args)
            if isinstance(result, dict) and result.get("success") is False:
                return ensure_canonical_error_envelope(name, result, arguments=args)
            if isinstance(result, dict):
                return ensure_canonical_success_envelope(name, result, arguments=args)
            return result
        except Exception as e:  # noqa: BLE001 — mirrors handle_call_tool
            return build_agent_friendly_error(name, e, arguments=args)

    for action in ("outline", "analyze"):
        env = await boundary(
            "structure",
            {
                "action": action,
                "file_path": UNPARSEABLE_FILE,
                "output_format": "json",
            },
        )
        verdict = env.get("verdict") or (env.get("agent_summary") or {}).get("verdict")
        assert env.get("success") is False, f"{action}: masked as success"
        assert verdict == "ERROR", f"{action}: verdict={verdict!r}"
        assert env.get("error_type") == "language_unsupported", (
            f"{action}: error_type={env.get('error_type')!r}"
        )
