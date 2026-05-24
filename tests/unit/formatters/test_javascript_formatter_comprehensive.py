#!/usr/bin/env python3
"""Comprehensive JavaScript-formatter test entry point — placeholder.

Historically this file re-imported every ``TestJavaScript*`` class from the
split modules so the full JS-formatter suite could be run with one path.
Pytest's xdist (``--dist=loadfile``) then collected the same test classes
*twice* — once from this aggregator and once from the source module —
producing flaky cross-worker shared-state collisions on tests like
``TestJavaScriptFormatterRobustness::test_memory_usage_with_repeated_calls``.

The re-imports were removed so each test class is collected exactly once
from its source file. To run the full JS-formatter suite, use::

    uv run pytest tests/unit/formatters/test_javascript_formatter_*.py \\
                  tests/unit/formatters/test_js_formatter_*.py

This file is intentionally empty (no ``test_*`` defs, no re-exports). It
stays in the repo for backwards-compatible path references.
"""
