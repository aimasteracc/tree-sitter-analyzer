"""Lossless wire encoding for Git paths that may contain arbitrary bytes."""

from __future__ import annotations

import base64
import os

from .source_oracle import SourceOracleError, normalize_repo_path

_PREFIX = "git-path-b64:"


def path_to_wire(path: str) -> str:
    """Return a UTF-8-safe, unambiguous representation of an internal Git path."""
    raw = os.fsencode(path)
    try:
        literal = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        literal = ""
    if literal == path and not literal.startswith(_PREFIX):
        return literal
    token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return _PREFIX + token


def path_from_wire(value: str) -> str:
    """Decode a wire token, or validate an ordinary UTF-8 path literal."""
    if not isinstance(value, str):
        raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH")
    if not value.startswith(_PREFIX):
        try:
            value.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH") from exc
        return normalize_repo_path(value)
    payload = value[len(_PREFIX) :]
    if not payload:
        raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH")
    try:
        raw = base64.b64decode(
            payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True
        )
        decoded = os.fsdecode(raw)
    except (ValueError, UnicodeError) as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH") from exc
    path = normalize_repo_path(decoded)
    if path_to_wire(path) != value:
        raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH")
    return path


def path_storage(path: str) -> int:
    """Charge both retained raw bytes and their public wire representation."""
    return len(os.fsencode(path)) + len(path_to_wire(path).encode("utf-8")) + 2
