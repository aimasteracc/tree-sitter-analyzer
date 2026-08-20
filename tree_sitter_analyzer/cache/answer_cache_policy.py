#!/usr/bin/env python3
"""Who may be cached, and how the key components are derived (RFC-0027 L6.1).

Rule 1 of L6.1 is the fence that keeps the cache from being a correctness bug:
an action may enter :data:`CACHEABLE_ACTIONS` only if it performs no filesystem
write, no index mutation, no lease acquisition and no ledger append. Otherwise a
cache hit returns the previous answer **without performing the requested side
effect**.

The RFC requires that the allowlist "may never be editable by hand alone", so
:func:`audited_pure_actions` derives the pure set **mechanically** from each
inner tool's own MCP ``annotations`` (``readOnlyHint`` / ``destructiveHint``) —
a declaration every tool already maintains for the MCP protocol, independently
of this module. ``CACHEABLE_ACTIONS`` must be a subset of it, and a bespoke
route (which declares no annotations) is never pure: it fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from .fingerprint import compute_graph_fingerprint

#: Routes whose answers may be memoised.
#:
#: Admission requires BOTH of:
#:
#: * the route is in :func:`audited_pure_actions` (rule 1, contract-tested), and
#: * its cost dominates the ~20 ms generation stamp a lookup must pay.
#:
#: The second criterion has teeth. ``structure action=outline`` is audited pure
#: but runs at 2.9 ms warm, so caching it would make it *slower*; it is
#: deliberately absent. ``nav action=callers`` is a bespoke route (no
#: annotations) and so is not pure by audit — and at 17 ms warm it has nothing
#: to gain either. Both remaining entries were measured in **seconds** or
#: hundreds of milliseconds warm in
#: ``docs/baselines/rfc0025-l5-latency-windows-e0.json``.
#:
#: Expanding this set is a data-only change, but the contract test in
#: ``tests/unit/test_answer_cache_policy.py`` gates it.
CACHEABLE_ACTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("edit", "safe"),
        ("health", "file"),
    }
)

#: Argument keys whose values name a path and are therefore normalised to a
#: project-relative form, so an absolute and a relative reference to the same
#: file share one cache entry. Deliberately a closed list: guessing which
#: string is a path risks conflating two genuinely different arguments.
_PATH_ARG_KEYS: frozenset[str] = frozenset({"file_path", "path", "file", "target"})

#: Facade control key that selects the route and is never part of the answer.
_CONTROL_KEYS: frozenset[str] = frozenset({"action"})

#: Declared non-source inputs. Only the constraint config: it is the one
#: non-source file whose content changes a verdict.
_CONSTRAINT_CONFIG_PATHS: tuple[str, ...] = (
    "architectural-constraints.yml",
    os.path.join(".tree-sitter-analyzer", "constraints.yml"),
)


# --------------------------------------------------------------------------
# rule 1 — the mechanical side-effect audit
# --------------------------------------------------------------------------


def audited_pure_actions(project_root: str) -> frozenset[tuple[str, str]]:
    """Return every ``(facade, action)`` the side-effect audit marks pure.

    "Pure" is read off the inner tool's own MCP annotations: ``readOnlyHint is
    True and destructiveHint is False``. That declaration exists for the MCP
    protocol and is maintained per tool, so it cannot be bent by editing
    :data:`CACHEABLE_ACTIONS`.

    Fails closed in three ways: a bespoke route declares no annotations and is
    excluded; a tool whose annotations are absent or non-boolean is excluded;
    and an inner whose definition raises is excluded.
    """
    from ..mcp._tool_registry import create_tool_registry
    from ..mcp.tools.facade_tool import FacadeTool

    pure: set[tuple[str, str]] = set()
    registry, _ = create_tool_registry(project_root)
    for _name, tool in registry:
        if not isinstance(tool, FacadeTool):
            continue
        for action, inner in tool.action_map.items():
            try:
                annotations = inner.get_tool_definition().get("annotations") or {}
            except Exception:  # noqa: BLE001 — an unreadable tool is not pure
                continue
            if (
                annotations.get("readOnlyHint") is True
                and annotations.get("destructiveHint") is False
            ):
                pure.add((tool.facade_name, action))
    return frozenset(pure)


def is_cacheable(tool: str, action: str) -> bool:
    """Whether ``(tool, action)`` is on the allowlist."""
    return (tool, action) in CACHEABLE_ACTIONS


# --------------------------------------------------------------------------
# key components
# --------------------------------------------------------------------------


def _digest(label: str, *parts: str) -> str:
    """Length-framed digest so ``("ab", "c")`` cannot collide with ``("a", "bc")``."""
    hasher = hashlib.sha256()
    hasher.update(label.encode("utf-8"))
    for part in parts:
        encoded = part.encode("utf-8")
        hasher.update(len(encoded).to_bytes(8, "big"))
        hasher.update(encoded)
    return f"{label}:{hasher.hexdigest()[:32]}"


def _relativize(value: str, project_root: str) -> str:
    """Return ``value`` project-relative with forward slashes, when inside root.

    A path outside the project is returned untouched: rewriting it could make
    two different files share a key.
    """
    try:
        root = os.path.realpath(project_root)
        absolute = os.path.realpath(
            value if os.path.isabs(value) else os.path.join(root, value)
        )
        relative = os.path.relpath(absolute, root)
    except (OSError, ValueError):
        return value
    if relative.startswith(os.pardir):
        return value
    return relative.replace(os.sep, "/")


def normalize_args(arguments: dict[str, Any], project_root: str) -> str:
    """Canonical JSON of the answer-determining arguments.

    Keys sorted (so call-site ordering is irrelevant), the facade's ``action``
    control key dropped (it is already a key component), and path-shaped values
    made project-relative. ``output_format`` is *kept*: TOON and JSON are
    genuinely different answers.
    """
    normalized: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in _CONTROL_KEYS:
            continue
        if key in _PATH_ARG_KEYS and isinstance(value, str) and value:
            normalized[key] = _relativize(value, project_root)
        else:
            normalized[key] = value
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)


def current_generation(project_root: str) -> str:
    """Return the live source-tree generation stamp for ``project_root``.

    Built on :func:`compute_graph_fingerprint` — the project's existing
    invalidation primitive for its graph caches — because it is the only cheap
    stamp available on **every** platform. The RFC-0022 oracle
    (``index_source_snapshot.capture_current_source_snapshot``, which mints
    ``idxsrc-v3:``) is POSIX-only: it returns ``SOURCE_SCOPE_UNSUPPORTED``
    unless ``os.name == "posix"`` and ``/dev/fd`` exists, so on Windows — where
    the committed L5 baseline was measured, and where the primary user runs —
    it can never produce a stamp. Keying off it would mean the cache never
    engages on the platform that needs it.

    What this stamp detects: any file added, removed, or modified in place
    (``file_count`` + ``max_mtime_ns``). What it does NOT detect: a content
    change that leaves both the file count and the maximum mtime unchanged
    (an mtime rollback, or a clock skew that moves an mtime backwards). That is
    exactly the residual risk the project already accepts for
    ``DependencyGraph`` / ``CallGraph`` invalidation, so the answer cache is no
    weaker than the graph caches whose answers it memoises.

    The canonical project root is folded in because :class:`AnswerKey` has no
    ``project_root`` field: without it, two projects analysed in one process
    (``server.set_project_path``) could collide on an identical fingerprint.

    Cost on this repository: ~20 ms for 2,342 source files. It scales linearly
    with the file count, so at the RFC-0025 100k-file target it would no longer
    be negligible — a bound is future work, tracked with the persistence
    question.
    """
    fingerprint = compute_graph_fingerprint(project_root)
    root_digest = _digest("root", os.path.realpath(project_root))
    return f"gfp1:{root_digest}:{fingerprint.file_count}:{fingerprint.max_mtime_ns}"


def resolver_rules_digest() -> str:
    """Digest the composition of the RFC-0010 resolver-language registry.

    Detects a resolver being registered, removed, or rebound to different hooks
    — a resolver-rule change that would alter an answer at an unchanged source
    generation. It does NOT detect an edit *inside* a resolver body; that is
    covered by the package version in :func:`producer_version` for released
    code. Late registration during a process's life bumps this digest and so
    triggers one conservative whole-cache eviction, which is the safe direction.
    """
    try:
        from ..synapse_resolver._registry import (
            get_language_resolver,
            registered_languages,
        )
    except Exception:  # noqa: BLE001 — no registry means nothing to digest
        return _digest("rr", "unavailable")

    parts: list[str] = []
    for language in sorted(registered_languages()):
        resolver = get_language_resolver(language)
        if resolver is None:  # pragma: no cover - registry mutated concurrently
            continue
        parts.append(language)
        for hook in (resolver.build_context, resolver.resolve_callee):
            parts.append(
                f"{getattr(hook, '__module__', '?')}.{getattr(hook, '__qualname__', '?')}"
            )
    return _digest("rr", *parts)


def producer_version(tool: str, action: str) -> str:
    """Digest of everything that can change the answer at a fixed source tree.

    Components: the TSA package version, the answer-cache schema version, the
    route's ``action_version`` from the single ``wire_owner`` registry, and the
    resolver-rule digest. A bump in any of them must miss the cache — otherwise
    an upgrade replays the previous release's verdict under the new schema.
    """
    import tree_sitter_analyzer

    from ..wire_owner import ACTION_VERSIONS
    from .answer_cache import ANSWER_CACHE_SCHEMA_VERSION

    return _digest(
        "pv1",
        str(getattr(tree_sitter_analyzer, "__version__", "unknown")),
        ANSWER_CACHE_SCHEMA_VERSION,
        f"{tool}.{action}",
        ACTION_VERSIONS.get((tool, action), "unversioned"),
        resolver_rules_digest(),
    )


def extra_inputs_digest(project_root: str) -> str:
    """Digest the declared non-source inputs — the constraint config.

    ``architectural-constraints.yml`` (or ``.tree-sitter-analyzer/constraints.yml``)
    is the one non-source file whose content changes a verdict, so an edit to it
    must miss the cache. An absent config digests to a stable "absent" marker,
    which means *creating* the file also bumps the digest.
    """
    parts: list[str] = []
    for relative in _CONSTRAINT_CONFIG_PATHS:
        candidate = os.path.join(project_root, relative)
        try:
            with open(candidate, "rb") as handle:
                raw = handle.read()
        except OSError:
            parts.extend((relative, "absent"))
            continue
        parts.extend((relative, hashlib.sha256(raw).hexdigest()))
    return _digest("xi1", *parts)


def build_answer_key(
    tool: str,
    action: str,
    arguments: dict[str, Any],
    project_root: str | None,
) -> Any:
    """Return an :class:`~.answer_cache.AnswerKey`, or ``None`` when uncacheable.

    ``None`` — never an exception — is returned when the route is not
    allowlisted, when there is no bound project root, or when any component
    cannot be computed. The caller then simply computes the answer, so a
    failure to build a key degrades to the pre-cache behaviour.
    """
    from .answer_cache import AnswerKey

    if not is_cacheable(tool, action):
        return None
    if not project_root:
        return None
    try:
        return AnswerKey(
            tool=tool,
            action=action,
            normalized_args=normalize_args(arguments, project_root),
            generation=current_generation(project_root),
            producer_version=producer_version(tool, action),
            extra_inputs=extra_inputs_digest(project_root),
        )
    except Exception:  # noqa: BLE001 — no key means compute, never guess
        return None


def provenance_block(key: Any, served_from: str) -> dict[str, str]:
    """The RFC-0027 rule 5 visibility block: ``served_from`` + every component.

    An agent must always be able to tell a replayed answer from a fresh one, so
    this is attached to both a hit and a miss.
    """
    return {
        "served_from": served_from,
        "tool": key.tool,
        "action": key.action,
        "normalized_args": key.normalized_args,
        "generation": key.generation,
        "producer_version": key.producer_version,
        "extra_inputs": key.extra_inputs,
    }


__all__ = [
    "CACHEABLE_ACTIONS",
    "audited_pure_actions",
    "build_answer_key",
    "current_generation",
    "extra_inputs_digest",
    "is_cacheable",
    "normalize_args",
    "producer_version",
    "provenance_block",
    "resolver_rules_digest",
]
