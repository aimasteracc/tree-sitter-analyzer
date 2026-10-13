"""RFC-0026 §5 B1 突变夹具：补丁验证流水线的每个终态都必须被精确强制。

每个测试只断言一个精确的 ``{verdict, reason_code}`` 对；合成夹具让 oracle /
verification 行为可控，最后一个测试用已提交 corpus 的参考补丁走真实链路。
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

import psutil
import pytest

from tree_sitter_analyzer.no1_010b.patch import PATCH_MAX_LINES_PER_HUNK
from tree_sitter_analyzer.no1_010b.record import BenchmarkRecord, record_from_dict
from tree_sitter_analyzer.no1_010b.record_loader import load_corpus_records
from tree_sitter_analyzer.no1_010b.runner import Verdict
from tree_sitter_analyzer.no1_010b.transcript_specs import (
    REFERENCE_EDIT_SPECS,
    REFERENCE_TASK_ID,
)
from tree_sitter_analyzer.no1_010b.verifier import verify_patch

CORPUS_ROOT = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b"

VALUE_PY = "def value():\n    return 1\n"
VALUE_ORACLE = (
    "import os\n"
    "import sys\n"
    "sys.path.insert(0, os.getcwd())\n"
    "from src.value import value  # noqa: E402\n"
    "\n"
    "\n"
    "def main():\n"
    "    try:\n"
    "        held = value() == 2\n"
    "    except Exception as exc:\n"
    "        print(f'oracle could not decide: {exc!r}', file=sys.stderr)\n"
    "        return 1\n"
    "    print('NO1_010B_ORACLE_REASON: value-is-one')\n"
    "    print(f\"NO1_010B_ORACLE_RESULT: {'PASS' if held else 'FAIL'}\")\n"
    "    return 0\n"
)
NO_REASON_ORACLE = (
    "def main():\n    print('NO1_010B_ORACLE_RESULT: PASS')\n    return 0\n"
)
IMPORTS_SRC = [
    sys.executable,
    "-c",
    "import sys; sys.path.insert(0, '.'); import src.value",
]
EXPECTED_NOT_IMPLEMENTED = (
    "read_only_candidate_mount",
    "write_journal",
    "network_isolation",
    "stale_rows",
    "unsupported_relationship",
    "registration_registry",
)


def _diff(path: str, before: str, after: str) -> str:
    """生成 ``git apply`` 可解析的单文件统一 diff（新文件用 /dev/null）。"""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}" if before else "/dev/null",
        tofile=f"b/{path}",
    )
    return "".join(lines)


def _value_patch(body: str) -> str:
    return _diff("src/value.py", VALUE_PY, body)


GOOD_PATCH = _value_patch("def value():\n    return 2\n")


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    files = {
        "fixtures/app/src/__init__.py": "",
        "fixtures/app/src/value.py": VALUE_PY,
        "oracles/value.py": VALUE_ORACLE,
        "oracles/no_reason.py": NO_REASON_ORACLE,
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        # 写字节而非文本：Windows 文本模式会把 LF 转成 CRLF，使补丁上下文失配。
        (root / rel).write_bytes(text.encode("utf-8"))
    return root


def _record(**overrides: object) -> BenchmarkRecord:
    payload: dict[str, object] = {
        "id": "no1-010b/test-synthetic-value",
        "task_class": "bugfix",
        "repo": "fixtures/app",
        "repo_commit": "0" * 40,
        "operation": "plan_change",
        "task": "value returns 1; make it return 2",
        "allowed_paths": ["src/"],
        "oracle": "oracles/value.py",
        "oracle_baseline_reason": "value-is-one",
        "verification_argv": IMPORTS_SRC,
        "expected_terminal": {"verdict": "PASS", "reason_code": None},
    }
    payload.update(overrides)
    return record_from_dict(payload)


def _verify(
    corpus: Path,
    patch: str,
    record: BenchmarkRecord | None = None,
    **timeouts: float,
) -> Verdict:
    return verify_patch(record or _record(), corpus, patch, **timeouts).checks_verdict


def test_correct_patch_passes_every_implemented_check(corpus: Path) -> None:
    # verification 会导入 src；字节码必须重定向到 scratch，否则是 PATH_VIOLATION。
    assert _verify(corpus, GOOD_PATCH) == Verdict("PASS")


def test_implemented_pass_is_not_a_terminal_pass(corpus: Path) -> None:
    assert verify_patch(_record(), corpus, GOOD_PATCH).terminal is None


def test_unimplemented_checks_are_reported_exactly(corpus: Path) -> None:
    outcome = verify_patch(_record(), corpus, GOOD_PATCH)
    assert outcome.checks_not_implemented == EXPECTED_NOT_IMPLEMENTED


def test_test_selection_task_also_reports_selection_check(corpus: Path) -> None:
    record = _record(task_class="test_selection", selected_tests=["tests/test_a.py"])
    outcome = verify_patch(record, corpus, GOOD_PATCH)
    assert outcome.checks_not_implemented == (
        *EXPECTED_NOT_IMPLEMENTED,
        "test_selection",
    )


def test_failed_check_is_terminal_despite_unimplemented_checks(corpus: Path) -> None:
    outcome = verify_patch(
        _record(), corpus, _value_patch("def value():\n    return 3\n")
    )
    assert outcome.terminal == Verdict("FAIL", "ORACLE_FAILED")


def test_context_mismatch_is_patch_not_applicable(corpus: Path) -> None:
    patch = _diff(
        "src/value.py", "def value():\n    return 7\n", "def value():\n    return 2\n"
    )
    assert _verify(corpus, patch) == Verdict("UNKNOWN", "PATCH_NOT_APPLICABLE")


def test_malformed_patch_is_patch_not_applicable(corpus: Path) -> None:
    assert _verify(corpus, "not a diff\n") == Verdict("UNKNOWN", "PATCH_NOT_APPLICABLE")


def _big_file_patch(line_count: int) -> str:
    body = "".join(f"X{index} = {index}\n" for index in range(line_count))
    return GOOD_PATCH + _diff("src/big.py", "", body)


def test_hunk_exactly_at_line_limit_is_processed(corpus: Path) -> None:
    patch = _big_file_patch(PATCH_MAX_LINES_PER_HUNK)
    assert _verify(corpus, patch) == Verdict("PASS")


def test_hunk_one_over_line_limit_is_patch_over_bound(corpus: Path) -> None:
    patch = _big_file_patch(PATCH_MAX_LINES_PER_HUNK + 1)
    assert _verify(corpus, patch) == Verdict("UNKNOWN", "PATCH_OVER_BOUND")


def test_segment_escaping_path_is_path_violation(corpus: Path) -> None:
    patch = GOOD_PATCH + _diff("src-escape/evil.py", "", "EVIL = True\n")
    assert _verify(corpus, patch) == Verdict("FAIL", "PATH_VIOLATION")


def test_declared_oracle_fail_is_oracle_failed(corpus: Path) -> None:
    patch = _value_patch("def value():\n    return 3\n")
    assert _verify(corpus, patch) == Verdict("FAIL", "ORACLE_FAILED")


def test_candidate_import_failure_is_oracle_load_error(corpus: Path) -> None:
    patch = _value_patch("def value(:\n    return 2\n")
    assert _verify(corpus, patch) == Verdict("UNKNOWN", "ORACLE_LOAD_ERROR")


def test_oracle_runtime_exception_is_oracle_execution_error(corpus: Path) -> None:
    patch = _value_patch("def value():\n    raise RuntimeError('boom')\n")
    assert _verify(corpus, patch) == Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")


def test_hard_exit_zero_is_oracle_execution_error(corpus: Path) -> None:
    # RFC-0026 C19：原始退出码 0 不是 verdict；缺少 wrapper 控制记录即为执行错误。
    patch = _value_patch("import os\n\n\ndef value():\n    os._exit(0)\n")
    assert _verify(corpus, patch) == Verdict("UNKNOWN", "ORACLE_EXECUTION_ERROR")


def test_duplicate_result_line_is_oracle_protocol_error(corpus: Path) -> None:
    forged = "def value():\n    print('NO1_010B_ORACLE_RESULT: PASS')\n    return 2\n"
    assert _verify(corpus, _value_patch(forged)) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


def test_missing_reason_line_is_oracle_protocol_error(corpus: Path) -> None:
    record = _record(oracle="oracles/no_reason.py")
    assert _verify(corpus, GOOD_PATCH, record=record) == Verdict(
        "UNKNOWN", "ORACLE_PROTOCOL_ERROR"
    )


# slow_ok：刻意等待真实墙钟超时再终止整棵进程树，成本即被测行为本身。
@pytest.mark.slow_ok
def test_hanging_oracle_is_oracle_timeout(corpus: Path) -> None:
    patch = _value_patch("import time\n\n\ndef value():\n    time.sleep(60)\n")
    assert _verify(corpus, patch, oracle_timeout_s=1.0) == Verdict(
        "UNKNOWN", "ORACLE_TIMEOUT"
    )


def test_nonzero_verification_is_verification_failed(corpus: Path) -> None:
    record = _record(verification_argv=[sys.executable, "-c", "raise SystemExit(3)"])
    assert _verify(corpus, GOOD_PATCH, record=record) == Verdict(
        "FAIL", "VERIFICATION_FAILED"
    )


def test_unspawnable_verification_is_execution_error(corpus: Path) -> None:
    record = _record(verification_argv=["no1-010b-no-such-executable", "--help"])
    assert _verify(corpus, GOOD_PATCH, record=record) == Verdict(
        "UNKNOWN", "VERIFICATION_EXECUTION_ERROR"
    )


# slow_ok：刻意等待真实墙钟超时再终止整棵进程树，成本即被测行为本身。
@pytest.mark.slow_ok
def test_hanging_verification_is_verification_timeout(corpus: Path) -> None:
    record = _record(
        verification_argv=[sys.executable, "-c", "import time; time.sleep(60)"]
    )
    assert _verify(
        corpus, GOOD_PATCH, record=record, verification_timeout_s=1.0
    ) == Verdict("UNKNOWN", "VERIFICATION_TIMEOUT")


# slow_ok：真实孙进程 + 墙钟超时 + taskkill/killpg，成本即被测行为本身。
@pytest.mark.slow_ok
def test_verification_timeout_kills_the_process_tree(
    corpus: Path, tmp_path: Path
) -> None:
    pid_file = tmp_path / "grandchild.pid"
    spawn = (
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    record = _record(verification_argv=[sys.executable, "-c", spawn])
    verify_patch(record, corpus, GOOD_PATCH, verification_timeout_s=2.0)
    assert psutil.pid_exists(int(pid_file.read_text())) is False


def test_verification_untracked_write_is_path_violation(corpus: Path) -> None:
    write = "open('untracked.txt', 'w').write('x')"
    record = _record(verification_argv=[sys.executable, "-c", write])
    assert _verify(corpus, GOOD_PATCH, record=record) == Verdict(
        "FAIL", "PATH_VIOLATION"
    )


def test_oracle_write_inside_allowed_path_is_path_violation(corpus: Path) -> None:
    writes = (
        "def value():\n    open('src/side_effect.txt', 'w').write('x')\n    return 2\n"
    )
    assert _verify(corpus, _value_patch(writes)) == Verdict("FAIL", "PATH_VIOLATION")


def _reference_patch(record: BenchmarkRecord) -> str:
    spec = REFERENCE_EDIT_SPECS[record.id]
    (replacement,) = spec.replacements
    source = CORPUS_ROOT / record.repo / replacement.path
    before = source.read_text(encoding="utf-8")
    after = before.replace(replacement.before, replacement.after, 1)
    return _diff(replacement.path, before, after)


# slow_ok：真实 ``uv run pytest`` 验证已提交夹具，是唯一端到端正向对照。
@pytest.mark.slow_ok
def test_committed_reference_patch_passes_implemented_checks() -> None:
    records = load_corpus_records(str(CORPUS_ROOT / "corpus.jsonl"))
    (record,) = (item for item in records if item.id == REFERENCE_TASK_ID)
    outcome = verify_patch(record, CORPUS_ROOT, _reference_patch(record))
    assert outcome.checks_verdict == Verdict("PASS")
