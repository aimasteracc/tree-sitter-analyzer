"""Notifier channels for the homeostasis loop.

A :class:`Notifier` is anything with a ``dispatch(event: dict) -> None``
method. Concrete channels: stdout, file (JSONL), shell command, webhook
stub. :class:`StackedNotifier` composes several into one and protects
sibling channels from each other's failures.

Event dict canonical shape (built by ``HealthHomeostasisLoop``)::

    {
        "file":           "/repo/main.py",
        "grade":          "D",
        "previous_grade": "B",      # None on cold start
        "delta_score":    -27.0,
        "recommendation": "...",
        "timestamp_iso":  "2026-05-23T12:00:00+00:00",
    }

Template substitution uses ``str.format_map`` with a :class:`SafeDict`
subclass that returns ``"{key}"`` for missing keys — never raises,
never falls through to a shell. ``ShellNotifier`` always runs
``subprocess.Popen`` with ``shell=False`` so a malicious file name
cannot expand into command injection.
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- protocol


@runtime_checkable
class Notifier(Protocol):
    """Anything with a ``dispatch`` method qualifies as a notifier."""

    def dispatch(self, event: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------- helpers


class SafeDict(dict):
    """Dict subclass that returns ``"{key}"`` for missing tokens.

    Used with ``str.format_map`` so a template referencing an unknown
    placeholder (typo, future field) does NOT raise ``KeyError`` and
    does NOT silently drop the placeholder — it leaves the brace form
    in place so the operator can spot it.
    """

    def __missing__(self, key: str) -> str:  # noqa: D401
        return "{" + key + "}"


def _format_event(event: dict[str, Any]) -> str:
    """Default one-line stdout summary for an event."""
    file_ = event.get("file", "?")
    prev = event.get("previous_grade")
    new = event.get("grade", "?")
    delta = event.get("delta_score", 0.0)
    ts = event.get("timestamp_iso", "")
    prev_repr = prev if prev else "-"
    return f"[health] {file_} {prev_repr} -> {new} (delta={delta:+.1f}) at {ts}"


# ---------------------------------------------------------------- channels


class StdoutNotifier:
    """Print one structured line per event to stdout."""

    def dispatch(self, event: dict[str, Any]) -> None:
        try:
            line = _format_event(event)
        except Exception:  # pragma: no cover — defensive
            line = f"[health] {event!r}"
        sys.stdout.write(line + "\n")
        try:
            sys.stdout.flush()
        except Exception:
            pass


class FileNotifier:
    """Append one JSONL record per event to ``path``.

    Parent directories are created on demand. The file is opened in
    append mode for each dispatch — small files, infrequent events,
    easy to reason about under crash recovery.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def dispatch(self, event: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.debug("FileNotifier mkdir failed: %s", exc)
            return
        try:
            line = json.dumps(event, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError) as exc:
            logger.debug("FileNotifier serialize failed: %s", exc)
            return
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
        except OSError as exc:
            logger.debug("FileNotifier write failed: %s", exc)


class ShellNotifier:
    """Invoke a shell-style command with event tokens substituted.

    Substitution uses ``str.format_map(SafeDict(...))`` — brace syntax
    ``{file}``, ``{grade}``, etc. Unknown tokens stay literal. The
    resulting string is split with :mod:`shlex` and handed to
    :class:`subprocess.Popen` with ``shell=False`` so a hostile event
    payload cannot escape into the parent shell.

    Failure modes (timeout, missing binary, non-zero exit) are logged
    at DEBUG and never raised — the loop must keep running.
    """

    _TIMEOUT_SEC = 10.0

    def __init__(self, template: str) -> None:
        self._template = str(template)

    def dispatch(self, event: dict[str, Any]) -> None:
        tokens = SafeDict({k: _stringify(v) for k, v in event.items()})
        try:
            rendered = self._template.format_map(tokens)
        except Exception as exc:
            logger.debug("ShellNotifier template render failed: %s", exc)
            return

        try:
            argv = shlex.split(rendered)
        except ValueError as exc:
            logger.debug("ShellNotifier shlex split failed: %s", exc)
            return
        if not argv:
            return

        try:
            proc = subprocess.Popen(  # noqa: S603 - shell=False below
                argv,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, FileNotFoundError) as exc:
            logger.debug("ShellNotifier popen failed: %s", exc)
            return

        try:
            proc.communicate(timeout=self._TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            logger.debug("ShellNotifier timed out, killing pid=%s", proc.pid)
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.communicate(timeout=1.0)
            except Exception:
                pass
        except Exception as exc:
            logger.debug("ShellNotifier wait failed: %s", exc)


class WebhookNotifier:
    """Stub: construction is fine, ``dispatch`` raises ``NotImplementedError``.

    Kept as a typed seam so the CLI can advertise the channel today
    while the actual HTTP delivery lands later.
    """

    implemented: bool = False

    def __init__(self, url: str) -> None:
        self._url = str(url)

    @property
    def url(self) -> str:
        return self._url

    def dispatch(self, event: dict[str, Any]) -> None:
        raise NotImplementedError(
            "WebhookNotifier is not yet implemented; "
            f"would have POSTed event for {event.get('file', '?')} to {self._url}"
        )


class StackedNotifier:
    """Fan an event out to multiple channels; isolate failures."""

    def __init__(self, *notifiers: Notifier) -> None:
        # Accept either positional args (StackedNotifier(a, b)) or a
        # single iterable (StackedNotifier([a, b])) — CLI wiring uses
        # the list form.
        if len(notifiers) == 1 and not hasattr(notifiers[0], "dispatch"):
            self._channels = list(notifiers[0])  # type: ignore[arg-type]
        else:
            self._channels = list(notifiers)

    def dispatch(self, event: dict[str, Any]) -> None:
        for channel in self._channels:
            try:
                channel.dispatch(event)
            except Exception as exc:
                logger.debug(
                    "StackedNotifier channel %r raised, continuing: %s",
                    type(channel).__name__,
                    exc,
                )


# ---------------------------------------------------------------- factory


def build_notifier(
    channels: list[str] | None = None,
    *,
    file_path: str | Path | None = None,
    webhook_url: str | None = None,
    shell_template: str | None = None,
) -> Notifier:
    """Build a :class:`Notifier` from CLI channel strings.

    ``channels`` is a list like ``["stdout", "file", "shell", "webhook"]``.
    Unknown channel names are silently skipped (logged at DEBUG). If no
    channels resolve, returns a stdout-only fallback so the loop is
    never silently muted.
    """
    selected: list[Notifier] = []
    for raw in channels or []:
        name = (raw or "").strip().lower()
        if not name:
            continue
        if name == "stdout":
            selected.append(StdoutNotifier())
        elif name == "file":
            if file_path is None:
                logger.debug("build_notifier: 'file' channel requires file_path")
                continue
            selected.append(FileNotifier(file_path))
        elif name == "shell":
            if shell_template is None:
                logger.debug("build_notifier: 'shell' channel requires shell_template")
                continue
            selected.append(ShellNotifier(shell_template))
        elif name == "webhook":
            if webhook_url is None:
                logger.debug("build_notifier: 'webhook' channel requires webhook_url")
                continue
            selected.append(WebhookNotifier(webhook_url))
        else:
            logger.debug("build_notifier: unknown channel %r — skipped", raw)

    if not selected:
        return StdoutNotifier()
    if len(selected) == 1:
        return selected[0]
    return StackedNotifier(*selected)


# ---------------------------------------------------------------- internals


def _stringify(value: Any) -> str:
    """Best-effort string for template substitution.

    None becomes empty string so ``{previous_grade}`` is empty on cold
    start instead of literal ``"None"``. Numerics use their natural
    ``str()`` form so ``delta_score`` keeps a sign / decimal point.
    """
    if value is None:
        return ""
    return str(value)
