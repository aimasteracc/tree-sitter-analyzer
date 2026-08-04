#!/usr/bin/env python3
"""Classify whether a Windows pytest failure is safe for one bounded retry."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_OUTCOME = re.compile(
    r"^(?P<outcome>FAILED|ERROR) (?P<nodeid>\S+) - (?P<reason>.+)$",
    re.MULTILINE,
)
_BUDGET = "Unit test exceeded per-test budget:"


def classify(output: str) -> dict[str, object]:
    """Allow retry only when every reported failure is a runtime-budget failure."""

    failures = tuple(_OUTCOME.finditer(output))
    nodeids = tuple(match.group("nodeid") for match in failures)
    budget_only = bool(failures) and all(
        match.group("outcome") == "FAILED" and _BUDGET in match.group("reason")
        for match in failures
    )
    return {
        "retry_eligible": budget_only,
        "nodeids": list(nodeids) if budget_only else [],
        "failure_count": len(failures),
        "reason": "budget_only" if budget_only else "non_budget_or_unclassified",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--nodeids-output", type=Path, required=True)
    args = parser.parse_args()
    result = classify(args.log.read_text(encoding="utf-8", errors="replace"))
    args.nodeids_output.write_text(
        "".join(f"{nodeid}\n" for nodeid in result["nodeids"]), encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["retry_eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
