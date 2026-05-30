"""Detect files that are referenced as negative test fixtures.

Files like ``tree_sitter_analyzer/languages/java_plugin.py`` are pulled in
from the production source tree to act as **inputs** for tests (e.g. "this
file has deep nesting; detect it"). Refactoring such a file silently
breaks the tests that depend on its specific shape — the
``feedback_test-fixture-files`` incident burned a full session this way.

This module is the single source of truth for "is path X currently
behaving as a test fixture?" — it powers the ``is_fixture`` envelope
field on every edit-relevant tool plus the ``safe_to_edit`` verdict
override (PRD §P3).

Detection is two-tier and zero-LLM:

* **Tier 1 — allowlist.** Read ``CLAUDE.md``'s ``fixture_allowlist``
  YAML frontmatter via :mod:`tree_sitter_analyzer.utils.claude_md_frontmatter`
  (PR-0.3). Human-curated, authoritative, confidence ``1.0``.

* **Tier 2 — heuristic AST scan.** Walk the top-level module bodies of
  every ``tests/**/*.py`` file looking for three signal patterns that
  empirically correspond to fixture references in this codebase (see
  ``.recon/p3-is-fixture-design.md`` §1 for the grep evidence):

  ``constant_assignment`` (0.85)
      ``SAMPLE_FOO = str(PROJECT_ROOT / "tree_sitter_analyzer" / "..."
      / "<file>")``

  ``path_literal`` (0.9)
      A module-level ``Path(...) / ...`` join chain ending in a string
      literal that resolves to a project basename, regardless of the
      LHS name (covers ``GOLDEN_DIR`` etc.).

  ``repo_relative_literal`` (0.7)
      A bare string literal anywhere in a ``tests/`` file that matches
      ``tree_sitter_analyzer/.../<file>.py`` — the canonical
      repo-relative form. Lower confidence because it might just be
      a docstring example.

A sibling-cluster suppression rule kills the dominant false positive
(plugin-manifest lists like ``["go_plugin.py", "java_plugin.py", ...]``)
by setting confidence to ``0.0`` for basenames appearing inside a
list/tuple of ≥3 ``*_plugin.py`` literals.

The cache uses a content-hash signature (SHA-1 over every
``tests/**/*.py``'s ``(mtime_ns, size)`` tuple) stored at
``.ast-cache/fixture_index.json``. Directory mtime alone is unreliable
on macOS APFS, NFS, and CI tarballs (see Backend Architect review §4
in PRD §0 errata).
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..utils.claude_md_frontmatter import (
    load_frontmatter,
    parse_fixture_allowlist,
)

logger = logging.getLogger(__name__)


# Confidence thresholds — coupled with safe_to_edit verdict mapping.
# ≥ 0.85 → UNSAFE; 0.7 ≤ c < 0.85 → CAUTION; < 0.7 → no override.
_CONFIDENCE_UNSAFE = 0.85
_CONFIDENCE_CAUTION = 0.7

_ALLOWLIST_CONFIDENCE = 1.0
_PATH_LITERAL_CONFIDENCE = 0.9
_CONSTANT_ASSIGNMENT_CONFIDENCE = 0.85
_REPO_RELATIVE_CONFIDENCE = 0.7

# Module-level constant names that strongly signal "this string is a
# fixture path". Matched as ``^(SAMPLE|FIXTURE|GOLDEN)_``.
_FIXTURE_NAME_PREFIX = re.compile(r"^(SAMPLE|FIXTURE|GOLDEN)_", re.IGNORECASE)

# A plugin-manifest list contains string literals like ``"go_plugin.py"``
# — when ≥3 such siblings are present we suppress fixture hits for them
# (Idiom C in the design doc).
_PLUGIN_MANIFEST_PATTERN = re.compile(r"^[a-z_]+_plugin\.py$")

# The canonical repo-relative path form we look for as a Tier-2 signal.
_REPO_RELATIVE_PATTERN = re.compile(r"^tree_sitter_analyzer/.+\.py$")

_TARGETED_SKIP_BASENAMES = {"__init__.py", "__main__.py"}

# Where the cache lives. Computed relative to project_root at runtime.
_CACHE_PATH_SUFFIX = ".ast-cache/fixture_index.json"
_CACHE_SCHEMA_VERSION = 1

# Environment variable that disables the detector entirely (roll-back lever).
_DISABLE_ENV_VAR = "TSA_DISABLE_FIXTURE_DETECTION"


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureFact:
    """Result of asking "is this file a fixture?".

    ``is_fixture`` is ``True`` whenever ``confidence >= _CONFIDENCE_CAUTION``
    — i.e. a confident-enough-to-act-on signal. Below that threshold the
    fact still records the signal source for diagnostics, but consumers
    treat the file as non-fixture.
    """

    is_fixture: bool
    confidence: float
    source: str
    evidence: tuple[str, ...]
    note: str


_NEGATIVE = FixtureFact(
    is_fixture=False,
    confidence=0.0,
    source="none",
    evidence=(),
    note="",
)

_DISABLED = FixtureFact(
    is_fixture=False,
    confidence=0.0,
    source="disabled",
    evidence=(),
    note="",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_fixture(file_path: str, project_root: str | Path) -> FixtureFact:
    """Return whether ``file_path`` is a registered or detected fixture.

    ``file_path`` is interpreted relative to ``project_root`` unless it
    is already absolute. The query is O(1) on cache hit and at most
    O(tests/) on miss.

    Failure modes (corrupt cache, unreadable test file, malformed YAML)
    all return ``_NEGATIVE`` and emit one WARNING — never raise.
    """

    if os.environ.get(_DISABLE_ENV_VAR):
        return _DISABLED

    root = Path(project_root).resolve()
    relative = _to_relative(file_path, root)
    if not relative:
        return _NEGATIVE

    # Tier 1 — allowlist first; cheap and authoritative.
    allowlist_hit = _check_allowlist(root, relative)
    if allowlist_hit is not None:
        return allowlist_hit

    cache_path = root / _CACHE_PATH_SUFFIX
    if _cache_is_readable(cache_path):
        targeted_hit = _targeted_fixture_scan(root, relative)
        if targeted_hit is not None:
            return targeted_hit
    if not _basename_seen_in_tests(root, Path(relative).name):
        return _NEGATIVE

    # Tier 2 — load (or rebuild) the test-fixture index and look up.
    index = _load_or_build_index(root)
    return index.get(relative, _NEGATIVE)


def fixture_to_verdict(fact: FixtureFact) -> str | None:
    """Map a :class:`FixtureFact` to a ``safe_to_edit`` verdict override.

    Returns ``"UNSAFE"`` when confidence is ``>= 0.85``, ``"CAUTION"``
    for ``0.7 ≤ c < 0.85``, ``None`` otherwise. The caller composes this
    with :func:`safe_to_edit_helpers._max_verdict` so a fixture-grade
    override is treated the same way as a constraint-violation override.

    Both ``UNSAFE`` and ``CAUTION`` are members of
    ``base_tool._LEGAL_VERDICTS`` and have severity ranks (3 and 2
    respectively) in ``safe_to_edit_helpers._VERDICT_SEVERITY`` — see
    PRD §0 errata F5 for why we deliberately do NOT use ``REFUSE``.
    """

    if fact.confidence >= _CONFIDENCE_UNSAFE:
        return "UNSAFE"
    if fact.confidence >= _CONFIDENCE_CAUTION:
        return "CAUTION"
    return None


def list_fixtures(project_root: str | Path) -> list[FixtureFact]:
    """Return every detected fixture (Tier 1 ∪ Tier 2) for diagnostics.

    The result is sorted by descending confidence then by path so the
    output is deterministic across runs. Used by the
    ``--list-fixtures`` CLI flag (lands in P3.2) and by tests that need
    a deterministic enumeration.
    """

    if os.environ.get(_DISABLE_ENV_VAR):
        return []

    root = Path(project_root).resolve()
    # Pre-cache: union of allowlist paths and Tier-2 index.
    allowlist_facts = _allowlist_facts(root)
    index = _load_or_build_index(root)

    by_path: dict[str, FixtureFact] = {}
    for path, fact in index.items():
        by_path[path] = fact
    # Allowlist wins on conflict (higher confidence) — overwrite Tier-2.
    for path, fact in allowlist_facts.items():
        by_path[path] = fact

    facts = list(by_path.values())
    facts.sort(key=lambda f: (-f.confidence, f.evidence[0] if f.evidence else ""))
    return facts


# ---------------------------------------------------------------------------
# Tier 1 — allowlist
# ---------------------------------------------------------------------------


def _allowlist_facts(project_root: Path) -> dict[str, FixtureFact]:
    """Return ``{relative_path: FixtureFact}`` for every allowlist entry.

    Tier-1 evidence is always the canonical CLAUDE.md path so consumers
    have a single stable reference; the entry's ``note`` propagates
    through so agents see the human-authored rationale.
    """

    try:
        data = load_frontmatter(project_root)
    except Exception as exc:  # noqa: BLE001 — degraded-mode contract
        logger.warning("fixture_detector: load_frontmatter failed: %s", exc)
        return {}

    entries = parse_fixture_allowlist(data)
    result: dict[str, FixtureFact] = {}
    for entry in entries:
        normalised = entry.path.replace("\\", "/")
        result[normalised] = FixtureFact(
            is_fixture=True,
            confidence=_ALLOWLIST_CONFIDENCE,
            source="allowlist",
            evidence=("CLAUDE.md frontmatter",),
            note=entry.note,
        )
    return result


def _check_allowlist(project_root: Path, relative: str) -> FixtureFact | None:
    """Quick path-equality check against the allowlist.

    Returns the matching :class:`FixtureFact` if found, ``None`` if not
    — distinct from ``_NEGATIVE`` so the caller knows to consult Tier 2.
    """

    return _allowlist_facts(project_root).get(relative)


# ---------------------------------------------------------------------------
# Tier 2 — AST scan with on-disk content-hash cache
# ---------------------------------------------------------------------------


def _iter_test_files(tests_dir: Path) -> list[Path]:
    """Return Python test files while pruning generated and hidden dirs."""
    files: list[Path] = []
    skip_dirs = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
    }
    for dirpath, dirnames, filenames in os.walk(tests_dir):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in skip_dirs and not name.startswith(".")
        ]
        for filename in filenames:
            if filename.endswith(".py"):
                files.append(Path(dirpath) / filename)
    return files


def _targeted_fixture_scan(
    project_root: Path,
    relative: str,
) -> FixtureFact | None:
    """Fast exact-path scan for the common single-file ``is_fixture`` query."""
    tests_dir = project_root / "tests"
    if not tests_dir.is_dir():
        return None

    basename = Path(relative).name
    if basename in _TARGETED_SKIP_BASENAMES:
        return None
    best: FixtureFact | None = None
    for path in _iter_test_files(tests_dir):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        evidence = (_safe_relative(path, project_root),)
        confidence = 0.0
        if relative in source:
            confidence = max(confidence, _REPO_RELATIVE_CONFIDENCE)
        if basename and basename in source and "PROJECT_ROOT" in source:
            confidence = max(confidence, _CONSTANT_ASSIGNMENT_CONFIDENCE)
        if confidence <= 0.0:
            continue
        fact = FixtureFact(
            is_fixture=confidence >= _CONFIDENCE_CAUTION,
            confidence=confidence,
            source="targeted_text_scan",
            evidence=evidence,
            note="",
        )
        if best is None or fact.confidence > best.confidence:
            best = fact
            if best.confidence >= _CONFIDENCE_UNSAFE:
                break
    return best


def _basename_seen_in_tests(project_root: Path, basename: str) -> bool:
    """Return whether the filename appears anywhere in tests/ source."""
    tests_dir = project_root / "tests"
    if not tests_dir.is_dir() or not basename:
        return False
    for path in _iter_test_files(tests_dir):
        try:
            if basename in path.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _load_or_build_index(project_root: Path) -> dict[str, FixtureFact]:
    """Return the Tier-2 index, building (and caching) on signature change."""

    tests_dir = project_root / "tests"
    if not tests_dir.is_dir():
        return {}

    signature = _tests_signature(tests_dir)
    cache_path = project_root / _CACHE_PATH_SUFFIX

    cached = _read_cache(cache_path, signature)
    if cached is not None:
        return cached

    index = _scan_tests(tests_dir, project_root)
    _write_cache(cache_path, signature, index)
    return index


def _tests_signature(tests_dir: Path) -> str:
    """Compute a SHA-1 over every ``tests/**/*.py``'s ``(mtime_ns, size)``."""

    hasher = hashlib.sha1(usedforsecurity=False)
    for path in sorted(_iter_test_files(tests_dir)):
        try:
            st = path.stat()
        except OSError:
            continue
        hasher.update(f"{path}|{st.st_mtime_ns}|{st.st_size}\n".encode())
    return hasher.hexdigest()


