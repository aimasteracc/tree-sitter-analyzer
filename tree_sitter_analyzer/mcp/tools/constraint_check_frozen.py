"""Frozen RFC-0022 execution path for architectural constraint checks."""

from __future__ import annotations

import fnmatch
import inspect
import os
import sqlite3
from collections.abc import Callable
from typing import Any, cast

from ... import source_oracle
from ...constants import EXCLUDE_DIRS
from ...constraints.parser import ConstraintParseError, load_constraints_bytes
from ...git_path_codec import path_to_wire
from ...index_source_scope import SourceScopeDescriptor
from ...languages.lang_extension_map import EXT_TO_LANG
from ...source_oracle import SourceOracleError
from ..utils.format_helper import apply_toon_format_to_response

_CONFIG_CANDIDATES = (
    "architectural-constraints.yml",
    ".tree-sitter-analyzer/constraints.yml",
)


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
        if any(
            fnmatch.fnmatch(normalized, pattern)
            for pattern in source_scope.effective_excludes
        ):
            return False
        path_parts = tuple(part for part in normalized.split("/") if part)
        covered = False
        for root in source_scope.roots:
            root_parts = tuple(
                part
                for part in root.replace("\\", "/").split("/")
                if part not in ("", ".")
            )
            if path_parts[: len(root_parts)] != root_parts:
                continue
            descendants = path_parts[len(root_parts) : -1]
            if any(
                part in EXCLUDE_DIRS or part.startswith(".") for part in descendants
            ):
                continue
            covered = True
            break
        if not covered:
            return False
    return True


def _snapshot_error(
    tool: Any, code: str, output_format: str, detail: str | None = None
) -> dict[str, Any]:
    return cast(dict[str, Any], tool._snapshot_error(code, output_format, detail))


