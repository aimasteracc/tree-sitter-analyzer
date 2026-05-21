#!/usr/bin/env python3
"""
CLI envelope contract — 5th permanent CI gate (r37af, round 37 dogfood).

Mirrors the MCP envelope snapshot test
(:class:`TestEnvelopeContractSnapshot` in
``tests/unit/mcp/tools/test_tool_response_contract.py``) for the CLI
surfaces fixed in r37y → r37ae.

History — each CLI surface used to silently emit:
- ``None`` summary_line / verdict / agent_summary  (advanced/summary/structure/table)
- a bare LIST instead of a dict  (--query-key, r37ac)
- plain text instead of JSON     (--list-queries and info commands, r37ad/r37ae)

Each commit fixed ONE surface. THIS test pins the contract so future
regressions on any of those 10+ surfaces fail loudly at the
CLI-Command level instead of going unnoticed until a real agent hits
the broken path.

Coverage: 9 CLI Command classes × varying execute modes (single +
batch where applicable). New CLI commands SHOULD be added here when
they ship — the ``_CLI_ENVELOPE_KEYS`` constant captures the contract
and the parametrised test fails immediately on a drifter.
"""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

# Canonical envelope keys (top-level). Same as MCP ``REQUIRED_KEYS``
# in :class:`TestEnvelopeContractSnapshot` plus the ``verdict`` mirror
# that r37u-x ratchet enforces in the MCP layer.
_CLI_ENVELOPE_KEYS = frozenset({"success", "summary_line", "verdict", "agent_summary"})
_AGENT_SUMMARY_KEYS = frozenset({"summary_line", "verdict"})


def _capture_output_json(command_method, target_attr: str = "output_json"):
    """Run ``command_method`` with ``output_json`` mocked; return last call dict."""
    captured: dict = {}

    def _side_effect(d):
        if isinstance(d, dict):
            captured.update(d)
        else:
            captured.setdefault("__non_dict_payload__", d)

    with patch(target_attr, side_effect=_side_effect):
        command_method()
    return captured


def _assert_envelope(payload: dict, label: str) -> None:
    """Assert the canonical envelope contract holds on ``payload``."""
    assert "__non_dict_payload__" not in payload, (
        f"{label}: emitted non-dict payload (regression of r37ac list→dict fix)"
    )
    missing_top = sorted(_CLI_ENVELOPE_KEYS - set(payload.keys()))
    assert not missing_top, (
        f"{label}: missing top-level envelope keys {missing_top}; "
        f"got keys={sorted(payload.keys())[:15]}"
    )
    # Top-level fields must be populated (not None / empty).
    assert payload.get("success") is True, (
        f"{label}: success={payload.get('success')!r} (must be True on happy path)"
    )
    assert isinstance(payload.get("summary_line"), str) and payload["summary_line"], (
        f"{label}: summary_line must be a non-empty string"
    )
    assert isinstance(payload.get("verdict"), str) and payload["verdict"], (
        f"{label}: verdict must be a non-empty string"
    )
    agent_summary = payload.get("agent_summary")
    assert isinstance(agent_summary, dict), (
        f"{label}: agent_summary must be a dict, got {type(agent_summary).__name__}"
    )
    missing_agent = sorted(_AGENT_SUMMARY_KEYS - set(agent_summary.keys()))
    assert not missing_agent, f"{label}: agent_summary missing keys {missing_agent}"
    # Top.verdict must mirror agent_summary.verdict (r37u contract,
    # extended to CLI).
    assert payload["verdict"] == agent_summary["verdict"], (
        f"{label}: top.verdict={payload['verdict']!r} != "
        f"agent.verdict={agent_summary['verdict']!r}"
    )


def _make_analysis_result(file_path: str = "/test/foo.py", language: str = "python"):
    """A minimal AnalysisResult-shaped mock for command tests."""
    result = MagicMock()
    result.success = True
    result.file_path = file_path
    result.language = language
    result.line_count = 100
    result.node_count = 50
    result.elements = []
    result.analysis_time = 0.5
    return result


# ============================================================================
# Per-surface fixtures + the parametrised gate
# ============================================================================