def _read_cache(cache_path: Path, signature: str) -> dict[str, FixtureFact] | None:
    """Return the cached index for ``signature`` or ``None`` on mismatch."""

    if not cache_path.is_file():
        return None
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "fixture_detector: cache at %s is unreadable (%s); rescanning",
            cache_path,
            exc,
        )
        return None

    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") != _CACHE_SCHEMA_VERSION:
        return None
    if raw.get("tests_signature") != signature:
        return None

    fixtures = raw.get("fixtures")
    if not isinstance(fixtures, dict):
        return None

    result: dict[str, FixtureFact] = {}
    for path, payload in fixtures.items():
        if not isinstance(payload, dict):
            continue
        try:
            evidence_tuple = tuple(str(e) for e in payload.get("evidence", ()))
            result[path] = FixtureFact(
                is_fixture=bool(payload["is_fixture"]),
                confidence=float(payload["confidence"]),
                source=str(payload["source"]),
                evidence=evidence_tuple,
                note=str(payload.get("note", "")),
            )
        except (KeyError, TypeError, ValueError):
            # Skip a single malformed row rather than discarding the
            # whole cache; the next save will overwrite it cleanly.
            continue
    return result


def _write_cache(
    cache_path: Path, signature: str, index: dict[str, FixtureFact]
) -> None:
    """Persist the rebuilt index, swallowing OS-level write failures."""

    payload = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "tests_signature": signature,
        "fixtures": {
            path: {
                "is_fixture": fact.is_fixture,
                "confidence": fact.confidence,
                "source": fact.source,
                "evidence": list(fact.evidence),
                "note": fact.note,
            }
            for path, fact in index.items()
        },
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "fixture_detector: could not write cache to %s: %s",
            cache_path,
            exc,
        )


