"""
Pydantic v2 dataclasses for the codegraph-comparison benchmark harness.

Run records capture raw execution metrics; eval records capture LLM-judge scores.
Repo, question, and arm specs define the benchmark configuration.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass


@dataclass(config=ConfigDict(extra="forbid"))
class RunRecord:
    """One execution of a question under one arm at one repeat index."""

    run_id: str  # format: "{question_id}__{arm}__{agent_backend}__{repeat:02d}"
    repo: str
    question_id: str
    arm: str
    repeat: int
    started_at: str  # ISO 8601
    ended_at: str  # ISO 8601
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    tool_calls: int
    file_reads: int
    search_calls: int
    index_queries: int
    answer: str
    citations: list[str]
    transcript_path: str
    error: str | None = None
    agent_backend: str = "claude"
    model: str = ""
    cached_input_tokens: int = 0
    reasoning_output_tokens: int = 0
    # Real provider accounting pulled verbatim from the agent's result/usage
    # block (claude --print / codex stream) — NOT estimated. cache_read /
    # cache_creation split out the prompt-cache mechanics so cost attribution
    # isn't blurred; total_cost_usd is the provider's own dollar figure (use it
    # over estimated_cost_usd for cost claims); num_turns is the agent's turn
    # count (the real lever behind cost divergence, per the cost-analysis-rigor
    # lesson). All default to 0 so pre-existing runs.jsonl records still validate
    # under extra='forbid'.
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    total_cost_usd: float = 0.0
    num_turns: int = 0
    # Per-invocation id (one per cmd_run / cmd_run_matrix) that uniquifies raw
    # artifact filenames so repeated runs of the same run_id don't overwrite each
    # other. run_id stays the logical grouping key; session_id distinguishes
    # invocations. Optional so older runs.jsonl records still validate.
    session_id: str = ""

    @classmethod
    def make_id(
        cls, question_id: str, arm: str, repeat: int, agent_backend: str = "claude"
    ) -> str:
        """Return the canonical run_id string."""
        return f"{question_id}__{arm}__{agent_backend}__{repeat:02d}"


@dataclass(config=ConfigDict(extra="forbid"))
class EvalRecord:
    """LLM-judge scores for one RunRecord."""

    run_id: str
    correctness: int  # 1-5
    completeness: int  # 1-5
    citation_quality: int  # 1-5
    hallucination_risk: int  # 1-5  (5 = high risk, bad)
    overall: float
    missing_key_points: list[str]
    bad_citations: list[str]
    evaluator_model: str
    evaluated_at: str  # ISO 8601


class BenchmarkStatus(str, Enum):
    """Fail-closed outcome for one versioned benchmark attempt."""

    SUCCESS = "SUCCESS"
    PRODUCT_FAILURE = "PRODUCT_FAILURE"
    INFRA_FAILURE = "INFRA_FAILURE"
    INVALID = "INVALID"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class AttemptIdentityV1:
    """Immutable identity for one physical attempt of a logical run."""

    experiment_id: str
    session_id: str
    run_id: str
    attempt_no: int

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.session_id or not self.run_id:
            raise ValueError("Attempt identity fields must be non-empty")
        if self.attempt_no < 0:
            raise ValueError("attempt_no must be non-negative")


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class IndexStatsV1:
    """Comparable index readiness and provenance for one attempt."""

    eligible_source_files: int
    indexed_source_files: int
    excluded_source_files: int
    parse_error_files: int
    eligible_paths_hash: str
    indexed_paths_hash: str
    excluded_paths_hash: str
    parse_error_paths_hash: str
    indexed_paths: tuple[str, ...]
    excluded_paths: tuple[str, ...]
    parse_error_paths: tuple[str, ...]
    build_seconds: float
    index_size_bytes: int
    repo_fingerprint: str
    tool_fingerprint: str
    readiness_oracles: tuple[str, ...]

    def __post_init__(self) -> None:
        counts = (
            self.eligible_source_files,
            self.indexed_source_files,
            self.excluded_source_files,
            self.parse_error_files,
            self.index_size_bytes,
        )
        if any(value < 0 for value in counts) or self.build_seconds < 0:
            raise ValueError("Index statistics must be non-negative")
        provenance = (
            self.eligible_paths_hash,
            self.indexed_paths_hash,
            self.excluded_paths_hash,
            self.parse_error_paths_hash,
            self.repo_fingerprint,
            self.tool_fingerprint,
        )
        if not all(provenance):
            raise ValueError("Index provenance fields must be non-empty")
        for paths in (self.indexed_paths, self.excluded_paths, self.parse_error_paths):
            if tuple(sorted(set(paths))) != paths or any(not path for path in paths):
                raise ValueError(
                    "Index path sets must be sorted, unique, and non-empty"
                )


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RunRecordV1:
    """Strict provenance record for one RFC-0021 benchmark attempt."""

    benchmark_version: Literal[1]
    experiment_id: str
    session_id: str
    run_id: str
    attempt_no: int
    retry_of: AttemptIdentityV1 | None
    status: BenchmarkStatus
    repo: str
    question_id: str
    arm: str
    repeat: int
    agent_backend: str
    model: str
    config_hash: str
    question_hash: str
    oracle_hash: str
    tool_fingerprint: str
    repo_commit: str
    benchmark_git_sha: str
    agent_cli_fingerprint: str
    platform: str
    environment_fingerprint: str
    blocker_reason: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost_usd: float
    tool_calls: int
    answer: str
    started_at: str = ""
    ended_at: str = ""
    elapsed_seconds: float = 0.0
    estimated_cost_usd: float = 0.0
    cost_source: Literal["provider", "estimated", "none"] = "none"
    cached_input_tokens: int = 0
    reasoning_output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    num_turns: int = 0
    file_reads: int = 0
    search_calls: int = 0
    index_queries: int = 0
    citations: tuple[str, ...] = ()
    transcript_path: str = ""
    index_stats: IndexStatsV1 | None = None

    @property
    def identity(self) -> AttemptIdentityV1:
        """Return the full physical-attempt identity."""
        return AttemptIdentityV1(
            self.experiment_id,
            self.session_id,
            self.run_id,
            self.attempt_no,
        )

    def __post_init__(self) -> None:
        _ = self.identity
        required = {
            "repo": self.repo,
            "question_id": self.question_id,
            "arm": self.arm,
            "agent_backend": self.agent_backend,
            "model": self.model,
            "config_hash": self.config_hash,
            "question_hash": self.question_hash,
            "oracle_hash": self.oracle_hash,
            "tool_fingerprint": self.tool_fingerprint,
            "repo_commit": self.repo_commit,
            "benchmark_git_sha": self.benchmark_git_sha,
            "agent_cli_fingerprint": self.agent_cli_fingerprint,
            "platform": self.platform,
            "environment_fingerprint": self.environment_fingerprint,
        }
        missing = tuple(name for name, value in required.items() if not value)
        if missing:
            raise ValueError(f"V1 provenance fields must be non-empty: {missing}")
        non_negative = {
            "repeat": self.repeat,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "tool_calls": self.tool_calls,
            "elapsed_seconds": self.elapsed_seconds,
            "estimated_cost_usd": self.estimated_cost_usd,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "num_turns": self.num_turns,
            "file_reads": self.file_reads,
            "search_calls": self.search_calls,
            "index_queries": self.index_queries,
        }
        invalid = tuple(name for name, value in non_negative.items() if value < 0)
        if invalid:
            raise ValueError(f"V1 numeric fields must be non-negative: {invalid}")
        if self.status is BenchmarkStatus.NOT_EVALUATED:
            if not self.blocker_reason:
                raise ValueError("NOT_EVALUATED requires blocker_reason")
            zero_fields = (
                self.input_tokens,
                self.output_tokens,
                self.total_tokens,
                self.total_cost_usd,
                self.tool_calls,
                self.estimated_cost_usd,
                self.cached_input_tokens,
                self.reasoning_output_tokens,
                self.cache_read_tokens,
                self.cache_creation_tokens,
                self.num_turns,
                self.file_reads,
                self.search_calls,
                self.index_queries,
            )
            if any(zero_fields) or self.answer or self.transcript_path:
                raise ValueError(
                    "NOT_EVALUATED attempts must have zero usage and answer"
                )
        elif self.status is BenchmarkStatus.SUCCESS and self.blocker_reason is not None:
            raise ValueError("SUCCESS must not include blocker_reason")


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class EvalRecordV1:
    """Arm-blind evaluation tied to a full V1 attempt identity."""

    benchmark_version: Literal[1]
    experiment_id: str
    session_id: str
    run_id: str
    attempt_no: int
    correctness: int
    completeness: int
    citation_location_validity: float
    claim_support: int
    overall: float
    evaluator_model: str
    hallucination_risk: int = 1
    missing_key_points: tuple[str, ...] = ()
    bad_citations: tuple[str, ...] = ()
    evaluated_at: str = ""

    @property
    def identity(self) -> AttemptIdentityV1:
        """Return the evaluated physical-attempt identity."""
        return AttemptIdentityV1(
            self.experiment_id,
            self.session_id,
            self.run_id,
            self.attempt_no,
        )

    def __post_init__(self) -> None:
        _ = self.identity
        if not 0.0 <= self.citation_location_validity <= 1.0:
            raise ValueError("citation_location_validity must be between 0 and 1")
        scores = (
            self.correctness,
            self.completeness,
            self.claim_support,
            self.hallucination_risk,
        )
        if any(score < 1 or score > 5 for score in scores):
            raise ValueError("V1 evaluation scores must be between 1 and 5")
        if not 1.0 <= self.overall <= 5.0:
            raise ValueError("overall must be between 1 and 5")
        if not self.evaluator_model:
            raise ValueError("evaluator_model must be non-empty")


def parse_run_record(raw: dict[str, Any]) -> RunRecord | RunRecordV1:
    """Dispatch legacy and V1 run records without weakening either schema."""
    version = raw.get("benchmark_version")
    if version is None:
        return RunRecord(**raw)
    if type(version) is int and version == 1:
        return RunRecordV1(**raw)
    raise ValueError(f"Unsupported benchmark_version: {version}")


def parse_eval_record(raw: dict[str, Any]) -> EvalRecord | EvalRecordV1:
    """Dispatch legacy and V1 evaluation records by explicit version."""
    version = raw.get("benchmark_version")
    if version is None:
        return EvalRecord(**raw)
    if type(version) is int and version == 1:
        return EvalRecordV1(**raw)
    raise ValueError(f"Unsupported benchmark_version: {version}")


@dataclass(config=ConfigDict(extra="forbid"))
class RepoSpec:
    """A pinned repository entry from repos.yaml."""

    id: str
    name: str
    language: str
    url: str
    commit: str  # pinned SHA
    approx_files: int | None = None


@dataclass(config=ConfigDict(extra="forbid"))
class QuestionSpec:
    """One benchmark question bound to a specific repo."""

    id: str
    repo: str
    category: str  # entrypoint-tracing | call-chain | module-boundary | change-impact | subsystem-overview
    prompt: str
    expected_key_points: list[str]
    must_cite_files: bool = True
    anti_hallucination_checks: list[str] | None = None

    def __post_init__(self) -> None:
        valid_categories = {
            "entrypoint-tracing",
            "call-chain",
            "module-boundary",
            "change-impact",
            "subsystem-overview",
        }
        if self.category not in valid_categories:
            raise ValueError(
                f"category {self.category!r} not in {sorted(valid_categories)}"
            )
        if self.anti_hallucination_checks is None:
            object.__setattr__(self, "anti_hallucination_checks", [])


@dataclass(config=ConfigDict(extra="forbid"))
class ArmSpec:
    """One treatment arm (tool combination) in the benchmark."""

    id: str
    adapter: str  # native | codegraph | tree_sitter_analyzer
    index_mode: str  # none | warm | cold


@dataclass(config=ConfigDict(extra="forbid"))
class IndexStats:
    """Timing and size stats from a single index build."""

    build_seconds: float
    index_size_bytes: int
    file_count: int


@dataclass(config=ConfigDict(extra="forbid"))
class ToolMetrics:
    """Tool-call breakdown extracted from a single run transcript."""

    tool_calls: int
    file_reads: int
    search_calls: int
    index_queries: int
