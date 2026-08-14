#!/usr/bin/env python3
"""Path-bearing network syscall classification for RFC-0022 strace."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

from rfc0022_strace_model import AuthorityError, TraceCall, Violation


def classify_unix_bind(
    call: TraceCall,
    cwd: Path,
    decode_c_string: Callable[[str], str],
) -> Violation | None:
    if len(call.arguments) < 2:
        raise AuthorityError("bind socket address is incomplete")
    address = call.arguments[1]
    if "AF_UNIX" not in address or "sun_path=@" in address:
        return None
    match = re.search(r'sun_path=("(?:\\.|[^"\\])*")', address)
    if match is None:
        raise AuthorityError("UNIX bind path is not exact")
    raw_path = decode_c_string(match.group(1))
    path = Path(raw_path)
    target = os.path.normpath(raw_path if path.is_absolute() else os.fspath(cwd / path))
    return Violation(
        call.timestamp,
        call.pid,
        call.line,
        call.syscall,
        "unix_socket_path_mutation",
        target,
        call.result,
    )
