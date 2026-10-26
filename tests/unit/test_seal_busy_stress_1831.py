"""TEMPORARY (#1831): repeat the call-graph-store fixture's full index under CI load.

Each case fails with the typed cause and the seal holder evidence from the
warning log. Removed before merge.
"""

from __future__ import annotations

import logging

import pytest

_SOURCES = {
    "pkg/__init__.py": "from .core import helper\n",
    "pkg/core.py": (
        "def helper(x):\n    return x + 1\n\n"
        "class Engine:\n"
        "    def run(self):\n        return self.step() + helper(1)\n\n"
        "    def step(self):\n        return 2\n\n"
        "helper(0)\n"
    ),
    "app.py": (
        "from pkg.core import Engine, helper\n\n"
        "def main():\n    e = Engine()\n    e.run()\n    return helper(3)\n\n"
        "main()\n"
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("attempt", range(120))
async def test_full_index_publishes_under_load(tmp_path, caplog, attempt):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in _SOURCES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="tree_sitter_analyzer.cache"):
        result = await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": "full"})
    seal_logs = [
        r.getMessage() for r in caplog.records if "SEAL_BUSY" in r.getMessage()
    ]
    assert result["published"] is True and not seal_logs, {
        "SEAL_PROBE_1831": seal_logs,
        **{
            key: result.get(key)
            for key in (
                "error_code",
                "error",
                "phase",
                "summary_line",
                "elapsed_seconds",
            )
        },
    }
