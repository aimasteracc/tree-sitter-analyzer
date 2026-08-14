#!/usr/bin/env python3
"""Drop privilege escalation before execing an RFC-0022 authority target."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

PR_SET_NO_NEW_PRIVS = 38
PR_GET_NO_NEW_PRIVS = 39


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] != "--" or len(args) == 1:
        raise ValueError("launcher requires -- followed by an absolute target argv")
    target = args[1:]
    executable = Path(target[0])
    if not executable.is_absolute():
        raise ValueError("launcher target executable must be absolute")
    getresuid = getattr(os, "getresuid", None)
    getresgid = getattr(os, "getresgid", None)
    if getresuid is None or getresgid is None:
        raise RuntimeError("launcher requires Linux credential inspection")
    if 0 in {*getresuid(), *getresgid(), *os.getgroups()}:
        raise PermissionError("launcher refuses root identity or root group membership")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    if libc.prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1:
        raise RuntimeError("PR_SET_NO_NEW_PRIVS did not take effect")
    os.execv(os.fspath(executable), target)
    raise RuntimeError("execv unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
