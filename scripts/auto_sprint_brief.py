#!/usr/bin/env python3
"""auto_sprint_brief — pick one sprint plan work item and emit a Claude Code
brief.

This is the Level 1.5 bridge in the autonomous-dev architecture
(docs/AUTONOMOUS_DEV.md): a sprint plan from auto_review.py becomes a
self-contained, paste-into-Claude-Code (or pipe-into-Anthropic-API) brief.

The brief is deliberately read-only: it does NOT shell out to git or to
the Anthropic API. It just prints text. You decide where to send it:

  * paste it into a fresh Claude Code session
  * pipe it into ``anthropic`` CLI in CI (Level 2)
  * commit it to docs/ as an audit trail

Exit codes
----------
0  Brief printed.
1  Sprint plan is empty (no work to brief).
2  Sprint plan file missing or malformed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


_HEADER = """# Autonomous Sprint Brief

You are taking one work item from the daily auto-sprint plan. Stay narrow:
fix exactly what is in scope, do not refactor surrounding code, and stop
once the verification gate is green.

## Ground rules (non-negotiable)

1. **No `--no-verify`** on commits, and **no `--dangerously-skip-permissions`**.
   If pre-commit hooks fail, fix the root cause or stop and report.
2. **No autonomous merge.** Open a PR. Let a human merge it.
3. **No secret writes.** Do not commit `.env`, credentials, or any path
   matching `.secrets.baseline`'s patterns.
4. **Stay in scope.** Only edit files this brief explicitly names plus
   their direct tests. If you discover scope creep, stop and write
   findings to `docs/AUDIT_FINDINGS_*.md` — do NOT silently expand.
5. **Bail out triggers.** Stop, write your state to memory, and surface a
   diagnosis instead of pushing through if you hit any of:
   - same test fails 3 times after edits
   - file size exceeds 800 lines after refactor
   - mypy on the changed files reports new errors (not pre-existing)
   - --project-health grade drops vs baseline
"""

_FOOTER_TEMPLATE = """\
## Verification gate (all must be green before opening PR)

Run, in order, and stop on first failure:

```bash
{post_edit_block}
```

Then:

```bash
# 1. Unit tests for affected modules (use --change-impact output).
uv run python -m tree_sitter_analyzer --change-impact --format json | jq .

# 2. Golden master regression (catches plugin-unification breakage).
uv run pytest -q tests/regression/test_plugin_golden_masters.py

# 3. Type check on changed files (pre-commit mypy is broken — see
#    AUDIT-INFRA-1 — so we run on the diff manually):
uv run mypy $(git diff --name-only HEAD~..HEAD -- '*.py')

# 4. The agent's own self-check: did we make things worse?
uv run python scripts/auto_review.py --max-items 5 --quiet --out /tmp/post.json
diff <(jq '.summary' /tmp/pre.json) <(jq '.summary' /tmp/post.json) || true
```

## Commit + PR

- One commit per logical change. Conventional Commits prefix (`fix(...)`,
  `feat(...)`, `perf(...)`, `test(...)`, `docs(...)`).
- Body explains WHY, references the audit ID (e.g. `PERF-4`).
- Open PR against `feat/autonomous-dev`. Title: `<conv-prefix>: <one line>`.
- Body includes: (a) before/after numbers if perf, (b) regression test
  reference, (c) any audit findings to mark as ✅ fixed.

## When done

Update the project's internal quality tracker to mark this finding ✅ fixed
with a short measured-after block. Then stop. Do NOT pick up the next
work item.
"""


def _load_plan(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"auto_sprint_brief: plan not found at {path}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"auto_sprint_brief: cannot read plan: {exc}", file=sys.stderr)
        sys.exit(2)


def _pick(plan: dict[str, Any], index: int) -> dict[str, Any] | None:
    items = plan.get("work_items") or []
    if not items:
        return None
    if 0 <= index < len(items):
        return items[index]  # type: ignore[no-any-return]
    return None


def _render(item: dict[str, Any], plan: dict[str, Any]) -> str:
    rel = os.path.relpath(item["file_path"], start=str(ROOT))
    weakest = item.get("weakest_dimension", "?")
    grade = item.get("grade", "?")
    score = item.get("score", 0.0)
    signal = item.get("signal", "?")
    patterns = item.get("patterns", []) or []

    pattern_block = "(none flagged)"
    if patterns:
        lines = []
        for p in patterns[:8]:
            lines.append(
                f"  - L{p.get('line', '?')}: {p.get('type', '?')} "
                f"({p.get('severity', '?')}) — {p.get('message', '')}"
            )
        pattern_block = "\n".join(lines)
        if len(patterns) > 8:
            pattern_block += f"\n  - …and {len(patterns) - 8} more"

    safety = " ".join(item.get("safety_command", []) or ["(none)"])
    refactor = " ".join(item.get("refactor_command", []) or ["(none)"])
    post_edit_lines = [" ".join(c) for c in (item.get("post_edit_commands", []) or [])]
    post_edit_block = "\n".join(post_edit_lines) or "(none specified)"

    diff_impact = plan.get("diff_impact", {}) or {}
    risk = (diff_impact.get("agent_summary") or {}).get("risk", "unknown")

    return f"""{_HEADER}

## Selected work item

- **File:** `{rel}`
- **Grade / score / signal:** `{grade}` · {score:.1f} · `{signal}`
- **Weakest dimension:** `{weakest}`
- **Current diff risk:** `{risk}`
- **Code patterns flagged in this file:**
{pattern_block}

## Recommended discovery commands (run before editing)

```bash
# Safety preview: who depends on this file? What does my edit risk breaking?
{safety}

# Refactor suggestions from the project's own tool:
{refactor}
```

## Snapshot the baseline so we can verify "no regression"

```bash
uv run python scripts/auto_review.py --max-items 5 --quiet --out /tmp/pre.json
uv run pytest -q tests/regression/test_plugin_golden_masters.py
```

{_FOOTER_TEMPLATE.format(post_edit_block=post_edit_block)}"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=ROOT / "artifacts" / "auto-review.json",
        help="sprint plan JSON to read (default: artifacts/auto-review.json)",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="which work item to brief (0 = top of backlog, default)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write brief to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

    plan = _load_plan(args.plan)
    item = _pick(plan, args.index)
    if item is None:
        print("auto_sprint_brief: plan is empty — no work to brief 🎉")
        return 1

    brief = _render(item, plan)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(brief, encoding="utf-8")
        print(f"auto_sprint_brief: wrote brief to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(brief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
