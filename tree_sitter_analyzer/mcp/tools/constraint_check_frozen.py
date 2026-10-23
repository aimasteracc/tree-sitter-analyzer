"""Frozen RFC-0022 execution path for architectural constraint checks."""

from __future__ import annotations

import fnmatch
import inspect
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from ... import source_oracle
from ...constants import EXCLUDE_DIRS
from ...constraints.parser import ConstraintParseError, load_constraints_bytes
from ...git_path_codec import path_to_wire
from ...index_source_scope import SourceScopeDescriptor
from ...languages.lang_extension_map import EXT_TO_LANG
from ...source_oracle import SourceOracleError
from ...wire_owner import EDIT_CONSTRAINTS_ACTION_VERSION
from ..utils.format_helper import apply_output_format_to_response

_CONFIG_CANDIDATES = (
    "architectural-constraints.yml",
    ".tree-sitter-analyzer/constraints.yml",
)

#: ``fail(code, output_format=..., detail=None)`` — an error envelope that
#: carries the frozen diff's provenance.
_FailFn = Callable[..., dict[str, Any]]
#: ``(violation rows, evaluated edge count, index snapshot)``.
_Evaluation = tuple[list[dict[str, Any]], int, Any]


def _config_publish_guard(
    diff: Any, project_root: str, deadline: float
) -> Callable[[], str | None]:
    """Build the final-publish guard for impact-owned configuration bytes."""

    if diff.mode == "staged":
        # Stage zero is the authoritative configuration plane.  The registry's
        # final staged generation check already protects the captured index;
        # the worktree config is neither consumed nor authoritative, including
        # when the captured config contains zero rules.
        return lambda: None

    def validate() -> str | None:
        rechecked = None
        rechecked_name = None
        for candidate in _CONFIG_CANDIDATES:
            probe = source_oracle.safe_workspace_path(
                diff.root_identity.realpath or project_root,
                candidate,
                deadline=deadline,
                limit=1024 * 1024,
                allow_directory=True,
            )
            rechecked = probe
            if probe.kind in {"missing", "directory"}:
                continue
            rechecked_name = candidate
            break
        selected = rechecked if rechecked_name is not None else None
        rechecked_data = selected.data if selected is not None else None
        rechecked_metadata = selected.metadata if selected is not None else ()
        if (
            rechecked is None
            or diff.constraint_config_path != rechecked_name
            or diff.constraint_config_data != rechecked_data
            or diff.constraint_config_metadata != rechecked_metadata
        ):
            return "CONSTRAINT_CONFIG_CHANGED"
        return None

    return validate


def _supported_scope_is_covered(paths: list[str], source_scope: object) -> bool:
    """Return whether every graph-supported path is selected by the index scope."""
    if not isinstance(source_scope, SourceScopeDescriptor):
        return False
    # The evaluator selects an edge when either endpoint is changed.  A scope
    # that omits arbitrary roots or caller/callee candidates cannot certify the
    # absence of an edge crossing into the changed endpoint.  Default golden
    # corpus exclusions are fixed by the discovery policy; caller-supplied
    # exclusions and partial roots are not graph-authoritative here.
    if source_scope.roots != (".",) or source_scope.exclude_patterns:
        return False
    for path in paths:
        normalized = path.replace("\\", "/") if os.name == "nt" else path
        if EXT_TO_LANG.get(os.path.splitext(normalized)[1].lower()) is None:
            continue
        if not _scope_covers_path(normalized, source_scope):
            return False
    return True


def _scope_covers_path(normalized: str, source_scope: SourceScopeDescriptor) -> bool:
    """Return whether one graph-supported path is selected by *source_scope*.

    ``effective_excludes`` and ``roots`` are read once per path, as the
    scope may be a replayed (re-read) descriptor.
    """
    if any(
        fnmatch.fnmatch(normalized, pattern)
        for pattern in source_scope.effective_excludes
    ):
        return False
    path_parts = tuple(part for part in normalized.split("/") if part)
    return any(_root_covers(path_parts, root) for root in source_scope.roots)


def _root_covers(path_parts: tuple[str, ...], root: str) -> bool:
    """Return whether *root* selects the path without an excluded descendant."""
    root_parts = tuple(
        part for part in root.replace("\\", "/").split("/") if part not in ("", ".")
    )
    if path_parts[: len(root_parts)] != root_parts:
        return False
    descendants = path_parts[len(root_parts) : -1]
    return not any(part in EXCLUDE_DIRS or part.startswith(".") for part in descendants)


def _snapshot_error(
    tool: Any, code: str, output_format: str, detail: str | None = None
) -> dict[str, Any]:
    envelope = cast(dict[str, Any], tool._snapshot_error(code, output_format, detail))
    envelope.setdefault("action_version", EDIT_CONSTRAINTS_ACTION_VERSION)
    return envelope


def _deadline_kwargs(
    func: Callable[..., Any], deadline: float | None
) -> dict[str, Any]:
    """Pass ``deadline`` only to callables whose signature accepts it."""
    return (
        {"deadline": deadline}
        if "deadline" in inspect.signature(func).parameters
        else {}
    )


