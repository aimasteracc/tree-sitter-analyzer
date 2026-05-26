"""Answer quality evaluator for the CodeGraph comparison benchmark harness.

Evaluates a RunRecord against its QuestionSpec by:
  1. Checking cited files exist in the repo (file citation check)
  2. Checking expected key points appear in the answer (coverage check)
  3. Calling an LLM (Claude Haiku) to score semantic quality
  4. Applying auto-penalties and computing an overall score
  5. Appending an EvalRecord to results/evals.jsonl

Public API
----------
    evaluate_run(run, question, repo_path, model, dry_run) -> dict
    evaluate_all(runs_jsonl, questions_yaml, prepared_manifest, results_dir,
                 model, dry_run) -> list[dict]

CLI
---
    python benchmarks/codegraph_compare/evaluate.py \\
        --runs results/runs.jsonl \\
        --questions questions.yaml \\
        --manifest results/prepared_repos.json \\
        --dry-run

Created: 2026-05-26
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# File extensions recognised when scanning citation strings for path fragments
_CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".swift",
        ".kt",
        ".cpp",
        ".c",
        ".h",
        ".cs",
        ".rb",
        ".php",
        ".sh",
        ".bash",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".cfg",
        ".ini",
        ".sql",
        ".md",
    }
)

# Prompts directory (sibling of this file)
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_EVALUATOR_PROMPT_FILE = _PROMPTS_DIR / "evaluator.md"

# Default LLM evaluator prompt (used when prompts/evaluator.md is absent)
_DEFAULT_EVALUATOR_PROMPT = """\
You are evaluating the quality of an AI assistant's answer to a code-intelligence question.

## Question
{question}

## Expected key points (the answer should cover these)
{key_points}

## Answer under evaluation
{answer}

---

Score the answer on each dimension from 1 (very poor) to 5 (excellent):

1. **correctness** — Are the facts stated in the answer accurate and consistent with what you
   would expect from a correct code-intelligence query?
2. **completeness** — Does the answer cover all the expected key points?
3. **citation_quality** — Does the answer cite specific files, line numbers, or symbols that
   support each claim? Are the citations concrete and useful?
4. **hallucination_risk** — How likely is it that the answer contains invented or fabricated
   details? (5 = very unlikely to hallucinate; 1 = very likely to hallucinate)

Return ONLY a JSON object in this exact format — no markdown fences, no extra text:

