"""RFC-0042 P2a: the resident handle's stamps, switch, request scope and probes.

The end-to-end behaviour on a real index is in
``tests/integration/test_resident_handle.py``; these tests pin the rules that
make a handle safe to reuse: only a sealed database, both stamps re-checked per
request, the switch, a request-local connection that never crosses threads or
outlives the request, and probes that fall back to today's code.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import threading
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools import certification_timeouts, index_rebuild_signal
from tree_sitter_analyzer.resident import handle, loader


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    handle.reset()
    yield
    handle.reset()


def _sealed_db(tmp_path: Path) -> Path:
    database = tmp_path / "index.db"
    conn = sqlite3.connect(database)
    conn.execute(
        "CREATE TABLE ast_build_state (id INTEGER PRIMARY KEY, building INTEGER "
        "NOT NULL, started_at REAL NOT NULL, pid INTEGER NOT NULL)"
    )
    conn.commit()
    conn.close()
    os.chmod(database, stat.S_IREAD)
    return database


def _fake_handle(tmp_path: Path, database: Path) -> handle.ResidentHandle:
    selector = tmp_path / "active.json"
    selector.write_text("{}", encoding="utf-8")

    class _Location:
        path = database
        published = True

    sel = handle.file_stamp(selector)
    db = handle.file_stamp(database)
    assert sel is not None and db is not None
    return handle.ResidentHandle(
        root=str(tmp_path),
        real_root=os.path.realpath(tmp_path),
        selector_path=str(selector),
        selector_stamp=sel,
        database_stamp=db,
        location=_Location(),
        live_probe=object(),
    )


def _install(found: handle.ResidentHandle, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handle, "build", lambda _root: found)


def test_stamps_and_sealing(tmp_path: Path) -> None:
    assert handle.file_stamp(tmp_path / "missing") is None
    writable = tmp_path / "w.db"
    writable.write_bytes(b"x")
    assert handle._sealed(handle.file_stamp(writable)) is False
    database = _sealed_db(tmp_path)
    assert handle._sealed(handle.file_stamp(database)) is True
    assert handle._sealed(None) is False
    assert handle._sealed(handle.file_stamp(tmp_path)) is False  # a directory


def test_a_changed_selector_or_database_is_not_current(tmp_path: Path) -> None:
    database = _sealed_db(tmp_path)
    found = _fake_handle(tmp_path, database)
    assert found.current() is True
    Path(found.selector_path).write_text("{} ", encoding="utf-8")
    assert found.current() is False
    found = _fake_handle(tmp_path, database)
    os.chmod(database, stat.S_IREAD | stat.S_IWRITE)
    assert found.current() is False


def test_off_never_builds_or_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fake_handle(tmp_path, _sealed_db(tmp_path))
    _install(found, monkeypatch)
    monkeypatch.setenv(loader.ENV_VAR, "off")
    assert handle.acquire(str(tmp_path)) is None
    with handle.request(str(tmp_path)) as current:
        assert current is None
        assert handle.live_probe(str(tmp_path)) is None
        assert handle.rebuilding(str(tmp_path)) is None
    assert handle.stats()["built"] == 0
    assert handle.acquire(None) is None


def test_acquire_reuses_a_current_handle_and_drops_a_stale_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fake_handle(tmp_path, _sealed_db(tmp_path))
    builds: list[str] = []

    def counted(root: str) -> handle.ResidentHandle | None:
        builds.append(root)
        return found if len(builds) == 1 else None

    monkeypatch.setattr(handle, "build", counted)
    assert handle.acquire(str(tmp_path)) is found
    assert handle.acquire(str(tmp_path)) is found
    assert builds == [str(tmp_path)]
    Path(found.selector_path).write_text("[]", encoding="utf-8")
    assert handle.acquire(str(tmp_path)) is None  # stale, rebuild refused
    assert handle.peek(str(tmp_path)) is None
    assert handle.stats() == {"built": 1, "reused": 1, "dropped": 1}


def test_at_most_max_roots_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fake_handle(tmp_path, _sealed_db(tmp_path))
    _install(found, monkeypatch)
    for index in range(handle.MAX_ROOTS + 2):
        handle.acquire(f"root{index}")
    assert len(handle._handles) == handle.MAX_ROOTS
    assert handle.peek("root0") is None


def test_the_request_connection_is_local_and_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _sealed_db(tmp_path)
    found = _fake_handle(tmp_path, database)
    _install(found, monkeypatch)
    root = str(tmp_path)
    seen: list[Any] = []
    with handle.request(root) as current:
        assert current is found
        assert handle.current_handle(root) is found
        assert handle.current_handle(found.real_root) is found
        assert handle.current_handle("elsewhere") is None
        assert handle.live_probe(root) is found.live_probe
        assert handle.rebuilding(root) is False
        assert handle.rebuilding(root) is False
        active = handle._REQUEST.get()
        assert active is not None and active.connection is not None
        seen.append(active)
        # Nested use for the same root reuses the request (one connection).
        with handle.request(root) as nested:
            assert nested is found
            assert handle._REQUEST.get() is active

        # Another thread with a copied context reads today's way.
        def other() -> None:
            seen.append(handle.rebuilding(root))

        import contextvars

        ctx = contextvars.copy_context()
        thread = threading.Thread(target=ctx.run, args=(other,))
        thread.start()
        thread.join(10)
    assert seen[1] is None
    assert seen[0].connection is None  # closed with the request
    assert handle._REQUEST.get() is None
    os.chmod(database, stat.S_IREAD | stat.S_IWRITE)
    os.replace(database, database.with_name("moved.db"))  # no handle left open


def test_the_rebuild_flag_is_read_through_the_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _sealed_db(tmp_path)
    found = _fake_handle(tmp_path, database)
    _install(found, monkeypatch)
    from tree_sitter_analyzer.cache import build_state

    values = iter([True, False])
    monkeypatch.setattr(build_state, "build_in_progress", lambda _c, **_k: next(values))
    with handle.request(str(tmp_path)):
        assert index_rebuild_signal.is_index_rebuilding(str(tmp_path)) is True
        assert index_rebuild_signal.is_index_rebuilding(str(tmp_path)) is False


def test_a_failing_rebuild_read_is_false_and_a_failing_connect_is_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fake_handle(tmp_path, _sealed_db(tmp_path))
    _install(found, monkeypatch)
    from tree_sitter_analyzer.cache import build_state

    def broken(_conn: Any, **_kwargs: Any) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(build_state, "build_in_progress", broken)
    with handle.request(str(tmp_path)):
        assert handle.rebuilding(str(tmp_path)) is False

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise sqlite3.OperationalError("unable to open")

    monkeypatch.setattr(handle.sqlite3, "connect", refuse)
    with handle.request(str(tmp_path)):
        assert handle.rebuilding(str(tmp_path)) is None


def test_build_refuses_what_it_cannot_cache(tmp_path: Path) -> None:
    assert handle.build(str(tmp_path)) is None  # no selector at all


def test_cleared_timeout_record_is_not_recomputed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(certification_timeouts.DIR_ENV, "off")
    certification_timeouts.clear()
    computed: list[str] = []
    monkeypatch.setattr(
        certification_timeouts,
        "evidence_key",
        lambda root: computed.append(root) or "k",
    )
    certification_timeouts.record(str(tmp_path), None)  # a certified read
    assert certification_timeouts.should_skip(str(tmp_path)) is False
    assert computed == []
    certification_timeouts.record(str(tmp_path), "INDEX_SNAPSHOT_DEADLINE")
    assert certification_timeouts.should_skip(str(tmp_path)) is True
    assert computed == [str(tmp_path), str(tmp_path)]
    certification_timeouts.clear()


def test_timeout_records_use_the_requests_real_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fake_handle(tmp_path, _sealed_db(tmp_path))
    _install(found, monkeypatch)
    monkeypatch.setenv(certification_timeouts.DIR_ENV, "off")
    certification_timeouts.clear()
    with handle.request(str(tmp_path)):
        assert certification_timeouts._real(str(tmp_path)) == found.real_root
        certification_timeouts.record(str(tmp_path), None)
    assert found.real_root in certification_timeouts._MEMO
    certification_timeouts.clear()
