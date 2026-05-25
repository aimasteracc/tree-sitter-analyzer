"""End-to-end tests for tree-sitter-analyzer.

Unlike ``tests/unit/`` (which exercises individual functions in
isolation), the E2E suite **spawns the real MCP server as a
subprocess** and drives it through JSON-RPC, the same protocol VS
Code's MCP extension and Claude Code use. The goal is to catch
"unit tests pass but the user is broken" bugs — the failure mode
that produced four real-world incidents in a single afternoon
(2026-05-25):

* server claimed a ``LoggingCapability`` it didn't implement →
  ``[error]`` line in every client log on every connect
* ``subprocess`` calls used ``text=True`` without ``encoding=`` →
  ``UnicodeDecodeError`` on every tool call under
  cp932/cp936/cp949 Windows locales
* ``codegraph_metrics`` synchronously triggered a 50 s AST index
  build on cold cache → MCP client 30 s timeout, "tool never
  returns"
* ``perf_logger`` hard-coded ``DEBUG`` + propagated to root →
  every tool call emitted two stderr lines, client rendered both
  as ``[warning]``

All four passed 4 200+ unit tests. They all would have failed an
honest end-to-end smoke test against an actual MCP client.

See ``conftest.py`` for the framework primitives; tests live in
``test_mcp_smoke.py`` (general invariants) and
``test_today_bugs_regression.py`` (one regression test per
incident above).
"""
