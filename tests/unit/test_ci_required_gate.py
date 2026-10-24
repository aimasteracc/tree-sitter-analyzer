"""The ci.yml Quality Gate fails closed on selected lanes (scripts/ci_required_gate.py)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import ci_required_gate
from scripts.ci_required_gate import LANES, evaluate, main
from scripts.ci_route import load_routing_config, route_changed_files

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
CONFIG = load_routing_config(PROJECT_ROOT / "config" / "ci-routing.yml")


def _needs(changed: list[str], **overrides: str) -> dict[str, object]:
    """``toJSON(needs)`` for a run whose route saw ``changed``.

    Every selected lane succeeds and every unselected lane is skipped, as
    GitHub reports them; ``overrides`` replaces individual lane results.
    """
    outputs = route_changed_files(changed, CONFIG)
    rendered = {
        key: ("true" if value else "false") if isinstance(value, bool) else str(value)
        for key, value in outputs.items()
    }
    needs: dict[str, object] = {"route": {"result": "success", "outputs": rendered}}
    for lane, flag in LANES.items():
        needs[lane] = {
            "result": "success" if rendered[flag] == "true" else "skipped",
            "outputs": {},
        }
    for lane, result in overrides.items():
        needs[lane.replace("_", "-")] = {"result": result, "outputs": {}}
    return needs


def _failed(needs: dict[str, object]) -> list[str]:
    verdicts, errors = evaluate(needs)
    return [v.lane for v in verdicts if not v.ok] + errors


def test_code_change_with_every_selected_lane_green_passes() -> None:
    needs = _needs(["tree_sitter_analyzer/mcp/server.py"])

    assert _failed(needs) == []


def test_docs_only_change_passes_with_matrix_skipped() -> None:
    """An unselected lane may be skipped: docs-only skips the test matrix."""
    needs = _needs(["docs/guide.md"])

    assert (needs["test"], _failed(needs)) == (
        {"result": "skipped", "outputs": {}},
        [],
    )


@pytest.mark.parametrize("result", ["skipped", "cancelled", "failure"])
def test_selected_lane_that_did_not_succeed_fails(result: str) -> None:
    """The bug this gate fixes: a selected lane that ended skipped passed."""
    needs = _needs(["tree_sitter_analyzer/mcp/server.py"], test=result)

    assert _failed(needs) == ["test"]


def test_selected_lane_missing_from_needs_fails() -> None:
    needs = _needs(["tree_sitter_analyzer/mcp/server.py"])
    del needs["build"]

    assert _failed(needs) == ["build"]


@pytest.mark.parametrize("result", ["cancelled", "failure"])
def test_unselected_lane_failure_still_fails(result: str) -> None:
    needs = _needs(["docs/guide.md"], build=result)

    assert _failed(needs) == ["build"]


def test_route_failure_and_missing_flags_fail_every_lane() -> None:
    needs = {"route": {"result": "failure", "outputs": {}}}

    verdicts, errors = evaluate(needs)

    assert [v.lane for v in verdicts if v.ok] == []
    assert errors[0] == "route job did not succeed: failure"


def test_run_that_selects_nothing_substantive_fails() -> None:
    needs = _needs(["tree_sitter_analyzer/mcp/server.py"])
    route = needs["route"]
    assert isinstance(route, dict)
    route["outputs"] = {**route["outputs"], "run_test_matrix": "false"}
    for lane in ("test", "test-quality-audit"):
        needs[lane] = {"result": "skipped", "outputs": {}}

    assert _failed(needs) == [
        "neither the test matrix nor the docs check was selected (route misfire?)"
    ]


def test_unmapped_job_in_needs_fails() -> None:
    needs = _needs(["tree_sitter_analyzer/mcp/server.py"])
    needs["new-lane"] = {"result": "success", "outputs": {}}

    assert _failed(needs)[0].startswith("jobs in needs without a lane mapping")


def test_main_exit_code_and_step_summary(monkeypatch, tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv(
        "CI_NEEDS",
        json.dumps(_needs(["tree_sitter_analyzer/mcp/server.py"], e2e="skipped")),
    )

    assert main([]) == 1
    assert "| e2e | yes | skipped | FAIL: selected but skipped |" in summary.read_text(
        encoding="utf-8"
    )


def test_main_rejects_non_json_needs(monkeypatch) -> None:
    monkeypatch.setenv("CI_NEEDS", "")

    assert main([]) == 1


def _gate_job() -> str:
    text = CI_YML.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^  quality-gate:\n(?P<body>.*?)(?=^  [a-z0-9_-]+:|\Z)", text
    )
    assert match is not None
    return match.group("body")


def test_lane_map_matches_the_gate_needs_in_ci_yml() -> None:
    """Every job the gate waits on has a lane mapping, and nothing else."""
    needs = re.search(r"(?m)^    needs: \[(?P<jobs>[^\]]+)\]", _gate_job())
    assert needs is not None
    jobs = {job.strip() for job in needs.group("jobs").split(",")}

    assert jobs - {ci_required_gate.ROUTE_JOB} == set(LANES)


def test_lane_flags_are_route_outputs_and_gate_each_job() -> None:
    """Each lane's flag is a route output, and is the flag in the job's ``if:``."""
    text = CI_YML.read_text(encoding="utf-8")
    for lane, flag in LANES.items():
        assert f"      {flag}: ${{{{ steps.route.outputs.{flag} }}}}" in text, flag
        job = re.search(
            rf"(?ms)^  {re.escape(lane)}:\n(?P<body>.*?)(?=^  [a-z0-9_-]+:|\Z)", text
        )
        assert job is not None, lane
        assert f"if: needs.route.outputs.{flag} == 'true'" in job.group("body"), lane


def test_gate_runs_the_script_with_needs_and_always() -> None:
    body = _gate_job()

    assert "if: always()" in body
    assert "CI_NEEDS: ${{ toJSON(needs) }}" in body
    assert "python3 scripts/ci_required_gate.py" in body
    assert "check_routed" not in body
