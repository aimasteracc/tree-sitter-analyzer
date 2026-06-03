"""Smoke tests: does the MCP server actually start, initialize, and list tools?

These are the cheapest possible E2E checks. Every other E2E test in
this suite assumes these pass; if they fail, nothing else in the
suite is meaningful.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests.e2e.conftest import REPO_ROOT, MCPClient, initialized

pytestmark = pytest.mark.e2e

# GitHub Actions cold-start is significantly slower than a warm local machine.
# Apply a multiplier to latency budgets and call timeouts so the same tests
# catch catastrophic hangs everywhere without false-failing on runner lag.
_CI_FACTOR = 5 if os.environ.get("CI") else 1


class TestStartup:
    def test_server_boots_and_responds_to_initialize(
        self, mcp_server: MCPClient
    ) -> None:
        response = mcp_server.initialize()
        assert "error" not in response, (
            f"initialize returned an error: {response.get('error')!r}\n"
            f"stderr:\n{mcp_server.stderr_text()}"
        )
        result = response["result"]
        info = result["serverInfo"]
        assert "tree-sitter-analyzer" in info["name"]
        # Version is a string in semver-ish form; we only assert it's
        # non-empty here. Specific version-bump tests live elsewhere.
        assert info["version"]

    def test_initialize_does_not_advertise_logging_capability(
        self, mcp_server: MCPClient
    ) -> None:
        """Regression for the v1.15.1 fake-LoggingCapability bug.

        We dropped the capability advertisement in PR #151 because we
        never registered a ``logging/setLevel`` handler. Re-adding it
        without the handler would put the ``[error] Failed to set
        MCP server log level`` line back in every client log.
        """
        response = mcp_server.initialize()
        assert "error" not in response
        capabilities = response["result"].get("capabilities", {}) or {}
        assert "logging" not in capabilities, (
            "MCP server is advertising a 'logging' capability again. "
            "If that's intentional, register a logging/setLevel "
            "handler first — otherwise clients will log the "
            "'-32601 Method not found' error on every connect."
        )

    def test_initialize_includes_agent_routing_instructions(
        self, mcp_server: MCPClient
    ) -> None:
        """The initialize response should steer agents before any tool call."""
        response = mcp_server.initialize()
        assert "error" not in response
        instructions = response["result"].get("instructions")
        assert instructions
        assert "TSA MCP Routing" in instructions
        # Instructions must name the real v2.0 facade tools + actions, not the
        # pre-facade codegraph_* names that no longer exist.
        assert "nav" in instructions
        assert "search" in instructions
        assert "action=context" in instructions
        assert "action=callee_tree" in instructions
        assert "codegraph_symbol_search" not in instructions
        assert "codegraph_navigate" not in instructions

    def test_repeated_headless_initialize_stays_under_budget(
        self, mcp_server_factory: Any
    ) -> None:
        """Repeated stdio spawn→initialize should not leave clients pending."""
        import time

        elapsed_samples: list[float] = []
        for _ in range(5):
            client = mcp_server_factory(REPO_ROOT)
            started = time.monotonic()
            response = client.initialize(timeout=10.0 * _CI_FACTOR)
            elapsed = time.monotonic() - started
            client.terminate()
            assert "error" not in response, (
                f"initialize returned an error: {response.get('error')!r}\n"
                f"stderr:\n{client.stderr_text()}"
            )
            elapsed_samples.append(elapsed)

        budget_sec = 2.0 * _CI_FACTOR
        assert max(elapsed_samples) < budget_sec, (
            "MCP spawn→initialize exceeded the headless startup budget: "
            f"{[round(sample, 3) for sample in elapsed_samples]} "
            f"(budget {budget_sec:.1f}s)"
        )

    def test_tools_list_returns_expected_minimum(self, mcp_server: MCPClient) -> None:
        """Wave C2: the public ``tools/list`` surface is exactly the 8 domain
        facades + ``set_project_path``. The legacy 63 tool names are reached via
        the deprecation shim (server.call_tool), NOT advertised in tools/list —
        that is the whole point of the cutover (eager-token budget).
        """
        client = initialized(mcp_server)
        tools = client.list_tools()
        names = {tool["name"] for tool in tools}
        required = {
            "search",
            "nav",
            "structure",
            "health",
            "edit",
            "project",
            "index",
            "viz",
            "set_project_path",
        }
        missing = required - names
        assert not missing, (
            f"Required MCP facades missing from tools/list: {sorted(missing)}\n"
            f"Present: {sorted(names)}"
        )
        # Exact surface: 8 facades + set_project_path. A regression that
        # re-registers the discrete tools (re-inflating eager tokens) fails here.
        assert len(tools) == 9, (
            f"Expected exactly 9 entries (8 facades + set_project_path), "
            f"got {len(tools)}: {sorted(names)}"
        )


class TestStderrCleanlinessAtStartup:
    """The MCP server should not log any [error]-grade noise at boot."""

    def test_no_jsonrpc_error_in_stderr_after_initialize(
        self, mcp_server: MCPClient
    ) -> None:
        """Regression for v1.15.1 / PR #151.

        Before the fix, ``[error] Failed to set MCP server log level:
        Error: MPC -32601: Method not found`` appeared on every
        connection because we advertised a capability we didn't
        implement. The fix dropped the advertisement; this test pins
        the silence.
        """
        initialized(mcp_server)
        stderr = mcp_server.stderr_text()
        # Be specific — any reference to the JSON-RPC method-not-found
        # code that surfaces inside an MCP context is the bug.
        forbidden_markers = [
            "-32601",
            "Method not found",
            "Failed to set MCP server log level",
        ]
        offenders = [m for m in forbidden_markers if m in stderr]
        assert not offenders, (
            f"Forbidden marker(s) appeared in server stderr: {offenders}\n"
            f"---stderr---\n{stderr}"
        )

    def test_no_unicode_decode_error_in_stderr(self, mcp_server: MCPClient) -> None:
        """Regression for v1.15.1 / PR #153 (cp932 crash).

        Before the fix, *every* subprocess call inside TSA's tools
        crashed its ``_readerthread`` with ``UnicodeDecodeError``
        when the user's locale was cp932/cp936/cp949. The fix
        forces ``encoding="utf-8"`` on every ``text=True`` subprocess
        call. This test pins the silence on the default locale; the
        locale CI matrix (``e2e-locale.yml``) catches the
        non-default-locale regression.
        """
        initialized(mcp_server)
        stderr = mcp_server.stderr_text()
        # We assert *no* UnicodeDecodeError; the bug always
        # surfaced via this exact class name.
        assert "UnicodeDecodeError" not in stderr, (
            "UnicodeDecodeError appeared in server stderr — the cp932 "
            "subprocess decoding regression is back.\n"
            f"---stderr---\n{stderr}"
        )


def test_framework_self_check_root_resolves() -> None:
    """Sanity: the framework's ``REPO_ROOT`` actually points to the repo."""
    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert (REPO_ROOT / "tree_sitter_analyzer").is_dir()


