#!/usr/bin/env python3
"""decision_journal MCP tool (r37fG phase 1b).

Wraps :class:`~tree_sitter_analyzer.decision_journal.DecisionJournal` in
the canonical MCP envelope so agents can record + query architectural
decisions across sessions. Storage lives at
``<project_root>/.ast-cache/decision_journal.db``.

Why this exists
---------------
Every other tool in the registry is **stateless across sessions**.
The agent that touches the codebase tomorrow doesn't remember why
yesterday's agent picked ``fd`` over ``find`` or why the route cache
keys on content hash. ``decision_journal`` is the only mechanism that
persists *reasoning* across sessions — the agent's institutional
memory. No competitor (Cursor, Aider, CodeGraph, Cline) has this.
"""

from __future__ import annotations

from typing import Any

from ...decision_journal import (
    _LEGAL_VERDICTS,
    DecisionJournal,
    DecisionRecord,
    JournalValidationError,
)
from ..utils.format_helper import apply_toon_format_to_response
from ._validators import invalid_enum_error
from .base_tool import BaseMCPTool, _canonicalize_verdict, mirror_summary_line

_VALID_MODES = ("record", "get", "search", "supersede")


def _record_to_envelope_dict(rec: DecisionRecord) -> dict[str, Any]:
    """Coerce a frozen record to the canonical envelope shape."""
    return rec.to_dict()


def _summary_line_for_mode(mode: str, count: int | None, rec_id: str | None) -> str:
    """Produce a single agent-readable headline."""
    if mode == "record":
        return f"decision_journal recorded id={rec_id}"
    if mode == "get":
        if rec_id is None:
            return "decision_journal get not_found"
        return f"decision_journal got id={rec_id}"
    if mode == "search":
        return f"decision_journal search matched={count or 0}"
    if mode == "supersede":
        if rec_id is None:
            return "decision_journal supersede not_found"
        return f"decision_journal superseded id={rec_id}"
    return f"decision_journal mode={mode}"


def _next_step_for_mode(mode: str, verdict: str) -> str:
    """Actionable hint embedded in agent_summary.next_step."""
    if verdict == "ERROR":
        return "Fix the input and retry."
    if verdict == "NOT_FOUND":
        return "Re-check the id, or call search(query=…) for adjacent decisions."
    if mode == "record":
        return (
            "Decision recorded. Surface this verdict in any future edits "
            "that touch the same scope_paths."
        )
    if mode == "search":
        return (
            "Review matches before proceeding. If any are CAUTION / REVIEW / "
            "UNSAFE / WARN / ERROR, surface them verbatim to the user — do "
            "NOT reframe as SAFE."
        )
    return "Use search to locate related decisions before editing."


