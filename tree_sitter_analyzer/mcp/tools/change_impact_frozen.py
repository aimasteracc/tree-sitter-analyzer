"""Strict frozen-snapshot scope projection for change impact."""

from __future__ import annotations

from typing import Any

from ...git_path_codec import path_from_wire, path_to_raw, path_to_wire
from .change_impact_support import _snapshot_records
from .utils.change_impact_git import _raw_path_is_excluded
from .utils.change_impact_response import (
    apply_scope_validation,
    attach_queue_ledger,
    build_no_changes_result,
)


def scope_matches_raw(scope: bytes, path: bytes) -> bool:
    prefix = scope.rstrip(b"/")
    return prefix == b"." or path == prefix or path.startswith(prefix + b"/")


def build_frozen_scope_result(
    frozen: dict[str, object],
    consumer: Any,
    mode: str,
    scope_paths: list[str],
    scope_mode: str,
) -> tuple[dict[str, Any], list[dict[str, object]], list[str], list[str]]:
    records = _snapshot_records(frozen)
    frozen_files = {
        path_to_wire(item.record.path): (item.record.raw_path, item.record.raw_old_path)
        for item in getattr(consumer.snapshot, "files", ())
    }
    if not frozen_files:
        frozen_files = {
            str(record["path"]): (
                path_to_raw(path_from_wire(str(record["path"]))),
                (
                    path_to_raw(path_from_wire(str(record["old_path"])))
                    if record.get("old_path")
                    else None
                ),
            )
            for record in records
        }
    # Exclude tool-owned paths on their exact raw byte segments.  In
    # particular, a non-UTF-8 child of .ast-cache must be removed before its
    # public path becomes a git-path-b64 token.
    visible_paths = {
        public_path
        for public_path, (raw_path, _raw_old_path) in frozen_files.items()
        if not _raw_path_is_excluded(raw_path)
    }
    workspace_changed = [
        str(record["path"])
        for record in records
        if str(record["path"]) in visible_paths
    ]
    scope_raw = [path_to_raw(scope) for scope in scope_paths]
    identities = {
        identity
        for public_path, pair in frozen_files.items()
        if public_path in visible_paths
        for identity in pair
        if identity is not None
    }
    changed_files = workspace_changed
    if scope_raw:
        changed_files = [
            public_path
            for public_path, (raw_path, raw_old_path) in frozen_files.items()
            if public_path in visible_paths
            and any(
                scope_matches_raw(scope, raw_path)
                or (raw_old_path is not None and scope_matches_raw(scope, raw_old_path))
                for scope in scope_raw
            )
        ]
    inventory_raw = getattr(consumer.snapshot, "_inventory_raw_paths", ())
    if not inventory_raw:
        inventory_raw = tuple(
            path_to_raw(path) for path in consumer.snapshot.inventory_paths
        )
    scope_identities = {
        raw for raw in inventory_raw if not _raw_path_is_excluded(raw)
    }.union(identities)
    invalid_scope = [
        path_to_wire(scope)
        for scope, raw_scope in zip(scope_paths, scope_raw, strict=True)
        if not any(
            scope_matches_raw(raw_scope, identity) for identity in scope_identities
        )
    ]
    public_scope = [path_to_wire(path) for path in scope_paths]
    if changed_files:
        result: dict[str, Any] = {
            "success": True,
            "mode": mode,
            "changed_files": changed_files,
            "changed_count": len(changed_files),
            "diff_stat": f"{len(changed_files)} frozen file(s) changed",
            "affected_files": [],
            "affected_files_unknown": True,
            "tests_to_run": [],
            "tests_to_run_unknown": True,
            "verdict": "REVIEW",
            "risk_level": "unknown",
            "summary": (
                f"{len(changed_files)} frozen file(s) changed; affected files and "
                "tests are unknown without live analysis"
            ),
            "agent_summary": {
                "verdict": "REVIEW",
                "changed_files": changed_files,
                "affected_files": [],
                "affected_files_unknown": True,
                "tests_to_run": [],
                "tests_to_run_unknown": True,
            },
        }
    else:
        result = build_no_changes_result(mode, public_scope)
    result["scope_paths"] = public_scope
    result["scope_filtered"] = bool(scope_paths)
    result = attach_queue_ledger(
        result,
        mode=mode,
        scope_paths=public_scope,
        scoped_changed_files=changed_files,
        workspace_changed_files=workspace_changed,
        scope_mode=scope_mode,
    )
    result = apply_scope_validation(result, invalid_scope)
    assessed = (
        sorted(set(changed_files).union(set(public_scope).difference(invalid_scope)))
        if scope_mode == "strict"
        else sorted(set(workspace_changed).union(public_scope))
    )
    return result, records, changed_files, assessed