{
  "correctness": <int 1-5>,
  "completeness": <int 1-5>,
  "citation_quality": <int 1-5>,
  "hallucination_risk": <int 1-5>,
  "reasoning": "<one or two sentences explaining the scores>"
}
"""

# Score to use for all dimensions when a run errored or was a dry-run
_ERROR_SCORE = 0
_DRY_RUN_SCORE = 0

# Safe default scores when LLM response cannot be parsed
_SAFE_DEFAULT_SCORES: dict[str, Any] = {
    "correctness": 3,
    "completeness": 3,
    "citation_quality": 3,
    "hallucination_risk": 3,
    "reasoning": "LLM response could not be parsed; safe defaults used.",
}


# ---------------------------------------------------------------------------
# Stderr helper (keeps stdout machine-readable)
# ---------------------------------------------------------------------------


def _stderr(*args: Any, **kwargs: Any) -> None:
    print(*args, **kwargs, file=sys.stderr)


# ---------------------------------------------------------------------------
# Lazy anthropic import guard
# ---------------------------------------------------------------------------


def _require_anthropic() -> Any:
    """Return the ``anthropic`` module, raising a clear error if not installed."""
    try:
        import anthropic

        return anthropic
    except ImportError as exc:
        raise RuntimeError(
            "The 'anthropic' Python SDK is required for LLM evaluation. "
            "Install it with:  pip install anthropic\n"
            "Or run with --dry-run to skip LLM evaluation."
        ) from exc


# ---------------------------------------------------------------------------
# Step 1: File citation check
# ---------------------------------------------------------------------------


def _extract_cited_paths(citations: list[str]) -> list[str]:
    """Extract strings from citations that look like file paths.

    A candidate path must contain a ``/`` or end with a recognised code
    extension.  Inline path fragments like ``src/foo.py:42`` are stripped
    of the trailing ``:42`` suffix.
    """
    candidates: list[str] = []
    for citation in citations:
        # Split on whitespace and common delimiters to find embedded paths
        for token in re.split(r'[\s,;"\']', citation):
            token = token.strip()
            if not token:
                continue
            # Strip trailing colon+digits (e.g. "src/foo.py:42" → "src/foo.py")
            token = re.sub(r":\d+$", "", token)
            # A plausible path either contains "/" or ends in a code extension
            suffix = Path(token).suffix.lower()
            if "/" in token or suffix in _CODE_EXTENSIONS:
                # Strip a leading "./" for consistent lookup
                if token.startswith("./"):
                    token = token[2:]
                candidates.append(token)
    return candidates


def _check_citations(
    citations: list[str],
    repo_path: Path,
) -> tuple[list[str], list[str]]:
    """Check citation strings against the file system.

    Returns ``(good_citations, bad_citations)`` where each element is the
    extracted path string.  A path is "bad" if it doesn't exist inside
    ``repo_path``.
    """
    good: list[str] = []
    bad: list[str] = []

    for path_str in _extract_cited_paths(citations):
        candidate = repo_path / path_str
        if candidate.exists():
            good.append(path_str)
        else:
            bad.append(path_str)

    return good, bad


# ---------------------------------------------------------------------------
# Step 2: Key point coverage check
# ---------------------------------------------------------------------------


def _check_key_points(
    answer: str,
    expected_key_points: list[str],
) -> tuple[list[str], list[str]]:
    """Return ``(covered_points, missing_points)`` based on case-insensitive
    substring matching of each expected key point in the answer text.
    """
    answer_lower = answer.lower()
    covered: list[str] = []
    missing: list[str] = []
    for point in expected_key_points:
        if point.lower() in answer_lower:
            covered.append(point)
        else:
            missing.append(point)
    return covered, missing


# ---------------------------------------------------------------------------
# Step 3: LLM evaluation
# ---------------------------------------------------------------------------


def _build_eval_prompt(
    question_text: str,
    expected_key_points: list[str],
    answer: str,
) -> str:
    """Build the full evaluation prompt string."""
    if _EVALUATOR_PROMPT_FILE.is_file():
        template = _EVALUATOR_PROMPT_FILE.read_text(encoding="utf-8")
    else:
        template = _DEFAULT_EVALUATOR_PROMPT

    key_points_block = "\n".join(f"- {p}" for p in expected_key_points)
    return template.format(
        question=question_text,
        key_points=key_points_block,
        answer=answer,
    )


def _call_llm(
    prompt: str,
    model: str,
) -> dict[str, Any]:
    """Call the Claude API and parse the returned JSON scores.

    Returns a dict with keys: correctness, completeness, citation_quality,
    hallucination_risk, reasoning.

    Falls back to _SAFE_DEFAULT_SCORES on any parse or API error.
    """
    anthropic = _require_anthropic()
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        _stderr(f"[evaluate] LLM API call failed: {exc}")
        result = dict(_SAFE_DEFAULT_SCORES)
        result["reasoning"] = f"LLM API call failed: {exc}"
        return result

    raw_text = response.content[0].text if response.content else ""

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract a JSON object substring as a fallback
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                _stderr(f"[evaluate] Could not parse LLM JSON response: {raw_text!r}")
                result = dict(_SAFE_DEFAULT_SCORES)
                result["reasoning"] = (
                    "LLM response JSON unparseable; safe defaults used."
                )
                return result
        else:
            _stderr(f"[evaluate] No JSON object found in LLM response: {raw_text!r}")
            result = dict(_SAFE_DEFAULT_SCORES)
            result["reasoning"] = (
                "LLM response contained no JSON object; safe defaults used."
            )
            return result

    scores: dict[str, Any] = {}
    for key in (
        "correctness",
        "completeness",
        "citation_quality",
        "hallucination_risk",
    ):
        raw_val = parsed.get(key, _SAFE_DEFAULT_SCORES[key])
        try:
            scores[key] = max(1, min(5, int(raw_val)))
        except (TypeError, ValueError):
            scores[key] = _SAFE_DEFAULT_SCORES[key]

    scores["reasoning"] = str(
        parsed.get("reasoning", _SAFE_DEFAULT_SCORES["reasoning"])
    )
    return scores


# ---------------------------------------------------------------------------
# Step 4: Apply auto-penalties and compute overall
# ---------------------------------------------------------------------------


def _apply_penalties(
    scores: dict[str, Any],
    bad_citations: list[str],
    missing_key_points: list[str],
    total_key_points: int,
) -> dict[str, Any]:
    """Return a new scores dict with caps applied.

    Rules:
    - bad_citations non-empty → cap citation_quality at 3
    - >50% of key points missing → cap completeness at 2
    """
    result = dict(scores)

    if bad_citations and result["citation_quality"] > 3:
        result["citation_quality"] = 3

    if total_key_points > 0:
        missing_ratio = len(missing_key_points) / total_key_points
        if missing_ratio > 0.5 and result["completeness"] > 2:
            result["completeness"] = 2

    return result


def _compute_overall(scores: dict[str, Any]) -> float:
    """Compute the mean of the four scored dimensions."""
    keys = ("correctness", "completeness", "citation_quality", "hallucination_risk")
    total: int = sum(scores[k] for k in keys)
    return round(total / len(keys), 4)


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------


def _append_jsonl(path: Path, record: dict) -> None:
    """Append a single JSON record to a JSONL file, creating it if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_run(
    run: dict,
    question: dict,
    repo_path: Path,
    model: str = "claude-haiku-4-5-20251001",
    dry_run: bool = False,
    results_dir: Path | None = None,
) -> dict:
    """Evaluate one RunRecord against its QuestionSpec.

    Parameters
    ----------
    run:
        A RunRecord dict loaded from runs.jsonl.
    question:
        A QuestionSpec dict from questions.yaml.
    repo_path:
        Local path to the cloned repository.
    model:
        Claude model ID to use for LLM evaluation.
    dry_run:
        If True, skip the LLM call and return dummy scores (safe for CI).
    results_dir:
        Directory to append evals.jsonl to.  If None the record is returned
        but not persisted.

    Returns
    -------
    dict
        An EvalRecord with keys:
          run_id, question_id, arm_id, repo_path,
          correctness, completeness, citation_quality, hallucination_risk,
          overall, bad_citations, missing_key_points,
          reasoning, evaluated_with_llm, eval_model
    """
    try:
        return _evaluate_run_inner(
            run=run,
            question=question,
            repo_path=repo_path,
            model=model,
            dry_run=dry_run,
            results_dir=results_dir,
        )
    except Exception as exc:  # noqa: BLE001
        _stderr(
            f"[evaluate] Unexpected error evaluating {run.get('run_id', '?')}: {exc}"
        )
        record = _minimal_error_record(run, question, str(exc))
        if results_dir is not None:
            _append_jsonl(results_dir / "evals.jsonl", record)
        return record


