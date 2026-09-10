"""Dataclass-based output schema for --hotspot.

Uses stdlib @dataclass + dataclasses.asdict() — no Pydantic dependency.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestFocus:
    function: str
    cc: int
    suggestion: str


@dataclass
class HotspotEntry:
    rank: int
    file: str
    severity: str          # "CRITICAL" | "REVIEW" | "OK"
    score: float
    ca_raw: int
    ca_alias: int
    max_cc: int
    test_focus: TestFocus
    hops: int | None = None   # set only when --trace-from is active


@dataclass
class HotspotMetadata:
    files_analyzed: int
    files_in_output: int
    page: int
    page_size: int
    total_pages: int
    truncated: bool


@dataclass
class SubgraphSummary:
    entry_point: str
    depth: int
    files_in_subgraph: int
    total_project_files: int


@dataclass
class AliasDiffSummary:
    files_with_alias_gap: int
    total_files: int


@dataclass
class HotspotResult:
    success: bool
    metadata: HotspotMetadata | None = None
    threshold: dict[str, int] | None = None
    results: list[HotspotEntry] = field(default_factory=list)
    message: str | None = None
    subgraph_summary: SubgraphSummary | None = None
    alias_gap_summary: AliasDiffSummary | None = None
    error: str | None = None
    error_category: str | None = None  # "state"|"data"|"transient"|"configuration"
    recovery_hint: str | None = None   # "retry"|"try_alternative"|"fix_then_retry"|"fix_argument"
    # Canonical CLI envelope (required by test_cli_envelope_contract.py)
    summary_line: str | None = None
    verdict: str | None = None
    agent_summary: dict[str, Any] | None = None


def paginate(
    ranked: list[HotspotEntry],
    page: int,
    page_size: int,
) -> tuple[list[HotspotEntry], HotspotMetadata]:
    """Slice a pre-sorted list and return (page_slice, metadata).

    ranked must already be sorted descending by score.
    page is 1-indexed.
    total_pages is 0 when ranked is empty.
    """
    total = len(ranked)
    # ceiling division; yields 0 when total==0
    total_pages = -(-total // page_size) if total > 0 else 0
    start = (page - 1) * page_size
    end = start + page_size
    sliced = ranked[start:end]
    truncated = page < total_pages
    meta = HotspotMetadata(
        files_analyzed=total,
        files_in_output=len(sliced),
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        truncated=truncated,
    )
    return sliced, meta


def result_to_dict(result: HotspotResult) -> dict[str, Any]:
    """Serialize HotspotResult to a plain dict, omitting None-valued fields."""
    raw = dataclasses.asdict(result)
    return {k: v for k, v in raw.items() if v is not None}
