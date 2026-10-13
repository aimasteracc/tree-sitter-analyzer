"""RFC-0026 §3/§5 B1：verification 命令结局与进程生命周期。

每个测试只断言一个精确结果；最后一个测试用已提交 corpus 的参考补丁走真实
``uv run pytest`` 链路。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.unit.no1_010b._verifier_helpers import (
    CORPUS_ROOT,
    EXTRA_PY,
    GOOD_PATCH,
    diff,
    kill_quietly,
    make_record,
    reference_patch,
    spawn_grandchild_argv,
    still_running,
    verify,
)
from tree_sitter_analyzer.no1_010b.record_loader import load_corpus_records
from tree_sitter_analyzer.no1_010b.runner import Verdict
from tree_sitter_analyzer.no1_010b.transcript_specs import REFERENCE_TASK_ID
from tree_sitter_analyzer.no1_010b.verifier import verify_patch

# Windows 上 0xC0000005（访问冲突）以无符号 DWORD 上报；POSIX 上 SIGKILL 为 -9。
CRASH = (
    "import os\n"
    "if os.name == 'nt':\n"
    "    os._exit(-1073741819)\n"
    "os.kill(os.getpid(), 9)\n"
)


def test_patch_passing_oracle_but_breaking_verification_fails_it(
    value_corpus: Path,
) -> None:
    # RFC-0026 §5：oracle 只看 src/value.py；补丁同时破坏了 verification 导入的模块。
    patch = GOOD_PATCH + diff("src/extra.py", EXTRA_PY, "def extra(:\n    return 1\n")
    assert verify(value_corpus, patch) == Verdict("FAIL", "VERIFICATION_FAILED")


def test_unspawnable_verification_is_execution_error(value_corpus: Path) -> None:
    record = make_record(verification_argv=["no1-010b-no-such-executable", "--help"])
    assert verify(value_corpus, GOOD_PATCH, record=record) == Verdict(
        "UNKNOWN", "VERIFICATION_EXECUTION_ERROR"
    )


def test_crashed_verification_is_execution_error(value_corpus: Path) -> None:
    record = make_record(verification_argv=[sys.executable, "-c", CRASH])
    assert verify(value_corpus, GOOD_PATCH, record=record) == Verdict(
        "UNKNOWN", "VERIFICATION_EXECUTION_ERROR"
    )


# slow_ok：刻意等待真实墙钟超时再终止整个进程组，成本即被测行为本身。
@pytest.mark.slow_ok
def test_hanging_verification_is_verification_timeout(value_corpus: Path) -> None:
    record = make_record(
        verification_argv=[sys.executable, "-c", "import time; time.sleep(60)"]
    )
    assert verify(
        value_corpus, GOOD_PATCH, record=record, verification_timeout_s=1.0
    ) == Verdict("UNKNOWN", "VERIFICATION_TIMEOUT")


# slow_ok：真实孙进程 + 墙钟超时 + taskkill/killpg，成本即被测行为本身。
@pytest.mark.slow_ok
def test_verification_timeout_kills_the_process_tree(
    value_corpus: Path, tmp_path: Path
) -> None:
    pid_file = tmp_path / "grandchild.pid"
    argv = spawn_grandchild_argv(pid_file, linger=True)
    # 超时取 8 s：孙进程 pid 必须在超时触发前写出（xdist 负载下启动也够用）。
    verdict = verify(
        value_corpus,
        GOOD_PATCH,
        record=make_record(verification_argv=argv),
        verification_timeout_s=8.0,
    )
    pid = int(pid_file.read_text())
    try:
        observed = (verdict, still_running(pid))
    finally:
        kill_quietly(pid)
    assert observed == (Verdict("UNKNOWN", "VERIFICATION_TIMEOUT"), False)


# slow_ok：真实孙进程存活轮询，成本即被测行为本身。
@pytest.mark.slow_ok
@pytest.mark.xfail(
    sys.platform == "win32",
    strict=True,
    reason=(
        "known gap, tracked: RFC-0026 B1 process_escape_containment; taskkill /T "
        "cannot reach orphans once the command's own process has exited"
    ),
)
def test_normal_exit_terminates_leftover_process_group(
    value_corpus: Path, tmp_path: Path
) -> None:
    pid_file = tmp_path / "grandchild.pid"
    argv = spawn_grandchild_argv(pid_file, linger=False)
    verify(value_corpus, GOOD_PATCH, record=make_record(verification_argv=argv))
    pid = int(pid_file.read_text())
    try:
        alive = still_running(pid)
    finally:
        kill_quietly(pid)
    assert alive is False


# slow + slow_ok：真实 ``uv run pytest`` 验证已提交夹具，是唯一端到端正向对照；
# Windows CI 在 xdist 下需要远超默认 30 s 的墙钟。
@pytest.mark.slow
@pytest.mark.slow_ok
@pytest.mark.timeout(300)
def test_committed_reference_patch_passes_implemented_checks() -> None:
    records = load_corpus_records(str(CORPUS_ROOT / "corpus.jsonl"))
    (record,) = (item for item in records if item.id == REFERENCE_TASK_ID)
    outcome = verify_patch(record, CORPUS_ROOT, reference_patch(record))
    assert outcome.checks_verdict == Verdict("PASS")
