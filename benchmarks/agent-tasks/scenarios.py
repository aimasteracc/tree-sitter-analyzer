"""Agent-task scenarios for the CodeGraph bench harness.

Each scenario exposes two callables:

* ``run_tsa(repo, **kw) -> dict``  — single MCP tool call, returns the tool's
  raw response envelope (tool_calls=1, agent_decidable=verdict != ERROR).
* ``run_baseline(repo, **kw) -> dict`` — simulates an agent without our MCP
  tools doing the same task with ``cat``/``ls``/``rg``/``git`` (counted via
  subprocess).

The scenarios are deliberately small and side-effect-free so the harness can
call them in a tight loop. They never write to ``repo``; they only read.

Created: 2026-05-22 r37fE
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess  # nosec B404 — baseline mode genuinely needs a shell agent
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 1 token ≈ 4 chars for English code; the same heuristic OpenAI / Anthropic
# use in their tokenizer docs as a back-of-envelope estimate. Real tokenizers
# vary 10-30% but for differential bench (us vs CodeGraph vs baseline) the
# constant cancels — what matters is comparable measurement, not absolute
# truth. Comment kept so future readers don't "fix" it with tiktoken.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from a text blob using the 4-chars-per-token heuristic."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _serialize_for_tokens(obj: Any) -> str:
    """Render ``obj`` to a string for token estimation.

    Strings pass through. Dicts/lists fall back to ``repr`` so the same object
    always estimates to the same number — JSON would also work but adds
    encoding cost on hot paths.
    """
    if isinstance(obj, str):
        return obj
    return repr(obj)


def _run_subprocess(cmd: list[str], cwd: str | Path, timeout: float = 30.0) -> str:
    """Run a shell command and return stdout (stderr swallowed).

    Returns empty string on any failure — baseline agents are graceful, they
    just keep trying other tools.
    """
    try:
        proc = subprocess.run(  # nosec B603 — cmd is a literal list, no shell=True
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.stdout or ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _is_decidable(result: dict[str, Any]) -> bool:
    """A result is agent-decidable when it has a verdict that isn't ERROR.

    The bench treats SAFE/CAUTION/REVIEW/UNSAFE/INFO/WARN/NOT_FOUND as
    decidable — the agent gets actionable signal. ERROR or missing verdict
    means the agent has to retry / escalate, which counts against the tool.
    """
    verdict = result.get("verdict")
    if not isinstance(verdict, str):
        # Some tools surface the verdict only via agent_summary
        agent_summary = result.get("agent_summary") or {}
        verdict = (
            agent_summary.get("verdict") if isinstance(agent_summary, dict) else None
        )
    if not isinstance(verdict, str) or not verdict:
        return False
    return verdict.upper() != "ERROR"


# ---------------------------------------------------------------------------
# Scenario: cold-start
# ---------------------------------------------------------------------------


def cold_start_tsa(repo: str, **_: Any) -> dict[str, Any]:
    """TSA cold-start: 1 call to get_project_summary."""
    from tree_sitter_analyzer.mcp.tools.get_project_summary_tool import (
        GetProjectSummaryTool,
    )

    tool = GetProjectSummaryTool(repo)
    result = asyncio.run(tool.execute({"output_format": "json"}))
    return {
        "result": result,
        "tool_calls": 1,
        "agent_decidable": _is_decidable(result),
    }


def cold_start_baseline(repo: str, **_: Any) -> dict[str, Any]:
    """Baseline cold-start: agent reads README + lists files + tails git log."""
    out_parts: list[str] = []
    calls = 0

    readme = Path(repo) / "README.md"
    if readme.exists():
        try:
            out_parts.append(
                readme.read_text(encoding="utf-8", errors="replace")[:8000]
            )
        except OSError:
            pass
        calls += 1

    out_parts.append(_run_subprocess(["ls", "-la"], repo, timeout=10))
    calls += 1

    if shutil.which("git"):
        out_parts.append(
            _run_subprocess(["git", "log", "--oneline", "-20"], repo, timeout=10)
        )
        calls += 1

    # Naive entry-point hunt — what an agent would do without a project index.
    out_parts.append(
        _run_subprocess(
            [
                "find",
                ".",
                "-maxdepth",
                "2",
                "-name",
                "main.py",
                "-o",
                "-name",
                "__main__.py",
            ],
            repo,
            timeout=10,
        )
    )
    calls += 1

    combined = "\n".join(out_parts)
    return {
        "result": {"baseline_output": combined[:4000], "verdict": "INFO"},
        "tool_calls": calls,
        "agent_decidable": bool(combined.strip()),
    }


# ---------------------------------------------------------------------------
# Scenario: find-callers
# ---------------------------------------------------------------------------


def find_callers_tsa(repo: str, symbol: str = "execute", **_: Any) -> dict[str, Any]:
    """TSA find-callers: 1 call to codegraph_call_graph mode=callers."""
    from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool

    tool = CodeGraphCallTool(repo)
    result = asyncio.run(
        tool.execute(
            {
                "mode": "callers",
                "function_name": symbol,
                "output_format": "json",
            }
        )
    )
    return {
        "result": result,
        "tool_calls": 1,
        "agent_decidable": _is_decidable(result),
    }


def find_callers_baseline(
    repo: str, symbol: str = "execute", **_: Any
) -> dict[str, Any]:
    """Baseline find-callers: agent greps for the symbol with rg/grep."""
    grep_tool = "rg" if shutil.which("rg") else "grep"
    calls = 0
    out_parts: list[str] = []

    if grep_tool == "rg":
        # rg: one call gets file:line hits across the tree
        out_parts.append(_run_subprocess(["rg", "-n", symbol, "."], repo, timeout=30))
        calls += 1
    else:
        # grep: needs -r and excludes; one call still
        out_parts.append(
            _run_subprocess(
                ["grep", "-rn", "--include=*.py", symbol, "."], repo, timeout=30
            )
        )
        calls += 1

    # Agent would then read a few sample files to filter true callers from
    # method definitions — model this as 3 follow-up reads of the most-cited
    # files. That's the realistic agent workflow.
    sample_files = [
        line.split(":", 1)[0] for line in out_parts[0].splitlines()[:6] if ":" in line
    ]
    seen: set[str] = set()
    for fp in sample_files:
        if fp in seen or len(seen) >= 3:
            continue
        seen.add(fp)
        full = Path(repo) / fp
        if full.exists() and full.is_file():
            try:
                out_parts.append(
                    full.read_text(encoding="utf-8", errors="replace")[:2000]
                )
            except OSError:
                pass
            calls += 1

    combined = "\n".join(out_parts)
    return {
        "result": {"baseline_output": combined[:4000], "verdict": "INFO"},
        "tool_calls": calls,
        "agent_decidable": bool(combined.strip()),
    }


# ---------------------------------------------------------------------------
# Scenario: change-impact
# ---------------------------------------------------------------------------


def change_impact_tsa(repo: str, **_: Any) -> dict[str, Any]:
    """TSA change-impact: 1 call to analyze_change_impact mode=diff."""
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    tool = ChangeImpactTool(repo)
    result = asyncio.run(
        tool.execute({"mode": "diff", "output_format": "json", "include_tests": True})
    )
    return {
        "result": result,
        "tool_calls": 1,
        "agent_decidable": _is_decidable(result)
        and bool(result.get("verification_command")),
    }


def change_impact_baseline(repo: str, **_: Any) -> dict[str, Any]:
    """Baseline change-impact: agent runs git diff + greps for test files."""
    calls = 0
    out_parts: list[str] = []

    if not shutil.which("git"):
        return {
            "result": {"baseline_output": "git not available", "verdict": "ERROR"},
            "tool_calls": 0,
            "agent_decidable": False,
        }

    diff = _run_subprocess(["git", "diff", "--name-only", "HEAD"], repo, timeout=15)
    out_parts.append(diff)
    calls += 1

    out_parts.append(_run_subprocess(["git", "status", "--short"], repo, timeout=15))
    calls += 1

    # For each changed file, agent would grep for its module name in tests/
    # to guess which tests to re-run. Cap at 5 files to avoid pathological
    # diffs blowing up the baseline.
    grep_tool = "rg" if shutil.which("rg") else "grep"
    for fname in diff.splitlines()[:5]:
        stem = Path(fname).stem
        if not stem or stem == "__init__":
            continue
        if grep_tool == "rg":
            out_parts.append(
                _run_subprocess(["rg", "-l", stem, "tests/"], repo, timeout=15)
            )
        else:
            out_parts.append(
                _run_subprocess(["grep", "-rl", stem, "tests/"], repo, timeout=15)
            )
        calls += 1

    combined = "\n".join(out_parts)
    # Baseline has NO verification_command — the agent has to guess which
    # tests to run. That's the point of the comparison.
    return {
        "result": {
            "baseline_output": combined[:4000],
            "verdict": "INFO",
            "verification_command": None,
        },
        "tool_calls": calls,
        "agent_decidable": False,  # no concrete verification_command → not decidable
    }


# ---------------------------------------------------------------------------
# Scenario: refactor-suggest
# ---------------------------------------------------------------------------


def refactor_suggest_tsa(repo: str, file: str = "", **_: Any) -> dict[str, Any]:
    """TSA refactor-suggest: 1 call to refactoring_suggestions."""
    from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
        RefactoringSuggestionsTool,
    )

    target = file or _pick_default_file(repo)
    tool = RefactoringSuggestionsTool(repo)
    result = asyncio.run(
        tool.execute(
            {
                "file_path": target,
                "output_format": "json",
                "max_suggestions": 10,
                "include_extractions": True,
            }
        )
    )
    return {
        "result": result,
        "tool_calls": 1,
        "agent_decidable": _is_decidable(result),
    }


def refactor_suggest_baseline(repo: str, file: str = "", **_: Any) -> dict[str, Any]:
    """Baseline refactor-suggest: agent reads file + greps for long methods.

    Real-world agent fallback: open the file, scan for nesting (`if ... if ...
    if`), count method lengths by hand. We model: 1 read + 2 greps.
    """
    target = file or _pick_default_file(repo)
    target_path = Path(repo) / target
    calls = 0
    out_parts: list[str] = []

    if target_path.exists():
        try:
            out_parts.append(
                target_path.read_text(encoding="utf-8", errors="replace")[:8000]
            )
        except OSError:
            pass
        calls += 1

    grep_tool = "rg" if shutil.which("rg") else "grep"
    if grep_tool == "rg":
        out_parts.append(
            _run_subprocess(["rg", "-n", "def ", target], repo, timeout=10)
        )
        out_parts.append(
            _run_subprocess(["rg", "-n", "class ", target], repo, timeout=10)
        )
    else:
        out_parts.append(
            _run_subprocess(["grep", "-n", "def ", target], repo, timeout=10)
        )
        out_parts.append(
            _run_subprocess(["grep", "-n", "class ", target], repo, timeout=10)
        )
    calls += 2

    combined = "\n".join(out_parts)
    # Baseline produces raw signal — no actionable extraction plan, no
    # ordered priorities. Decidable-by-verdict but useless to an agent
    # that wants to apply the refactor.
    return {
        "result": {"baseline_output": combined[:4000], "verdict": "INFO"},
        "tool_calls": calls,
        "agent_decidable": False,  # no priority-ordered plan → not decidable
    }


def _pick_default_file(repo: str) -> str:
    """Choose a non-trivial Python file for refactor-suggest.

    Prefers files with the most lines, but caps the search to the first 200
    .py files so a giant monorepo doesn't make the bench scenario itself
    slow.
    """
    repo_path = Path(repo)
    candidates: list[tuple[int, str]] = []
    for path in repo_path.rglob("*.py"):
        if "/.tox/" in str(path) or "/__pycache__/" in str(path):
            continue
        if "test_" in path.name or path.name == "conftest.py":
            continue
        try:
            # ``with`` block — the bare generator in 21.x leaked the file
            # handle and pytest's ResourceWarning hook turned it into an
            # error. Counting via ``.read().count("\n")`` keeps the close
            # path explicit and is fast enough for the 200-file cap.
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                line_count = fh.read().count("\n")
        except OSError:
            continue
        candidates.append((line_count, str(path.relative_to(repo_path))))
        if len(candidates) >= 200:
            break
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Registry — bench_runner uses these names
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, Any]] = {
    "cold-start": {
        "tsa": cold_start_tsa,
        "baseline": cold_start_baseline,
        "tsa_tool": "get_project_summary",
    },
    "find-callers": {
        "tsa": find_callers_tsa,
        "baseline": find_callers_baseline,
        "tsa_tool": "codegraph_call_graph",
    },
    "change-impact": {
        "tsa": change_impact_tsa,
        "baseline": change_impact_baseline,
        "tsa_tool": "analyze_change_impact",
    },
    "refactor-suggest": {
        "tsa": refactor_suggest_tsa,
        "baseline": refactor_suggest_baseline,
        "tsa_tool": "refactoring_suggestions",
    },
}


def list_scenarios() -> list[str]:
    """Return the scenario ids the harness knows about."""
    return sorted(SCENARIOS.keys())
