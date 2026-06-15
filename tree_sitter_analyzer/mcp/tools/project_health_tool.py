#!/usr/bin/env python3
"""
Project Health MCP Tool

Bulk health scoring for an entire project in one call.
Returns grade distribution, F/D file list with recommendations, and top refactoring targets.
"""

import shlex
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ...health_scorer import DIMENSION_WEIGHTS, HealthScorer
from ...utils import setup_logger
from .base_tool import BaseMCPTool
from .file_health_tool import _build_signal

logger = setup_logger(__name__)


# F9: realistic timing buckets — round-16b dogfood on a 4.4k-file repo took
# ~5min, while the previous description claimed 30s–3min. The post-hook
# uses these numbers to emit a budget hint agents can plan against.
def _estimate_seconds(total_files: int) -> int:
    """Return a rough wall-clock estimate so callers can size their timeouts.

    The numbers come from instrumented project-health runs on three
    differently-sized repos (small ~150 files, medium ~1k, large 4k+).
    They are deliberately conservative — agents that budget by these
    numbers should still finish before the call times out.
    """
    if total_files < 200:
        return 30
    if total_files < 1000:
        return 90
    if total_files < 3000:
        return 240
    # 3k+ files: 5 min and up — the round-16b case took ~280s.
    return 360


_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "egg-info",
    ".eggs",
    ".idea",
    ".vscode",
    "htmlcov",
    ".cache",
    ".claude",
    ".deepseek",
    ".autonomous-runtime",
}

_AGENT_BACKLOG_LIMIT = 5
_GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
_AGENT_BACKLOG_EXCLUDED_SEGMENTS = {"examples", "golden_masters"}
_AGENT_BACKLOG_EXCLUDED_FILENAMES = {
    "CHANGELOG.md",
    "GITFLOW.md",
    "GITFLOW_ja.md",
    "README.md",
    "README_zh.md",
}