def execute_frozen(tool: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one immutable diff/config/index capability without project writes."""
    from ...diff_snapshot_registry import HARD_LIFETIME_SECONDS
    from ...diff_snapshot_registry import REGISTRY as DIFF_REGISTRY

    output_format = arguments.get("output_format", "json")
    snapshot_id = str(arguments["diff_snapshot_id"])
    project_root = tool.project_root
    if project_root is None:
        return _snapshot_error(tool, "MISSING_PROJECT_ROOT", output_format)
    acquire_deadline = None
    acquire_kwargs = (
        {"deadline": acquire_deadline}
        if "deadline" in inspect.signature(DIFF_REGISTRY.acquire).parameters
        else {}
    )
    consumer, error = DIFF_REGISTRY.acquire(snapshot_id, project_root, **acquire_kwargs)
    if error:
        return _snapshot_error(tool, error, output_format)
    assert consumer is not None
    try:
        diff = consumer.snapshot
        deadline = diff.created_monotonic + HARD_LIFETIME_SECONDS
        raw_scope = list(diff.assessed_scope_paths)
        frozen_scope = [path_to_wire(path) for path in raw_scope]
        if arguments["scope_paths"] != frozen_scope:
            return _snapshot_error(tool, "DIFF_SNAPSHOT_SCOPE_MISMATCH", output_format)

        config_error = getattr(diff, "constraint_config_error", None)
        if config_error is not None:
            return _snapshot_error(tool, config_error, output_format)
        guard = _config_publish_guard(diff, project_root, deadline)
        config_changed = any(
            candidate in diff.assessed_scope_paths for candidate in _CONFIG_CANDIDATES
        )
        evaluation_scope = None if config_changed else frozenset(frozen_scope)
        config_name = diff.constraint_config_path
        if config_name is None:
            response: dict[str, Any] = {
                "success": True,
                "state": "not_applicable",
                "reason": "NO_CONFIG",
                "verdict": "INFO",
                "violations": [],
                "rule_count": 0,
                "evaluated_edge_count": 0,
            }
        else:
            try:
                constraints = load_constraints_bytes(
                    diff.constraint_config_data or b"", config_name
                )
            except ConstraintParseError as exc:
                return _snapshot_error(
                    tool, "CONSTRAINT_CONFIG_INVALID", output_format, str(exc)
                )
            if not constraints:
                response = {
                    "success": True,
                    "state": "applicable",
                    "verdict": "SAFE",
                    "violations": [],
                    "rule_count": 0,
                    "evaluated_edge_count": 0,
                }
            elif diff.mode == "staged" and not (
                diff.staged_source_matches_worktree
                and diff.staged_config_matches_worktree
            ):
                # Available index capabilities certify only the live source plane.
                # A divergent stage-zero plane must never borrow that live graph.
                return _snapshot_error(
                    tool, "CONSTRAINT_STAGED_INDEX_UNKNOWN", output_format
                )
            else:
                try:
                    from ...index_snapshot import (
                        acquire_index_snapshot,
                        lease_existing_snapshot,
                    )

                    lease = lease_existing_snapshot(
                        project_root,
                        **(
                            {"deadline": deadline}
                            if "deadline"
                            in inspect.signature(lease_existing_snapshot).parameters
                            else {}
                        ),
                    )
                    with lease as index:
                        if (
                            index.snapshot_id is None
                            or index.completeness != "complete"
                            or index.source_generation != diff.source_generation
                        ):
                            return _snapshot_error(
                                tool,
                                index.reason or "SOURCE_GENERATION_MISMATCH",
                                output_format,
                            )
                        if not _supported_scope_is_covered(
                            raw_scope, index.source_scope
                        ):
                            return _snapshot_error(
                                tool, "CONSTRAINT_INDEX_SCOPE_MISMATCH", output_format
                            )
                        with acquire_index_snapshot(
                            index.snapshot_id,
                            project_root,
                            diff.source_generation,
                            **(
                                {"deadline": deadline}
                                if "deadline"
                                in inspect.signature(acquire_index_snapshot).parameters
                                else {}
                            ),
                        ) as (_, conn):
                            rows, edge_count = tool._evaluate_connection(
                                conn,
                                constraints,
                                min_severity_rank=tool.severity_rank(
                                    arguments.get("severity_min", "warn")
                                ),
                                scope_paths=evaluation_scope,
                                deadline=deadline,
                            )
                        response = {
                            "success": True,
                            "state": "applicable",
                            "verdict": tool._compute_verdict(rows),
                            "violations": rows,
                            "rule_count": len(constraints),
                            "evaluated_edge_count": edge_count,
                            "snapshot_id": index.snapshot_id,
                            "index_fingerprint": index.index_fingerprint,
                        }
                except (
                    sqlite3.DatabaseError,
                    ValueError,
                    TypeError,
                    AttributeError,
                ) as exc:
                    return _snapshot_error(
                        tool, "CONSTRAINT_INDEX_UNKNOWN", output_format, str(exc)
                    )
                except (OSError, RuntimeError, SourceOracleError) as exc:
                    return _snapshot_error(
                        tool, "CONSTRAINT_CAPTURE_UNKNOWN", output_format, str(exc)
                    )

        # The configuration guard runs inside the registry's final oracle
        # before/after window, so no response is published from revalidated bytes
        # followed by a separate, racy generation check.
        error = DIFF_REGISTRY.validate_publish(
            consumer,
            guard,
            **(
                {"deadline": deadline}
                if "deadline"
                in inspect.signature(DIFF_REGISTRY.validate_publish).parameters
                else {}
            ),
        )
        if error:
            return _snapshot_error(tool, error, output_format)
        response.update(
            diff_snapshot_id=diff.snapshot_id,
            source_generation=diff.source_generation,
            assessed_scope_paths=frozen_scope,
        )
        return apply_toon_format_to_response(response, output_format)
    except (OSError, RuntimeError, SourceOracleError, sqlite3.DatabaseError) as exc:
        return _snapshot_error(
            tool, "CONSTRAINT_CAPTURE_UNKNOWN", output_format, str(exc)
        )
    finally:
        consumer.release()