def _scan_tests(tests_dir: Path, project_root: Path) -> dict[str, FixtureFact]:
    """Walk ``tests_dir`` and merge signals from every ``*.py`` file."""

    aggregator: dict[str, _Aggregator] = {}
    for path in _iter_test_files(tests_dir):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Tree-sitter is forgiving but the stdlib ast module is not;
            # broken test files just get skipped.
            continue
        relative_test = _safe_relative(path, project_root)
        _walk_module(tree, source, relative_test, project_root, aggregator)

    result: dict[str, FixtureFact] = {}
    for rel_path, agg in aggregator.items():
        if agg.suppressed:
            continue
        confidence = agg.confidence
        if confidence <= 0.0:
            continue
        result[rel_path] = FixtureFact(
            is_fixture=confidence >= _CONFIDENCE_CAUTION,
            confidence=confidence,
            source=agg.source,
            evidence=tuple(agg.evidence[:3]),
            note="",
        )
    return result


# ---------------------------------------------------------------------------
# AST walk internals
# ---------------------------------------------------------------------------


@dataclass
class _Aggregator:
    """Mutable accumulator while walking; converted to FixtureFact at the end."""

    confidence: float = 0.0
    source: str = "none"
    evidence: list[str] = field(default_factory=list)
    suppressed: bool = False

    def record(self, signal: str, confidence: float, where: str) -> None:
        if confidence > self.confidence:
            self.confidence = confidence
            self.source = signal
        if where not in self.evidence:
            self.evidence.append(where)


