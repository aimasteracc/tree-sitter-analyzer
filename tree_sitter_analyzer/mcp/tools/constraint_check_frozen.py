"""Frozen RFC-0022 execution path for architectural constraint checks."""

from __future__ import annotations

import fnmatch
import os
import sqlite3
import time
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


def _config_publish_guard(diff: Any, project_root: str) -> Callable[[], str | None]:
    """Build the final-publish guard for impact-owned configuration bytes."""

    if diff.mode == "staged" and diff.constraint_config_path is None:
        # Stage zero is the authoritative configuration plane.  The registry's
        # final staged generation check already protects the captured index;
        # probing the worktree here would both cross planes and turn an
        # unrelated untracked config into a false CONFIG_CHANGED result.
        return lambda: None

    def validate() -> str | None:
        rechecked = None
        rechecked_name = None
        for candidate in _CONFIG_CANDIDATES:
            probe = source_oracle.safe_workspace_path(
                diff.root_identity.realpath or project_root,
                candidate,
                deadline=time.monotonic() + 10.0,
                limit=1024 * 1024,
            )
            rechecked = probe
            if probe.kind != "missing":
                rechecked_name = candidate
                break
        if (
            rechecked is None
            or diff.constraint_config_path != rechecked_name
            or diff.constraint_config_data != rechecked.data
            or diff.constraint_config_metadata != rechecked.metadata
        ):
            return "CONSTRAINT_CONFIG_CHANGED"
        return None

    return validate


def _supported_scope_is_covered(paths: list[str], source_scope: object) -> bool:
    """Return whether every graph-supported path is selected by the index scope."""
    if not isinstance(source_scope, SourceScopeDescriptor):
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
    from ...diff_snapshot_registry import REGISTRY as DIFF_REGISTRY

    output_format = arguments.get("output_format", "json")
    snapshot_id = str(arguments["diff_snapshot_id"])
    project_root = tool.project_root
    if project_root is None:
        return _snapshot_error(tool, "MISSING_PROJECT_ROOT", output_format)
    consumer, error = DIFF_REGISTRY.acquire(snapshot_id, project_root)
    if error:
        return _snapshot_error(tool, error, output_format)
    assert consumer is not None
    try:
        diff = consumer.snapshot
        frozen_scope = [path_to_wire(path) for path in diff.assessed_scope_paths]
        if arguments["scope_paths"] != frozen_scope:
            return _snapshot_error(tool, "DIFF_SNAPSHOT_SCOPE_MISMATCH", output_format)

        guard = _config_publish_guard(diff, project_root)
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
            if diff.mode == "staged" and not (
                diff.staged_source_matches_worktree
                and diff.staged_config_matches_worktree
            ):
                # Available index capabilities certify only the live source plane.
                # A divergent stage-zero plane must never borrow that live graph.
                return _snapshot_error(
                    tool, "CONSTRAINT_STAGED_INDEX_UNKNOWN", output_format
                )
            try:
                constraints = load_constraints_bytes(
                    diff.constraint_config_data or b"", config_name
                )
            except ConstraintParseError as exc:
                return _snapshot_error(
                    tool, "CONSTRAINT_CONFIG_INVALID", output_format, str(exc)
                )
            try:
                from ...index_snapshot import (
                    acquire_index_snapshot,
                    lease_existing_snapshot,
                )

                with lease_existing_snapshot(project_root) as index:
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
                        frozen_scope, index.source_scope
                    ):
                        return _snapshot_error(
                            tool, "CONSTRAINT_INDEX_SCOPE_MISMATCH", output_format
                        )
                    with acquire_index_snapshot(
                        index.snapshot_id, project_root, diff.source_generation
                    ) as (_, conn):
                        rows, edge_count = tool._evaluate_connection(
                            conn,
                            constraints,
                            min_severity_rank=tool.severity_rank(
                                arguments.get("severity_min", "warn")
                            ),
                            scope_paths=frozenset(frozen_scope),
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
            except (sqlite3.DatabaseError, ValueError) as exc:
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
        error = DIFF_REGISTRY.validate_publish(consumer, guard)
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
