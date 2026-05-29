"""Parse the YAML frontmatter block at the top of a project's ``CLAUDE.md``.

Many TSA tools want a machine-readable view of two kinds of project rules
that previously lived as prose in ``CLAUDE.md`` § "Deliberate design
decisions":

* ``intentional_design`` — locked design decisions (e.g. "MCP defaults to
  TOON; do not flip to JSON"). When an edit touches one of these files /
  symbols, downstream verdict tools (``safe_to_edit`` etc.) should escalate
  the verdict per the rule's ``action_when_touched``.
* ``fixture_allowlist`` — files that are referenced from ``tests/`` as
  negative fixtures (the canonical example is
  ``tree_sitter_analyzer/languages/java_plugin.py``). Refactoring them
  silently breaks tests, so they must be machine-flagged.

This module is the parser only — it returns typed records but does NOT
apply them. Application (matching a file path against
``IntentionalDesignRule.file_patterns`` or returning a fixture verdict)
belongs to the consumer tool.

The verdict vocabulary used here matches
``tree_sitter_analyzer/mcp/tools/utils/safe_to_edit_helpers.py`` —
``{SAFE, CAUTION, UNSAFE, ERROR, NOTE}``. The architect's original spec
used ``REFUSE``; that token does not exist in TSA and would silently
disable any rule that requested it, so the loader coerces it (with a
warning) to ``NOTE``. This is PRD §0 errata F5.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pathspec
import yaml

logger = logging.getLogger(__name__)


# The verdict vocabulary mirrors ``base_tool._LEGAL_VERDICTS`` — the
# canonical wire-format set every MCP tool must emit. Kept as a frozenset
# so callers can validate without importing ``base_tool``. Keep in sync if
# ``_LEGAL_VERDICTS`` ever evolves (``test_tool_response_contract`` enforces
# the wire side; this constant is the rule-author side).
VALID_VERDICT_ACTIONS: frozenset[str] = frozenset(
    {"SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND"}
)

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<body>.*?)\n---\s*(?:\n|$)",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntentionalDesignRule:
    """A locked design-decision rule extracted from ``intentional_design``.

    ``file_patterns`` are pre-compiled gitwildmatch specs (so consumers do
    not need to import pathspec). ``raw_globs`` preserves the original
    strings for display / debugging.
    """

    id: str
    raw_globs: tuple[str, ...]
    file_patterns: tuple[pathspec.PathSpec, ...]
    symbols: tuple[str, ...]
    action: str
    note: str


@dataclass(frozen=True)
class FixtureAllowlistEntry:
    """A single ``fixture_allowlist`` entry.

    Unlike ``IntentionalDesignRule``, fixtures are exact paths, not globs —
    a fixture relationship is a fact about a specific file, not a class
    of files.
    """

    path: str
    note: str


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_frontmatter(project_root: str | Path) -> dict[str, Any]:
    """Return the parsed YAML frontmatter from ``<project_root>/CLAUDE.md``.

    Failure modes — all return ``{}`` after logging a warning rather than
    raising, because consumers (e.g. ``safe_to_edit``) want graceful
    degradation when the frontmatter is missing or broken:

    * No ``CLAUDE.md`` at the project root.
    * The file exists but has no leading ``---`` block.
    * The frontmatter block is empty (``---\\n---``) — ``yaml.safe_load``
      returns ``None`` for an empty document, which we coerce to ``{}``.
    * Malformed YAML — ``yaml.YAMLError`` is caught and reported.

    Returning the raw dict (rather than a typed record) keeps the loader
    decoupled from any single rule schema; ``parse_intentional_design``
    and ``parse_fixture_allowlist`` are the typed entry points.
    """

    root = Path(project_root)
    claude_md = root / "CLAUDE.md"

    if not claude_md.is_file():
        return {}

    try:
        text = claude_md.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read CLAUDE.md at %s: %s", claude_md, exc)
        return {}

    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}

    body = match.group("body")

    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        # The YAML body lives inside the user's CLAUDE.md, so include the
        # path in the warning to make recovery obvious.
        logger.warning(
            "Could not parse YAML frontmatter in %s: %s",
            claude_md,
            exc,
        )
        return {}

    if data is None:
        # Empty frontmatter (``---\n---``) parses to ``None``; treat as empty.
        return {}

    if not isinstance(data, dict):
        # Anything else (a list, a scalar) is malformed for our purposes —
        # we expect a top-level mapping of section names to entry lists.
        logger.warning(
            "CLAUDE.md frontmatter is not a mapping in %s (got %s)",
            claude_md,
            type(data).__name__,
        )
        return {}

    return data


# ---------------------------------------------------------------------------
# parse_intentional_design
# ---------------------------------------------------------------------------


def _coerce_globs(raw: Any, rule_id: str) -> tuple[str, ...] | None:
    """Return a non-empty tuple of glob strings, or ``None`` on validation error."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        logger.warning(
            "intentional_design[%s] 'files' must be a non-empty list; skipping",
            rule_id,
        )
        return None
    return tuple(str(g) for g in raw)


