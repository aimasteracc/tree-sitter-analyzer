"""RFC-0042 P1b on a real index: no idle cliff, same answers, same freshness.

With the TTL shortened to 2 s, a query after 3.5 s of idle captures again when
the loader is off (today's cliff) and reuses the renewed lease when it is on.
The answers are identical either way, and an edit made while the lease is
being renewed is seen exactly as today: a renewal is a full capture, so it
re-checks the sources and never extends a lease over changed files.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import index_snapshot
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.resident import loader

from . import test_resident_identity as base
from .test_resident_identity import (
    _LOADER_THREAD,
    _QUERIES,
    _SECOND_CALLER,
    _SOURCES,
    _args,
    _ask_all,
    _load,
    _stable,
    _today,
)

# The same fixed fixture project and process isolation as the identity tests.
project = base.project
_isolated = base._isolated

_TTL = 2.0
_IDLE = 3.5


@pytest.fixture(autouse=True)
def _short_ttl(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(index_snapshot, "_TTL_SECONDS", _TTL)
    monkeypatch.setattr(loader, "RENEW_MARGIN_SECONDS", 1.0)
    monkeypatch.setattr(loader, "MIN_RENEW_SECONDS", 0.2)


class _Captures:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.threads: list[str] = []
        self._lock = threading.Lock()
        original = index_snapshot._capture_existing_snapshot

        def counted(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                self.threads.append(threading.current_thread().name)
            return original(*args, **kwargs)

        monkeypatch.setattr(index_snapshot, "_capture_existing_snapshot", counted)

    def by_requests(self) -> int:
        with self._lock:
            return sum(1 for name in self.threads if name != _LOADER_THREAD)

    def by_loader(self) -> int:
        with self._lock:
            return sum(1 for name in self.threads if name == _LOADER_THREAD)


@pytest.mark.asyncio
async def test_without_the_loader_the_query_after_idle_captures_again(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(loader.ENV_VAR, "off")
    captures = _Captures(monkeypatch)
    tool = CodeGraphCallersTool(str(project))
    await tool.execute(_args(*_QUERIES[1]))
    assert captures.by_requests() == 1
    time.sleep(_IDLE)
    await tool.execute(_args(*_QUERIES[1]))
    assert captures.by_requests() == 2  # today's cliff: the lease expired


@pytest.mark.asyncio
async def test_a_renewed_lease_serves_the_query_after_idle(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = await _today(project, monkeypatch)
    captures = _Captures(monkeypatch)
    _load(project)
    tool = CodeGraphCallersTool(str(project))
    first = _stable(await tool.execute(_args(*_QUERIES[1])))
    time.sleep(_IDLE)
    after_idle = _stable(await tool.execute(_args(*_QUERIES[1])))
    assert captures.by_requests() == 0  # no request ever captured
    assert captures.by_loader() >= 2  # the load and at least one renewal
    assert first == after_idle == today[1]
    assert loader.status(str(project))["renewals"] >= 1
    assert await _ask_all(project) == today


@pytest.mark.asyncio
async def test_an_edit_is_seen_as_today_across_renewals(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A renewal re-checks the sources: the edit is never covered by an old lease."""
    _load(project)
    helper = project / "pkg" / "helper.py"
    helper.write_text(_SOURCES["pkg/helper.py"] + _SECOND_CALLER, encoding="utf-8")
    time.sleep(_IDLE)  # at least one renewal capture runs over the edited file
    resident = await _ask_all(project)
    today = await _today(project, monkeypatch)
    assert resident == today
    assert resident[3].get("completeness") != "complete"


@pytest.mark.asyncio
async def test_an_idle_server_stops_renewing(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loader, "ACTIVE_SECONDS", 0.5)
    captures = _Captures(monkeypatch)
    _load(project)
    time.sleep(_IDLE)
    settled = captures.by_loader()
    time.sleep(_IDLE)
    assert captures.by_loader() == settled  # idle: no capture CPU at all
    deadline = time.monotonic() + 3 * _TTL
    while captures.by_loader() == settled and time.monotonic() < deadline:
        loader.touch(str(project))  # requests arrive again
        time.sleep(0.05)
    assert captures.by_loader() > settled, loader.status(str(project))