@dataclass(frozen=True)
class _Outcome:
    """A response payload; ``final`` payloads are returned without publishing."""

    payload: dict[str, Any]
    final: bool = False


@dataclass(frozen=True)
class _FrozenRun:
    """Immutable inputs shared by one frozen constraint evaluation."""

    tool: Any
    arguments: dict[str, Any]
    diff: Any
    project_root: str
    raw_scope: list[str]
    evaluation_scope: frozenset[str] | None
    deadline: float
    output_format: str
    fail: _FailFn


def execute_frozen(tool: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one immutable diff/config/index capability without project writes."""
    from ...diff_snapshot_registry import HARD_LIFETIME_SECONDS
    from ...diff_snapshot_registry import REGISTRY as DIFF_REGISTRY

    output_format = arguments.get("output_format", "json")
    snapshot_id = str(arguments["diff_snapshot_id"])
    project_root = tool.project_root
    if project_root is None:
        return _snapshot_error(tool, "MISSING_PROJECT_ROOT", output_format)
    consumer, error = DIFF_REGISTRY.acquire(
        snapshot_id, project_root, **_deadline_kwargs(DIFF_REGISTRY.acquire, None)
    )
    if error:
        return _snapshot_error(tool, error, output_format)
    assert consumer is not None
    fail = _provenance_fail(tool, consumer, output_format)
    try:
        diff = consumer.snapshot
        deadline = diff.created_monotonic + HARD_LIFETIME_SECONDS
        raw_scope = list(diff.assessed_scope_paths)
        frozen_scope = [path_to_wire(path) for path in raw_scope]
        if arguments["scope_paths"] != frozen_scope:
            return fail("DIFF_SNAPSHOT_SCOPE_MISMATCH")

        config_error = getattr(diff, "constraint_config_error", None)
        if config_error is not None:
            return fail(config_error)
        guard = _config_publish_guard(diff, project_root, deadline)
        config_changed = any(
            candidate in diff.assessed_scope_paths for candidate in _CONFIG_CANDIDATES
        )
        run = _FrozenRun(
            tool=tool,
            arguments=arguments,
            diff=diff,
            project_root=project_root,
            raw_scope=raw_scope,
            evaluation_scope=None if config_changed else frozenset(frozen_scope),
            deadline=deadline,
            output_format=output_format,
            fail=fail,
        )
        outcome = _rules_outcome(run)
        if outcome.final:
            return outcome.payload

        # The configuration guard runs inside the registry's final oracle
        # before/after window, so no response is published from revalidated bytes
        # followed by a separate, racy generation check.
        error = DIFF_REGISTRY.validate_publish(
            consumer,
            guard,
            **_deadline_kwargs(DIFF_REGISTRY.validate_publish, deadline),
        )
        if error:
            return fail(error)
        response = outcome.payload
        response.update(
            diff_snapshot_id=diff.snapshot_id,
            source_generation=diff.source_generation,
            assessed_scope_paths=frozen_scope,
        )
        return apply_output_format_to_response(response, output_format)
    except (OSError, RuntimeError, SourceOracleError, sqlite3.DatabaseError) as exc:
        return fail("CONSTRAINT_CAPTURE_UNKNOWN", detail=str(exc))
    finally:
        consumer.release()


def _provenance_fail(tool: Any, consumer: Any, default_format: str) -> _FailFn:
    """Build ``fail`` for one acquired diff-snapshot consumer."""

    def fail(
        code: str, output_format: str = default_format, detail: str | None = None
    ) -> dict[str, Any]:
        envelope = _snapshot_error(tool, code, output_format, detail)
        # The consumer's snapshot may itself be the failing read (e.g. a
        # broken registry), so provenance must be best-effort.
        try:
            snapshot_id = consumer.snapshot.snapshot_id
            generation = consumer.snapshot.source_generation
        except Exception:  # noqa: BLE001 - error envelopes must not re-raise
            snapshot_id = None
            generation = None
        envelope.update(
            diff_snapshot_id=snapshot_id,
            source_generation=generation,
        )
        return envelope

    return fail


def _rules_outcome(run: _FrozenRun) -> _Outcome:
    """Load the frozen configuration and evaluate its rules (if any)."""
    diff = run.diff
    config_name = diff.constraint_config_path
    if config_name is None:
        return _Outcome(
            {
                "success": True,
                "state": "not_applicable",
                "reason": "NO_CONFIG",
                "verdict": "INFO",
                "action_version": EDIT_CONSTRAINTS_ACTION_VERSION,
                "violations": [],
                "rule_count": 0,
                "evaluated_edge_count": 0,
                "diff_snapshot_id": diff.snapshot_id,
                "source_generation": diff.source_generation,
            }
        )
    try:
        constraints = load_constraints_bytes(
            diff.constraint_config_data or b"", config_name
        )
    except ConstraintParseError as exc:
        return _Outcome(run.fail("CONSTRAINT_CONFIG_INVALID", detail=str(exc)), True)
    if not constraints:
        return _Outcome(
            {
                "success": True,
                "state": "applicable",
                "verdict": "SAFE",
                "action_version": EDIT_CONSTRAINTS_ACTION_VERSION,
                "violations": [],
                "rule_count": 0,
                "evaluated_edge_count": 0,
            }
        )
    if diff.mode == "staged" and not (
        diff.staged_source_matches_worktree and diff.staged_config_matches_worktree
    ):
        # Available index capabilities certify only the live source plane.
        # A divergent stage-zero plane must never borrow that live graph.
        return _Outcome(run.fail("CONSTRAINT_STAGED_INDEX_UNKNOWN"), True)
    return _graph_rules_outcome(run, constraints)


def _graph_rules_outcome(run: _FrozenRun, constraints: Any) -> _Outcome:
    """Evaluate graph-backed rules against the pinned index capability."""
    try:
        # RFC-0022 P0.4: in explicit read_existing mode the caller reserved a
        # specific index capability; acquiring any other snapshot would answer
        # the graph rules against the wrong capability.  The reserved pair is
        # mandatory here, and only that registry-owned snapshot is used.
        reserved_id = run.arguments.get("snapshot_id")
        reserved_generation = run.arguments.get("source_generation")
        reserved = isinstance(reserved_id, str) and isinstance(reserved_generation, str)
        if run.arguments.get("access_mode") == "read_existing" and not reserved:
            return _Outcome(run.fail("CONSTRAINT_INDEX_CAPABILITY_REQUIRED"), True)
        if reserved:
            evaluated = _evaluate_reserved(
                run, constraints, str(reserved_id), str(reserved_generation)
            )
        else:
            # Legacy same-process route (no explicit read_existing contract):
            # pin the current published capability.
            evaluated = _evaluate_leased(run, constraints)
        if isinstance(evaluated, dict):
            return _Outcome(evaluated, True)
        rows, edge_count, index = evaluated
        return _Outcome(
            {
                "success": True,
                "state": "applicable",
                "verdict": run.tool._compute_verdict(rows),
                "action_version": EDIT_CONSTRAINTS_ACTION_VERSION,
                "violations": rows,
                "rule_count": len(constraints),
                "evaluated_edge_count": edge_count,
                "snapshot_id": index.snapshot_id,
                "index_fingerprint": index.index_fingerprint,
            }
        )
    except (
        sqlite3.DatabaseError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        return _Outcome(
            _snapshot_error(
                run.tool, "CONSTRAINT_INDEX_UNKNOWN", run.output_format, str(exc)
            ),
            True,
        )
    except (OSError, RuntimeError, SourceOracleError) as exc:
        return _Outcome(
            _snapshot_error(
                run.tool, "CONSTRAINT_CAPTURE_UNKNOWN", run.output_format, str(exc)
            ),
            True,
        )


def _evaluate_rules(run: _FrozenRun, conn: Any, constraints: Any) -> tuple[Any, Any]:
    """Run the rule evaluator over one pinned index connection."""
    return cast(
        tuple[Any, Any],
        run.tool._evaluate_connection(
            conn,
            constraints,
            min_severity_rank=run.tool.severity_rank(
                run.arguments.get("severity_min", "warn")
            ),
            scope_paths=run.evaluation_scope,
            deadline=run.deadline,
        ),
    )


def _evaluate_reserved(
    run: _FrozenRun,
    constraints: Any,
    reserved_id: str,
    reserved_generation: str,
) -> _Evaluation | dict[str, Any]:
    """Evaluate against the caller-reserved index capability."""
    from ...index_snapshot import acquire_index_snapshot

    with acquire_index_snapshot(
        reserved_id,
        run.project_root,
        reserved_generation,
        **_deadline_kwargs(acquire_index_snapshot, run.deadline),
    ) as (index, conn):
        if (
            index.completeness != "complete"
            or index.source_generation != run.diff.source_generation
        ):
            return run.fail(index.reason or "SOURCE_GENERATION_MISMATCH")
        if not _supported_scope_is_covered(run.raw_scope, index.source_scope):
            return run.fail("CONSTRAINT_INDEX_SCOPE_MISMATCH")
        rows, edge_count = _evaluate_rules(run, conn, constraints)
    return rows, edge_count, index


def _evaluate_leased(run: _FrozenRun, constraints: Any) -> _Evaluation | dict[str, Any]:
    """Evaluate against the currently published index capability."""
    from ...index_snapshot import acquire_index_snapshot, lease_existing_snapshot

    lease = lease_existing_snapshot(
        run.project_root,
        **_deadline_kwargs(lease_existing_snapshot, run.deadline),
    )
    with lease as index:
        if (
            index.snapshot_id is None
            or index.completeness != "complete"
            or index.source_generation != run.diff.source_generation
        ):
            return run.fail(index.reason or "SOURCE_GENERATION_MISMATCH")
        if not _supported_scope_is_covered(run.raw_scope, index.source_scope):
            return run.fail("CONSTRAINT_INDEX_SCOPE_MISMATCH")
        with acquire_index_snapshot(
            index.snapshot_id,
            run.project_root,
            run.diff.source_generation,
            **_deadline_kwargs(acquire_index_snapshot, run.deadline),
        ) as (_, conn):
            rows, edge_count = _evaluate_rules(run, conn, constraints)
    return rows, edge_count, index