def _evaluate_run_inner(
    run: dict,
    question: dict,
    repo_path: Path,
    model: str,
    dry_run: bool,
    results_dir: Path | None,
) -> dict:
    run_id = run.get("run_id", "")
    question_id = question.get("id", run.get("question_id", ""))
    arm_id = run.get("arm_id", "")
    run_repo_path = run.get("repo_path", str(repo_path))

    # ------------------------------------------------------------------
    # Fast-path: failed or dry-run runs
    # ------------------------------------------------------------------

    if run.get("error"):
        record = _minimal_error_record(
            run,
            question,
            f"run failed: {run['error']}",
        )
        if results_dir is not None:
            _append_jsonl(results_dir / "evals.jsonl", record)
        return record

    answer = run.get("answer", "")
    if answer == "DRY_RUN":
        record = _build_record(
            run_id=run_id,
            question_id=question_id,
            arm_id=arm_id,
            repo_path=run_repo_path,
            correctness=_DRY_RUN_SCORE,
            completeness=_DRY_RUN_SCORE,
            citation_quality=_DRY_RUN_SCORE,
            hallucination_risk=_DRY_RUN_SCORE,
            overall=0.0,
            bad_citations=[],
            missing_key_points=[],
            reasoning="dry run",
            evaluated_with_llm=False,
            eval_model=model,
        )
        if results_dir is not None:
            _append_jsonl(results_dir / "evals.jsonl", record)
        return record

    # ------------------------------------------------------------------
    # Step 1: File citation check
    # ------------------------------------------------------------------

    citations: list[str] = run.get("citations", [])
    _good_citations, bad_citations = _check_citations(citations, repo_path)

    # ------------------------------------------------------------------
    # Step 2: Key point coverage check
    # ------------------------------------------------------------------

    expected_key_points: list[str] = question.get("expected_key_points", [])
    _covered, missing_key_points = _check_key_points(answer, expected_key_points)

    # ------------------------------------------------------------------
    # Step 3: LLM evaluation (or dry-run stub)
    # ------------------------------------------------------------------

    if dry_run:
        scores: dict[str, Any] = {
            "correctness": 3,
            "completeness": 3,
            "citation_quality": 3,
            "hallucination_risk": 3,
            "reasoning": "dry_run=True; LLM evaluation skipped.",
        }
        evaluated_with_llm = False
    else:
        question_text = question.get("question", question.get("prompt", ""))
        eval_prompt = _build_eval_prompt(
            question_text=question_text,
            expected_key_points=expected_key_points,
            answer=answer,
        )
        scores = _call_llm(eval_prompt, model=model)
        evaluated_with_llm = True

    # ------------------------------------------------------------------
    # Step 4: Apply auto-penalties and compute overall
    # ------------------------------------------------------------------

    penalised = _apply_penalties(
        scores=scores,
        bad_citations=bad_citations,
        missing_key_points=missing_key_points,
        total_key_points=len(expected_key_points),
    )
    overall = _compute_overall(penalised)

    # ------------------------------------------------------------------
    # Step 5: Build and persist the EvalRecord
    # ------------------------------------------------------------------

    record = _build_record(
        run_id=run_id,
        question_id=question_id,
        arm_id=arm_id,
        repo_path=run_repo_path,
        correctness=penalised["correctness"],
        completeness=penalised["completeness"],
        citation_quality=penalised["citation_quality"],
        hallucination_risk=penalised["hallucination_risk"],
        overall=overall,
        bad_citations=bad_citations,
        missing_key_points=missing_key_points,
        reasoning=penalised["reasoning"],
        evaluated_with_llm=evaluated_with_llm,
        eval_model=model,
    )

    if results_dir is not None:
        _append_jsonl(results_dir / "evals.jsonl", record)

    return record


