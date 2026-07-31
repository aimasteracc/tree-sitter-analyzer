"""Manifest-bound execution evidence for the RFC-0021 Gin Smoke."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from benchmarks.codegraph_compare.integrity import (
    ExpectedCellV1,
    ExperimentManifestV1,
)
from benchmarks.codegraph_compare.schemas import (
    BenchmarkStatus,
    IndexStatsV1,
    RunRecordV1,
)

_ARM_SERVER = {
    "native-only": None,
    "tsa-warm": "tree-sitter-analyzer",
    "codegraph-warm": "codegraph",
}
_FORBIDDEN_ORACLE_TERMS = (
    "expected_key_points",
    "anti_hallucination_checks",
    "oracle_hash",
)
_WRITE_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)"
    r"(?:rm|mv|cp|install|tee|touch|mkdir|chmod|chown)\b"
    r"|\bgit\s+(?:add|commit|checkout|switch|reset|clean|restore)\b"
    r"|\bsed\s+-i\b|(?:^|[^<])>{1,2}(?!=)",
    re.IGNORECASE,
)
_INDEX_COMMAND = re.compile(
    r"\b(?:codegraph|tree[-_]sitter[-_]analyzer)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PolicyAudit:
    """Mechanical transcript-policy decision for one physical attempt."""

    arm: str
    transcript_path: str
    observed_mcp_servers: tuple[str, ...]
    observed_mcp_tools: tuple[str, ...]
    violations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.violations


def audit_codex_transcript(transcript_path: Path, arm: str) -> PolicyAudit:
    """Fail closed on malformed, cross-arm, mutating, or oracle-bearing events."""

    if arm not in _ARM_SERVER:
        raise ValueError(f"Unsupported Smoke arm: {arm}")
    violations: list[str] = []
    servers: list[str] = []
    tools: list[str] = []
    if not transcript_path.is_file():
        violations.append("TRANSCRIPT_MISSING")
        return PolicyAudit(arm, str(transcript_path), (), (), tuple(violations))

    expected_server = _ARM_SERVER[arm]
    for line_number, line in enumerate(
        transcript_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            violations.append(f"MALFORMED_JSON:{line_number}")
            continue
        if not isinstance(event, dict):
            violations.append(f"NON_OBJECT_EVENT:{line_number}")
            continue
        lowered = line.lower()
        if any(term in lowered for term in _FORBIDDEN_ORACLE_TERMS):
            violations.append(f"ORACLE_EXPOSURE:{line_number}")
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "file_change":
            violations.append(f"FILE_CHANGE:{line_number}")
        elif item_type == "web_search":
            violations.append(f"NETWORK_TOOL:{line_number}")
        elif item_type == "command_execution":
            command = str(item.get("command") or "")
            if _WRITE_COMMAND.search(command):
                violations.append(f"MUTATING_COMMAND:{line_number}")
            if _INDEX_COMMAND.search(command):
                violations.append(f"INDEX_COMMAND_OUTSIDE_MCP:{line_number}")
        elif item_type == "mcp_tool_call":
            server = str(item.get("server") or item.get("server_name") or "")
            tool = str(item.get("tool") or item.get("tool_name") or "")
            servers.append(server)
            tools.append(tool)
            if not server or server != expected_server:
                violations.append(f"CROSS_ARM_MCP:{line_number}")

    if expected_server is not None and expected_server not in servers:
        violations.append("MISSING_INDEX_QUERY")
    return PolicyAudit(
        arm,
        str(transcript_path),
        tuple(servers),
        tuple(tools),
        tuple(dict.fromkeys(violations)),
    )


def build_v1_attempt(
    manifest: ExperimentManifestV1,
    expected_cell: ExpectedCellV1,
    legacy_record: dict[str, Any],
    *,
    index_stats: IndexStatsV1 | None,
    policy_audit: PolicyAudit,
) -> RunRecordV1:
    """Bind one legacy runner result to its immutable V1 experiment identity."""

    identity = {
        "run_id": expected_cell.run_id,
        "repo": expected_cell.repo,
        "question_id": expected_cell.question_id,
        "arm": expected_cell.arm,
        "repeat": expected_cell.repeat,
        "agent_backend": expected_cell.agent_backend,
        "model": manifest.model,
        "session_id": manifest.primary_session_id,
    }
    mismatches = [
        key for key, value in identity.items() if legacy_record.get(key) != value
    ]
    if mismatches:
        raise ValueError(f"Runner record identity mismatch: {tuple(mismatches)}")
    if expected_cell.arm in manifest.indexed_arms and index_stats is None:
        raise ValueError("Indexed Smoke attempts require manifest-bound index evidence")
    if expected_cell.arm not in manifest.indexed_arms and index_stats is not None:
        raise ValueError("Native Smoke attempts cannot carry index evidence")

    error = legacy_record.get("error")
    if not policy_audit.ok:
        status = BenchmarkStatus.INVALID
        blocker = "POLICY_AUDIT:" + ",".join(policy_audit.violations)
    elif error:
        status = BenchmarkStatus.PRODUCT_FAILURE
        blocker = str(error)
    else:
        status = BenchmarkStatus.SUCCESS
        blocker = None
    reported_cost = float(legacy_record.get("total_cost_usd", 0.0))
    estimated_cost = float(legacy_record.get("estimated_cost_usd", 0.0))
    cost_source: Literal["provider", "estimated", "none"] = (
        "provider"
        if reported_cost > 0
        else "estimated"
        if estimated_cost > 0
        else "none"
    )

    return RunRecordV1(
        benchmark_version=1,
        experiment_id=manifest.experiment_id,
        session_id=manifest.primary_session_id,
        run_id=expected_cell.run_id,
        attempt_no=0,
        retry_of=None,
        status=status,
        repo=expected_cell.repo,
        question_id=expected_cell.question_id,
        arm=expected_cell.arm,
        repeat=expected_cell.repeat,
        agent_backend=manifest.agent_backend,
        model=manifest.model,
        config_hash=manifest.config_hash,
        question_hash=manifest.question_hash,
        oracle_hash=manifest.oracle_hash,
        tool_fingerprint=dict(manifest.tool_fingerprints)[expected_cell.arm],
        repo_commit=dict(manifest.repo_commits)[expected_cell.repo],
        benchmark_git_sha=manifest.benchmark_git_sha,
        agent_cli_fingerprint=manifest.agent_cli_fingerprint,
        platform=manifest.platform,
        environment_fingerprint=manifest.environment_fingerprint,
        blocker_reason=blocker,
        input_tokens=int(legacy_record.get("input_tokens", 0)),
        output_tokens=int(legacy_record.get("output_tokens", 0)),
        total_tokens=int(legacy_record.get("total_tokens", 0)),
        total_cost_usd=reported_cost,
        tool_calls=int(legacy_record.get("tool_calls", 0)),
        answer=str(legacy_record.get("answer", "")),
        started_at=str(legacy_record.get("started_at", "")),
        ended_at=str(legacy_record.get("ended_at", "")),
        elapsed_seconds=float(legacy_record.get("elapsed_seconds", 0.0)),
        estimated_cost_usd=estimated_cost,
        cost_source=cost_source,
        cached_input_tokens=int(legacy_record.get("cached_input_tokens", 0)),
        reasoning_output_tokens=int(
            legacy_record.get("reasoning_output_tokens", 0)
        ),
        cache_read_tokens=int(legacy_record.get("cache_read_tokens", 0)),
        cache_creation_tokens=int(legacy_record.get("cache_creation_tokens", 0)),
        num_turns=int(legacy_record.get("num_turns", 0)),
        file_reads=int(legacy_record.get("file_reads", 0)),
        search_calls=int(legacy_record.get("search_calls", 0)),
        index_queries=int(legacy_record.get("index_queries", 0)),
        citations=tuple(legacy_record.get("citations", ())),
        transcript_path=str(legacy_record.get("transcript_path", "")),
        index_stats=index_stats,
    )


def append_v1_attempt(
    results_dir: Path,
    manifest: ExperimentManifestV1,
    attempt: RunRecordV1,
    policy_audit: PolicyAudit,
) -> Path:
    """Append one unique attempt and its audit without overwriting evidence."""

    experiment_dir = results_dir / "experiments" / manifest.manifest_hash
    experiment_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = experiment_dir / "runs.jsonl"
    identity = (
        attempt.experiment_id,
        attempt.session_id,
        attempt.run_id,
        attempt.attempt_no,
    )
    if attempts_path.exists():
        for line in attempts_path.read_text(encoding="utf-8").splitlines():
            raw = json.loads(line)
            observed = (
                raw.get("experiment_id"),
                raw.get("session_id"),
                raw.get("run_id"),
                raw.get("attempt_no"),
            )
            if observed == identity:
                raise ValueError(f"Duplicate physical attempt: {identity}")
    with attempts_path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                asdict(attempt),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )

    audit_path = experiment_dir / f"policy_{attempt.run_id}.json"
    if audit_path.exists():
        raise ValueError(f"Policy audit already exists: {audit_path.name}")
    audit_path.write_text(
        json.dumps(
            asdict(policy_audit),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return attempts_path


def run_manifest_smoke(
    *,
    manifest: ExperimentManifestV1,
    repo_entries: list[dict[str, Any]],
    arm_entries: list[dict[str, Any]],
    questions_by_repo: dict[str, list[dict[str, Any]]],
    supplied_index_stats: dict[tuple[str, str], IndexStatsV1],
    results_dir: Path,
    repo_path_resolver: Any,
    adapter_factory: Any,
    run_one: Any,
) -> int:
    """Execute the manifest schedule and persist every terminal V1 attempt."""

    if manifest.agent_backend != "codex":
        raise ValueError("NO1-001B manifest execution requires the Codex backend")
    repos = {str(entry["id"]): entry for entry in repo_entries}
    arms = {str(entry["id"]): entry for entry in arm_entries}
    questions = {
        (repo_id, str(question["id"])): question
        for repo_id, entries in questions_by_repo.items()
        for question in entries
    }
    adapters: dict[tuple[str, str], Any] = {}
    configs: dict[tuple[str, str, str], Any] = {}
    failed = 0
    for cell in manifest.expected_cells:
        repo_entry = repos[cell.repo]
        _ = arms[cell.arm]
        question = questions[(cell.repo, cell.question_id)]
        repo_path = repo_path_resolver(repo_entry)
        adapter_key = (cell.repo, cell.arm)
        if adapter_key not in adapters:
            adapters[adapter_key] = adapter_factory(cell.arm)
        adapter = adapters[adapter_key]
        config_key = (cell.repo, cell.arm, cell.question_id)
        if config_key not in configs:
            configs[config_key] = adapter.build_run_config(
                repo_path, str(question["prompt"])
            )
        legacy = run_one(
            question_id=cell.question_id,
            question_prompt=str(question["prompt"]),
            arm_id=cell.arm,
            repo_path=repo_path,
            repeat=cell.repeat,
            run_config=configs[config_key],
            results_dir=results_dir,
            timeout_seconds=manifest.timeout_seconds,
            model=manifest.model,
            agent_backend=manifest.agent_backend,
            dry_run=False,
            session_id=manifest.primary_session_id,
        )
        transcript = Path(str(legacy.get("transcript_path", "")))
        audit = audit_codex_transcript(transcript, cell.arm)
        attempt = build_v1_attempt(
            manifest,
            cell,
            legacy,
            index_stats=supplied_index_stats.get((cell.repo, cell.arm)),
            policy_audit=audit,
        )
        append_v1_attempt(results_dir, manifest, attempt, audit)
        if attempt.status is not BenchmarkStatus.SUCCESS:
            failed += 1
    return 0 if failed == 0 else 1


def run_manifest_setup_gate(
    *,
    args: Any,
    manifest: ExperimentManifestV1,
    supplied_index_stats: dict[tuple[str, str], IndexStatsV1] | None,
    repo_entries: list[dict[str, Any]],
    arm_entries: list[dict[str, Any]],
    question_entries_by_repo: dict[str, list[dict[str, Any]]],
    repeats: int,
    session_id: str,
    results_dir: Path,
    repo_path_resolver: Any,
    append_event: Any,
) -> int:
    """Validate external V1 evidence without creating adapters or model calls."""

    from benchmarks.codegraph_compare.adapters.claude_runner import (
        validate_backend_arm_support,
    )
    from benchmarks.codegraph_compare.setup_validation import (
        validate_matrix_setup,
        write_manifest_setup_evidence,
    )

    def unused_adapter_factory(arm_id: str) -> Any:
        raise AssertionError(f"setup-only must not create adapter {arm_id}")

    setup_result = validate_matrix_setup(
        repo_entries,
        arm_entries,
        questions_by_repo=question_entries_by_repo,
        repo_path_resolver=repo_path_resolver,
        adapter_factory=unused_adapter_factory,
        manifest=manifest,
        repeats=repeats,
        agent_backend=args.agent_backend,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        supplied_index_stats=supplied_index_stats,
        backend_validator=lambda arm_id: validate_backend_arm_support(
            args.agent_backend, arm_id
        ),
    )
    evidence_path = write_manifest_setup_evidence(
        results_dir,
        session_id=session_id,
        manifest=manifest,
        result=setup_result,
    )
    if not setup_result.ok:
        append_event(manifest, "BLOCKED", "setup_failed")
        print(
            f"[setup] FAILED: {len(setup_result.failures)} indexed cell(s); "
            "no model calls started.",
            file=sys.stderr,
        )
        for failure in setup_result.failures:
            print(
                f"  repo={failure.repo_id}  arm={failure.arm_id}  "
                f"{failure.code}: {failure.message}",
                file=sys.stderr,
            )
        print(f"Setup evidence: {evidence_path}", file=sys.stderr)
        return 1

    append_event(manifest, "PLANNED", "setup_passed")
    print(
        "[setup] PASSED: manifest-bound V1 evidence validated; no model calls started.",
        file=sys.stderr,
    )
    print(f"Setup evidence: {evidence_path}", file=sys.stderr)
    return 0


def execute_bound_manifest(
    *,
    manifest: ExperimentManifestV1 | None,
    args: Any,
    supplied_index_stats: dict[tuple[str, str], IndexStatsV1] | None,
    repo_entries: list[dict[str, Any]],
    arm_entries: list[dict[str, Any]],
    question_entries_by_repo: dict[str, list[dict[str, Any]]],
    repeats: int,
    session_id: str,
    results_dir: Path,
    repo_path_resolver: Any,
    append_event: Any,
    adapter_factory: Any,
    run_one: Any,
) -> int | None:
    """Run setup and the frozen schedule when a manifest was supplied."""

    if manifest is None:
        return None
    setup_result = run_manifest_setup_gate(
        args=args,
        manifest=manifest,
        supplied_index_stats=supplied_index_stats,
        repo_entries=repo_entries,
        arm_entries=arm_entries,
        question_entries_by_repo=question_entries_by_repo,
        repeats=repeats,
        session_id=session_id,
        results_dir=results_dir,
        repo_path_resolver=repo_path_resolver,
        append_event=append_event,
    )
    if setup_result != 0:
        return setup_result
    append_event(manifest, "RUNNING", "smoke_started")
    result = run_manifest_smoke(
        manifest=manifest,
        repo_entries=repo_entries,
        arm_entries=arm_entries,
        questions_by_repo=question_entries_by_repo,
        supplied_index_stats=supplied_index_stats or {},
        results_dir=results_dir,
        repo_path_resolver=repo_path_resolver,
        adapter_factory=adapter_factory,
        run_one=run_one,
    )
    outcome = "smoke_completed" if result == 0 else "smoke_invalid"
    status = "COMPLETE" if result == 0 else "FAILED"
    append_event(manifest, status, outcome)
    return result