def _walk_module(
    tree: ast.Module,
    source: str,
    relative_test: str,
    project_root: Path,
    aggregator: dict[str, _Aggregator],
) -> None:
    """Inspect the top-level nodes of ``tree`` and update ``aggregator``."""

    # Track module-level name → "PathLike" bindings so we know that
    # ``SAMPLE = str(PROJECT_ROOT / ...)`` should be analysed even
    # though it doesn't start with ``Path(...)``.
    path_names: set[str] = {"PROJECT_ROOT"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            _record_path_binding(node, path_names)

    # Identify plugin-manifest lists / tuples first so the basenames
    # they contain get suppressed even if a different signal later
    # tries to escalate them.
    for descendant in ast.walk(tree):
        if isinstance(descendant, (ast.List, ast.Tuple)):
            basenames = _plugin_manifest_basenames(descendant)
            for basename in basenames:
                rel = _basename_to_repo_relative(basename, project_root)
                if rel:
                    agg = aggregator.setdefault(rel, _Aggregator())
                    agg.suppressed = True

    # Second pass — the actual signal collection at module level only.
    for node in tree.body:
        if isinstance(node, ast.Assign):
            _process_assign(
                node, source, path_names, relative_test, project_root, aggregator
            )
        else:
            _process_repo_relative_literals(
                node, source, relative_test, project_root, aggregator
            )


def _record_path_binding(node: ast.Assign, path_names: set[str]) -> None:
    """If ``node`` assigns from ``Path(...)`` or a known path-name, remember it."""

    if not node.targets or not isinstance(node.targets[0], ast.Name):
        return
    name = node.targets[0].id
    if _expr_is_path_like(node.value, path_names):
        path_names.add(name)


def _expr_is_path_like(expr: ast.expr, path_names: set[str]) -> bool:
    """Heuristic: does ``expr`` evaluate to something on the filesystem?"""

    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Name) and func.id == "Path":
            return True
        if isinstance(func, ast.Attribute) and func.attr in {"resolve", "parent"}:
            return _expr_is_path_like(func.value, path_names)
    if isinstance(expr, ast.Name) and expr.id in path_names:
        return True
    if isinstance(expr, ast.Attribute):
        return _expr_is_path_like(expr.value, path_names)
    if isinstance(expr, ast.Subscript):
        return _expr_is_path_like(expr.value, path_names)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return _expr_is_path_like(expr.left, path_names) or _expr_is_path_like(
            expr.right, path_names
        )
    return False


