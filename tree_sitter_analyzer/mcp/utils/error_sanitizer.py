"""Central exception sanitizer for MCP tool responses (SEC-2).

Raw ``str(exception)`` strings leak two things to the calling AI agent:

  1. **Absolute filesystem paths** — gives an attacker a map of the
     deployment (e.g. ``FileNotFoundError: '/home/alice/proj/.env'``).
  2. **Library internals** — class names, version-specific quirks, stack
     fragments that simplify a follow-up attack.

This module is a single chokepoint. Tool authors should never call
``str(e)`` directly when building the ``error`` field of an MCP response;
they should call :func:`sanitize_exception` (or the convenience
:func:`safe_error_message` wrapper).

The sanitizer is conservative:

* Absolute paths that resolve inside ``project_root`` are converted to
  relative ``./...`` form.
* Absolute paths that resolve **outside** ``project_root`` (e.g.
  ``/etc/passwd``, ``/Users/alice/secret``) are redacted to
  ``<external-path>``.
* The exception class name is preserved so legitimate consumers
  (debug-mode logs, integration tests) still get the type.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# A path-looking token: starts with ``/`` (POSIX) or a drive letter +
# ``\`` (Windows), followed by characters up to a clear delimiter or line
# boundary. Spaces are intentionally allowed: unquoted paths such as
# ``/Users/alice/My Secrets/key.txt`` must be redacted as one unit. Matches
# absolute paths inside log lines such as
# ``[Errno 2] No such file or directory: '/x/y.py'``.
_ABSOLUTE_PATH_RE = re.compile(
    r"""
    (?<![A-Za-z0-9])       # start or punctuation boundary such as -, _, =, [
    (
        (?:[A-Za-z]:)?     # optional Windows drive letter
        [/\\]              # leading slash
        (?:[^'\"\(\)\[\]\{\}=,;\r\n]+)
    )
    """,
    re.VERBOSE,
)

_ERROR_DETAIL_TEXT_LIMIT = 500
_ERROR_DETAIL_FIELDS = (
    "considered",
    "action",
    "status",
    "language",
    "error_type",
    "reason",
    "error_message",
    "error",
)
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[/\\]")


def _sanitize_path_token(token: str, project_root: str | None) -> str:
    """Convert one absolute-path token to a relative or redacted form."""
    if not token:
        return token
    # ``pathlib.Path`` follows the host OS. On POSIX it treats Windows drive
    # and UNC paths as relative, which could make ``C:\Users\...`` appear to
    # live under the current project and leak it as ``./C:\Users\...``.
    if os.name != "nt" and (
        _WINDOWS_DRIVE_PATH_RE.match(token) or token.startswith("\\\\")
    ):
        return "<external-path>"
    try:
        resolved = Path(token).resolve(strict=False)
    except (OSError, RuntimeError):
        # Unresolvable (cycle, ENAMETOOLONG, …) — redact to be safe.
        return "<unresolvable-path>"
    if project_root:
        try:
            root_resolved = Path(project_root).resolve()
            rel = resolved.relative_to(root_resolved)
            return f"./{rel.as_posix()}"
        except (OSError, ValueError):
            pass
    return "<external-path>"


def sanitize_message(text: str, project_root: str | None = None) -> str:
    """Replace absolute-path tokens in ``text`` with relative/redacted forms.

    Idempotent: re-running on already-sanitised text is a no-op (the
    placeholders contain no slashes that the regex would match again).
    """
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        start = match.start(1)
        if (
            start > 0
            and text[start - 1] == "."
            and (start == 1 or not text[start - 2].isalnum())
        ):
            # Keep an already-sanitized project-relative ``./...`` path
            # idempotent, while still catching ``failure./etc/shadow``.
            return match.group(1)
        return _sanitize_path_token(match.group(1), project_root)

    return _ABSOLUTE_PATH_RE.sub(_replace, text)


def _sanitize_detail_file_path(value: Any, project_root: str | None) -> str:
    """Normalize a structured file field without tokenizing on whitespace."""
    text = str(value)
    if not text:
        return text

    if os.name != "nt" and (
        _WINDOWS_DRIVE_PATH_RE.match(text) or text.startswith("\\\\")
    ):
        return "<external-path>"

    path = Path(text)
    if path.is_absolute():
        return _sanitize_path_token(text, project_root)

    if not project_root:
        return "<external-path>" if ".." in path.parts else text

    try:
        root_resolved = Path(project_root).resolve()
        candidate = (root_resolved / path).resolve(strict=False)
        candidate.relative_to(root_resolved)
    except (OSError, RuntimeError, ValueError):
        return "<external-path>"
    return text


def _bounded_sanitized_text(
    value: Any,
    project_root: str | None,
) -> tuple[str, bool]:
    safe_value = sanitize_message(str(value), project_root)
    if len(safe_value) <= _ERROR_DETAIL_TEXT_LIMIT:
        return safe_value, False
    return safe_value[: _ERROR_DETAIL_TEXT_LIMIT - 3] + "...", True


def sanitize_error_detail(
    detail: dict[str, Any],
    project_root: str | None = None,
) -> dict[str, Any]:
    """Return a safe, bounded copy of one per-file error detail.

    Core indexing keeps raw diagnostics because it has no dependency on the
    MCP layer. Responses cross the trust boundary here: paths are made
    project-relative (or redacted), and unbounded parser/library messages are
    capped so one pathological failure cannot inflate an MCP response.
    """
    cleaned: dict[str, Any] = {}
    file_path = detail.get("file")
    if file_path is not None:
        cleaned["file"] = _sanitize_detail_file_path(file_path, project_root)

    for field in _ERROR_DETAIL_FIELDS:
        if field not in detail or detail[field] is None:
            continue
        safe_value, truncated = _bounded_sanitized_text(detail[field], project_root)
        if truncated:
            cleaned[f"{field}_truncated"] = True
        cleaned[field] = safe_value

    return cleaned


def sanitize_exception(exc: BaseException, project_root: str | None = None) -> str:
    """Build a sanitised error string from an exception.

    Format: ``"<ExcClass>: <sanitised message>"``. The class name is kept
    because it is a high-information / low-leak signal that downstream
    handlers and tests rely on.

    ``project_root`` lets in-project paths survive as relative paths so
    the error stays actionable; pass ``None`` to redact every absolute
    path.
    """
    msg = str(exc)
    cleaned = sanitize_message(msg, project_root)
    cls = type(exc).__name__
    if cleaned == msg or not msg:
        # Only include the class name if it actually adds signal.
        return f"{cls}: {cleaned}" if cleaned else cls
    return f"{cls}: {cleaned}"


def safe_error_message(
    exc: BaseException,
    project_root: str | None = None,
    *,
    include_class: bool = True,
) -> str:
    """Convenience wrapper used inside MCP tool error returns.

    Tool code that used to write ``{"error": str(e)}`` now writes
    ``{"error": safe_error_message(e, self.project_root)}``.
    """
    if include_class:
        return sanitize_exception(exc, project_root)
    return sanitize_message(str(exc), project_root)


def bounded_safe_error_message(
    exc: BaseException,
    project_root: str | None = None,
    *,
    prefix: str = "",
    max_length: int = _ERROR_DETAIL_TEXT_LIMIT,
) -> tuple[str, bool]:
    """Return one bounded MCP error string and whether truncation occurred."""
    message = f"{prefix}{safe_error_message(exc, project_root)}"
    if len(message) <= max_length:
        return message, False
    if max_length <= 3:
        return "." * max_length, True
    return message[: max_length - 3] + "...", True


def project_root_from_env() -> str | None:
    """Best-effort fallback when a caller doesn't pass project_root.

    Honors the same env var as :class:`FileOutputManager`. Returns
    ``None`` if nothing is set — :func:`sanitize_message` then redacts
    every absolute path.
    """
    return os.environ.get("TSA_PROJECT_ROOT") or os.environ.get(
        "TREE_SITTER_PROJECT_ROOT"
    )
