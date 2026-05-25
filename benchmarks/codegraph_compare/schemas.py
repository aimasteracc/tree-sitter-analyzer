"""
Pydantic v2 dataclasses for the codegraph-comparison benchmark harness.

Run records capture raw execution metrics; eval records capture LLM-judge scores.
Repo, question, and arm specs define the benchmark configuration.
"""

from __future__ import annotations

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass


@dataclass(config=ConfigDict(extra="forbid"))
class RunRecord:
    """One execution of a question under one arm at one repeat index."""

    run_id: str  # format: "{question_id}__{arm}__{repeat:02d}"
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

    @classmethod
    def make_id(cls, question_id: str, arm: str, repeat: int) -> str:
        """Return the canonical run_id string."""
        return f"{question_id}__{arm}__{repeat:02d}"


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
