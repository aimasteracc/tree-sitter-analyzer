#!/usr/bin/env python3
"""YAML loader for architectural-constraints.yml.

Public surface:
    load_constraints(project_root) -> list[Constraint]
    match_glob(pattern, path) -> bool
    ConstraintParseError

The loader is deliberately strict about top-level keys (unknown ones are
fatal — silently dropping them would mean a misspelled wrapper key ships
to prod with zero enforced rules) but lenient about per-rule keys
(unknown ones are warn-and-skip — this is the forward-compat seam for
rolling out new rule types ahead of analyzer upgrades).

Glob semantics: ``**`` matches any number of path components including
zero, but ``/`` is significant. ``mcp/**`` matches ``mcp/a/b.py`` but
NOT ``cli/mcp_helpers.py``. This is the same rule fnmatch's recursive
shell-glob model implies; ``fnmatch.translate`` gets it right.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .schema import Constraint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class ConstraintParseError(ValueError):
    """Raised on malformed YAML or schema violations.

    Carries enough context (line numbers, key names) in the message that
    an agent reading the error can self-correct without re-reading the
    whole file. Tests assert ``"line"`` / offending-key tokens appear in
    the string.
    """


# ---------------------------------------------------------------------------
# Internal compiled form — used by evaluator for fast matching.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CompiledConstraint:
    """A constraint with its globs pre-compiled to regex.

    Kept ``frozen=True`` so it can be cached. The original
    :class:`Constraint` is preserved so the violation row can attribute
    the rule by id/reason/severity without a separate lookup.
    """

    constraint: Constraint
    from_re: re.Pattern[str]
    to_re: re.Pattern[str]
    exception_res: tuple[re.Pattern[str], ...]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _find_config_file(project_root: Path) -> Path | None:
    """Return the constraints YAML path or None when nothing is configured.

    Resolution order (per spec):
      1. ``<project_root>/architectural-constraints.yml`` (preferred)
      2. ``<project_root>/.tree-sitter-analyzer/constraints.yml``
    """
    candidates = (
        project_root / "architectural-constraints.yml",
        project_root / ".tree-sitter-analyzer" / "constraints.yml",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset({"version", "constraints"})
_REQUIRED_RULE_KEYS: frozenset[str] = frozenset(
    {"id", "severity", "rule", "from", "to", "reason"}
)
_OPTIONAL_RULE_KEYS: frozenset[str] = frozenset({"exceptions"})
_ALLOWED_RULE_KEYS: frozenset[str] = _REQUIRED_RULE_KEYS | _OPTIONAL_RULE_KEYS
_ALLOWED_SEVERITIES: frozenset[str] = frozenset({"error", "warn", "info"})
_ALLOWED_RULES: frozenset[str] = frozenset({"forbid"})


def load_constraints(project_root: str | Path) -> list[Constraint]:
    """Load and validate architectural-constraints from ``project_root``.

    Returns an empty list when no config file is present — a repo with
    no constraints.yml is a perfectly valid state.

    Raises:
        ConstraintParseError: on malformed YAML or unknown top-level
            keys. Per-rule problems (unknown keys, bad severity, missing
            required keys) emit a warning and skip the rule rather than
            failing the whole load.
    """
    root = Path(project_root)
    config_path = _find_config_file(root)
    if config_path is None:
        return []

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConstraintParseError(
            f"Could not read constraints file at line 1 of {config_path}: {exc}"
        ) from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        # Surface the mark/line so the agent can jump straight to the
        # offending location instead of re-reading the file.
        line_hint = _extract_line(exc)
        raise ConstraintParseError(
            f"Malformed YAML in {config_path} at line {line_hint}: {exc}"
        ) from exc

    if data is None:
        return []

    if not isinstance(data, dict):
        raise ConstraintParseError(
            f"Top-level of {config_path} must be a mapping at line 1, "
            f"got {type(data).__name__}"
        )

    # Strict on the top level: unknown keys are fatal.
    for key in data:
        if key not in _ALLOWED_TOP_LEVEL:
            raise ConstraintParseError(
                f"unknown top-level key: {key!r} in {config_path} at line 1. "
                f"Allowed: {sorted(_ALLOWED_TOP_LEVEL)}"
            )

    rules_raw = data.get("constraints") or []
    if not isinstance(rules_raw, list):
        raise ConstraintParseError(
            f"'constraints' must be a list at line 1 of {config_path}, "
            f"got {type(rules_raw).__name__}"
        )

    constraints: list[Constraint] = []
    for index, rule_raw in enumerate(rules_raw, start=1):
        parsed = _parse_rule(rule_raw, index, config_path)
        if parsed is not None:
            constraints.append(parsed)
    return constraints


def match_glob(pattern: str, path: str) -> bool:
    """Return True when ``path`` matches ``pattern`` under our glob model.

    ``**`` descends into arbitrary subdirectories, ``*`` matches a single
    path component (no slashes). Top-level prefixes are NOT enough — the
    full pattern, including separators, must match.

    Exposed publicly so tests can pin the semantics without going through
    the evaluator.
    """
    return _compile_glob(pattern).fullmatch(path) is not None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_rule(rule_raw: Any, index: int, config_path: Path) -> Constraint | None:
    """Validate one rule mapping; return the Constraint or None to skip.

    Skips (with a WARNING log) when the rule has an unknown per-rule key,
    a missing required key, or an invalid severity / rule type. The
    forward-compat seam: a new constraint type added in v2 still lets a
    v1 analyzer load the file by skipping rules it doesn't understand.
    """
    if not isinstance(rule_raw, dict):
        logger.warning(
            "constraints: rule #%d in %s is not a mapping; skipping",
            index,
            config_path,
        )
        return None

    rule_id = rule_raw.get("id", f"<rule#{index}>")

    # Unknown per-rule key → warn and skip the rule.
    for key in rule_raw:
        if key not in _ALLOWED_RULE_KEYS:
            logger.warning(
                "constraints: rule %r in %s has unknown key %r; skipping rule",
                rule_id,
                config_path,
                key,
            )
            return None

    # Required keys must all be present.
    missing = _REQUIRED_RULE_KEYS - set(rule_raw.keys())
    if missing:
        logger.warning(
            "constraints: rule %r in %s is missing required key(s) %s; skipping rule",
            rule_id,
            config_path,
            sorted(missing),
        )
        return None

    severity = rule_raw["severity"]
    if severity not in _ALLOWED_SEVERITIES:
        logger.warning(
            "constraints: rule %r in %s has invalid severity %r; allowed: %s; skipping",
            rule_id,
            config_path,
            severity,
            sorted(_ALLOWED_SEVERITIES),
        )
        return None

    rule_kind = rule_raw["rule"]
    if rule_kind not in _ALLOWED_RULES:
        logger.warning(
            "constraints: rule %r in %s uses unsupported rule type %r; "
            "allowed: %s; skipping",
            rule_id,
            config_path,
            rule_kind,
            sorted(_ALLOWED_RULES),
        )
        return None

    exceptions_raw = rule_raw.get("exceptions") or []
    if not isinstance(exceptions_raw, list):
        logger.warning(
            "constraints: rule %r in %s has non-list 'exceptions'; skipping",
            rule_id,
            config_path,
        )
        return None

    return Constraint(
        id=str(rule_raw["id"]),
        severity=str(severity),
        rule=str(rule_kind),
        from_glob=str(rule_raw["from"]),
        to_glob=str(rule_raw["to"]),
        reason=str(rule_raw["reason"]),
        exceptions=tuple(str(e) for e in exceptions_raw),
    )


def _compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile an fnmatch-style glob to a regex with ``**`` support.

    ``fnmatch.translate`` already produces a regex that anchors with
    ``\\Z``. We patch it so ``**`` matches across slashes (otherwise
    fnmatch treats every ``*`` as "no slashes") while a single ``*``
    keeps its single-component meaning.
    """
    # Reserve a placeholder for ``**`` so the regular fnmatch translation
    # of single ``*`` doesn't eat it.
    sentinel = "\x00DBLSTAR\x00"
    intermediate = pattern.replace("**", sentinel)
    translated = fnmatch.translate(intermediate)
    # ``fnmatch.translate`` escapes every char, so the sentinel survives
    # as the escaped form. Replace whatever shape it came out as with
    # ``.*`` so it crosses slashes.
    escaped_sentinel = re.escape(sentinel)
    final = translated.replace(escaped_sentinel, ".*")
    return re.compile(final)


def compile_constraints(
    constraints: list[Constraint],
) -> list[_CompiledConstraint]:
    """Pre-compile each constraint's globs to regex.

    Hot-path helper for the evaluator: doing the compile once per run
    rather than once per edge keeps the inner loop O(rules * edges)
    string matches instead of O(rules * edges) compile + match.
    """
    compiled: list[_CompiledConstraint] = []
    for constraint in constraints:
        compiled.append(
            _CompiledConstraint(
                constraint=constraint,
                from_re=_compile_glob(constraint.from_glob),
                to_re=_compile_glob(constraint.to_glob),
                exception_res=tuple(
                    _compile_glob(exc) for exc in constraint.exceptions
                ),
            )
        )
    return compiled


def _extract_line(exc: yaml.YAMLError) -> int | str:
    """Pull a 1-based line number out of a PyYAML error, or '?' as fallback."""
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    if mark is not None:
        try:
            return int(mark.line) + 1
        except Exception:  # noqa: BLE001 — defensive: malformed mark
            return "?"
    return "?"