def _minimal_error_record(run: dict, question: dict, reason: str) -> dict:
    """Build a zero-score EvalRecord for a failed or un-evaluable run."""
    return _build_record(
        run_id=run.get("run_id", ""),
        question_id=question.get("id", run.get("question_id", "")),
        arm_id=run.get("arm_id", ""),
        repo_path=run.get("repo_path", ""),
        correctness=_ERROR_SCORE,
        completeness=_ERROR_SCORE,
        citation_quality=_ERROR_SCORE,
        hallucination_risk=_ERROR_SCORE,
        overall=0.0,
        bad_citations=[],
        missing_key_points=[],
        reasoning=reason,
        evaluated_with_llm=False,
        eval_model="",
    )


def _build_record(
    *,
    run_id: str,
    question_id: str,
    arm_id: str,
    repo_path: str,
    correctness: int,
    completeness: int,
    citation_quality: int,
    hallucination_risk: int,
    overall: float,
    bad_citations: list[str],
    missing_key_points: list[str],
    reasoning: str,
    evaluated_with_llm: bool,
    eval_model: str,
) -> dict:
    """Assemble a canonical EvalRecord dict."""
    return {
        "run_id": run_id,
        "question_id": question_id,
        "arm_id": arm_id,
        "repo_path": repo_path,
        "correctness": correctness,
        "completeness": completeness,
        "citation_quality": citation_quality,
        "hallucination_risk": hallucination_risk,
        "overall": overall,
        "bad_citations": bad_citations,
        "missing_key_points": missing_key_points,
        "reasoning": reasoning,
        "evaluated_with_llm": evaluated_with_llm,
        "eval_model": eval_model,
    }


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------


