"""Pin the macOS SQL platform-compat consolidation.

macOS arm64 runners are capacity-constrained, so the four Python versions run
sequentially inside ONE macOS job instead of four ~30 s jobs. Ubuntu/Windows
stay a per-version matrix. The versions must stay in lockstep with the matrix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "sql-platform-compat.yml"
VERSIONS = ["3.10", "3.11", "3.12", "3.13"]


def _jobs() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def test_matrix_job_has_no_macos_and_keeps_all_versions() -> None:
    matrix = _jobs()["test-compatibility"]["strategy"]["matrix"]
    assert matrix["os"] == ["ubuntu-latest", "windows-latest"]
    assert [str(v) for v in matrix["python-version"]] == VERSIONS


def test_single_macos_job_covers_all_four_versions() -> None:
    jobs = _jobs()
    macos_jobs = {
        name: job
        for name, job in jobs.items()
        if "macos" in str(job.get("runs-on", ""))
    }
    assert list(macos_jobs) == ["test-compatibility-macos"]
    job = macos_jobs["test-compatibility-macos"]
    assert "strategy" not in job
    assert job["env"]["MACOS_PYTHON_VERSIONS"].split() == VERSIONS
    script = "\n".join(s.get("run", "") for s in job["steps"])
    assert "for v in $MACOS_PYTHON_VERSIONS" in script
    assert '--python "$v"' in script
    assert '-k "test_sql"' in script
    assert "platform_compat.record" in script
    assert "platform_compat.compare" in script
    # Any failing version must fail the job (after all versions have run).
    assert 'failed="$failed $v"' in script
    assert 'if [ -n "$failed" ]' in script
    assert "exit 1" in script


def test_workflow_stays_reusable_and_gate_aggregates_it() -> None:
    ci = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    job = ci["jobs"]["sql-platform-compat"]
    assert job["uses"] == "./.github/workflows/sql-platform-compat.yml"
    assert "sql-platform-compat" in ci["jobs"]["quality-gate"]["needs"]
    assert ci["jobs"]["quality-gate"]["name"] == "Quality Gate"
