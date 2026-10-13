"""RFC-0026 §3/§5 B1：oracle 结局的每个 UNKNOWN 子码与 ORACLE_FAILED 精确对。

oracle 在同一进程内导入候选代码；补丁里的 ``value()`` 因此能操纵 oracle 进程。
每个测试只断言一个精确的 ``{verdict, reason_code}`` 对。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.no1_010b._verifier_helpers import (
    GOOD_PATCH,
    make_record,
    value_patch,
    verify,
)
from tree_sitter_analyzer.no1_010b.oracle import ORACLE_OUTPUT_MAX_BYTES
from tree_sitter_analyzer.no1_010b.runner import Verdict
from tree_sitter_analyzer.no1_010b.verifier import verify_patch

# 审查者的 stdout 替换伪造：先写出伪造的 PASS 声明，再把 sys.stdout 换成黑洞，
# 使 oracle 真实的 FAIL 声明无处可去。
STDOUT_SWAP_FORGE = (
    "import io, sys\n\n\n"
    "def value():\n"
    "    sys.stdout.write("
    "'NO1_010B_ORACLE_REASON: value-is-one\\nNO1_010B_ORACLE_RESULT: PASS\\n')\n"
    "    sys.stdout = io.StringIO()\n"
    "    return 3\n"
)


def test_declared_oracle_fail_is_oracle_failed(value_corpus: Path) -> None:
    patch = value_patch("def value():\n    return 3\n")
    assert verify(value_corpus, patch) == Verdict("FAIL", "ORACLE_FAILED")


def test_candidate_import_failure_is_oracle_load_error(value_corpus: Path) -> None:
    patch = value_patch("def value(:\n    return 2\n")
    assert verify(value_corpus, patch) == Verdict("UNKNOWN", "ORACLE_LOAD_ERROR")


def test_oracle_main_returning_nonzero_is_execution_error(value_corpus: Path) -> None:
    # 候选在 value() 中抛错，oracle 捕获后 main() 返回 1。
    patch = value_patch("def value():\n    raise RuntimeError('boom')\n")
    assert verify(value_corpus, patch) == Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")


def test_oracle_main_raising_is_execution_error(value_corpus: Path) -> None:
    record = make_record(oracle="oracles/raising.py")
    assert verify(value_corpus, GOOD_PATCH, record=record) == Verdict(
        "UNKNOWN", "ORACLE_EXECUTION_ERROR"
    )


def test_hard_exit_zero_is_oracle_execution_error(value_corpus: Path) -> None:
    # RFC-0026 C19：原始退出码 0 不是 verdict；缺少 wrapper 控制记录即为执行错误。
    patch = value_patch("import os\n\n\ndef value():\n    os._exit(0)\n")
    assert verify(value_corpus, patch) == Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")


def test_malformed_control_record_is_oracle_execution_error(
    value_corpus: Path,
) -> None:
    body = (
        "import os, sys\n\n\n"
        "def value():\n"
        "    open(sys.argv[2], 'w').write('{not json')\n"
        "    os._exit(0)\n"
    )
    assert verify(value_corpus, value_patch(body)) == Verdict(
        "UNKNOWN", "ORACLE_EXECUTION_ERROR"
    )


def test_duplicate_result_line_is_oracle_protocol_error(value_corpus: Path) -> None:
    forged = "def value():\n    print('NO1_010B_ORACLE_RESULT: PASS')\n    return 2\n"
    assert verify(value_corpus, value_patch(forged)) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


def test_missing_reason_line_is_oracle_protocol_error(value_corpus: Path) -> None:
    record = make_record(oracle="oracles/no_reason.py")
    assert verify(value_corpus, GOOD_PATCH, record=record) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


def test_capture_one_byte_over_limit_is_oracle_protocol_error(
    value_corpus: Path,
) -> None:
    # 界限按原始字节计数（与 B0 一致），且 fd 级写入同样进入捕获流。
    body = (
        "import os\n\n\n"
        "def value():\n"
        f"    os.write(1, b'x' * {ORACLE_OUTPUT_MAX_BYTES + 1})\n"
        "    return 2\n"
    )
    assert verify(value_corpus, value_patch(body)) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


def test_stderr_diagnostic_after_result_is_oracle_protocol_error(
    value_corpus: Path,
) -> None:
    # 解释器退出时写到 fd 2 的诊断位于结果行之后，声明因此不再是最终输出。
    body = (
        "import atexit, os\n\n\n"
        "def value():\n"
        "    atexit.register(os.write, 2, b'late diagnostic\\n')\n"
        "    return 2\n"
    )
    assert verify(value_corpus, value_patch(body)) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


def test_non_utf8_capture_is_oracle_protocol_error(value_corpus: Path) -> None:
    body = "import os\n\n\ndef value():\n    os.write(1, b'\\xff\\n')\n    return 2\n"
    assert verify(value_corpus, value_patch(body)) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


def test_deleted_capture_is_oracle_execution_error(value_corpus: Path) -> None:
    # POSIX 上候选删除捕获文件后 runner 无从读取；Windows 上删除被拒、value()
    # 抛错使 main() 返回 1——两条路径都必须是执行错误，绝不是 PASS。
    body = (
        "import os, sys\n\n\ndef value():\n    os.remove(sys.argv[3])\n    return 2\n"
    )
    assert verify(value_corpus, value_patch(body)) == Verdict(
        "UNKNOWN", "ORACLE_EXECUTION_ERROR"
    )


def test_wrapper_hard_exit_nonzero_is_oracle_execution_error(
    value_corpus: Path,
) -> None:
    patch = value_patch("import os\n\n\ndef value():\n    os._exit(3)\n")
    assert verify(value_corpus, patch) == Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")


def test_continuous_writer_is_protocol_error_before_timeout(
    value_corpus: Path,
) -> None:
    # Codex P2：上限在捕获期间执行；若只在退出后检查，此处会等到 60 s 超时。
    body = (
        "import os\n\n\n"
        "def value():\n"
        "    while True:\n"
        "        os.write(1, b'x' * 65536)\n"
    )
    assert verify(value_corpus, value_patch(body), oracle_timeout_s=60.0) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


# slow_ok：刻意等待真实墙钟超时再终止整个进程组，成本即被测行为本身。
@pytest.mark.slow_ok
def test_hanging_oracle_is_oracle_timeout(value_corpus: Path) -> None:
    patch = value_patch("import time\n\n\ndef value():\n    time.sleep(60)\n")
    assert verify(value_corpus, patch, oracle_timeout_s=1.0) == Verdict(
        "UNKNOWN", "ORACLE_TIMEOUT"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "known gap, tracked: RFC-0026 B1 read_only_candidate_mount/write_journal; "
        "in-process candidate code can forge the oracle stream, so a forged PASS "
        "still surfaces as a provisional PASS until the kernel sandbox exists"
    ),
)
def test_stdout_swap_forge_does_not_yield_pass(value_corpus: Path) -> None:
    outcome = verify_patch(make_record(), value_corpus, value_patch(STDOUT_SWAP_FORGE))
    assert outcome.checks_verdict != Verdict("PASS")
