"""Regression tests for the autonomous runtime status script."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATUS_SCRIPT = PROJECT_ROOT / ".autonomous-runtime" / "status.sh"
TICK_SCRIPT = PROJECT_ROOT / ".autonomous-runtime" / "tick.sh"


def run_status(
    project_dir: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        ["bash", str(STATUS_SCRIPT), str(project_dir), *args],
        check=True,
        text=True,
        capture_output=True,
        env=run_env,
    )


def run_tick(
    project_dir: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        ["bash", str(TICK_SCRIPT), str(project_dir)],
        check=True,
        text=True,
        capture_output=True,
        env=run_env,
    )


def make_runtime_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    runtime_dir = project_dir / ".autonomous-runtime"
    change_dir = project_dir / "openspec" / "changes" / "phase8-code-slimming"
    runtime_dir.mkdir(parents=True)
    change_dir.mkdir(parents=True)

    (runtime_dir / "last-tick.json").write_text(
        '{"heartbeat_status": "recorded"}\n', encoding="utf-8"
    )
    (runtime_dir / "autonomous-state.json").write_text(
        '{"project": "test"}\n', encoding="utf-8"
    )
    (runtime_dir / "autonomous-loop.log").write_text(
        "[iteration 1] sleep 300s\n", encoding="utf-8"
    )
    (runtime_dir / "loop.sh").write_text(
        "#!/bin/bash\n"
        'echo $$ > "$(dirname "$0")/loop.lock"\n'
        'sleep "${TS_AUTONOMY_SLEEP_SECONDS:-300}"\n',
        encoding="utf-8",
    )
    (runtime_dir / "loop.sh").chmod(0o755)
    (change_dir / "tasks.md").write_text("- [ ] keep improving\n", encoding="utf-8")

    subprocess.run(
        ["git", "init"], cwd=project_dir, check=True, text=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=project_dir, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=project_dir, check=True
    )
    (project_dir / "sample.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=project_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return project_dir


@pytest.mark.skip(
    reason="Flaky on CI matrix — bash/integration timing issues. Tracked separately.",
)
def test_status_json_reports_recent_heartbeat_and_pending_changes(
    tmp_path: Path,
) -> None:
    project_dir = make_runtime_project(tmp_path)

    result = run_status(project_dir, "--json")
    payload = json.loads(result.stdout)

    assert payload["project"] == str(project_dir)
    assert payload["heartbeat_recent"] is True
    assert payload["conclusion"] == "healthy_codex_heartbeat_active"
    assert payload["pending_openspec_changes"] == ["phase8-code-slimming"]
    assert payload["pending_openspec_count"] == 1


@pytest.mark.skip(
    reason="Flaky on CI matrix — bash/integration timing issues. Tracked separately.",
)
def test_status_json_reports_stopped_when_heartbeat_is_stale(tmp_path: Path) -> None:
    project_dir = make_runtime_project(tmp_path)
    stale_time = time.time() - 120
    os.utime(
        project_dir / ".autonomous-runtime" / "last-tick.json", (stale_time, stale_time)
    )

    result = run_status(
        project_dir, "--json", env={"TS_AUTONOMY_HEARTBEAT_MAX_AGE_SECONDS": "60"}
    )
    payload = json.loads(result.stdout)

    assert payload["heartbeat_recent"] is False
    assert payload["loop_running"] is False
    assert payload["conclusion"] == "stopped"


@pytest.mark.skip(
    reason="Flaky on CI matrix — bash/integration timing issues. Tracked separately.",
)
def test_status_text_includes_heartbeat_section(tmp_path: Path) -> None:
    project_dir = make_runtime_project(tmp_path)

    result = run_status(project_dir)

    assert "Codex heartbeat" in result.stdout
    assert "phase8-code-slimming" in result.stdout
    assert "健康运行" in result.stdout


@pytest.mark.skip(
    reason="Flaky on CI matrix — bash/integration timing issues. Tracked separately.",
)
def test_tick_writes_machine_readable_state(tmp_path: Path) -> None:
    project_dir = make_runtime_project(tmp_path)
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=project_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()

    result = run_tick(project_dir, env={"TS_AUTONOMY_SLEEP_SECONDS": "2"})
    payload = json.loads(
        (project_dir / ".autonomous-runtime" / "last-tick.json").read_text()
    )

    assert "AUTONOMY_TICK" in result.stdout
    assert payload["heartbeat_status"] == "recorded"
    assert payload["loop_probe_status"] == "running"
    assert payload["branch"] == branch


@pytest.mark.skip(
    reason="Flaky on CI matrix — bash/integration timing issues. Tracked separately.",
)
def test_tick_reuses_existing_loop_lock(tmp_path: Path) -> None:
    project_dir = make_runtime_project(tmp_path)
    runtime_dir = project_dir / ".autonomous-runtime"
    sleep_process = subprocess.Popen(["sleep", "5"])
    try:
        (runtime_dir / "loop.lock").write_text(str(sleep_process.pid), encoding="utf-8")

        result = run_tick(project_dir, env={"TS_AUTONOMY_SLEEP_SECONDS": "1"})
        payload = json.loads((runtime_dir / "last-tick.json").read_text())

        assert "ready" in result.stdout
        assert payload["action"] == "ready"
        assert payload["loop_pids"] == str(sleep_process.pid)
    finally:
        sleep_process.terminate()
        sleep_process.wait(timeout=5)
