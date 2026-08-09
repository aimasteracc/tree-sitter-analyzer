"""Crash recovery for a visible production dispatch journal claim."""

from __future__ import annotations

import os

from benchmarks.codegraph_compare.production_collector import _FILE_NOFOLLOW
from benchmarks.codegraph_compare.production_dispatch_wire import (
    ProductionDispatchRequestV1,
    _canonical,
    _open_existing_dir,
    load_journal_event_v1,
)


def recover_hanging_journal(request: ProductionDispatchRequestV1) -> bool:
    if not request.journal_root.is_dir():
        return False
    fd = _open_existing_dir(request.journal_root)
    try:
        try:
            terminal = os.open(
                "999-terminal.json", os.O_RDONLY | _FILE_NOFOLLOW, dir_fd=fd
            )
        except FileNotFoundError:
            terminal = None
        if terminal is not None:
            os.close(terminal)
            return False
        reserved = os.open("000-reserved.json", os.O_RDONLY | _FILE_NOFOLLOW, dir_fd=fd)
        try:
            body = b""
            while True:
                chunk = os.read(reserved, 65536)
                if not chunk:
                    break
                body += chunk
            event = load_journal_event_v1(body)
            if event["envelope_hash"] != request.envelope_hash:
                raise ValueError("hanging reservation envelope mismatch")
        finally:
            os.close(reserved)
        payload = (
            _canonical(
                {
                    "schema_version": 1,
                    "event": "TERMINAL",
                    "status": "UNKNOWN",
                    "violations": ["RECOVERED_HANGING_CLAIM"],
                    "evidence_digest": None,
                }
            )
            + b"\n"
        )
        terminal = os.open(
            "999-terminal.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o400,
            dir_fd=fd,
        )
        try:
            offset = 0
            while offset < len(payload):
                offset += os.write(terminal, payload[offset:])
            os.fsync(terminal)
        finally:
            os.close(terminal)
        os.fsync(fd)
        return True
    finally:
        os.close(fd)