class ProjectHealthTool(BaseMCPTool):
    """MCP Tool that scores every source file and returns a project health report."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "check_project_health",
            "description": (
                "Score ALL files: grade distribution (A-F), worst files, smells, "
                "top refactoring targets. First call on any project. "
                "SLOW: scans every source file. Budget ~30s on <200 files, "
                "~90s on <1k, ~4min on <3k, 5min+ on 3k+ file repos. "
                "``max_files`` only caps display, not scan scope. The "
                "response carries an ``agent_summary.budget_seconds`` field "
                "(estimated and actual) so callers can size timeouts.\n\n"
                "VERDICT INTEGRITY: agent_summary.verdict gates project-wide "
                "quality posture. It is derived from the actual grade distribution "
                "and worst-file census — not from how the user framed the request. "
                "If the user asks 'is the codebase healthy?' and this tool returns "
                "CAUTION / REVIEW / WARN because of a heavy D/F tail, the calling "
                "agent MUST report that verdict and the worst files. Do NOT round "
                "up to SAFE/INFO so the answer feels reassuring. Legal vocabulary: "
                "SAFE / CAUTION / REVIEW / UNSAFE / INFO / WARN / ERROR / NOT_FOUND."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_grade": {
                    "type": "string",
                    "enum": ["A", "B", "C", "D", "F"],
                    "description": "Minimum grade to include in detail list (default: D — shows D and F)",
                    "default": "D",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to include in detail list (default: 20)",
                    "default": 20,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
                "compact_only": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "RFC-0012: with output_format=toon, return only the "
                        "control surface alongside toon_content, dropping "
                        "metadata already encoded in the blob."
                    ),
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        root = self.project_root
        min_grade = arguments.get("min_grade", "D")
        max_files = _normalize_max_files(arguments.get("max_files", 20))
        output_format = arguments.get("output_format", "toon")
        compact_only = bool(arguments.get("compact_only", False))

        scorer = HealthScorer()
        # F9: measure the scan so the response carries an honest
        # ``actual_seconds`` next to ``estimated_seconds``. Agents that
        # obeyed the previous ``30s–3min`` description timed out on
        # 4k-file repos; recording the truth lets the next caller plan.
        scan_start = time.monotonic()
        all_scores, walk_stats = scorer.score_project_with_stats(root)
        actual_seconds = round(time.monotonic() - scan_start, 1)
        result = _build_project_health_result(
            root,
            all_scores,
            min_grade,
            max_files,
            actual_seconds=actual_seconds,
            walk_stats=walk_stats,
        )

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(
            result, output_format, compact_only=compact_only
        )


_GRADE_RECOMMENDATIONS = {
    "F": "has critical issues — split or rewrite recommended",
    "D": "needs attention — refactor the weakest dimension first",
}


@dataclass(frozen=True)
class _ProjectHealthAggregates:
    """Pre-computed aggregates shared between health-result fields.

    r37f2 (dogfood): held the call-graph between the half-dozen helpers
    that ``_build_project_health_result`` had to thread through the dict
    construction. Bundling them into a frozen dataclass lets the
    response-assembly helper read fields by name instead of taking a
    13-parameter signature.
    """

    grade_counts: Counter
    grade_distribution: dict[str, int]
    dim_avgs: dict[str, float | None]
    signal_dims: dict[str, float]
    worst: list[Any]
    weakest_dim: str
    agent_backlog: list[dict[str, Any]]
    files: list[dict[str, Any]]
    visible_limit: int


def _compute_project_health_aggregates(
    all_scores: list[Any], min_grade: str, max_files: int
) -> _ProjectHealthAggregates:
    """Pre-compute the aggregates that the response dict needs.

    Grouped here so the construction site stays declarative — every
    aggregate is named once when assembled and again when consumed.
    """
    grade_counts = Counter(score.grade for score in all_scores)
    grade_distribution = {grade: grade_counts.get(grade, 0) for grade in "ABCDF"}
    dim_avgs = _average_dimensions(all_scores)
    signal_dims = _numeric_dimensions(dim_avgs)
    worst = _scores_at_or_below_min_grade(all_scores, min_grade)
    weakest_dim = _weakest_dimension(dim_avgs)
    visible_limit = _visible_file_limit(max_files)
    agent_backlog = _build_agent_backlog(all_scores, limit=visible_limit)
    files = _file_details(worst, max_files)
    return _ProjectHealthAggregates(
        grade_counts=grade_counts,
        grade_distribution=grade_distribution,
        dim_avgs=dim_avgs,
        signal_dims=signal_dims,
        worst=worst,
        weakest_dim=weakest_dim,
        agent_backlog=agent_backlog,
        files=files,
        visible_limit=visible_limit,
    )


def _build_project_health_result(
    root: str,
    all_scores: list[Any],
    min_grade: str,
    max_files: int,
    actual_seconds: float | None = None,
    walk_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON-ready project-health response.

    ``actual_seconds`` is the measured scan wall-clock from the calling
    tool. When omitted (legacy callers and unit tests that build results
    directly), the timing fields fall back to the size-based estimate.

    r37f2 (dogfood): 56→25 lines. The 9 aggregates moved to
    ``_compute_project_health_aggregates`` returning a frozen dataclass;
    the response dict is now an inline literal with named-field access.
    """
    from .base_tool import mirror_summary_line

    agg = _compute_project_health_aggregates(all_scores, min_grade, max_files)
    # Bug #783 fix: compute verdict once from the grade distribution and set it
    # at the top level explicitly so top-level verdict and agent_summary.verdict
    # are guaranteed to agree. Previously the top-level verdict was populated
    # solely by mirror_summary_line() which only runs when one side was missing;
    # if both were already set (e.g. by the canonical envelope hook) and they
    # happened to differ, neither side was updated.
    risk = _project_risk(agg.grade_distribution)
    verdict = _project_risk_to_verdict(risk)
    payload: dict[str, Any] = {
        "success": True,
        "verdict": verdict,
        "project_root": root,
        "total_files": len(all_scores),
        "matching_file_count": len(agg.worst),
        "detail_limit": max_files,
        "detail_count": len(agg.files),
        "hidden_detail_count": max(0, len(agg.worst) - len(agg.files)),
        "grade_distribution": agg.grade_distribution,
        "signal": _build_signal(agg.signal_dims),
        "average_dimensions": agg.dim_avgs,
        "coverage_status": _coverage_status(agg.dim_avgs),
        "weakest_dimension": agg.weakest_dim,
        "top_refactoring_targets": _top_refactoring_targets(
            agg.worst, agg.visible_limit
        ),
        "agent_summary": _build_project_agent_summary(
            root=root,
            total_files=len(all_scores),
            grade_distribution=agg.grade_distribution,
            weakest_dim=agg.weakest_dim,
            agent_backlog=agg.agent_backlog,
            max_files=max_files,
            actual_seconds=actual_seconds,
        ),
        "agent_backlog": agg.agent_backlog,
        "files": agg.files,
        "recommendation": _build_project_recommendation(
            agg.grade_counts, agg.weakest_dim, len(all_scores)
        ),
    }
    # Coverage-transparency fields (TRUST_BUT_VERIFY_2026-05-23 contract):
    # surface how much of the project was actually scanned vs scored so
    # an agent can answer "did you really look at my whole project?".
    if walk_stats:
        scanned = int(walk_stats.get("total_files_scanned", 0))
        analyzed = int(walk_stats.get("total_files_scored", len(all_scores)))
        payload["total_files_scanned"] = scanned
        payload["total_files_analyzed"] = analyzed
        payload["total_files_skipped"] = int(walk_stats.get("total_files_skipped", 0))
        payload["skip_reasons"] = walk_stats.get(
            "skip_reasons", {"excluded_dir": 0, "scoring_failed": 0}
        )
        payload["coverage_pct"] = (
            round(100.0 * analyzed / scanned, 1) if scanned else 100.0
        )
    return mirror_summary_line(payload)