def _process_assign(
    node: ast.Assign,
    source: str,
    path_names: set[str],
    relative_test: str,
    project_root: Path,
    aggregator: dict[str, _Aggregator],
) -> None:
    """Extract signals from a top-level ``name = ...`` statement."""

    name = _assignment_target_name(node)
    rhs_strings = list(_collect_strings(node.value))
    rhs_is_path = _expr_is_path_like(node.value, path_names)
    has_fixture_name = name is not None and bool(_FIXTURE_NAME_PREFIX.match(name))

    where = f"{relative_test}:{node.lineno}"

    for literal in rhs_strings:
        basename = os.path.basename(literal.replace("\\", "/"))
        if not basename.endswith(".py"):
            continue
        rel = _basename_to_repo_relative(basename, project_root)
        if not rel:
            continue
        agg = aggregator.setdefault(rel, _Aggregator())
        if agg.suppressed:
            continue
        if rhs_is_path:
            agg.record("path_literal", _PATH_LITERAL_CONFIDENCE, where)
        elif has_fixture_name:
            agg.record("constant_assignment", _CONSTANT_ASSIGNMENT_CONFIDENCE, where)
        elif _REPO_RELATIVE_PATTERN.match(literal):
            agg.record("repo_relative_literal", _REPO_RELATIVE_CONFIDENCE, where)