# ---------------------------------------------------------------------------
# E2E-2 — Tool call latency budgets
#
# Each PRIMARY tool must respond within a budget even on a cold cache.
# The budgets below are intentionally conservative (5-10s for indexing,
# 5s for lightweight reads) to catch the class of bug where a tool hangs
# at 50s (the codegraph_metrics cold-cache regression from v1.15.1).
# ---------------------------------------------------------------------------


class TestToolLatencyBudgets:
    """Regression for v1.15.1: codegraph_metrics cold-cache took >50s.

    After PR #151 made metrics non-blocking (returns a 'run index first'
    hint instead of waiting), every PRIMARY tool must respond well under
    the budgets below.
    """

    def _call_and_measure(
        self,
        client: MCPClient,
        tool_name: str,
        arguments: dict,
        budget_sec: float,
    ) -> dict:
        import time

        t0 = time.monotonic()
        response = client.call(tool_name, arguments, timeout=budget_sec + 5.0)
        elapsed = time.monotonic() - t0
        assert elapsed < budget_sec, (
            f"{tool_name} took {elapsed:.1f}s — over the {budget_sec}s budget.\n"
            f"stderr:\n{client.stderr_text()}"
        )
        return response

    def test_codegraph_metrics_cold_cache_under_5s(
        self, mcp_server_factory: Any
    ) -> None:
        """Regression for the 50s codegraph_metrics hang (PR #151).

        When no AST index exists the tool must return immediately with a
        'run index first' hint rather than blocking.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            client = mcp_server_factory(tmpdir)
            initialized(client)
            response = self._call_and_measure(
                client,
                "codegraph_metrics",
                {"sections": ["cache", "health"]},
                budget_sec=5.0,
            )
        assert "error" not in response, (
            f"codegraph_metrics returned a JSON-RPC error: {response.get('error')}"
        )

    def test_check_project_health_under_10s(self, mcp_server: MCPClient) -> None:
        """check_project_health on the TSA repo itself must complete in 10s (×3 in CI)."""
        initialized(mcp_server)
        self._call_and_measure(
            mcp_server,
            "check_project_health",
            {},
            budget_sec=10.0 * _CI_FACTOR,
        )

    def test_safe_to_edit_under_5s(self, mcp_server: MCPClient) -> None:
        """safe_to_edit on a known file must complete in 5s (×3 in CI)."""
        initialized(mcp_server)
        self._call_and_measure(
            mcp_server,
            "safe_to_edit",
            {"file_path": "tree_sitter_analyzer/__init__.py"},
            budget_sec=5.0 * _CI_FACTOR,
        )


# ---------------------------------------------------------------------------
# E2E-3 — stderr noise budget
#
# At the default log level a single tool call should produce no PERF or
# DEBUG lines on stderr. These levels are for developer diagnostics and
# must not appear in normal operation.
# ---------------------------------------------------------------------------


class TestStderrNoiseBudget:
    """Regression for v1.15.1 PERF/DEBUG log noise visible in client logs."""

    def test_no_debug_lines_after_tool_call(self, mcp_server: MCPClient) -> None:
        """At default log level, a tool call must not emit DEBUG lines.

        Before the v1.15.1 logging fix, every tool call emitted dozens of
        DEBUG/PERF lines that cluttered the client IDE log panel.
        """
        initialized(mcp_server)
        mcp_server.call(
            "safe_to_edit",
            {"file_path": "tree_sitter_analyzer/__init__.py"},
            timeout=10.0 * _CI_FACTOR,
        )
        stderr = mcp_server.stderr_text()
        debug_lines = [
            line
            for line in stderr.splitlines()
            if " - DEBUG - " in line or "PERF " in line
        ]
        assert not debug_lines, (
            f"Found {len(debug_lines)} DEBUG/PERF line(s) at default log level:\n"
            + "\n".join(debug_lines[:10])
        )

    def test_no_error_lines_after_normal_tool_call(self, mcp_server: MCPClient) -> None:
        """A successful tool call must not produce any [error]-level log lines."""
        initialized(mcp_server)
        mcp_server.call(
            "check_project_health",
            {},
            timeout=15.0 * _CI_FACTOR,
        )
        stderr = mcp_server.stderr_text()
        error_lines = [
            line
            for line in stderr.splitlines()
            if " - ERROR - " in line or "[error]" in line.lower()
        ]
        assert not error_lines, (
            f"Found {len(error_lines)} ERROR line(s) after a normal tool call:\n"
            + "\n".join(error_lines[:10])
        )