def _normalize_max_files(value: Any) -> int:
    """Normalize user-provided project-health detail limit."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 20


def _visible_file_limit(max_files: int) -> int:
    """Keep compact target/backlog lists aligned with the requested detail limit."""
    return min(_AGENT_BACKLOG_LIMIT, max_files)


def _average_dimensions(scores: list[Any]) -> dict[str, float | None]:
    """Average health dimensions across a scored project."""
    dim_avgs: dict[str, float | None] = {}
    for dim in DIMENSION_WEIGHTS:
        vals = [
            score.dimensions.get(dim, 0)
            for score in scores
            if dim in score.dimensions
            and isinstance(score.dimensions[dim], (int, float))
        ]
        dim_avgs[dim] = round(sum(vals) / len(vals), 1) if vals else None
    return dim_avgs


def _numeric_dimensions(dimensions: dict[str, float | None]) -> dict[str, float]:
    """Keep only numeric dimensions for signal and comparison logic."""
    return {
        dimension: score
        for dimension, score in dimensions.items()
        if isinstance(score, (int, float))
    }


def _coverage_status(dimensions: dict[str, float | None]) -> str:
    """Track whether project coverage data was available."""
    return "available" if dimensions.get("coverage") is not None else "unavailable"


def _scores_at_or_below_min_grade(scores: list[Any], min_grade: str) -> list[Any]:
    """Return files whose grade is at or below the requested detail threshold."""
    min_rank = _GRADE_ORDER.get(min_grade, _GRADE_ORDER["D"])
    worst = [
        score
        for score in scores
        if _GRADE_ORDER.get(score.grade, _GRADE_ORDER["F"]) >= min_rank
    ]
    worst.sort(key=lambda score: score.total)
    return worst


def _file_details(scores: list[Any], max_files: int) -> list[dict[str, Any]]:
    """Build detailed file health rows for project-health output.

    Both ``file`` and ``file_path`` keys hold the path; ``total_score`` and
    ``health_score`` hold the numeric score. The dual-key layout matches
    ``file_health_tool`` (which emits ``file_path`` / ``health_score``) so
    callers can use either tool's vocabulary without checking the source.
    """
    return [
        {
            "file": score.file_path,
            "file_path": score.file_path,
            "grade": score.grade,
            "total_score": score.total,
            "health_score": score.total,
            "signal": _build_signal(score.dimensions),
            "weakest_dimension": _weakest_dimension(score.dimensions),
            "dimensions": score.dimensions,
        }
        for score in scores[:max_files]
    ]


def _top_refactoring_targets(
    scores: list[Any],
    max_files: int = _AGENT_BACKLOG_LIMIT,
) -> list[dict[str, Any]]:
    """Build the compact top-refactoring target list."""
    candidates = [score for score in scores if _is_agent_backlog_candidate(score)]
    return [
        {
            "file": score.file_path,
            "file_path": score.file_path,
            "grade": score.grade,
            "score": score.total,
            "health_score": score.total,
            "signal": _build_signal(score.dimensions),
            "action": _file_action(score),
        }
        for score in candidates[:max_files]
    ]


def _build_project_recommendation(
    grade_counts: Counter, weakest_dim: str, total: int
) -> str:
    f_count = grade_counts.get("F", 0)
    d_count = grade_counts.get("D", 0)

    if f_count > 0:
        return (
            f"{f_count} file(s) graded F and {d_count} graded D out of {total}. "
            f"Focus on F-grade files first — they have the worst code health. "
            f"Project-wide weakest dimension: '{weakest_dim}'."
        )

    if d_count > 0:
        return (
            f"{d_count} file(s) graded D out of {total}. "
            f"Improve the '{weakest_dim}' dimension for the biggest overall gain."
        )

    return f"All {total} files are grade C or better. Project health looks good."


def _file_action(score: Any) -> str:
    """Suggest the next tool to call for a specific file."""
    grade = score.grade
    dims = score.dimensions if hasattr(score, "dimensions") else {}
    weakest = _weakest_dimension(dims)
    file_path = score.file_path

    if grade in ("D", "F"):
        return f"edit action=refactor file_path='{file_path}'"

    if grade == "C":
        if weakest:
            return f"health action=file file_path='{file_path}' — weak: {weakest}"
        return f"health action=file file_path='{file_path}'"

    return ""


def _build_agent_backlog(
    scores: list[Any],
    limit: int = _AGENT_BACKLOG_LIMIT,
) -> list[dict[str, Any]]:
    """Build a machine-friendly backlog from project health scores."""
    candidates = [score for score in scores if _is_agent_backlog_candidate(score)]
    candidates.sort(key=lambda score: (score.total, score.file_path))
    return [_build_agent_backlog_item(score) for score in candidates[:limit]]


def _is_agent_backlog_candidate(score: Any) -> bool:
    """Return whether a score should become an autonomous agent queue item."""
    if score.grade not in {"C", "D", "F"}:
        return False
    return not _is_non_actionable_sample_path(score.file_path)


def _is_non_actionable_sample_path(file_path: str) -> bool:
    """Skip demo fixtures and docs that are intentionally poor queue heads."""
    normalized = file_path.replace("\\", "/")
    segments = set(normalized.split("/"))
    if segments & _AGENT_BACKLOG_EXCLUDED_SEGMENTS:
        return True
    return normalized.rsplit("/", 1)[-1] in _AGENT_BACKLOG_EXCLUDED_FILENAMES


def _project_summary_line(
    *,
    risk: str,
    total_files: int,
    grade_distribution: dict[str, int],
    agent_backlog_count: int,
    weakest_dim: str,
    estimated_seconds: float,
    actual_seconds: float | None,
) -> str:
    """Build the ``project_health risk=... files=... A=N B=N ...`` headline line.

    F9 contract: budget segment carries both the size-based estimate and
    the measured wall-clock (when available) so agents can plan against
    the actual scan time.
    """
    grade_breakdown = " ".join(
        f"{grade}={grade_distribution.get(grade, 0)}"
        for grade in ("A", "B", "C", "D", "F")
    )
    budget_segment = f"estimated_seconds={estimated_seconds}"
    if actual_seconds is not None:
        budget_segment += f" actual_seconds={actual_seconds}"
    return (
        f"project_health risk={risk} files={total_files} {grade_breakdown} "
        f"backlog={agent_backlog_count} weakest={weakest_dim or 'unknown'} "
        f"{budget_segment}"
    )


def _project_summary_base(
    *,
    summary_line: str,
    verdict: str,
    risk: str,
    total_files: int,
    grade_distribution: dict[str, int],
    weakest_dim: str,
    agent_backlog_count: int,
    estimated_seconds: float,
    actual_seconds: float | None,
    max_files: int,
) -> dict[str, Any]:
    """Build the always-present fields of the project_health agent_summary.

    Q5 (round-33 dogfood): ``file_count`` aliases ``total_files`` for
    cross-tool consumers; full ``grade_distribution`` inlined so callers
    don't have to string-parse ``summary_line``.
    N3 (round-27): ``verdict`` mirrored to the safety-tool vocabulary so
    agents branching on ``verdict`` get the same answer as
    modification_guard / safe_to_edit.
    """
    return {
        "summary_line": summary_line,
        "verdict": verdict,
        "risk": risk,
        "total_files": total_files,
        "file_count": total_files,
        "grade_distribution": dict(grade_distribution),
        "weakest_dimension": weakest_dim,
        "d_count": grade_distribution.get("D", 0),
        "f_count": grade_distribution.get("F", 0),
        "backlog_count": agent_backlog_count,
        "budget_seconds": {
            "estimated": estimated_seconds,
            "actual": actual_seconds,
        },
        "verification_command": "uv run pytest -q",
        "project_health_command": (
            "uv run python -m tree_sitter_analyzer "
            f"--project-health --max-files {max_files} --format json"
        ),
    }


def _attach_queue_head_fields(
    summary: dict[str, Any], queue_head: dict[str, Any], root: str
) -> dict[str, Any]:
    """Add queue-head pointers + next-step CLI hints to ``summary``."""
    summary["queue_head"] = _project_queue_head(queue_head)
    summary["next_step"] = (
        "Run safe-to-edit for the project queue head: "
        f"{queue_head['safety_cli_command']}"
    )
    summary["queue_head_command"] = queue_head["recommended_cli_command"]
    summary["safety_command"] = queue_head["safety_cli_command"]
    summary["stop_condition"] = (
        "Queue head improves or leaves the project-health backlog; "
        "run uv run pytest -q at the queue boundary."
    )
    if root:
        summary["project_root"] = root
    return summary


def _build_project_agent_summary(
    *,
    root: str,
    total_files: int,
    grade_distribution: dict[str, int],
    weakest_dim: str,
    agent_backlog: list[dict[str, Any]],
    max_files: int = 20,
    actual_seconds: float | None = None,
) -> dict[str, Any]:
    """Build a compact project-level summary for autonomous agent loops.

    F9: ``budget_seconds`` carries the size-based estimate plus the actual
    scan wall-clock when the caller measured it. Agents that previously
    timed out on the documented 30s–3min budget now have a real number to
    plan against.

    r37ep (dogfood): 91 → ~20 lines of orchestration. ``_project_summary_line``
    builds the headline; ``_project_summary_base`` builds the always-present
    fields; ``_attach_queue_head_fields`` adds the queue-head-specific block.
    """
    risk = _project_risk(grade_distribution)
    verdict = _project_risk_to_verdict(risk)
    estimated_seconds = _estimate_seconds(total_files)
    queue_head = agent_backlog[0] if agent_backlog else None

    summary_line = _project_summary_line(
        risk=risk,
        total_files=total_files,
        grade_distribution=grade_distribution,
        agent_backlog_count=len(agent_backlog),
        weakest_dim=weakest_dim,
        estimated_seconds=estimated_seconds,
        actual_seconds=actual_seconds,
    )
    summary = _project_summary_base(
        summary_line=summary_line,
        verdict=verdict,
        risk=risk,
        total_files=total_files,
        grade_distribution=grade_distribution,
        weakest_dim=weakest_dim,
        agent_backlog_count=len(agent_backlog),
        estimated_seconds=estimated_seconds,
        actual_seconds=actual_seconds,
        max_files=max_files,
    )

    if not queue_head:
        return summary | {
            "next_step": "No project-health queue item needs action.",
            "stop_condition": "Project health remains grade C or better with no D/F backlog.",
        }

    return _attach_queue_head_fields(summary, queue_head, root)


def _project_queue_head(queue_head: dict[str, Any]) -> dict[str, Any]:
    """Return the fields agents need before opening the next project item."""
    return {
        "file": queue_head["file"],
        "priority": queue_head["priority"],
        "grade": queue_head["grade"],
        "score": queue_head["score"],
        "signal": queue_head["signal"],
        "weakest_dimension": queue_head["weakest_dimension"],
    }


def _project_risk(grade_distribution: dict[str, int]) -> str:
    """Convert project health distribution into a compact risk label."""
    if grade_distribution.get("F", 0) > 0:
        return "critical"
    if grade_distribution.get("D", 0) > 0:
        return "high"
    if grade_distribution.get("C", 0) > 0:
        return "medium"
    return "low"


def _project_risk_to_verdict(risk: str) -> str:
    """Map project-level risk to the cross-tool verdict vocabulary.

    N3 (round-27): keeps the safety-tool verdict alphabet consistent
    across modification_guard / safe_to_edit / project_health.

    - ``critical`` (F-grade files exist) → ``REVIEW`` (the F count is
      surfaced separately; an agent has to inspect the worst files
      before acting). Not ``UNSAFE`` — project_health describes the
      project, not a specific edit.
    - ``high`` (D-grade files) → ``REVIEW``
    - ``medium`` (C-grade only) → ``CAUTION``
    - ``low`` (A/B only) → ``SAFE``
    """
    risk_lower = (risk or "").lower()
    if risk_lower in ("critical", "high"):
        return "REVIEW"
    if risk_lower == "medium":
        return "CAUTION"
    return "SAFE"


def _build_agent_backlog_item(score: Any) -> dict[str, Any]:
    """Build one project-health backlog item with MCP and CLI parity."""
    file_path = score.file_path
    dims = score.dimensions if hasattr(score, "dimensions") else {}
    weakest = _weakest_dimension(dims)
    quoted_path = shlex.quote(file_path)

    return {
        "file": file_path,
        "priority": _agent_backlog_priority(score.grade),
        "grade": score.grade,
        "score": score.total,
        "signal": _build_signal(dims),
        "weakest_dimension": weakest,
        "reason": _agent_backlog_reason(score.grade, weakest),
        "recommended_mcp_command": _file_action(score),
        "recommended_cli_command": _recommended_cli_command(score.grade, quoted_path),
        "safety_mcp_command": f"edit action=safe file_path='{file_path}'",
        "safety_cli_command": (
            "uv run python -m tree_sitter_analyzer "
            f"{quoted_path} --safe-to-edit --format json"
        ),
        "post_edit_commands": [
            (
                "uv run python -m tree_sitter_analyzer "
                f"{quoted_path} --file-health --format json"
            ),
            "uv run python -m tree_sitter_analyzer --change-impact --format json",
            "uv run pytest -q",
        ],
    }


def _recommended_cli_command(grade: str, quoted_path: str) -> str:
    """Return the CLI command matching the recommended MCP action."""
    command_flag = "--refactor" if grade in {"D", "F"} else "--file-health"
    return (
        "uv run python -m tree_sitter_analyzer "
        f"{quoted_path} {command_flag} --format json"
    )


def _agent_backlog_priority(grade: str) -> str:
    """Return an execution priority for autonomous project-health backlogs."""
    if grade == "F":
        return "critical"
    if grade == "D":
        return "high"
    if grade == "C":
        return "medium"
    return "low"


def _agent_backlog_reason(grade: str, weakest: str) -> str:
    """Explain why project-health queued this file."""
    if grade in {"D", "F"}:
        return f"grade {grade}; run safe-to-edit, then refactor weakest dimension: {weakest}"
    return f"grade {grade}; inspect weakest dimension before deciding whether to refactor: {weakest}"


def _weakest_dimension(dimensions: dict[str, float | None]) -> str:
    """Return the weakest dimension name, or an empty string when unavailable."""
    numeric_dimensions = _numeric_dimensions(dimensions)
    return (
        min(numeric_dimensions, key=lambda k: numeric_dimensions[k])
        if numeric_dimensions
        else ""
    )
