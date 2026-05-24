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

# A path-looking token: starts with ``/`` (POSIX) or a drive letter +
# ``\`` (Windows), followed by at least one non-whitespace, non-quote
# character. Matches absolute paths inside log lines such as
# ``[Errno 2] No such file or directory: '/x/y.py'``.
_ABSOLUTE_PATH_RE = re.compile(
    r"""
    (?:                    # opening boundary that we keep
        (?<=[\s'\"\(:])    # whitespace, quote, paren, colon
        |
        ^                  # or start of string
    )
    (
        (?:[A-Za-z]:)?     # optional Windows drive letter
        [/\\]              # leading slash
        (?:[^\s'\"\(\)]+)  # one or more non-whitespace, non-quote chars
    )
    """,
    re.VERBOSE,
)


def _sanitize_path_token(token: str, project_root: str | None) -> str:
    """Convert one absolute-path token to a relative or redacted form."""
    if not token:
        return token
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
        return _sanitize_path_token(match.group(1), project_root)

    return _ABSOLUTE_PATH_RE.sub(_replace, text)


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


def project_root_from_env() -> str | None:
    """Best-effort fallback when a caller doesn't pass project_root.

    Honors the same env var as :class:`FileOutputManager`. Returns
    ``None`` if nothing is set — :func:`sanitize_message` then redacts
    every absolute path.
    """
    return os.environ.get("TSA_PROJECT_ROOT") or os.environ.get(
        "TREE_SITTER_PROJECT_ROOT"
    )