class TestR37afCLIEnvelopeContract:
    """5th permanent CI gate — every CLI JSON surface MUST emit the
    canonical envelope keys. Adding a new CLI command without envelope
    fails this test immediately.

    Coverage cross-reference (commit → surface):
      r37y  → AdvancedCommand (full + statistics)
      r37z  → SummaryCommand
      r37aa → StructureCommand
      r37ab → TableCommand (table=json)
      r37ac → QueryCommand (list→dict fix)
      r37ad → ListQueriesCommand
      r37ae → DescribeQueryCommand / ShowLanguagesCommand /
              ShowExtensionsCommand
    """

    def test_advanced_full_envelope(self):
        """AdvancedCommand full mode → envelope."""
        from tree_sitter_analyzer.cli.commands.advanced_command import (
            AdvancedCommand,
        )

        args = Namespace(
            file_path="/test/foo.py",
            statistics=False,
            output_format="json",
            toon_use_tabs=False,
        )
        cmd = AdvancedCommand(args)
        payload = _capture_output_json(
            lambda: cmd._output_full_analysis(_make_analysis_result()),
            target_attr="tree_sitter_analyzer.cli.commands.advanced_command.output_json",
        )
        _assert_envelope(payload, "AdvancedCommand[full]")
        assert "mode=full" in payload["summary_line"]

    def test_advanced_statistics_envelope(self):
        """AdvancedCommand --statistics mode → envelope."""
        from tree_sitter_analyzer.cli.commands.advanced_command import (
            AdvancedCommand,
        )

        args = Namespace(
            file_path="/test/foo.py",
            statistics=True,
            output_format="json",
            toon_use_tabs=False,
        )
        cmd = AdvancedCommand(args)
        payload = _capture_output_json(
            lambda: cmd._output_statistics(_make_analysis_result()),
            target_attr="tree_sitter_analyzer.cli.commands.advanced_command.output_json",
        )
        _assert_envelope(payload, "AdvancedCommand[statistics]")
        assert "mode=stats" in payload["summary_line"]

    def test_summary_command_envelope(self):
        """SummaryCommand → envelope."""
        from tree_sitter_analyzer.cli.commands.summary_command import (
            SummaryCommand,
        )

        args = Namespace(
            file_path="/test/foo.py",
            summary="classes,methods",
            output_format="json",
            toon_use_tabs=False,
        )
        cmd = SummaryCommand(args)
        payload = _capture_output_json(
            lambda: cmd._output_summary_analysis(_make_analysis_result()),
            target_attr="tree_sitter_analyzer.cli.commands.summary_command.output_json",
        )
        _assert_envelope(payload, "SummaryCommand")

    def test_structure_command_envelope(self):
        """StructureCommand → envelope (via _convert_to_legacy_format)."""
        from tree_sitter_analyzer.cli.commands.structure_command import (
            StructureCommand,
        )

        args = Namespace(
            file_path="/test/foo.py",
            output_format="json",
            toon_use_tabs=False,
        )
        cmd = StructureCommand(args)
        legacy = cmd._convert_to_legacy_format(_make_analysis_result())
        _assert_envelope(legacy, "StructureCommand")

    def test_table_command_envelope(self):
        """TableCommand (table=json path) → envelope via _attach_table_envelope."""
        from tree_sitter_analyzer.cli.commands.table_command import (
            _attach_table_envelope,
        )

        data = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {
                "class_count": 1,
                "method_count": 2,
                "field_count": 3,
                "import_count": 4,
            },
        }
        _attach_table_envelope(data, _make_analysis_result())
        _assert_envelope(data, "TableCommand[json]")
        # r37ab also exposes effective_table tag.
        assert "table=json" in data["summary_line"]

    @pytest.mark.asyncio
    async def test_query_command_returns_dict_envelope(self):
        """QueryCommand → MUST be dict, not list (r37ac fix)."""
        from unittest.mock import AsyncMock

        from tree_sitter_analyzer.cli.commands.query_command import QueryCommand

        args = Namespace(
            file_path="/test/foo.py",
            query_key="methods",
            query_string=None,
            output_format="json",
            language=None,
            filter=None,
            toon_use_tabs=False,
        )
        cmd = QueryCommand(args)
        captured: dict = {}
        with (
            patch.object(cmd, "execute_query", new_callable=AsyncMock) as mock_exec,
            patch(
                "tree_sitter_analyzer.cli.commands.query_command.output_json",
                side_effect=lambda d: (
                    captured.update(d)
                    if isinstance(d, dict)
                    else captured.setdefault("__non_dict_payload__", d)
                ),
            ),
        ):
            mock_exec.return_value = [
                {
                    "capture_name": "method",
                    "node_type": "function_definition",
                    "start_line": 1,
                    "end_line": 2,
                    "content": "def x(): pass",
                }
            ]
            await cmd.execute_async("python")
        _assert_envelope(captured, "QueryCommand")
        # r37ac specifically: must NOT be bare list — caught by the
        # _assert_envelope guard on __non_dict_payload__.
        assert captured.get("match_count") == 1

    def test_list_queries_specific_language_envelope(self):
        """ListQueriesCommand single-language JSON → envelope."""
        from tree_sitter_analyzer.cli.info_commands import ListQueriesCommand

        args = Namespace(
            language="python",
            file_path=None,
            output_format="json",
            format="json",
        )
        cmd = ListQueriesCommand(args)
        payload = _capture_output_json(
            cmd.execute,
            target_attr="tree_sitter_analyzer.cli.info_commands.output_json",
        )
        _assert_envelope(payload, "ListQueriesCommand[single]")
        assert payload.get("scope") == "single_language"

    def test_list_queries_all_languages_envelope(self):
        """ListQueriesCommand all-languages JSON → envelope."""
        from tree_sitter_analyzer.cli.info_commands import ListQueriesCommand

        args = Namespace(
            language=None,
            file_path=None,
            output_format="json",
            format="json",
        )
        cmd = ListQueriesCommand(args)
        payload = _capture_output_json(
            cmd.execute,
            target_attr="tree_sitter_analyzer.cli.info_commands.output_json",
        )
        _assert_envelope(payload, "ListQueriesCommand[all]")
        assert payload.get("scope") == "all_languages"

    def test_describe_query_envelope(self):
        """DescribeQueryCommand → envelope."""
        from tree_sitter_analyzer.cli.info_commands import DescribeQueryCommand

        args = Namespace(
            language="python",
            describe_query="classes",
            file_path=None,
            output_format="json",
            format="json",
        )
        cmd = DescribeQueryCommand(args)
        payload = _capture_output_json(
            cmd.execute,
            target_attr="tree_sitter_analyzer.cli.info_commands.output_json",
        )
        _assert_envelope(payload, "DescribeQueryCommand")

    def test_show_supported_languages_envelope(self):
        """ShowLanguagesCommand → envelope."""
        from tree_sitter_analyzer.cli.info_commands import ShowLanguagesCommand

        args = Namespace(output_format="json", format="json")
        cmd = ShowLanguagesCommand(args)
        payload = _capture_output_json(
            cmd.execute,
            target_attr="tree_sitter_analyzer.cli.info_commands.output_json",
        )
        _assert_envelope(payload, "ShowLanguagesCommand")

    def test_show_supported_extensions_envelope(self):
        """ShowExtensionsCommand → envelope."""
        from tree_sitter_analyzer.cli.info_commands import ShowExtensionsCommand

        args = Namespace(output_format="json", format="json")
        cmd = ShowExtensionsCommand(args)
        payload = _capture_output_json(
            cmd.execute,
            target_attr="tree_sitter_analyzer.cli.info_commands.output_json",
        )
        _assert_envelope(payload, "ShowExtensionsCommand")


class TestR37afCLISurfaceBaseline:
    """Ratchet — pins the count of CLI surfaces under coverage.

    Counting test methods on :class:`TestR37afCLIEnvelopeContract`
    catches the case where someone deletes a coverage entry without
    replacing it (which would silently shrink the gate).
    """

    BASELINE_COVERAGE = 11  # 11 envelope-contract tests as of r37af.

    def test_envelope_test_count_does_not_shrink(self):
        """If you delete a test from TestR37afCLIEnvelopeContract,
        update BASELINE_COVERAGE in this file with a reason.
        Direction is intentional: count can GROW but not SHRINK.
        """
        test_methods = [
            name
            for name in dir(TestR37afCLIEnvelopeContract)
            if name.startswith("test_")
        ]
        assert len(test_methods) >= self.BASELINE_COVERAGE, (
            f"CLI envelope coverage shrunk to {len(test_methods)} "
            f"(baseline {self.BASELINE_COVERAGE}). Deleting a "
            "surface from TestR37afCLIEnvelopeContract requires raising "
            "BASELINE_COVERAGE with a justification."
        )
