"""RFC-0018 Part 3 (safe subset) — decision-tool envelopes must not ship
*empty* agent_next_action guidance command fields.

An empty ``mcp_command:""`` / ``cli_command:""`` / ``post_edit_commands:[]``
carries zero information for an agent but costs tokens in EVERY response on
BOTH surfaces (the field is encoded into ``toon_content`` as well as the
top-level dict). The healthy-file path is the common case, so the waste is
paid on the majority of file_health calls.

These tests drive the REAL ``handle_call_tool`` boundary (NOT
``tool.execute`` — the boundary-order trap from RFC-0012) and assert the
empty command fields are absent from BOTH the JSON envelope and the TOON
``toon_content`` blob. Written RED-first: the fields are present until the
build sites stop emitting them when empty.

Scope guard (verified, do NOT broaden): only the empty placeholders are
dropped. The populated refactor action (``_build_refactor_agent_action``,
priority != "none") keeps its real commands — covered by the unchanged
``test_file_health_result_includes_direct_agent_commands_for_smells`` in
``test_file_health_tool.py``.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

_EMPTY_GUIDANCE_KEYS = ("mcp_command", "cli_command", "post_edit_commands")


def _capture_call_tool_handler(server: TreeSitterAnalyzerMCPServer):
    """Capture the ``handle_call_tool`` closure (mirrors test_toon_losslessness_637)."""
    with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True):
        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured: dict = {}

            def capture_decorator(name):
                def decorator(func):
                    captured[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server
            server.create_server()
            return captured["call_tool"]


async def _call(handler, file_path: str, output_format: str) -> tuple[dict, str]:
    """Return (parsed_envelope, raw_wire_text) for a file_health call."""
    raw = await handler(
        "check_file_health",
        {"file_path": file_path, "output_format": output_format},
    )
    text = raw[0].text
    return json.loads(text), text


@pytest.fixture()
def handler(tmp_path):
    server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
    return _capture_call_tool_handler(server)


def _healthy_file(tmp_path) -> str:
    src = tmp_path / "clean.py"
    src.write_text("def f(x):\n    return x + 1\n")
    return str(src)


@pytest.mark.asyncio
async def test_no_empty_guidance_fields_json(handler, tmp_path):
    """JSON envelope: agent_next_action carries no empty command fields."""
    body, _ = await _call(handler, _healthy_file(tmp_path), "json")
    action = body.get("agent_next_action")
    assert isinstance(action, dict), "healthy file_health must carry agent_next_action"
    present = [k for k in _EMPTY_GUIDANCE_KEYS if k in action]
    assert present == [], (
        f"empty guidance fields shipped in JSON envelope: {present} (action={action})"
    )


@pytest.mark.asyncio
async def test_no_empty_guidance_fields_toon(handler, tmp_path):
    """TOON wire: the empty command fields are absent from toon_content too.

    The fields are encoded into ``toon_content`` during execute(), so a
    top-level-only strip would leave them in the TOON blob. This asserts
    the strip happens BEFORE encoding (at the build site).
    """
    body, _ = await _call(handler, _healthy_file(tmp_path), "toon")
    toon = body.get("toon_content")
    assert isinstance(toon, str) and toon, "toon mode must carry toon_content"
    leaked = [k for k in _EMPTY_GUIDANCE_KEYS if f"{k}:" in toon]
    assert leaked == [], f"empty guidance fields leaked into toon_content: {leaked}"


@pytest.mark.asyncio
async def test_no_empty_guidance_fields_empty_file(handler, tmp_path):
    """The empty-file terminal response also drops the empty command fields."""
    src = tmp_path / "empty.py"
    src.write_text("")
    body, _ = await _call(handler, str(src), "json")
    action = body.get("agent_next_action", {})
    present = [k for k in _EMPTY_GUIDANCE_KEYS if k in action]
    assert present == [], f"empty-file response shipped empty guidance: {present}"
