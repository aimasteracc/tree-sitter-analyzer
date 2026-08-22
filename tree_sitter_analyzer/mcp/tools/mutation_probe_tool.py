#!/usr/bin/env python3
"""``edit action=mutation_probe`` inner tool (RFC-0029).

Asks: "does this test constrain this code?" by applying exactly one mutation
at a specified code location and checking whether the test detects it.

This tool is NOT read-only: it spawns a subprocess that executes test code.
It therefore lives on the ``edit`` facade (where ``readOnlyHint=False``),
not on the ``health`` facade (which asserts ``readOnlyHint=True``).

The action name is ``mutation_probe`` (not ``constrains``) because
``difflib.get_close_matches("constrains", existing_actions, cutoff=0.6)``
returns ``"constraints"`` at ratio 0.952 — a one-character typo would
silently route to the wrong action.  ``mutation_probe`` has no such
collision.
"""

from __future__ import annotations

from typing import Any

from .base_tool import BaseMCPTool

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "test_node_id": {
            "type": "string",
            "description": (
                "Fully-qualified pytest node id, e.g. "
                "'tests/unit/latency/test_latency.py::test_p50_positive'."
            ),
        },
        "code_location": {
            "type": "string",
            "description": (
                "Code location to mutate: 'path/to/file.py:N' where N is a "
                "1-indexed line number relative to the project root."
            ),
        },
        "timeout": {
            "type": "number",
            "description": "Wall-clock budget in seconds (default 60).",
            "default": 60.0,
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "description": "Output format (default: toon for MCP callers).",
            "default": "toon",
        },
    },
    "required": ["test_node_id", "code_location"],
    "additionalProperties": False,
}


class MutationProbeTool(BaseMCPTool):
    """Inner tool for ``edit action=mutation_probe``."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "mutation_probe",
            "description": (
                "Ask whether a specific test constrains a specific line of code "
                "by applying one mutation from a closed set and checking if the "
                "test goes red for an assertion-derived reason. "
                "Verdict: 'constrains' | 'does_not_constrain' | 'unknown'. "
                "Params: test_node_id (required), code_location 'file.py:N' "
                "(required), timeout (default 60 s), output_format."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                # NOT read-only: spawns a subprocess that executes test code.
                "readOnlyHint": False,
                "destructiveHint": False,  # never writes to the working tree
                "idempotentHint": False,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        for required in ("test_node_id", "code_location"):
            val = arguments.get(required)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"'{required}' is required and must be a non-empty string"
                )
        loc = arguments["code_location"]
        if ":" not in loc:
            raise ValueError(
                f"code_location must be 'file.py:N' (line number); got {loc!r}"
            )
        timeout = arguments.get("timeout", 60.0)
        if not isinstance(timeout, (int, float)) or float(timeout) <= 0:
            raise ValueError("timeout must be a positive number")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        from ...mutation_probe import probe

        test_node_id: str = arguments["test_node_id"]
        code_location: str = arguments["code_location"]
        timeout: float = float(arguments.get("timeout", 60.0))
        output_format: str = arguments.get("output_format", "toon")
        project_root = self.project_root or "."

        result = probe(
            test_node_id=test_node_id,
            code_location=code_location,
            project_root=project_root,
            timeout=timeout,
        )

        verdict_upper = result.verdict.upper().replace("_", " ")
        summary_line = (
            f"mutation_probe: {result.verdict} — {result.mutation}"
            if result.verdict == "constrains"
            else f"mutation_probe: {result.verdict}"
            + (f" ({result.reason})" if result.reason else "")
        )

        response: dict[str, Any] = {
            "success": True,
            "verdict": verdict_upper,
            "summary_line": summary_line,
            **result.to_dict(),
            "agent_summary": {
                "verdict": verdict_upper,
                "summary_line": summary_line,
                "next_step": _next_step(result.verdict, result.reason),
            },
        }

        if output_format == "toon":
            from ..utils.format_helper import apply_toon_format_to_response

            return apply_toon_format_to_response(response, output_format)
        return response


def _next_step(verdict: str, reason: str | None) -> str:
    if verdict == "constrains":
        return (
            "The test detects this mutation — it provides some constraint. "
            "This does NOT mean the test is complete; see the false-negative "
            "profile for what the mutation set does not cover."
        )
    if verdict == "does_not_constrain":
        return (
            "The test did not detect the mutation — it asserts nothing about "
            "this code path. Consider adding an exact assertion that would "
            "go red if this mutation were applied."
        )
    # unknown
    subcodes = {
        "BASELINE_NOT_GREEN": "Fix the test first (it is failing without any mutation).",
        "NO_INVERTIBLE_BRANCH": (
            "No applicable mutation in the closed set exists at this line. "
            "Try a nearby line with an if/while/comparison/return/call."
        ),
        "NOT_ISOLABLE": (
            "The test node was not collected. Check the node id spelling and "
            "ensure no marker filter deselects it."
        ),
        "MUTATED_RUN_CRASHED": (
            "The mutation caused a non-assertion crash (ImportError, "
            "AttributeError, …). A crash is not detection; the test does "
            "not constrain this code."
        ),
        "TIMEOUT": "The probe exceeded the timeout budget.",
        "INVALID_LOCATION": "Correct the code_location format to 'file.py:N'.",
        "FILE_NOT_FOUND": "Verify the file path is relative to the project root.",
    }
    return subcodes.get(reason or "", "Check the 'reason' field for details.")