def evaluate_all(
    runs_jsonl: Path,
    questions_yaml: Path,
    prepared_manifest: Path,
    results_dir: Path,
    model: str = "claude-haiku-4-5-20251001",
    dry_run: bool = False,
) -> list[dict]:
    """Batch-evaluate every run in ``runs_jsonl``.

    Parameters
    ----------
    runs_jsonl:
        Path to the JSONL file produced by the benchmark runner (each line is
        a RunRecord).
    questions_yaml:
        Path to the YAML file containing QuestionSpec entries.
    prepared_manifest:
        Path to the JSON manifest produced by ``repo_prep.py`` — used to
        resolve ``repo_id → local_path``.
    results_dir:
        Directory to write ``evals.jsonl`` into.
    model:
        Claude model ID for LLM evaluation.
    dry_run:
        Skip LLM calls when True.

    Returns
    -------
    list[dict]
        All EvalRecord dicts produced in this batch.
    """
    # Load questions indexed by id
    questions_by_id = _load_questions(questions_yaml)

    # Load repo manifest: repo_id → local_path
    repo_path_by_id = _load_repo_paths(prepared_manifest)

    # Stream runs from JSONL
    runs = _load_runs(runs_jsonl)

    evals: list[dict] = []
    for run in runs:
        question_id = run.get("question_id", "")
        question = questions_by_id.get(question_id)
        if question is None:
            _stderr(
                f"[evaluate] Warning: no question found for question_id={question_id!r}; "
                "skipping run."
            )
            continue

        # Resolve repo_path: prefer the stored path in the run, fallback to manifest
        repo_path_str = run.get("repo_path", "")
        if repo_path_str:
            repo_path = Path(repo_path_str)
        else:
            repo_id = run.get("repo_id", "")
            if repo_id and repo_id in repo_path_by_id:
                repo_path = repo_path_by_id[repo_id]
            else:
                _stderr(
                    f"[evaluate] Warning: cannot resolve repo_path for run "
                    f"{run.get('run_id', '?')}; using empty path."
                )
                repo_path = Path("")

        record = evaluate_run(
            run=run,
            question=question,
            repo_path=repo_path,
            model=model,
            dry_run=dry_run,
            results_dir=results_dir,
        )
        evals.append(record)

    return evals


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def _load_questions(questions_yaml: Path) -> dict[str, dict]:
    """Load questions from YAML and index them by ``id``.

    Accepts two YAML shapes:
      - Top-level list of question mappings
      - ``{questions: [...]}`` mapping
    """
    if not questions_yaml.exists():
        raise FileNotFoundError(f"Questions file not found: {questions_yaml}")

    with questions_yaml.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict) and "questions" in raw:
        entries = raw["questions"]
    else:
        raise ValueError(
            f"questions.yaml must be a list or a dict with a 'questions' key: {questions_yaml}"
        )

    indexed: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        qid = str(entry.get("id", ""))
        if qid:
            indexed[qid] = entry
    return indexed


def _load_repo_paths(manifest_path: Path) -> dict[str, Path]:
    """Load ``{repo_id: local_path}`` from a prepared_repos.json manifest."""
    if not manifest_path.exists():
        _stderr(f"[evaluate] Warning: manifest not found: {manifest_path}")
        return {}

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        _stderr(f"[evaluate] Warning: manifest is not a JSON array: {manifest_path}")
        return {}

    result: dict[str, Path] = {}
    for entry in raw:
        repo_id = entry.get("id", "")
        local_path = entry.get("local_path", "")
        if repo_id and local_path:
            result[repo_id] = Path(local_path)
    return result


def _load_runs(runs_jsonl: Path) -> list[dict]:
    """Load all RunRecord dicts from a JSONL file."""
    if not runs_jsonl.exists():
        raise FileNotFoundError(f"runs.jsonl not found: {runs_jsonl}")

    runs: list[dict] = []
    with runs_jsonl.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _stderr(f"[evaluate] Warning: bad JSON on line {lineno}: {exc}")
    return runs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluate",
        description="Evaluate benchmark runs against expected answers.",
    )
    parser.add_argument(
        "--runs",
        required=True,
        metavar="PATH",
        help="Path to the runs.jsonl file.",
    )
    parser.add_argument(
        "--questions",
        required=True,
        metavar="PATH",
        help="Path to the questions.yaml file.",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        metavar="PATH",
        help="Path to the prepared_repos.json manifest.",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        metavar="DIR",
        help="Directory to write evals.jsonl into (default: results).",
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Claude model ID for LLM evaluation (default: claude-haiku-4-5-20251001).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls and use stub scores (no API key required).",
    )
    return parser


def _cmd_evaluate(args: argparse.Namespace) -> int:
    runs_jsonl = Path(args.runs)
    questions_yaml = Path(args.questions)
    manifest = Path(args.manifest)
    results_dir = Path(args.results_dir)

    try:
        evals = evaluate_all(
            runs_jsonl=runs_jsonl,
            questions_yaml=questions_yaml,
            prepared_manifest=manifest,
            results_dir=results_dir,
            model=args.model,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        _stderr(f"Error: {exc}")
        return 1
    except ValueError as exc:
        _stderr(f"Error: {exc}")
        return 1

    evals_path = results_dir / "evals.jsonl"
    print(f"evaluated {len(evals)} runs, wrote {evals_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return _cmd_evaluate(args)


if __name__ == "__main__":
    sys.exit(main())