def _process_repo_relative_literals(
    node: ast.AST,
    source: str,
    relative_test: str,
    project_root: Path,
    aggregator: dict[str, _Aggregator],
) -> None:
    """Catch repo-relative string literals outside of fixture-style assigns."""

    for child in ast.walk(node):
        if not isinstance(child, ast.Constant):
            continue
        value = child.value
        if not isinstance(value, str):
            continue
        if not _REPO_RELATIVE_PATTERN.match(value):
            continue
        basename = os.path.basename(value)
        rel = _basename_to_repo_relative(basename, project_root)
        if not rel:
            continue
        agg = aggregator.setdefault(rel, _Aggregator())
        if agg.suppressed:
            continue
        where = f"{relative_test}:{getattr(child, 'lineno', 0)}"
        agg.record("repo_relative_literal", _REPO_RELATIVE_CONFIDENCE, where)


def _assignment_target_name(node: ast.Assign) -> str | None:
    """Return the LHS name for ``X = ...``; ``None`` for tuple/attr targets."""

    if len(node.targets) != 1:
        return None
    target = node.targets[0]
    if isinstance(target, ast.Name):
        return target.id
    return None


def _cache_is_readable(cache_path: Path) -> bool:
    """Return ``True`` when the fixture cache file parses as expected JSON."""
    if not cache_path.is_file():
        return False
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") in (None, _CACHE_SCHEMA_VERSION)
        and isinstance(payload.get("fixtures"), dict)
    )


def _collect_strings(expr: ast.expr) -> list[str]:
    """All ``str`` constants reachable inside ``expr``."""

    out: list[str] = []
    for child in ast.walk(expr):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append(child.value)
    return out


def _plugin_manifest_basenames(node: ast.AST) -> list[str]:
    """If ``node`` is a list/tuple of ≥3 ``*_plugin.py`` literals, return them.

    Otherwise return an empty list. This is the Idiom-C suppression rule
    from the design doc — manifests of plugin filenames look like fixture
    references but are actually existence checks.
    """

    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    matches: list[str] = []
    for elt in node.elts:
        if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
            return []
        if not _PLUGIN_MANIFEST_PATTERN.match(elt.value):
            return []
        matches.append(elt.value)
    if len(matches) < 3:
        return []
    return matches


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _to_relative(file_path: str, project_root: Path) -> str | None:
    """Best-effort conversion of ``file_path`` to a project-relative form."""

    path = Path(file_path)
    if not path.is_absolute():
        return str(path).replace("\\", "/")
    try:
        return str(path.resolve().relative_to(project_root)).replace("\\", "/")
    except (ValueError, OSError):
        return None


def _safe_relative(path: Path, project_root: Path) -> str:
    """Resolve ``path`` relative to ``project_root`` with a string fallback."""

    try:
        return str(path.resolve().relative_to(project_root)).replace("\\", "/")
    except (ValueError, OSError):
        return str(path).replace("\\", "/")


def _basename_to_repo_relative(basename: str, project_root: Path) -> str | None:
    """Find the project-relative path for ``basename`` if exactly one exists.

    Tier-2 hits the basename layer; we need to map it back to the
    canonical project-relative path. Multiple matches resolve to
    ``None`` because we cannot disambiguate without more context.
    """

    if not basename or "/" in basename or "\\" in basename:
        # The string already included path separators — caller already
        # has the relative form.
        return (
            basename.replace("\\", "/") if "/" in basename or "\\" in basename else None
        )
    src_dir = project_root / "tree_sitter_analyzer"
    if not src_dir.is_dir():
        return None
    matches = [path for path in src_dir.rglob(basename) if path.is_file()]
    if len(matches) != 1:
        return None
    return _safe_relative(matches[0], project_root)


__all__ = [
    "FixtureFact",
    "fixture_to_verdict",
    "is_fixture",
    "list_fixtures",
]
