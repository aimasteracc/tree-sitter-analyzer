"""#1675: the MCP server imports the low-level SDK without its eager package inits.

The deferral only acts in a process where ``mcp`` is not imported yet, so every
check runs in a fresh interpreter.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(code: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


@pytest.mark.timeout(900)
def test_server_import_skips_unused_sdk_modules():
    out = _run(
        """
        import sys
        import tree_sitter_analyzer.mcp.server as server
        assert server.MCP_AVAILABLE
        unused = ["mcp.client.session", "mcp.server.fastmcp", "mcp.server.sse",
                  "uvicorn", "starlette", "pydantic_settings", "rich", "click",
                  "pygments", "httpx._main"]
        print(sorted(name for name in unused if name in sys.modules))
        """
    )
    assert out == "[]"


@pytest.mark.timeout(900)
def test_deferred_package_names_still_resolve_to_the_sdk_objects():
    out = _run(
        """
        import tree_sitter_analyzer.mcp.server as server
        import mcp.server.lowlevel.server as lowlevel
        from mcp.server import Server
        from mcp import ClientSession, types
        from mcp.client.session import ClientSession as Direct
        import mcp, mcp.server
        assert Server is lowlevel.Server is server.Server
        assert ClientSession is Direct
        assert types.Tool is server.Tool
        assert "FastMCP" in mcp.server.__all__ and "ClientSession" in mcp.__all__
        import httpx
        from httpx._status_codes import codes
        assert httpx.codes is codes and httpx.codes.REQUEST_TIMEOUT == 408
        assert callable(httpx.AsyncClient)
        print("ok")
        """
    )
    assert out == "ok"


@pytest.mark.timeout(900)
def test_deferral_is_a_no_op_once_the_sdk_is_imported():
    out = _run(
        """
        import mcp
        from tree_sitter_analyzer.mcp._sdk_lazy_import import defer_sdk_package_inits
        print(defer_sdk_package_inits(), hasattr(mcp, "ClientSession"))
        """
    )
    assert out == "False True"


@pytest.mark.timeout(900)
def test_missing_attribute_raises_attribute_error_after_running_the_init():
    out = _run(
        """
        from tree_sitter_analyzer.mcp._sdk_lazy_import import defer_sdk_package_inits
        assert defer_sdk_package_inits() is True
        import mcp
        try:
            mcp.definitely_not_a_name
        except AttributeError:
            print("AttributeError", "ClientSession" in vars(mcp))
        """
    )
    assert out == "AttributeError True"
