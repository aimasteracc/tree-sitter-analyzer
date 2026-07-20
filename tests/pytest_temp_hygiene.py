"""Managed pytest temporary-directory lifecycle."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

_MANAGED_TEMP_PATTERN = re.compile(r"run-(?P<pid>\d+)-[0-9a-f]{8}")


def _pytest_temp_parent() -> Path:
    """Return a writable, repository-external parent for pytest artifacts."""
    configured = os.environ.get("TSA_PYTEST_TEMP_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).resolve() / "tree-sitter-analyzer" / "runtime"

    return Path(tempfile.gettempdir()).resolve() / "tsa-run-cache"


def _process_is_running(pid: int) -> bool:
    """Return whether a process id still belongs to a live process."""
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def remove_stale_pytest_temp_roots(parent: Path) -> None:
    """Remove managed temp roots whose owning pytest process has exited."""
    if not parent.is_dir():
        return

    for candidate in parent.iterdir():
        match = _MANAGED_TEMP_PATTERN.fullmatch(candidate.name)
        if match is None or not candidate.is_dir():
            continue
        if _process_is_running(int(match.group("pid"))):
            continue
        shutil.rmtree(candidate, ignore_errors=True)


def _has_explicit_basetemp(config: Any) -> bool:
    args = tuple(str(arg) for arg in config.invocation_params.args)
    return any(arg == "--basetemp" or arg.startswith("--basetemp=") for arg in args)


def configure_pytest_temp_root(config: Any) -> None:
    """Route default pytest artifacts to a managed controller directory."""
    if hasattr(config, "workerinput"):
        return
    if _has_explicit_basetemp(config):
        return

    parent = _pytest_temp_parent()
    parent.mkdir(parents=True, exist_ok=True)
    remove_stale_pytest_temp_roots(parent)
    session_root = parent / f"run-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    session_root.mkdir()

    for variable in ("TEMP", "TMP", "TMPDIR"):
        os.environ[variable] = str(session_root)
    tempfile.tempdir = None
    if Path(tempfile.gettempdir()).resolve() != session_root:
        raise RuntimeError(f"pytest temp root is not writable: {session_root}")

    config.option.basetemp = str(session_root / "work")
    config._tsa_pytest_temp_root = session_root


def cleanup_pytest_temp_root(config: Any) -> None:
    """Remove the managed temp root created for this pytest controller."""
    session_root = getattr(config, "_tsa_pytest_temp_root", None)
    if session_root is None:
        return

    parent = session_root.parent
    shutil.rmtree(session_root, ignore_errors=True)
    try:
        parent.rmdir()
    except OSError:
        pass
