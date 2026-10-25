"""TEMPORARY #1821 diagnostic: fail any seal() that finds another open connection
on the build database, printing where that connection was opened."""

from __future__ import annotations

import os
import sqlite3
import threading
import traceback
import weakref

_OPENED: list = []
_SUBCLASSES: dict = {}
_REAL_CONNECT = sqlite3.connect


def _plain(path: str) -> str:
    plain = path.removeprefix("file:").split("?", 1)[0]
    if plain.startswith("///"):
        plain = plain[3:] if os.name == "nt" else plain[2:]
    from urllib.parse import unquote

    return os.path.normcase(os.path.realpath(unquote(plain)))


def _connect(*args, **kwargs):
    factory = kwargs.get("factory", sqlite3.Connection)
    if factory not in _SUBCLASSES:
        _SUBCLASSES[factory] = type(f"Probe{factory.__name__}", (factory,), {})
    kwargs["factory"] = _SUBCLASSES[factory]
    conn = _REAL_CONNECT(*args, **kwargs)
    path = str(args[0] if args else kwargs.get("database"))
    if "generations" in path:
        if len(_OPENED) > 5000:
            _OPENED[:] = [entry for entry in _OPENED if entry[0]() is not None]
        _OPENED.append(
            (
                weakref.ref(conn),
                path,
                threading.current_thread().name,
                os.environ.get("PYTEST_CURRENT_TEST", "?"),
                "".join(traceback.format_stack(limit=14)[:-1]),
            )
        )
    return conn


def _open_on(database: str) -> list[str]:
    target = os.path.normcase(os.path.realpath(database))
    found = []
    for ref, path, thread, test, stack in list(_OPENED):
        conn = ref()
        if conn is None:
            continue
        try:
            conn.total_changes  # noqa: B018
        except sqlite3.ProgrammingError as exc:
            if "closed" in str(exc):
                continue
        if _plain(path) == target:
            found.append(f"{path} thread={thread} opened-in={test}\n{stack}")
    return found


def install() -> None:
    from tree_sitter_analyzer.cache import generation_store

    sqlite3.connect = _connect
    seal = generation_store.GenerationStore.seal

    def probed_seal(self, selector):
        leaks = _open_on(str(self.database(selector)))
        if leaks:
            raise AssertionError(
                "SEAL_PROBE_1821 open connections:\n" + "\n".join(leaks)
            )
        return seal(self, selector)

    generation_store.GenerationStore.seal = probed_seal
