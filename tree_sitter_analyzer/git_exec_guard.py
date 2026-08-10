"""Single-threaded POSIX exec guard for bounded Git file writes."""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    """Apply RLIMIT_FSIZE before replacing this process with Git."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 4 or args[0] != "--fsize" or args[2] != "--":
        return 2
    try:
        limit = int(args[1])
    except ValueError:
        return 2
    if limit < 0:
        return 2
    command = args[3:]
    if not command or command[0] != "git":
        return 2
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        bounds = [limit]
        if hard != resource.RLIM_INFINITY:
            bounds.append(hard)
        if soft != resource.RLIM_INFINITY:
            bounds.append(soft)
        resource.setrlimit(resource.RLIMIT_FSIZE, (min(bounds), hard))
        os.execvp(command[0], command)  # nosec B606
    except (OSError, ValueError):
        return 126


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