def _compile_patterns(
    globs: tuple[str, ...], rule_id: str
) -> tuple[pathspec.PathSpec, ...] | None:
    """Compile glob strings to PathSpec objects, or ``None`` on error."""
    try:
        return tuple(pathspec.PathSpec.from_lines("gitwildmatch", [g]) for g in globs)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "intentional_design[%s] glob compilation failed: %s; skipping",
            rule_id,
            exc,
        )
        return None


def _coerce_symbols(raw: Any, rule_id: str) -> tuple[str, ...]:
    """Coerce raw ``symbols`` value to a tuple of strings."""
    if isinstance(raw, str):
        return (raw,)
    try:
        return tuple(str(s) for s in raw)
    except TypeError:
        logger.warning(
            "intentional_design[%s] 'symbols' must be a list of strings; treating as empty",
            rule_id,
        )
        return ()


def _build_design_rule(
    entry: dict[str, Any], rule_id: str
) -> IntentionalDesignRule | None:
    """Build one rule from a validated entry dict, or ``None`` on error."""
    globs = _coerce_globs(entry["files"], rule_id)
    if globs is None:
        return None
    patterns = _compile_patterns(globs, rule_id)
    if patterns is None:
        return None
    symbols = _coerce_symbols(entry.get("symbols") or (), rule_id)
    action = _normalise_action(entry.get("action_when_touched"), rule_id)
    return IntentionalDesignRule(
        id=rule_id,
        raw_globs=globs,
        file_patterns=patterns,
        symbols=symbols,
        action=action,
        note=str(entry["note"]),
    )


def parse_intentional_design(data: dict[str, Any]) -> list[IntentionalDesignRule]:
    """Compile the ``intentional_design`` section into typed records.

    Required fields per entry: ``id``, ``files``, ``note``.
    Optional fields: ``symbols`` (default empty tuple),
    ``action_when_touched`` (default ``INFO``; invalid values coerced to
    ``INFO`` with a warning per PRD §0 F5).
    """
    raw_entries = data.get("intentional_design")
    if not raw_entries:
        return []
    if not isinstance(raw_entries, list):
        logger.warning(
            "intentional_design must be a list, got %s", type(raw_entries).__name__
        )
        return []

    rules: list[IntentionalDesignRule] = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            logger.warning("intentional_design[%d] is not a mapping; skipping", index)
            continue
        missing = [k for k in ("id", "files", "note") if entry.get(k) in (None, "")]
        if missing:
            logger.warning(
                "intentional_design[%d] missing required field(s) %s; skipping",
                index,
                missing,
            )
            continue
        rule = _build_design_rule(entry, str(entry["id"]))
        if rule is not None:
            rules.append(rule)
    return rules


def _normalise_action(raw: Any, rule_id: str) -> str:
    """Coerce a raw ``action_when_touched`` value to a known verdict.

    F5 reminder (PRD §0 errata): the architect's original spec accepted
    ``REFUSE``. That token is NOT in TSA's canonical verdict set (see
    ``VALID_VERDICT_ACTIONS``), and silently dropping unknown values
    would let a rule targeting ``REFUSE`` bypass the override path
    entirely. We coerce instead to ``INFO`` — rank-0 in
    ``safe_to_edit_helpers._VERDICT_SEVERITY`` so it is neutral inside
    ``_max_verdict`` — and surface the mistake to the rule author via
    WARNING so the source can be updated.
    """

    if raw is None:
        return "INFO"
    normalised = str(raw).upper()
    if normalised not in VALID_VERDICT_ACTIONS:
        logger.warning(
            "intentional_design[%s] action_when_touched=%r is not in %s; "
            "coercing to INFO (see PRD §0 errata F5)",
            rule_id,
            raw,
            sorted(VALID_VERDICT_ACTIONS),
        )
        return "INFO"
    return normalised


# ---------------------------------------------------------------------------
# parse_fixture_allowlist
# ---------------------------------------------------------------------------


def parse_fixture_allowlist(data: dict[str, Any]) -> list[FixtureAllowlistEntry]:
    """Compile the ``fixture_allowlist`` section into typed records.

    Required fields per entry: ``path``.
    Optional fields: ``note`` (default empty string).
    """

    raw_entries = data.get("fixture_allowlist")
    if not raw_entries:
        return []
    if not isinstance(raw_entries, list):
        logger.warning(
            "fixture_allowlist must be a list, got %s",
            type(raw_entries).__name__,
        )
        return []

    entries: list[FixtureAllowlistEntry] = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            logger.warning("fixture_allowlist[%d] is not a mapping; skipping", index)
            continue

        path = entry.get("path")
        if not path:
            logger.warning(
                "fixture_allowlist[%d] missing required 'path'; skipping", index
            )
            continue

        entries.append(
            FixtureAllowlistEntry(
                path=str(path),
                note=str(entry.get("note") or ""),
            )
        )

    return entries


__all__ = [
    "FixtureAllowlistEntry",
    "IntentionalDesignRule",
    "VALID_VERDICT_ACTIONS",
    "load_frontmatter",
    "parse_fixture_allowlist",
    "parse_intentional_design",
]
