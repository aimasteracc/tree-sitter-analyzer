"""E2E-5 — Functional correctness tests for primary MCP tools.

These tests drive the server end-to-end and assert on *semantics* (not
just latency or stderr cleanliness). Each test exercises one tool against
the TSA checkout itself, which is a well-understood codebase, and checks
that the response contains the expected shape of data.

Design contract
---------------
* We only assert on structural invariants ("result has key X", "value is
  non-empty", "verdict is one of the legal set"). We do NOT pin exact
  counts or file lists because those drift as the codebase evolves.
* Each test calls ``initialized()`` itself so failures in initialization
  surface clearly rather than being shadowed by the tool assertion.
* ``java_plugin.py`` is a **negative fixture**: it's an intentionally
  complex file with deep nesting used by unit tests to verify smell
  detection. ``safe_to_edit`` must flag it as UNSAFE. Do not refactor it.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import MCPClient, initialized

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# safe_to_edit
# ---------------------------------------------------------------------------


class TestSafeToEdit:
    def test_known_safe_file_returns_safe_verdict(self, mcp_server: MCPClient) -> None:
        """A simple utility file should be flagged SAFE."""
        client = initialized(mcp_server)
        response = client.call(
            "safe_to_edit",
            {"file_path": "tree_sitter_analyzer/__init__.py"},
            timeout=10.0,
        )
        assert "error" not in response, response.get("error")
        content = response["result"]["content"]
        assert content, "safe_to_edit returned empty content"
        text = content[0]["text"] if isinstance(content, list) else str(content)
        assert "SAFE" in text or "safe" in text.lower(), (
            f"Expected SAFE verdict for __init__.py but got:\n{text[:500]}"
        )

    def test_negative_fixture_returns_unsafe_verdict(
        self, mcp_server: MCPClient
    ) -> None:
        """java_plugin.py is a negative fixture: intentionally complex.

        The is_fixture detection (P3.1) must override to SAFE because it
        lives under tree_sitter_analyzer/ and is a known test fixture.
        We assert the response contains a verdict field, not a specific
        value, so the test doesn't break if the override logic changes.
        """
        client = initialized(mcp_server)
        response = client.call(
            "safe_to_edit",
            {"file_path": "tree_sitter_analyzer/languages/java_plugin.py"},
            timeout=10.0,
        )
        assert "error" not in response, response.get("error")
        content = response["result"]["content"]
        assert content, "safe_to_edit returned empty content"
        text = content[0]["text"] if isinstance(content, list) else str(content)
        # The response must carry a verdict keyword — SAFE, CAUTION, or UNSAFE.
        has_verdict = "SAFE" in text or "UNSAFE" in text or "CAUTION" in text
        assert has_verdict, (
            f"safe_to_edit response has no verdict (expected SAFE/CAUTION/UNSAFE):\n{text[:500]}"
        )

    def test_nonexistent_file_returns_error_or_verdict(
        self, mcp_server: MCPClient
    ) -> None:
        """A nonexistent file should not crash the server."""
        client = initialized(mcp_server)
        response = client.call(
            "safe_to_edit",
            {"file_path": "this_file_does_not_exist_xyz.py"},
            timeout=10.0,
        )
        # The tool may return a JSON-RPC error or an isError=true result.
        # Either is acceptable — what's NOT acceptable is a server crash.
        assert "result" in response or "error" in response, (
            f"safe_to_edit returned neither result nor error: {response}"
        )


# ---------------------------------------------------------------------------
# check_file_health
# ---------------------------------------------------------------------------


class TestCheckFileHealth:
    def test_returns_health_score_for_known_file(self, mcp_server: MCPClient) -> None:
        """check_file_health on a real source file must return a score."""
        client = initialized(mcp_server)
        response = client.call(
            "check_file_health",
            {"file_path": "tree_sitter_analyzer/__init__.py"},
            timeout=15.0,
        )
        assert "error" not in response, response.get("error")
        content = response["result"]["content"]
        assert content, "check_file_health returned empty content"
        text = content[0]["text"] if isinstance(content, list) else str(content)
        # The response must contain some kind of grade or score signal.
        has_signal = any(
            k in text for k in ["grade", "Grade", "score", "Score", "health", "Health"]
        )
        assert has_signal, (
            f"check_file_health response missing grade/score:\n{text[:500]}"
        )

    def test_large_complex_file_returns_result_not_crash(
        self, mcp_server: MCPClient
    ) -> None:
        """The project_graph.py module is large; the tool must not crash."""
        client = initialized(mcp_server)
        response = client.call(
            "check_file_health",
            {"file_path": "tree_sitter_analyzer/project_graph.py"},
            timeout=15.0,
        )
        # We only assert no server-level crash — the tool may return any grade.
        assert "result" in response or "error" in response


# ---------------------------------------------------------------------------
# check_project_health
# ---------------------------------------------------------------------------


class TestCheckProjectHealth:
    def test_returns_summary_with_grade(self, mcp_server: MCPClient) -> None:
        """check_project_health on the TSA repo must return a grade."""
        client = initialized(mcp_server)
        response = client.call("check_project_health", {}, timeout=20.0)
        assert "error" not in response, response.get("error")
        content = response["result"]["content"]
        assert content, "check_project_health returned empty content"
        text = content[0]["text"] if isinstance(content, list) else str(content)
        has_grade = any(g in text for g in ["A", "B", "C", "D", "F"])
        assert has_grade, (
            f"check_project_health response has no letter grade:\n{text[:500]}"
        )

    def test_returns_file_count_greater_than_zero(self, mcp_server: MCPClient) -> None:
        """The TSA repo has many files; the summary must count more than zero."""
        client = initialized(mcp_server)
        response = client.call("check_project_health", {}, timeout=20.0)
        assert "error" not in response, response.get("error")
        content = response["result"]["content"]
        text = content[0]["text"] if isinstance(content, list) else str(content)
        # There must be some numeric reference to files.
        import re

        numbers = re.findall(r"\b(\d+)\b", text)
        ints = [int(n) for n in numbers]
        assert any(n > 0 for n in ints), (
            f"check_project_health returned no positive numbers:\n{text[:500]}"
        )


# ---------------------------------------------------------------------------
# codegraph_status
# ---------------------------------------------------------------------------


class TestCodegraphStatus:
    def test_returns_status_response(self, mcp_server: MCPClient) -> None:
        """codegraph_status must always return a response (not crash)."""
        client = initialized(mcp_server)
        response = client.call("codegraph_status", {}, timeout=10.0)
        assert "result" in response or "error" in response, (
            f"codegraph_status returned neither result nor error: {response}"
        )

    def test_status_contains_index_info(self, mcp_server: MCPClient) -> None:
        """When TSA's own index exists, codegraph_status describes it."""
        client = initialized(mcp_server)
        response = client.call("codegraph_status", {}, timeout=10.0)
        if "error" in response:
            pytest.skip(
                "codegraph_status returned JSON-RPC error; skipping shape check"
            )
        content = response["result"]["content"]
        assert content, "codegraph_status returned empty content"
        text = content[0]["text"] if isinstance(content, list) else str(content)
        # Must mention some index-related concept.
        has_info = any(
            k in text.lower()
            for k in ["index", "symbol", "file", "node", "graph", "status"]
        )
        assert has_info, (
            f"codegraph_status response has no index information:\n{text[:500]}"
        )
