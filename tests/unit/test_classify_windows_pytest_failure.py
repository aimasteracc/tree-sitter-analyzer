"""Behavioral tests for the Windows degraded-runner classifier."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.classify_windows_pytest_failure import classify, main


def test_budget_only_failures_are_retry_eligible() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "FAILED tests/unit/test_b.py::test_b - Failed: Unit test exceeded "
        "per-test budget: 9.10s > 8.0s.\n"
    )

    assert classify(output) == {
        "retry_eligible": True,
        "nodeids": ["tests/unit/test_a.py::test_a", "tests/unit/test_b.py::test_b"],
        "failure_count": 2,
        "reason": "budget_only",
    }


def test_assertion_failure_blocks_retry() -> None:
    output = "FAILED tests/unit/test_a.py::test_a - AssertionError: wrong value\n"

    assert classify(output) == {
        "retry_eligible": False,
        "nodeids": [],
        "failure_count": 1,
        "reason": "non_budget_or_unclassified",
    }


def test_mixed_failures_block_retry() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "FAILED tests/unit/test_b.py::test_b - RuntimeError: boom\n"
    )

    assert classify(output)["retry_eligible"] is False


def test_collection_error_blocks_retry() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "ERROR tests/unit/test_b.py - ImportError: missing dependency\n"
    )

    assert classify(output)["retry_eligible"] is False


@pytest.mark.parametrize("outcome", ["FAILED", "ERROR"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("parameter", ["", "[with spaces]"])
def test_reasonless_failure_blocks_budget_retry(
    tmp_path: Path, outcome: str, newline: str, parameter: str
) -> None:
    """无原因的失败仍须计入，且不能因另一项超时重跑成功而放行。"""
    # 2026-09-09：#1419 Windows worker 崩溃行被分类器忽略，导致错误绿灯。
    output = newline.join(
        [
            "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
            "per-test budget: 16.47s > 12.8s.",
            f"{outcome} tests/unit/test_decision_journal.py::TestSearch::test_search_returns_newest_first{parameter}",
            "2 failed, 23381 passed, 1211 skipped, 5 rerun in 801.13s",
            "",
        ]
    )
    assert classify(output) == {
        "retry_eligible": False,
        "nodeids": [],
        "failure_count": 2,
        "reason": "non_budget_or_unclassified",
    }
    log = tmp_path / "pytest-output.txt"
    log.write_text(output, encoding="utf-8", newline="")
    nodeids = tmp_path / "retry.txt"
    with patch.object(
        sys, "argv", ["classify", str(log), "--nodeids-output", str(nodeids)]
    ):
        assert main() == 1
    assert nodeids.read_bytes() == b""


def test_nodeid_file_uses_lf_so_the_ci_retry_can_match(tmp_path: Path) -> None:
    """节点文件必须使用 LF，避免 Bash 逐行读取后将回车保留在节点末尾。"""
    log = tmp_path / "pytest-output.txt"
    log.write_text(
        "FAILED tests/a.py::t1 - Failed: Unit test exceeded per-test "
        "budget: 8.48s > 8.0s." + chr(10),
        encoding="utf-8",
        newline="",
    )
    out = tmp_path / "windows-budget-retry.txt"
    argv = ["classify", str(log), "--nodeids-output", str(out)]

    with patch.object(sys, "argv", argv):
        assert main() == 0

    assert out.read_bytes() == b"tests/a.py::t1" + chr(10).encode()


@pytest.mark.parametrize("profile", ["test-matrix-pr", "test-matrix-full"])
@pytest.mark.parametrize("budget_only", [False, True])
def test_ci_retry_reads_exact_nodeids_with_system_bash(
    tmp_path: Path, profile: str, budget_only: bool
) -> None:
    """执行真实分类器和工作流重试片段，保持预算资格及节点字面值。"""
    # 2026-09-09：PR #1433 macOS 作业在获准重试后因 Bash 3 缺少 mapfile 失败。
    import os
    import shlex
    import shutil
    import subprocess

    import yaml

    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/reusable-test.yml").read_text(encoding="utf-8")
    )
    step = next(
        item
        for item in workflow["jobs"][profile]["steps"]
        if item.get("name") == "Run Tests (no coverage)"
    )
    command = step["run"][step["run"].index("if ! uv run python") :]
    command = command.replace(
        "scripts/classify_windows_pytest_failure.py",
        shlex.quote(str(root / "scripts/classify_windows_pytest_failure.py")),
    )
    nodeids = [
        "tests/test_a.py::test_x[with spaces]",
        r"tests/test_b.py::test_x[a'b\*$HOME]",
    ]
    reason = (
        "Failed: Unit test exceeded per-test budget: 9.01s > 8.0s."
        if budget_only
        else "AssertionError: actual behavior changed"
    )
    (tmp_path / "pytest-output.txt").write_text(
        "".join(f"FAILED {nodeid} - {reason}\n" for nodeid in nodeids),
        encoding="utf-8",
        newline="",
    )
    prefix = """
