"""Structure tools must NOT mask an engine parse failure as empty-success.

Regression for the Theme-D dogfood finding (2026-06-09): a ``.scala`` file
was extension-mapped to language ``scala`` by ``language_detector`` while no
``tree-sitter-scala`` grammar was installed, so the parse failed. The analysis
engine correctly returned ``AnalysisResult(success=False, ...)``, but the MCP
structure tools only checked ``result is None`` and then fabricated a
``{"success": True, "total_lines": 0, ... "0 classes, 0 methods"}`` envelope.

That lies to an AI agent: it reports a real, non-empty file as a healthy
empty file and even suggests ``extract_code_section`` for non-existent methods.
The CLI errored honestly on the same file, so it was also a CLI<->MCP parity
violation. Fixed in #414: both tools honor ``analysis_result.success`` and
propagate the failure so the MCP boundary maps it to a ``language_unsupported``
error envelope.

2026-06-10 update: scala graduated (tree-sitter-scala is now a declared
dependency), so no detected-but-grammarless language remains in the default
environment. The tests therefore mock the engine to return
``AnalysisResult(success=False, error_message="Unsupported language: ...")``
— the exact value the engine produced in the original incident — instead of
relying on a real unparseable corpus file. ``examples/Sample.java`` is used
as an existing on-disk path so path validation passes.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.models.result import AnalysisResult

# ---------------------------------------------------------------------------
# C++ content in .py (issue #707): tree-sitter parses via the Python grammar
# and sprinkles ERROR nodes throughout. The outline must surface parse_errors
# and escalate the verdict to WARN so agents don't trust the outline symbols.
# ---------------------------------------------------------------------------
_CPP_CONTENT = """\
#include <iostream>
int main() {
    std::cout << "hello world" << std::endl;
    return 0;
}
"""

# ---------------------------------------------------------------------------
# NUL bytes (issue #707): raw 0x00 in a Python source file shifts line spans
# and may corrupt symbol names. The outline must surface null_bytes +
# encoding_warning and escalate to WARN.
# ---------------------------------------------------------------------------
_PY_WITH_NUL = b"x = 1\x00\nprint(x)\n"

# Existing, non-empty file (so path checks pass); the mocked engine below is
# what simulates the "detected but unparseable" condition.
TARGET_FILE = "examples/Sample.java"


def _unparseable_result() -> AnalysisResult:
    """The engine's honest output for a detected-but-unparseable language."""
    return AnalysisResult(
        file_path=TARGET_FILE,
        language="java",
        success=False,
        error_message="Unsupported language: java",
        elements=[],
    )


