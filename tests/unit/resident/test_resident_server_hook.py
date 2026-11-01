"""RFC-0042 P1: the MCP server starts the loader after ``initialize``, never before.

The loader starts on the client's ``notifications/initialized`` (sent after it
received the ``initialize`` answer), and — for SDKs without notification
handlers — on the first ``tools/list`` or ``tools/call``. Starting never blocks
the handler, a failure to start never fails the request, and shutdown stops it.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")
from mcp import types  # noqa: E402

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer  # noqa: E402
from tree_sitter_analyzer.resident import loader  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_loader(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    loader.reset()
    loader.enable()
    yield
    loader.shutdown(timeout=10)
    loader.reset()


class _Gate:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls: list[str] = []

    def __call__(self, project_root: str) -> dict[str, Any]:
        self.calls.append(project_root)
        self.entered.set()
        self.release.wait(10)
        return {"state": "ready"}


def _server(root: Path) -> tuple[TreeSitterAnalyzerMCPServer, Any]:
    instance = TreeSitterAnalyzerMCPServer(str(root))
    return instance, instance.create_server()


@pytest.mark.asyncio
async def test_initialized_notification_starts_the_loader_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _Gate()
    monkeypatch.setattr(loader, "load", gate)
    _instance, server = _server(tmp_path)
    handler = server.notification_handlers[types.InitializedNotification]
    started = time.perf_counter()
    await handler(types.InitializedNotification(method="notifications/initialized"))
    assert time.perf_counter() - started < 0.5
    assert gate.entered.wait(5)
    assert gate.calls == [str(tmp_path)]
    gate.release.set()
    assert loader.wait(timeout=10)


@pytest.mark.asyncio
async def test_tools_list_starts_the_loader_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _Gate()
    gate.release.set()
    monkeypatch.setattr(loader, "load", gate)
    # The facade definitions are not under test; building them cold costs seconds.
    monkeypatch.setattr(TreeSitterAnalyzerMCPServer, "tool_definitions", lambda _s: [])
    _instance, server = _server(tmp_path)
    handler = server.request_handlers[types.ListToolsRequest]
    for _ in range(3):
        await handler(types.ListToolsRequest(method="tools/list"))
    assert loader.wait(timeout=10)
    assert gate.calls == [str(tmp_path)]


@pytest.mark.asyncio
async def test_tools_call_starts_the_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _Gate()
    gate.release.set()
    monkeypatch.setattr(loader, "load", gate)
    _instance, server = _server(tmp_path)
    handler = server.request_handlers[types.CallToolRequest]
    # A cheap call: set_project_path without arguments is refused at once (an
    # unknown tool name would build the whole tool registry first).
    await handler(
        types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name="set_project_path", arguments={}),
        )
    )
    assert loader.wait(timeout=10)
    assert gate.calls == [str(tmp_path)]


def test_a_failure_to_start_never_fails_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_root: str | None) -> bool:
        raise RuntimeError("cannot start a thread")

    monkeypatch.setattr(loader, "start", broken)
    instance, _server_obj = _server(tmp_path)
    instance.start_resident()  # logged, never raised


def test_set_project_path_starts_the_loader_for_the_new_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _Gate()
    gate.release.set()
    monkeypatch.setattr(loader, "load", gate)
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    instance = TreeSitterAnalyzerMCPServer(str(first))
    instance.set_project_path(str(second))
    assert loader.wait(timeout=10)
    assert gate.calls == [str(second)]
