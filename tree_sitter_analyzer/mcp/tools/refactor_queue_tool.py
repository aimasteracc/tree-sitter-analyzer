#!/usr/bin/env python3
"""``health action=refactor_queue`` / ``--refactor-queue`` — RFC-0027 §L8 item 2.

Joins three signals that already exist — health grade, 30-day churn, dead-symbol
density — and ranks files by the priority formula now pinned in
:mod:`tree_sitter_analyzer.refactor_queue`. No new analysis engine: the grades
come from :class:`~tree_sitter_analyzer.health_scorer.HealthScorer`, the dead
symbols from :func:`~tree_sitter_analyzer.dead_code_analyzer.analyze_dead_code`,
and the churn from the ``ast_symbol_activation`` table the indexer already
writes.

Read-only by construction: three reads, zero writes. That matters because this
action lives on the ``health`` facade, which declares ``readOnlyHint=True`` for
every action it exposes.

Honesty rule (CLAUDE.md §11 / RFC-0025 L5 precedent): when the AST index is
absent there is **no** churn signal, and ``log(1 + 0) == 0`` would silently
flatten every priority to zero — a queue of confident nonsense. This tool
returns ``status="CHURN_UNAVAILABLE"`` with an empty queue instead of
fabricating the zeros.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ...refactor_queue import RefactorQueueRow, rank_refactor_queue
from ...utils import setup_logger
from .base_tool import BaseMCPTool, format_summary_line

logger = setup_logger(__name__)

#: Emitted when ``.ast-cache/index.db`` has no churn to report.
CHURN_UNAVAILABLE = "CHURN_UNAVAILABLE"
#: Emitted when the queue was ranked from all three live signals.
STATUS_OK = "OK"

_DEFAULT_TOP_N = 5
_MAX_TOP_N = 50
#: Health-score at most this many churny files. Bounds the cost on a repo with
#: thousands of touched files; the truncation is reported, never hidden.
_MAX_CANDIDATES = 200

_DESCRIPTION = (
    "Top-N prioritized refactor queue: which files to clean up first, ranked "
    "by (1 - health/100) * log(1 + churn_30d) * (dead_ratio + 0.1). Joins the "
    "health grade, the 30-day churn from the AST index, and the dead-symbol "
    "density into one ordered list, each row carrying the weakest dimension "
    "and a concrete action (split / delete dead / extract).\n\n"
    "WHEN TO USE:\n"
    "- Engineering triage: 'what should we refactor next?'\n"
    "- Post-feature cleanup, or pre-sprint planning that needs concrete files\n"
    "\n"
    "WHEN NOT TO USE:\n"
    "- You already know the file — use action=file for a single-file grade\n"
    "- The repo has no git history or no AST index — churn is then absent and "
    "this returns CHURN_UNAVAILABLE rather than a queue of zeros"
)


def _normalize(root: Path, file_path: str) -> str:
    """Return ``file_path`` as a POSIX path relative to ``root`` when possible.

    The three signals disagree on absolute-vs-relative, so the join key has to
    be normalised or every row silently misses.
    """
    raw = Path(file_path)
    try:
        rel = raw.relative_to(root) if raw.is_absolute() else raw
    except ValueError:
        rel = raw
    return rel.as_posix()


def _churn_by_file(root: Path) -> dict[str, int]:
    """Summed ``mod_count_30d`` per file, or ``{}`` when the index is absent."""
    db_path = root / ".ast-cache" / "index.db"
    if not db_path.is_file():
        return {}
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT file_path, SUM(mod_count_30d) AS churn "
            "FROM ast_symbol_activation GROUP BY file_path"
        ).fetchall()
    except sqlite3.Error as exc:
        logger.debug("churn lookup failed: %s", exc)
        return {}
    finally:
        if conn is not None:
            conn.close()
    return {_normalize(root, str(r[0])): int(r[1] or 0) for r in rows if r[0]}


def _symbol_counts(root: Path) -> dict[str, int]:
    """Total indexed symbols per file, or ``{}`` when the index is absent."""
    db_path = root / ".ast-cache" / "index.db"
    if not db_path.is_file():
        return {}
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT file_path, COUNT(*) AS n FROM ast_symbol_rows GROUP BY file_path"
        ).fetchall()
    except sqlite3.Error as exc:
        logger.debug("symbol count lookup failed: %s", exc)
        return {}
    finally:
        if conn is not None:
            conn.close()
    return {_normalize(root, str(r[0])): int(r[1] or 0) for r in rows if r[0]}


def _dead_by_file(root: Path) -> dict[str, int]:
    """Dead-function count per file (transitive flood-fill), ``{}`` on failure."""
    from ...dead_code_analyzer import analyze_dead_code

    try:
        result = analyze_dead_code(
            str(root),
            include_test_files=False,
            include_unused_imports=False,
            include_variables=False,
        )
    except Exception as exc:  # noqa: BLE001 — a signal read must never raise
        logger.debug("dead code analysis failed: %s", exc)
        return {}
    counts: dict[str, int] = {}
    for dead in result.dead_functions:
        key = _normalize(root, dead.function.file_path)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _weakest(dimensions: dict[str, Any]) -> str:
    """Lowest-scoring dimension name, or ``""`` when none are measured."""
    measured = {
        k: v for k, v in (dimensions or {}).items() if isinstance(v, int | float)
    }
    if not measured:
        return ""
    return min(measured, key=lambda k: measured[k])


class RefactorQueueTool(BaseMCPTool):
    """MCP tool behind ``health action=refactor_queue`` / ``--refactor-queue``."""

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_TOP_N,
                    "default": _DEFAULT_TOP_N,
                    "description": (
                        f"How many queue rows to return (default {_DEFAULT_TOP_N}, "
                        f"max {_MAX_TOP_N})."
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": (
                        "Output format: 'toon' (default, token-efficient) or "
                        "'json'. The MCP-toon / CLI-json split is a locked "
                        "design decision (CLAUDE.md §1)."
                    ),
                },
            },
            "additionalProperties": False,
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "refactor_queue",
            "description": _DESCRIPTION,
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        top_n = arguments.get("top_n", _DEFAULT_TOP_N)
        if not isinstance(top_n, int) or isinstance(top_n, bool):
            raise ValueError("top_n must be an integer")
        if not 1 <= top_n <= _MAX_TOP_N:
            raise ValueError(f"top_n must be in [1, {_MAX_TOP_N}], got {top_n}")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        top_n = int(arguments.get("top_n", _DEFAULT_TOP_N))
        output_format = arguments.get("output_format", "toon")
        root = Path(self.project_root)

        churn = _churn_by_file(root)
        # An activation table of zeros is "no signal", not "no churn": every
        # log(1 + 0) term would be 0.0 and the queue would rank on nothing.
        if not any(value > 0 for value in churn.values()):
            return self._unavailable(output_format)

        rows, total_churny = self._collect_rows(root, churn)
        queue = rank_refactor_queue(rows, top_n=top_n)
        return self._respond(queue, len(rows), total_churny, top_n, output_format)

    def _collect_rows(
        self, root: Path, churn: dict[str, int]
    ) -> tuple[list[RefactorQueueRow], int]:
        """Join health + churn + dead-density, churn-first.

        Returns ``(rows, total_churny_files)``.

        Candidates are the churny files, not every file: ``log(1 + 0) == 0``
        means an untouched file can never rank, so scoring the whole project
        would be wasted work. It is also the difference between a usable tool
        and an unusable one — ``HealthScorer.score_project`` scores every file
        with ``fast_dependencies=False``, which rebuilds a project dependency
        graph per file and does not finish on a repo this size. Per-candidate
        ``score_file(fast_dependencies=True)`` is the same grade at a bounded
        cost.
        """
        from ...health_scorer import PROJECT_HEALTH_SOURCE_EXTS, HealthScorer

        candidates = sorted(
            (
                (count, path)
                for path, count in churn.items()
                if count > 0
                and Path(path).suffix.lower() in PROJECT_HEALTH_SOURCE_EXTS
                and (root / path).is_file()
            ),
            key=lambda pair: (-pair[0], pair[1]),
        )
        total_churny = len(candidates)
        if total_churny > _MAX_CANDIDATES:
            # Truncation is by churn descending, reported, never hidden:
            # log(1 + churn) is monotonic in churn, so this is the right
            # prefix to keep when only one of the three factors is known yet.
            candidates = candidates[:_MAX_CANDIDATES]

        dead = _dead_by_file(root)
        totals = _symbol_counts(root)
        scorer = HealthScorer()

        rows: list[RefactorQueueRow] = []
        for file_churn, key in candidates:
            try:
                score = scorer.score_file(str(root / key), fast_dependencies=True)
            except Exception as exc:  # noqa: BLE001 — one bad file, not a crash
                logger.debug("health scoring failed for %s: %s", key, exc)
                continue
            rows.append(
                RefactorQueueRow(
                    file_path=key,
                    grade=score.grade,
                    health_score=float(score.total),
                    weakest_dimension=_weakest(getattr(score, "dimensions", {})),
                    churn_30d=file_churn,
                    dead_symbols=dead.get(key, 0),
                    total_symbols=totals.get(key, 0),
                )
            )
        return rows, total_churny

    def _unavailable(self, output_format: str) -> dict[str, Any]:
        """No churn signal → an explicit status, never a queue of zeros."""
        from ..utils.format_helper import apply_toon_format_to_response

        summary_line = format_summary_line(
            "refactor_queue", f"status={CHURN_UNAVAILABLE}", "candidates=0"
        )
        next_step = (
            "No 30-day churn is readable from .ast-cache/index.db, so the "
            "queue cannot be ranked. Run `index action=build` (CLI: "
            "--build-project-index) on a repo with git history, then retry."
        )
        return apply_toon_format_to_response(
            {
                "success": True,
                "verdict": "WARN",
                "status": CHURN_UNAVAILABLE,
                "queue": [],
                "candidate_count": 0,
                "summary_line": summary_line,
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": next_step,
                    "verdict": "WARN",
                },
            },
            output_format,
        )

    def _respond(
        self,
        queue: list[dict[str, Any]],
        candidate_count: int,
        churny_file_count: int,
        top_n: int,
        output_format: str,
    ) -> dict[str, Any]:
        from ..utils.format_helper import apply_toon_format_to_response

        head = queue[0]["file_path"] if queue else "n/a"
        summary_line = format_summary_line(
            "refactor_queue",
            f"status={STATUS_OK}",
            f"candidates={candidate_count}",
            f"returned={len(queue)}",
            f"head={head}",
        )
        next_step = (
            f"health action=file file_path='{head}' to see which dimension "
            "dragged the grade down, then edit action=safe before touching it."
            if queue
            else "No churny file scored above zero — nothing to queue."
        )
        return apply_toon_format_to_response(
            {
                "success": True,
                "verdict": "INFO",
                "status": STATUS_OK,
                "formula": (
                    "(1 - health_score/100) * log(1 + churn_30d) * "
                    "(dead_symbols/total_symbols + 0.1)"
                ),
                "top_n": top_n,
                "candidate_count": candidate_count,
                "churny_file_count": churny_file_count,
                "candidate_cap": _MAX_CANDIDATES,
                "truncated": churny_file_count > _MAX_CANDIDATES,
                "queue": queue,
                "summary_line": summary_line,
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": next_step,
                    "verdict": "INFO",
                },
            },
            output_format,
        )
