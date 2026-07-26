"""Focused validation engine for RFC-0021 benchmark integrity."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import cast

from benchmarks.codegraph_compare.integrity import (
    ExpectedCellV1,
    ExperimentManifestV1,
    IntegrityVerdict,
    IntegrityViolation,
    RegistryEvent,
    _manifest_payload,
    _sha256,
    create_manifest,
    validate_setup_index_stats,
)
from benchmarks.codegraph_compare.schemas import (
    BenchmarkStatus,
    EvalRecordV1,
    RunRecordV1,
)

_REGISTRY_STATUSES = frozenset({"PLANNED", "RUNNING", "BLOCKED", "COMPLETE", "INVALID"})
_TERMINAL_FAILURE_STATUSES = frozenset({"BLOCKED", "INVALID"})
_PRODUCER_COMPLETION = ("COMPLETE", "producer_completed")


def _identity(record: RunRecordV1 | EvalRecordV1) -> tuple[str, str, str, int]:
    value = record.identity
    return value.experiment_id, value.session_id, value.run_id, value.attempt_no


def _cell_matches(record: RunRecordV1, cell: ExpectedCellV1) -> bool:
    return (
        record.repo == cell.repo
        and record.question_id == cell.question_id
        and record.arm == cell.arm
        and record.repeat == cell.repeat
        and record.agent_backend == cell.agent_backend
        and record.run_id == cell.run_id
    )


def _base_provenance_matches(
    record: RunRecordV1, manifest: ExperimentManifestV1
) -> bool:
    return (
        record.config_hash == manifest.config_hash
        and record.question_hash == manifest.question_hash
        and record.oracle_hash == manifest.oracle_hash
        and record.model == manifest.model
        and record.agent_backend == manifest.agent_backend
        and record.benchmark_git_sha == manifest.benchmark_git_sha
        and record.agent_cli_fingerprint == manifest.agent_cli_fingerprint
        and record.platform == manifest.platform
        and record.environment_fingerprint == manifest.environment_fingerprint
        and record.repo_commit == dict(manifest.repo_commits).get(record.repo)
        and record.tool_fingerprint == dict(manifest.tool_fingerprints).get(record.arm)
    )


def _index_stats_violation(
    record: RunRecordV1, manifest: ExperimentManifestV1
) -> str | None:
    indexed = record.arm in manifest.indexed_arms
    if not indexed:
        return "UNEXPECTED_INDEX_STATS" if record.index_stats is not None else None
    if record.status is BenchmarkStatus.NOT_EVALUATED:
        return None
    violation = validate_setup_index_stats(
        record.index_stats, manifest, record.repo, record.arm
    )
    if violation == "MIXED_INDEX_PROVENANCE":
        return violation
    return "INDEX_NOT_READY" if violation is not None else None


def _provenance_violation(
    record: RunRecordV1, manifest: ExperimentManifestV1
) -> str | None:
    if not _base_provenance_matches(record, manifest):
        return "MIXED_PROVENANCE"
    return _index_stats_violation(record, manifest)


def _validate_manifest(manifest: ExperimentManifestV1) -> list[IntegrityViolation]:
    violations: list[IntegrityViolation] = []
    recomputed_hash = _sha256(_manifest_payload(manifest))
    if (
        type(manifest.benchmark_version) is not int
        or manifest.benchmark_version != 1
        or manifest.manifest_hash != recomputed_hash
        or manifest.experiment_id != f"sha256:{recomputed_hash}"
    ):
        violations.append(IntegrityViolation(code="INVALID_MANIFEST_HASH"))
    try:
        normalized = create_manifest(
            benchmark_git_sha=manifest.benchmark_git_sha,
            config_hash=manifest.config_hash,
            question_hash=manifest.question_hash,
            oracle_hash=manifest.oracle_hash,
            seed=manifest.seed,
            timeout_seconds=manifest.timeout_seconds,
            schedule_hash=manifest.schedule_hash,
            agent_backend=manifest.agent_backend,
            model=manifest.model,
            agent_cli_fingerprint=manifest.agent_cli_fingerprint,
            platform=manifest.platform,
            environment_fingerprint=manifest.environment_fingerprint,
            primary_session_id=manifest.primary_session_id,
            retry_session_ids=manifest.retry_session_ids,
            expected_cells=manifest.expected_cells,
            required_arms=manifest.required_arms,
            indexed_arms=manifest.indexed_arms,
            tool_fingerprints=dict(manifest.tool_fingerprints),
            repo_commits=dict(manifest.repo_commits),
            repo_fingerprints=dict(manifest.repo_fingerprints),
            eligible_paths=dict(manifest.eligible_paths),
            eligible_paths_hashes=dict(manifest.eligible_paths_hashes),
            parse_error_allowlists=dict(manifest.parse_error_allowlists),
            required_readiness_oracles=dict(manifest.required_readiness_oracles),
        )
        if normalized != manifest:
            violations.append(IntegrityViolation(code="INVALID_MANIFEST_STRUCTURE"))
    except ValueError:
        violations.append(IntegrityViolation(code="INVALID_MANIFEST_STRUCTURE"))
    return violations


def _validate_registry(
    manifest: ExperimentManifestV1,
    registry_items: tuple[RegistryEvent, ...],
    reported_experiment_ids: tuple[str, ...],
) -> tuple[list[IntegrityViolation], tuple[str, ...]]:
    violations: list[IntegrityViolation] = []
    registered_ids = tuple(sorted({item.experiment_id for item in registry_items}))
    current_events = tuple(
        item for item in registry_items if item.experiment_id == manifest.experiment_id
    )
    binding_violation = _registry_binding_violation(manifest, current_events)
    if binding_violation is not None:
        violations.append(binding_violation)
    hidden_ids = (
        experiment_id
        for experiment_id in registered_ids
        if experiment_id not in reported_experiment_ids
    )
    violations.extend(
        IntegrityViolation(code="HIDDEN_EXPERIMENT", experiment_id=experiment_id)
        for experiment_id in hidden_ids
    )
    unregistered_reported = (
        set(reported_experiment_ids) - set(registered_ids) - {manifest.experiment_id}
    )
    if unregistered_reported:
        violations.append(IntegrityViolation(code="UNREGISTERED_REPORTED_EXPERIMENT"))
    return violations, registered_ids


def _registry_binding_violation(
    manifest: ExperimentManifestV1,
    current_events: tuple[RegistryEvent, ...],
) -> IntegrityViolation | None:
    if not current_events:
        return IntegrityViolation(
            code="UNREGISTERED_EXPERIMENT", experiment_id=manifest.experiment_id
        )
    if any(item.manifest_hash != manifest.manifest_hash for item in current_events):
        return IntegrityViolation(
            code="REGISTRY_MANIFEST_MISMATCH", experiment_id=manifest.experiment_id
        )
    if any(
        item.status not in _REGISTRY_STATUSES
        or item.status in _TERMINAL_FAILURE_STATUSES
        for item in current_events
    ):
        return IntegrityViolation(
            code="REGISTRY_TERMINAL_FAILURE", experiment_id=manifest.experiment_id
        )
    complete_positions = [
        index for index, item in enumerate(current_events) if item.status == "COMPLETE"
    ]
    if (
        complete_positions != [len(current_events) - 1]
        or (
            current_events[-1].status,
            current_events[-1].outcome,
        )
        != _PRODUCER_COMPLETION
    ):
        return IntegrityViolation(
            code="REGISTRY_PRODUCER_INCOMPLETE",
            experiment_id=manifest.experiment_id,
        )
    return None


def _collect_attempts(
    manifest: ExperimentManifestV1,
    run_items: tuple[RunRecordV1, ...],
    cells: dict[str, ExpectedCellV1],
) -> tuple[list[IntegrityViolation], dict[str, list[RunRecordV1]]]:
    violations: list[IntegrityViolation] = []
    allowed_sessions = {manifest.primary_session_id, *manifest.retry_session_ids}
    attempts_by_run: dict[str, list[RunRecordV1]] = {}
    seen: set[tuple[str, str, str, int]] = set()
    for record in run_items:
        identity = _identity(record)
        if identity in seen:
            violations.append(
                IntegrityViolation(code="DUPLICATE_ATTEMPT", identity=identity)
            )
            continue
        seen.add(identity)
        if record.experiment_id != manifest.experiment_id:
            violations.append(
                IntegrityViolation(code="MIXED_EXPERIMENT", identity=identity)
            )
            continue
        cell = cells.get(record.run_id)
        if cell is None:
            violations.append(
                IntegrityViolation(code="UNEXPECTED_RUN_CELL", identity=identity)
            )
            continue
        if record.session_id not in allowed_sessions:
            violations.append(
                IntegrityViolation(code="UNLINKED_SESSION", identity=identity)
            )
            continue
        if not _cell_matches(record, cell):
            violations.append(
                IntegrityViolation(code="CELL_PROVENANCE_MISMATCH", identity=identity)
            )
            attempts_by_run.setdefault(record.run_id, []).append(record)
            continue
        provenance_code = _provenance_violation(record, manifest)
        if provenance_code is not None:
            violations.append(
                IntegrityViolation(code=provenance_code, identity=identity)
            )
        attempts_by_run.setdefault(record.run_id, []).append(record)
    return violations, attempts_by_run


RetryBlock = tuple[tuple[str, str, int, str], str, str]


def _find_primary_attempt(
    manifest: ExperimentManifestV1,
    cell: ExpectedCellV1,
    candidates: list[RunRecordV1],
) -> tuple[RunRecordV1 | None, IntegrityViolation | None]:
    primaries = [
        item
        for item in candidates
        if item.session_id == manifest.primary_session_id
        and item.attempt_no == 0
        and item.retry_of is None
    ]
    if len(primaries) == 1:
        return primaries[0], None
    code = "MISSING_RUN_CELL" if not primaries else "DUPLICATE_PRIMARY"
    identity = (
        manifest.experiment_id,
        manifest.primary_session_id,
        cell.run_id,
        0,
    )
    return None, IntegrityViolation(code=code, identity=identity)


def _select_cell_attempt(
    manifest: ExperimentManifestV1,
    cell: ExpectedCellV1,
    candidates: list[RunRecordV1],
) -> tuple[RunRecordV1 | None, list[IntegrityViolation], RetryBlock | None]:
    violations: list[IntegrityViolation] = []
    primary, primary_violation = _find_primary_attempt(manifest, cell, candidates)
    if primary is None:
        return None, [cast(IntegrityViolation, primary_violation)], None
    retry_candidates = [item for item in candidates if item is not primary]
    if not retry_candidates:
        return primary, violations, None
    if primary.status is not BenchmarkStatus.INFRA_FAILURE:
        return (
            primary,
            [
                IntegrityViolation(
                    code="ILLEGAL_RETRY_STATUS", identity=_identity(primary)
                )
            ],
            None,
        )
    if len(retry_candidates) != 1:
        return (
            primary,
            [IntegrityViolation(code="MULTIPLE_RETRIES", identity=_identity(primary))],
            None,
        )
    retry = retry_candidates[0]
    valid_lineage = (
        retry.session_id in manifest.retry_session_ids
        and retry.attempt_no == 1
        and retry.retry_of == primary.identity
    )
    if not valid_lineage:
        return (
            primary,
            [
                IntegrityViolation(
                    code="INVALID_RETRY_LINEAGE", identity=_identity(retry)
                )
            ],
            None,
        )
    block = (cell.repo, cell.question_id, cell.repeat, cell.agent_backend)
    return retry, violations, (block, retry.session_id, cell.arm)


def _select_canonical_attempts(
    manifest: ExperimentManifestV1,
    attempts_by_run: dict[str, list[RunRecordV1]],
) -> tuple[
    list[IntegrityViolation],
    list[RunRecordV1],
    dict[tuple[str, str, int, str], dict[str, set[str]]],
]:
    violations: list[IntegrityViolation] = []
    canonical: list[RunRecordV1] = []
    retried_blocks: dict[tuple[str, str, int, str], dict[str, set[str]]] = {}
    for cell in manifest.expected_cells:
        selected, cell_violations, retry_block = _select_cell_attempt(
            manifest, cell, attempts_by_run.get(cell.run_id, [])
        )
        violations.extend(cell_violations)
        if selected is not None:
            canonical.append(selected)
        if retry_block is not None:
            block, session_id, arm = retry_block
            retried_blocks.setdefault(block, {}).setdefault(session_id, set()).add(arm)
    return violations, canonical, retried_blocks


def _validate_retry_blocks(
    manifest: ExperimentManifestV1,
    retried_blocks: dict[tuple[str, str, int, str], dict[str, set[str]]],
) -> list[IntegrityViolation]:
    violations: list[IntegrityViolation] = []
    for block, sessions in retried_blocks.items():
        expected_arms = {
            cell.arm
            for cell in manifest.expected_cells
            if (cell.repo, cell.question_id, cell.repeat, cell.agent_backend) == block
        }
        if len(sessions) != 1:
            violations.append(IntegrityViolation(code="MIXED_RETRY_SESSION"))
        elif next(iter(sessions.values())) != expected_arms:
            violations.append(IntegrityViolation(code="UNPAIRED_RETRY"))
    return violations


def _validate_evaluations(
    manifest: ExperimentManifestV1,
    eval_items: tuple[EvalRecordV1, ...],
    canonical: list[RunRecordV1],
) -> list[IntegrityViolation]:
    violations: list[IntegrityViolation] = []
    canonical_ids = {_identity(item) for item in canonical}
    eval_counts = Counter(_identity(item) for item in eval_items)
    for identity, count in eval_counts.items():
        if count > 1:
            violations.append(
                IntegrityViolation(code="DUPLICATE_EVAL", identity=identity)
            )
        if identity[0] != manifest.experiment_id:
            violations.append(
                IntegrityViolation(code="MIXED_EVAL_EXPERIMENT", identity=identity)
            )
        elif identity not in canonical_ids:
            violations.append(IntegrityViolation(code="EXTRA_EVAL", identity=identity))
    for selected in canonical:
        identity = _identity(selected)
        if selected.status is BenchmarkStatus.SUCCESS and eval_counts[identity] == 0:
            violations.append(
                IntegrityViolation(code="MISSING_EVAL_CELL", identity=identity)
            )
        if selected.status is BenchmarkStatus.NOT_EVALUATED:
            violations.append(
                IntegrityViolation(
                    code="REQUIRED_ARM_NOT_EVALUATED",
                    identity=identity,
                    arm=selected.arm,
                    reason=selected.blocker_reason,
                )
            )
        elif selected.status is not BenchmarkStatus.SUCCESS:
            violations.append(
                IntegrityViolation(
                    code="REQUIRED_CELL_FAILED",
                    identity=identity,
                    arm=selected.arm,
                    reason=selected.status.value,
                )
            )
        if selected.status is not BenchmarkStatus.SUCCESS and eval_counts[identity]:
            violations.append(
                IntegrityViolation(code="UNEXPECTED_EVAL_FOR_STATUS", identity=identity)
            )
    return violations


def _build_verdict(
    manifest: ExperimentManifestV1,
    *,
    violations: list[IntegrityViolation],
    canonical: list[RunRecordV1],
    run_items: tuple[RunRecordV1, ...],
    cells: dict[str, ExpectedCellV1],
    registered_ids: tuple[str, ...],
) -> IntegrityVerdict:
    only_not_evaluated = bool(violations) and all(
        item.code == "REQUIRED_ARM_NOT_EVALUATED" for item in violations
    )
    claim_level = (
        "NOT_EVALUATED" if only_not_evaluated else ("INVALID" if violations else "E1")
    )
    return IntegrityVerdict(
        publishable=not violations,
        claim_level=claim_level,
        violations=tuple(violations),
        canonical_attempts=tuple(canonical),
        reliability_attempts=tuple(
            item
            for item in run_items
            if item.experiment_id == manifest.experiment_id and item.run_id in cells
        ),
        disclosed_attempts=run_items,
        expected_cell_count=len(manifest.expected_cells),
        observed_cell_count=len(canonical),
        dominance_allowed=False,
        winner=None,
        disclosed_experiment_ids=registered_ids,
    )


def validate_experiment(
    manifest: ExperimentManifestV1,
    *,
    registry: Iterable[RegistryEvent],
    runs: Iterable[RunRecordV1],
    evals: Iterable[EvalRecordV1],
    reported_experiment_ids: tuple[str, ...],
) -> IntegrityVerdict:
    """Validate registry, exact cells, provenance, lineage, and evaluations."""
    registry_items = tuple(registry)
    run_items = tuple(runs)
    eval_items = tuple(evals)
    cells = {cell.run_id: cell for cell in manifest.expected_cells}
    violations = _validate_manifest(manifest)
    if violations:
        registered_ids = tuple(sorted({item.experiment_id for item in registry_items}))
        return _build_verdict(
            manifest,
            violations=violations,
            canonical=[],
            run_items=run_items,
            cells=cells,
            registered_ids=registered_ids,
        )
    registry_violations, registered_ids = _validate_registry(
        manifest, registry_items, reported_experiment_ids
    )
    violations.extend(registry_violations)
    attempt_violations, attempts_by_run = _collect_attempts(manifest, run_items, cells)
    violations.extend(attempt_violations)
    selection_violations, canonical, retried_blocks = _select_canonical_attempts(
        manifest, attempts_by_run
    )
    violations.extend(selection_violations)
    violations.extend(_validate_retry_blocks(manifest, retried_blocks))
    violations.extend(_validate_evaluations(manifest, eval_items, canonical))
    return _build_verdict(
        manifest,
        violations=violations,
        canonical=canonical,
        run_items=run_items,
        cells=cells,
        registered_ids=registered_ids,
    )
