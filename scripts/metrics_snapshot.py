#!/usr/bin/env python3
"""Weekly north-star metrics snapshot — measure the funnel or you can't optimize it.

Captures the discovery/adoption funnel for tree-sitter-analyzer:
- GitHub: stars, forks, watchers, open issues (via `gh api`)
- PyPI: last-week / last-month download counts (via pypistats.org public API)

Writes one JSON file per run into .recon/metrics/YYYY-MM-DD.json (git-ignored
scratch space; NOT part of CI). Run manually or from a local cron:

    uv run python scripts/metrics_snapshot.py
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "aimasteracc/tree-sitter-analyzer"
PACKAGE = "tree-sitter-analyzer"
OUT_DIR = Path(__file__).resolve().parent.parent / ".recon" / "metrics"


def _github() -> dict:
    try:
        raw = subprocess.run(
            ["gh", "api", f"repos/{REPO}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
        d = json.loads(raw)
        return {
            "stars": d.get("stargazers_count"),
            "forks": d.get("forks_count"),
            "watchers": d.get("subscribers_count"),
            "open_issues": d.get("open_issues_count"),
        }
    except Exception as e:  # noqa: BLE001 - snapshot must not die on one source
        return {"error": str(e)}


def _pypistats() -> dict:
    url = f"https://pypistats.org/api/packages/{PACKAGE}/recent"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            d = json.load(resp)["data"]
        return {
            "downloads_last_day": d.get("last_day"),
            "downloads_last_week": d.get("last_week"),
            "downloads_last_month": d.get("last_month"),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def main() -> int:
    today = _dt.date.today().isoformat()
    snapshot = {
        "date": today,
        "github": _github(),
        "pypi": _pypistats(),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{today}.json"
    out.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(json.dumps(snapshot, indent=2))
    print(f"\nwritten: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
