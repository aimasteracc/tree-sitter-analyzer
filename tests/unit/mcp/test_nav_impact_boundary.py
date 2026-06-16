"""P1 — RFC-0014 Phase A boundary integration test.

Dispatches ``nav action=impact include_tests=true/false`` through the REAL
``handle_call_tool`` closure (the MCP boundary), NOT through ``tool.execute``
directly.

Rationale: ``tool.execute`` bypasses ``FacadeTool._project_args``, which
whitelists args against the inner tool's schema.  If ``include_tests`` were
accidentally dropped from ``CodeGraphImpactTool.get_tool_schema``, calling
``execute`` directly would still receive the parameter, masking the bug.
The only way to detect a schema-projection regression is to go through
``handle_call_tool`` → ``_dispatch_tool`` → ``FacadeTool.execute`` →
``_project_args`` → inner ``execute``.

Pattern: mirrors ``test_toon_compact_only.py::_capture_call_tool_handler``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


def _make_ref(name: str, file: str) -> FunctionRef:
    return FunctionRef(file_path=file, name=name, start_line=1, language="python")


def _capture_call_tool_handler(server: TreeSitterAnalyzerMCPServer):
    """Capture the ``handle_call_tool`` closure registered by ``create_server``."""
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


def _make_mock_graph(func_ref: FunctionRef, callers=None, callees=None):
    """Build a minimal mock CallGraph for impact tests."""
    graph = MagicMock()
    graph.resolve_targets.return_value = [func_ref]
    graph.caller_refs_of.return_value = callers or []
    graph.callee_refs_of.return_value = callees or []
    graph.call_chain.return_value = []
    graph.callers_of.return_value = []
    graph.callees_of.return_value = []
    return graph


# Each test builds nav action=impact on a real tmp_path project (dependency
# graph + test partition); ~5s+ each, tips the 5s unit budget under Windows
# full-matrix xdist load. Real work, not a perf regression — budget-exempt.
@pytest.mark.slow_ok
class TestNavImpactBoundary:
    """RFC-0014 Phase A: boundary integration for nav action=impact.

    All assertions use exact ``==`` values (user-locked rule — no >= / > 0).
    The ``tests`` bucket shape is verified through the live ``handle_call_tool``
    path to catch _project_args schema-projection regressions.

    The call graph is mocked so the test is deterministic and requires no
    on-disk index.
    """

    @pytest.mark.asyncio
    async def test_include_tests_false_tests_bucket_present_no_file_lists(
        self, tmp_path
    ) -> None:
        """include_tests=False (default): tests bucket always present, no file lists.

        Through handle_call_tool boundary:
          - tests["test_callers_count"] == 3   (3 test callers)
          - tests["test_callees_count"] == 0
          - "test_caller_files" NOT in tests
          - "test_callee_files" NOT in tests
          - score == 0  (production callers = 0; risk partitioned from tests)
        """
        func_ref = _make_ref("target_fn", "src/target.py")
        test_callers = [_make_ref(f"test_{i}", "tests/test_mod.py") for i in range(3)]
        mock_graph = _make_mock_graph(func_ref, callers=test_callers)

        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        handler = _capture_call_tool_handler(server)

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_impact_tool"
                ".CodeGraphImpactTool._get_call_graph",
                return_value=mock_graph,
            ),
            patch.object(mock_graph, "build", return_value=None),
        ):
            raw = await handler(
                "nav",
                {
                    "action": "impact",
                    "mode": "risk_score",
                    "function_name": "target_fn",
                    "include_tests": False,
                    "output_format": "json",
                },
            )

        body = json.loads(raw[0].text)
        assert body["success"] is True
        assert "tests" in body
        assert body["tests"]["test_callers_count"] == 3
        assert body["tests"]["test_callees_count"] == 0
        assert "test_caller_files" not in body["tests"]
        assert "test_callee_files" not in body["tests"]
        assert body["score"] == 0

    @pytest.mark.asyncio
    async def test_include_tests_true_adds_file_lists(self, tmp_path) -> None:
        """include_tests=True: file lists appear in the tests bucket.

        Through handle_call_tool boundary — if _project_args silently dropped
        include_tests, test_caller_files would be absent and this assertion
        would fail, catching the regression.

          - tests["test_callers_count"] == 2
          - tests["test_caller_files"] == ["tests/test_a.py", "tests/test_b.py"]
          - tests["test_callee_files"] == []
          - score == 0  (no production callers)
        """
        func_ref = _make_ref("target_fn", "src/target.py")
        test_callers = [
            _make_ref("test_case_1", "tests/test_a.py"),
            _make_ref("test_case_2", "tests/test_b.py"),
        ]
        mock_graph = _make_mock_graph(func_ref, callers=test_callers)

        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        handler = _capture_call_tool_handler(server)

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_impact_tool"
                ".CodeGraphImpactTool._get_call_graph",
                return_value=mock_graph,
            ),
            patch.object(mock_graph, "build", return_value=None),
        ):
            raw = await handler(
                "nav",
                {
                    "action": "impact",
                    "mode": "risk_score",
                    "function_name": "target_fn",
                    "include_tests": True,
                    "output_format": "json",
                },
            )

        body = json.loads(raw[0].text)
        assert body["success"] is True
        assert "tests" in body
        assert body["tests"]["test_callers_count"] == 2
        assert body["tests"]["test_callees_count"] == 0
        # File lists must be present when include_tests=True survives projection.
        assert body["tests"]["test_caller_files"] == [
            "tests/test_a.py",
            "tests/test_b.py",
        ]
        assert body["tests"]["test_callee_files"] == []
        assert body["score"] == 0

    @pytest.mark.asyncio
    async def test_function_impact_mode_tests_bucket_in_risk(self, tmp_path) -> None:
        """function_impact mode: tests bucket nested under result["risk"].

        Through handle_call_tool boundary.
        risk["tests"]["test_callers_count"] == 1  (one test caller).
        """
        func_ref = _make_ref("my_fn", "src/a.py")
        test_caller = _make_ref("test_my_fn", "tests/test_a.py")
        mock_graph = _make_mock_graph(func_ref, callers=[test_caller])

        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        handler = _capture_call_tool_handler(server)

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_impact_tool"
                ".CodeGraphImpactTool._get_call_graph",
                return_value=mock_graph,
            ),
            patch.object(mock_graph, "build", return_value=None),
        ):
            raw = await handler(
                "nav",
                {
                    "action": "impact",
                    "mode": "function_impact",
                    "function_name": "my_fn",
                    "include_tests": False,
                    "output_format": "json",
                },
            )

        body = json.loads(raw[0].text)
        assert body["success"] is True
        # function_impact nests the risk score under a "risk" key
        risk = body.get("risk", {})
        assert "tests" in risk
        assert risk["tests"]["test_callers_count"] == 1

    @pytest.mark.asyncio
    async def test_ambiguous_symbol_sets_flag_and_unknown_level(self, tmp_path) -> None:
        """#799: when resolve_targets returns >1 result with no file_path qualifier,
        risk_score must set ambiguous=True, level='unknown', candidate_count>=2,
        and next_step must NOT say 'proceed with edit'.
        """
        func_ref_a = _make_ref("execute", "src/tool_a.py")
        func_ref_b = _make_ref("execute", "src/tool_b.py")
        # Mock graph returns two candidates — simulates overloaded name
        graph = MagicMock()
        graph.resolve_targets.return_value = [func_ref_a, func_ref_b]
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []

        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        handler = _capture_call_tool_handler(server)

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_impact_tool"
                ".CodeGraphImpactTool._get_call_graph",
                return_value=graph,
            ),
            patch.object(graph, "build", return_value=None),
        ):
            raw = await handler(
                "nav",
                {
                    "action": "impact",
                    "mode": "risk_score",
                    "function_name": "execute",
                    "output_format": "json",
                },
            )

        body = json.loads(raw[0].text)
        assert body["success"] is True
        assert body.get("ambiguous") is True
        assert body.get("candidate_count") == 2
        assert body.get("level") == "unknown"
        # #866: ambiguity message must fire BEFORE the NOT_FOUND branch
        next_step = body.get("next_step", "")
        assert "proceed with edit" not in next_step
        assert "Ambiguous" in next_step, f"Expected ambiguity hint, got: {next_step!r}"
        assert "not found" not in next_step.lower(), (
            f"Got NOT_FOUND message instead of ambiguity hint: {next_step!r}"
        )

    @pytest.mark.asyncio
    async def test_file_path_mismatch_gives_candidate_hint(self, tmp_path) -> None:
        """#867/#873: when file_path is set but doesn't match, warn with candidate files.

        CallGraph._resolve_targets falls back to unscoped candidates rather than
        returning [] — so targets is non-empty even for a wrong file_path.  The
        mismatch must be detected by checking whether any target lives in the
        requested file, not by testing for an empty list.
        """
        func_ref_a = _make_ref("execute", "src/tool_a.py")
        graph = MagicMock()

        # Real CallGraph fallback: always returns the candidate even when a
        # non-matching file_path is supplied — the scoped lookup fails and
        # _resolve_targets falls back to the unscoped list.
        def resolve_side_effect(name, fp=None):
            return [func_ref_a]

        graph.resolve_targets.side_effect = resolve_side_effect
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []

        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        handler = _capture_call_tool_handler(server)

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_impact_tool"
                ".CodeGraphImpactTool._get_call_graph",
                return_value=graph,
            ),
            patch.object(graph, "build", return_value=None),
        ):
            raw = await handler(
                "nav",
                {
                    "action": "impact",
                    "mode": "risk_score",
                    "function_name": "execute",
                    "file_path": "src/wrong_file.py",
                    "output_format": "json",
                },
            )

        body = json.loads(raw[0].text)
        assert body["success"] is True
        assert body.get("verdict") == "NOT_FOUND"
        next_step = body.get("next_step", "")
        assert "mismatch" in next_step.lower(), (
            f"Expected file_path mismatch hint, got: {next_step!r}"
        )
        assert "src/tool_a.py" in next_step, (
            f"Expected candidate file in hint, got: {next_step!r}"
        )

    @pytest.mark.slow_ok  # Real MCP boundary path; Windows full-matrix load exceeds 5s.
    @pytest.mark.asyncio
    async def test_file_path_dot_prefix_does_not_false_positive(self, tmp_path) -> None:
        """Codex P2 (#873): ./src/tool_a.py and src/tool_a.py are the same file.

        After path normalization, calling with file_path='./src/tool_a.py' when
        CallGraph stores 'src/tool_a.py' must NOT return file_path_mismatch.
        """
        func_ref_a = _make_ref("execute", "src/tool_a.py")
        graph = MagicMock()
        graph.resolve_targets.return_value = [func_ref_a]
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []

        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        handler = _capture_call_tool_handler(server)

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.codegraph_impact_tool"
                ".CodeGraphImpactTool._get_call_graph",
                return_value=graph,
            ),
            patch.object(graph, "build", return_value=None),
        ):
            raw = await handler(
                "nav",
                {
                    "action": "impact",
                    "mode": "risk_score",
                    "function_name": "execute",
                    # Caller passes ./src/tool_a.py; CallGraph stores src/tool_a.py
                    "file_path": "./src/tool_a.py",
                    "output_format": "json",
                },
            )

        body = json.loads(raw[0].text)
        assert body["success"] is True
        assert "file_path_mismatch" not in body, (
            "./src/tool_a.py and src/tool_a.py are the same path — no mismatch"
        )
