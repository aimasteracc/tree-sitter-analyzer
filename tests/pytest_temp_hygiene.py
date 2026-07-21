"""Managed pytest temporary-directory lifecycle."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

import psutil

_MANAGED_TEMP_PATTERN = re.compile(r"run-(?P<pid>\d+)-[0-9a-f]{8}")
_TEMP_VARIABLES = ("TEMP", "TMP", "TMPDIR")


def _current_user_key() -> str:
    """Return a filesystem-safe identifier for the current user."""
    if hasattr(os, "getuid"):
        return f"user-{os.getuid()}"
    username = os.environ.get("USERNAME", "unknown")
    safe_username = re.sub(r"[^A-Za-z0-9_.-]", "_", username)
    return f"user-{safe_username}"


def _pytest_temp_parent() -> Path:
    """Return a writable, repository-external parent for pytest artifacts."""
    configured = os.environ.get("TSA_PYTEST_TEMP_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).resolve() / "tree-sitter-analyzer" / "runtime"

    return (
        Path(tempfile.gettempdir()).resolve()
        / "tsa-run-cache"
        / _current_user_key()
    )


def _ensure_private_directory(path: Path) -> None:
    """Create a directory and restrict it to the current user."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def _process_is_running(pid: int) -> bool:
    """Return whether a process id still belongs to a live process."""
    return psutil.pid_exists(pid)


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
    if getattr(config.option, "basetemp", None) is not None:
        return True
    args = tuple(str(arg) for arg in config.invocation_params.args)
    return any(arg == "--basetemp" or arg.startswith("--basetemp=") for arg in args)


def _restore_process_temp_settings(config: Any) -> None:
    previous_environment = getattr(
        config, "_tsa_previous_temp_environment", None
    )
    if previous_environment is None:
        return

    for variable, value in previous_environment.items():
        if value is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = value
    tempfile.tempdir = config._tsa_previous_tempfile_tempdir


def configure_pytest_temp_root(config: Any) -> None:
    """Route default pytest artifacts to a managed controller directory."""
    if hasattr(config, "workerinput"):
        return
    if _has_explicit_basetemp(config):
        return

    parent = _pytest_temp_parent()
    _ensure_private_directory(parent)
    remove_stale_pytest_temp_roots(parent)
    session_root = parent / f"run-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    _ensure_private_directory(session_root)

    config._tsa_previous_temp_environment = {
        variable: os.environ.get(variable) for variable in _TEMP_VARIABLES
    }
    config._tsa_previous_tempfile_tempdir = tempfile.tempdir
    config._tsa_pytest_temp_root = session_root

    for variable in _TEMP_VARIABLES:
        os.environ[variable] = str(session_root)
    tempfile.tempdir = None
    if Path(tempfile.gettempdir()).resolve() != session_root:
        _restore_process_temp_settings(config)
        shutil.rmtree(session_root, ignore_errors=True)
        raise RuntimeError(f"pytest temp root is not writable: {session_root}")

    config.option.basetemp = str(session_root / "work")


def cleanup_pytest_temp_root(config: Any) -> None:
    """Remove the managed temp root created for this pytest controller."""
    session_root = getattr(config, "_tsa_pytest_temp_root", None)
    if session_root is None:
        return

    _restore_process_temp_settings(config)
    config._tsa_pytest_temp_root = None
    parent = session_root.parent
    shutil.rmtree(session_root, ignore_errors=True)
    try:
        parent.rmdir()
    except OSError:
        pass
