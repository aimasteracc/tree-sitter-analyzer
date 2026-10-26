"""Known MCP tool-response envelope violations (shrink-only).

Each entry silences one ``(tool, rule)`` pair reported by
``tests/pytest_tool_response_guard.py``. ``tool`` is an ``fnmatch`` pattern
over the guard's tool label (``nav action=callers`` for a facade call, the
tool definition name otherwise). Every entry names the issue that tracks the
producer fix; remove the entry in the PR that fixes it.

``tests/governance/test_tool_response_allowlist.py`` pins the entry count, so
the list can only get shorter.
"""

from __future__ import annotations

ALLOWLIST: list[dict[str, str]] = []