uv() {
  shift
  if [ "$1" = python ]; then
    shift
    "$TSA_TEST_PYTHON" "$@"
  else
    printf '%s\\0' "$@" > retry-argv.bin
  fi
}
test_status=1
"""
    bash = "/bin/bash" if sys.platform == "darwin" else shutil.which("bash")
    assert bash is not None
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-c", prefix + command],
        cwd=tmp_path,
        capture_output=True,
        env={
            **os.environ,
            "TSA_TEST_PYTHON": Path(sys.executable).as_posix(),
            "RUNNER_OS": "test",
        },
    )
    assert result.returncode == (0 if budget_only else 1), result.stderr
    receipt = tmp_path / "retry-argv.bin"
    if budget_only:
        assert receipt.read_bytes().split(b"\0") == [
            value.encode()
            for value in [
                "pytest",
                *nodeids,
                "-n",
                "auto",
                "-q",
                "--tb=short",
                "--maxfail=200",
                "",
            ]
        ]
    else:
        assert receipt.exists() is False


@pytest.mark.parametrize("profile", ["test-matrix-pr", "test-matrix-full"])
def test_coverage_failure_retains_diagnostics(tmp_path: Path, profile: str) -> None:
    """覆盖率失败必须在普通日志和诊断附件中保留，不能只写网页摘要。"""
    # 2026-09-09：PR #1431 作业 102450961508 只留下 exit 1，真实 pytest 错误丢失。
    import os
    import shutil
    import subprocess

    import yaml

    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/reusable-test.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"][profile]["steps"]
    coverage = next(step for step in steps if step.get("id") == "test-coverage")
    artifact = next(
        step for step in steps if step.get("name") == "Upload failed test diagnostics"
    )
    assert artifact["if"] == "failure() && hashFiles('pytest-output.txt') != ''"
    assert artifact["uses"] == "actions/upload-artifact@v7.0.1"
    assert artifact["with"]["path"] == "pytest-output.txt"
    assert artifact["with"]["name"] == (
        "pytest-failure-${{ inputs.matrix-profile }}-${{ matrix.os }}"
        "-py${{ matrix.python-version }}-attempt${{ github.run_attempt }}"
    )
    bash = "/bin/bash" if sys.platform == "darwin" else shutil.which("bash")
    assert bash is not None
    failure = "FAILED tests/test_subject.py::test_behavior - AssertionError: sentinel"
    prefix = f"uv() {{ printf '%s\\n' '{failure}'; return 1; }}\n"
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-c", prefix + coverage["run"]],
        cwd=tmp_path,
        capture_output=True,
        env={**os.environ, "GITHUB_STEP_SUMMARY": (tmp_path / "summary").as_posix()},
    )
    assert result.returncode == 1
    assert failure.encode() in result.stdout
    assert (tmp_path / "pytest-output.txt").read_text(
        encoding="utf-8"
    ) == failure + "\n"
