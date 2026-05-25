"""Claude API runner for a single benchmark question against one arm.

# TODO: replace dry-run stub with real Claude API calls once harness is validated

Currently operates in **dry-run / stub** mode:
  - Builds the full prompt that WOULD be sent (system + user message)
  - Writes it to results_dir/raw/<run_id>_prompt.txt
  - Returns a RunRecord with answer="DRY_RUN", all token counts=0, tool_calls=0
  - Never makes a real network call

This lets the harness structure, file layout, YAML loading, and CLI wiring be
validated end-to-end before live API credentials are needed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import RunConfig


def _make_run_id(question_id: str, arm_id: str, repeat: int) -> str:
    """Build a deterministic run identifier.

    Formula mirrors RunRecord.make_id in schemas.py so run IDs are consistent
    whether generated here or from the schema layer.
    """
    return f"{question_id}__{arm_id}__{repeat:02d}"


def _build_full_prompt(
    run_config: RunConfig,
    question_prompt: str,
) -> str:
    """Assemble the full prompt string that would be sent to Claude.

    Structure:
      <system_prompt>

      <extra_context>

      Question: <question_prompt>
    """
    parts: list[str] = [run_config.system_prompt]
    if run_config.extra_context:
        parts.append(run_config.extra_context)
    parts.append(f"Question: {question_prompt}")
    return "\n\n".join(parts)


def run_one(
    question_id: str,
    question_prompt: str,
    arm_id: str,
    repo_path: Path,
    repeat: int,
    run_config: RunConfig,
    results_dir: Path,
    timeout_seconds: int = 1200,
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Run one benchmark trial.  Returns a dict matching RunRecord schema.

    Writes the prompt to  results_dir/raw/<run_id>_prompt.txt
    Appends the run record to results_dir/runs.jsonl

    Parameters
    ----------
    question_id:
        Stable identifier for the question (e.g. "q01_cold_start").
    question_prompt:
        The verbatim question text shown to Claude.
    arm_id:
        Which benchmark arm is being tested (e.g. "native-only", "tsa-warm").
    repo_path:
        Absolute path to the repository under test.
    repeat:
        Zero-based repeat index for this (question, arm) pair.
    run_config:
        RunConfig built by the adapter for this run.
    results_dir:
        Root directory under which raw/ and runs.jsonl are written.
    timeout_seconds:
        Maximum wall-clock seconds allowed for the Claude session.
        Unused in dry-run mode but stored in the record for future reference.
    model:
        Claude model ID to invoke.  Stored in record; unused in dry-run mode.
    """
    run_id = _make_run_id(question_id, arm_id, repeat)
    started_at = datetime.now(timezone.utc).isoformat()
    started_perf = time.perf_counter()

    # ------------------------------------------------------------------
    # Build the full prompt
    # ------------------------------------------------------------------
    full_prompt = _build_full_prompt(run_config, question_prompt)

    # ------------------------------------------------------------------
    # Write prompt to disk
    # ------------------------------------------------------------------
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = raw_dir / f"{run_id}_prompt.txt"
    prompt_path.write_text(full_prompt, encoding="utf-8")

    # ------------------------------------------------------------------
    # Dry-run stub  (replace this block with real API call when validated)
    # ------------------------------------------------------------------
    answer = "DRY_RUN"
    tokens_in = 0
    tokens_out = 0
    tool_calls = 0
    error = None
    # ------------------------------------------------------------------

    ended_at = datetime.now(timezone.utc).isoformat()
    elapsed_seconds = round(time.perf_counter() - started_perf, 4)

    record: dict = {
        "run_id": run_id,
        "question_id": question_id,
        "arm_id": arm_id,
        "repo_path": str(repo_path),
        "repeat": repeat,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": elapsed_seconds,
        "answer": answer,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tool_calls": tool_calls,
        "error": error,
        "prompt_file": str(prompt_path),
    }

    # ------------------------------------------------------------------
    # Append record as JSONL
    # ------------------------------------------------------------------
    runs_jsonl = results_dir / "runs.jsonl"
    with runs_jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record