class DecisionJournalTool(BaseMCPTool):
    """MCP tool exposing the decision journal across record/get/search/supersede."""

    def __init__(self, project_root: str | None = None) -> None:
        self._journal: DecisionJournal | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        # Invalidate cached journal when the project root rebinds.
        self._journal = None

    def _get_journal(self) -> DecisionJournal:
        if self._journal is None:
            root = self.project_root or "."
            self._journal = DecisionJournal(root)
        return self._journal

    # ------------------------------------------------------------------
    # Tool definition
    # ------------------------------------------------------------------

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "decision_journal",
            "description": (
                "Persistent journal of architectural decisions. Records "
                "every decision with title, rationale, verdict, scope, "
                "alternatives considered, related symbols, and tags. The "
                "only registered MCP tool that persists *reasoning* across "
                "sessions — no competitor exposes this. "
                "Modes: record (new entry), get (by id), search "
                "(substring + verdict + path filter), supersede (link "
                "old→new). Storage: "
                "<project_root>/.ast-cache/decision_journal.db.\n\n"
                "WHEN TO USE:\n"
                "- BEFORE proposing a refactor: call search(query=…, "
                "path_scope=…) to find any recorded decision that affects "
                "the same code. Settled decisions should NOT be re-litigated.\n"
                "- AFTER landing a non-trivial design choice: call record() "
                "with the rationale + alternatives so the next agent inherits "
                "the reasoning.\n"
                "- WHEN reversing course: call supersede(old_id, new_id) so "
                "the chain is auditable.\n\n"
                "WHEN NOT TO USE:\n"
                "- Do NOT use this to record TODOs or feature requests — "
                "those belong in an issue tracker. The journal is for "
                "settled decisions WITH rationale.\n"
                "- Do NOT use this for short-lived task state — the journal "
                "is append-mostly; rows are not pruned by design.\n\n"
                "VERDICT INTEGRITY: agent_summary.verdict on this tool "
                "reflects the recorded decision's verdict (for record/get/"
                "supersede) or NOT_FOUND when no match (for get / search "
                "with 0 results) — NOT the calling user's stated goal. If a "
                "search returns a REVIEW/UNSAFE/WARN decision relevant to "
                "the current change, the calling agent MUST surface that "
                "verdict verbatim — do NOT reframe it as SAFE to keep the "
                "user moving. Legal vocabulary: SAFE / CAUTION / REVIEW / "
                "UNSAFE / INFO / WARN / ERROR / NOT_FOUND."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": list(_VALID_MODES),
                    "description": "record / get / search / supersede",
                    "default": "search",
                },
                "id": {
                    "type": "string",
                    "description": "Decision id (required for get / supersede.old_id)",
                },
                "new_id": {
                    "type": "string",
                    "description": "Replacement decision id (required for supersede)",
                },
                "title": {"type": "string"},
                "rationale": {"type": "string"},
                "verdict": {
                    "type": "string",
                    "enum": sorted(_LEGAL_VERDICTS),
                },
                "scope_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "alternatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["option", "why_rejected"],
                    },
                },
                "related_symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "query": {"type": "string"},
                "verdict_filter": {
                    "type": "string",
                    "enum": sorted(_LEGAL_VERDICTS),
                },
                "path_scope": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "search")
        if mode not in _VALID_MODES:
            raise invalid_enum_error("mode", mode, list(_VALID_MODES))
        if mode == "record":
            if not arguments.get("title") or not arguments.get("rationale"):
                raise ValueError("record mode requires title and rationale")
            if not arguments.get("verdict"):
                raise ValueError("record mode requires verdict")
        if mode == "get" and not arguments.get("id"):
            raise ValueError("get mode requires id")
        if mode == "supersede":
            if not arguments.get("id") or not arguments.get("new_id"):
                raise ValueError("supersede mode requires id and new_id")
        return True

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "search")
        output_format = arguments.get("output_format", "toon")
        journal = self._get_journal()

        try:
            payload = await self._dispatch_mode(mode, arguments, journal)
        except JournalValidationError as exc:
            return self._error_envelope(mode, str(exc), output_format)

        return apply_toon_format_to_response(payload, output_format)

    async def _dispatch_mode(
        self,
        mode: str,
        arguments: dict[str, Any],
        journal: DecisionJournal,
    ) -> dict[str, Any]:
        if mode == "record":
            return self._mode_record(arguments, journal)
        if mode == "get":
            return self._mode_get(arguments, journal)
        if mode == "search":
            return self._mode_search(arguments, journal)
        if mode == "supersede":
            return self._mode_supersede(arguments, journal)
        # Defensive; validate_arguments should have caught this.
        raise ValueError(f"Invalid mode: {mode}")

    def _mode_record(
        self, arguments: dict[str, Any], journal: DecisionJournal
    ) -> dict[str, Any]:
        rec = journal.record(
            title=arguments["title"],
            rationale=arguments["rationale"],
            verdict=arguments["verdict"],
            scope_paths=arguments.get("scope_paths"),
            alternatives=arguments.get("alternatives"),
            related_symbols=arguments.get("related_symbols"),
            tags=arguments.get("tags"),
        )
        verdict = _canonicalize_verdict(rec.verdict)
        summary_line = _summary_line_for_mode("record", None, rec.id)
        envelope: dict[str, Any] = {
            "success": True,
            "mode": "record",
            "decision": _record_to_envelope_dict(rec),
            "summary_line": summary_line,
            "verdict": verdict,
            "agent_summary": {
                "summary_line": summary_line,
                "verdict": verdict,
                "next_step": _next_step_for_mode("record", verdict),
            },
        }
        return mirror_summary_line(envelope)

    def _mode_get(
        self, arguments: dict[str, Any], journal: DecisionJournal
    ) -> dict[str, Any]:
        rec = journal.get(arguments["id"])
        if rec is None:
            verdict = "NOT_FOUND"
            summary_line = _summary_line_for_mode("get", None, None)
            envelope: dict[str, Any] = {
                "success": True,
                "mode": "get",
                "decision": None,
                "summary_line": summary_line,
                "verdict": verdict,
                "agent_summary": {
                    "summary_line": summary_line,
                    "verdict": verdict,
                    "next_step": _next_step_for_mode("get", verdict),
                },
            }
            return mirror_summary_line(envelope)
        verdict = _canonicalize_verdict(rec.verdict)
        summary_line = _summary_line_for_mode("get", None, rec.id)
        envelope = {
            "success": True,
            "mode": "get",
            "decision": _record_to_envelope_dict(rec),
            "summary_line": summary_line,
            "verdict": verdict,
            "agent_summary": {
                "summary_line": summary_line,
                "verdict": verdict,
                "next_step": _next_step_for_mode("get", verdict),
            },
        }
        return mirror_summary_line(envelope)

    def _mode_search(
        self, arguments: dict[str, Any], journal: DecisionJournal
    ) -> dict[str, Any]:
        results = journal.search(
            query=arguments.get("query"),
            verdict_filter=arguments.get("verdict_filter"),
            path_scope=arguments.get("path_scope"),
            limit=int(arguments.get("limit", 20)),
        )
        if not results:
            verdict = "NOT_FOUND"
        else:
            # If any matched verdict is itself UNSAFE/WARN/REVIEW/CAUTION/ERROR,
            # propagate that as the envelope verdict — the integrity contract
            # in the description tells the LLM to surface this verbatim.
            risky = {"UNSAFE", "WARN", "REVIEW", "CAUTION", "ERROR"}
            if any(r.verdict in risky for r in results):
                # Pick the strongest signal in priority order.
                priority = ["UNSAFE", "ERROR", "WARN", "REVIEW", "CAUTION"]
                seen = {r.verdict for r in results}
                verdict = next((v for v in priority if v in seen), "REVIEW")
            else:
                verdict = "INFO"
        summary_line = _summary_line_for_mode("search", len(results), None)
        envelope: dict[str, Any] = {
            "success": True,
            "mode": "search",
            "count": len(results),
            "decisions": [_record_to_envelope_dict(r) for r in results],
            "summary_line": summary_line,
            "verdict": verdict,
            "agent_summary": {
                "summary_line": summary_line,
                "verdict": verdict,
                "next_step": _next_step_for_mode("search", verdict),
            },
        }
        return mirror_summary_line(envelope)

    def _mode_supersede(
        self, arguments: dict[str, Any], journal: DecisionJournal
    ) -> dict[str, Any]:
        old_id = arguments["id"]
        new_id = arguments["new_id"]
        rec = journal.supersede(old_id, new_id)
        if rec is None:
            verdict = "NOT_FOUND"
            summary_line = _summary_line_for_mode("supersede", None, None)
            envelope: dict[str, Any] = {
                "success": True,
                "mode": "supersede",
                "decision": None,
                "summary_line": summary_line,
                "verdict": verdict,
                "agent_summary": {
                    "summary_line": summary_line,
                    "verdict": verdict,
                    "next_step": _next_step_for_mode("supersede", verdict),
                },
            }
            return mirror_summary_line(envelope)
        verdict = _canonicalize_verdict(rec.verdict)
        summary_line = _summary_line_for_mode("supersede", None, rec.id)
        envelope = {
            "success": True,
            "mode": "supersede",
            "decision": _record_to_envelope_dict(rec),
            "summary_line": summary_line,
            "verdict": verdict,
            "agent_summary": {
                "summary_line": summary_line,
                "verdict": verdict,
                "next_step": _next_step_for_mode("supersede", verdict),
            },
        }
        return mirror_summary_line(envelope)

    def _error_envelope(
        self, mode: str, message: str, output_format: str
    ) -> dict[str, Any]:
        summary_line = f"decision_journal error: {message[:80]}"
        envelope: dict[str, Any] = {
            "success": False,
            "mode": mode,
            "error": message,
            "summary_line": summary_line,
            "verdict": "ERROR",
            "agent_summary": {
                "summary_line": summary_line,
                "verdict": "ERROR",
                "next_step": "Fix the input and retry.",
            },
        }
        return apply_toon_format_to_response(
            mirror_summary_line(envelope), output_format
        )