def _patch_engine(tool: object) -> None:
    async def _fake_analyze(_request):  # noqa: ANN001
        return _unparseable_result()

    tool.analysis_engine.analyze = _fake_analyze  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_outline_does_not_mask_unparseable_language() -> None:
    """get_code_outline must not report a failed parse as empty-success."""
    tool = GetCodeOutlineTool(project_root=".")
    _patch_engine(tool)
    with pytest.raises(Exception) as exc_info:
        await tool.execute({"file_path": TARGET_FILE, "output_format": "json"})
    # The propagated message must let the boundary classify it as
    # ``language_unsupported`` (substring match in error_recovery).
    assert "unsupported language" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_analyze_structure_does_not_mask_unparseable_language() -> None:
    """analyze (structure) must not report a failed parse as empty-success."""
    tool = AnalyzeCodeStructureTool(project_root=".")
    _patch_engine(tool)
    with pytest.raises(Exception) as exc_info:
        await tool.execute({"file_path": TARGET_FILE, "output_format": "json"})
    assert "unsupported language" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_structure_boundary_classifies_as_language_unsupported() -> None:
    """The MCP boundary must surface an honest ``language_unsupported`` ERROR
    envelope (verdict=ERROR, success=False) — not a masked empty-success — for
    every structure action when the engine reports a parse failure.

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

    # The structure facade routes outline/analyze through inner tools held in
    # ``action_map`` — patch the engine of every inner tool that has one.
    # NOTE: this LOOKS like the classic loop-closure bug but is safe: the
    # closure captures nothing from ``inner`` (every iteration assigns an
    # identical zero-capture coroutine), and all inner tools share the same
    # engine singleton anyway, so each assignment overwrites the same attr.
    # conftest's reset_global_singletons clears the singleton after the test.
    structure_facade = server.tools["structure"]
    patched = 0
    for inner in structure_facade.action_map.values():
        if getattr(inner, "analysis_engine", None) is not None:

            async def _fake_analyze(_request):  # noqa: ANN001
                return _unparseable_result()

            inner.analysis_engine.analyze = _fake_analyze  # type: ignore[attr-defined]
            patched += 1
    assert patched == 2, (
        f"expected to patch exactly the outline+analyze inner tools, patched {patched}"
    )

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
                "file_path": TARGET_FILE,
                "output_format": "json",
            },
        )
        verdict = env.get("verdict") or (env.get("agent_summary") or {}).get("verdict")
        assert env.get("success") is False, f"{action}: masked as success"
        assert verdict == "ERROR", f"{action}: verdict={verdict!r}"
        assert env.get("error_type") == "language_unsupported", (
            f"{action}: error_type={env.get('error_type')!r}"
        )


# ---------------------------------------------------------------------------
# Issue #707 acceptance tests: parse-error / encoding diagnostics surfaced by
# get_code_outline via _attach_input_diagnostics.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outline_cpp_in_py_file_surfaces_parse_errors(tmp_path) -> None:
    """#707: C++ content in a .py file must set parse_errors=True, verdict=WARN.

    The Python tree-sitter grammar cannot parse C++ constructs (int main(),
    std::cout, etc.) and marks ERROR nodes in the tree.  The outline tool must
    surface this so agents don't trust phantom symbols.
    """
    py_file = tmp_path / "wrong_language.py"
    py_file.write_text(_CPP_CONTENT)
    tool = GetCodeOutlineTool(project_root=str(tmp_path))
    result = await tool.execute({"file_path": str(py_file), "output_format": "json"})
    assert result["success"] is True
    assert result.get("parse_errors") is True, (
        f"parse_errors must be True for C++-in-.py; got result keys={list(result)}"
    )
    assert result.get("verdict") == "WARN", (
        f"verdict must be WARN for parse errors; got {result.get('verdict')!r}"
    )


@pytest.mark.asyncio
async def test_outline_cpp_in_py_agent_summary_warns(tmp_path) -> None:
    """#707: agent_summary also carries verdict=WARN for parse-error files."""
    py_file = tmp_path / "wrong_language.py"
    py_file.write_text(_CPP_CONTENT)
    tool = GetCodeOutlineTool(project_root=str(tmp_path))
    result = await tool.execute({"file_path": str(py_file), "output_format": "json"})
    summary = result.get("agent_summary") or {}
    assert summary.get("verdict") == "WARN", (
        f"agent_summary.verdict must be WARN; got {summary.get('verdict')!r}"
    )
    next_step = summary.get("next_step", "")
    assert "parse error" in next_step.lower(), (
        f"agent_summary.next_step must mention parse errors; got {next_step!r}"
    )


@pytest.mark.asyncio
async def test_outline_nul_bytes_surfaces_encoding_warning(tmp_path) -> None:
    """#707: .py file with NUL bytes must set null_bytes=True, encoding_warning=True, verdict=WARN."""
    py_file = tmp_path / "has_nul.py"
    py_file.write_bytes(_PY_WITH_NUL)
    tool = GetCodeOutlineTool(project_root=str(tmp_path))
    result = await tool.execute({"file_path": str(py_file), "output_format": "json"})
    assert result["success"] is True
    assert result.get("null_bytes") is True, (
        f"null_bytes must be True for file with NUL bytes; got {list(result)}"
    )
    assert result.get("encoding_warning") is True, (
        "encoding_warning must be True for file with NUL bytes"
    )
    assert result.get("verdict") == "WARN", (
        f"verdict must be WARN for encoding warnings; got {result.get('verdict')!r}"
    )


@pytest.mark.asyncio
async def test_outline_nul_bytes_agent_summary_warns(tmp_path) -> None:
    """#707: agent_summary carries verdict=WARN + NUL-byte next_step for NUL files."""
    py_file = tmp_path / "has_nul.py"
    py_file.write_bytes(_PY_WITH_NUL)
    tool = GetCodeOutlineTool(project_root=str(tmp_path))
    result = await tool.execute({"file_path": str(py_file), "output_format": "json"})
    summary = result.get("agent_summary") or {}
    assert summary.get("verdict") == "WARN", (
        f"agent_summary.verdict must be WARN; got {summary.get('verdict')!r}"
    )
    next_step = summary.get("next_step", "")
    assert "nul" in next_step.lower(), (
        f"agent_summary.next_step must mention NUL bytes; got {next_step!r}"
    )
