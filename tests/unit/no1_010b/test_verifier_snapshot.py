"""RFC-0026 §2/§5 B1：候选树快照复核与 corpus 篡改检测。

候选树任何新增、删除、内容或 mode 改变（含特殊文件与不可读条目）都是
``FAIL/PATH_VIOLATION``；corpus 中本次使用的夹具/oracle 树被改动则 attempt 无效
（``UNKNOWN/SANDBOX_FAILURE``）。每个测试只断言一个精确对。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.unit.no1_010b._verifier_helpers import (
    GOOD_PATCH,
    make_record,
    value_patch,
    verify,
)
from tree_sitter_analyzer.no1_010b.runner import Verdict


def _with_verification(value_corpus: Path, script: str) -> Verdict:
    record = make_record(verification_argv=[sys.executable, "-c", script])
    return verify(value_corpus, GOOD_PATCH, record=record)


def test_verification_untracked_write_is_path_violation(value_corpus: Path) -> None:
    verdict = _with_verification(value_corpus, "open('untracked.txt', 'w').write('x')")
    assert verdict == Verdict("FAIL", "PATH_VIOLATION")


def test_oracle_write_inside_allowed_path_is_path_violation(
    value_corpus: Path,
) -> None:
    writes = (
        "def value():\n    open('src/side_effect.txt', 'w').write('x')\n    return 2\n"
    )
    assert verify(value_corpus, value_patch(writes)) == Verdict(
        "FAIL", "PATH_VIOLATION"
    )


def test_mode_only_change_is_path_violation(value_corpus: Path) -> None:
    verdict = _with_verification(
        value_corpus, "import os; os.chmod('src/value.py', 0o444)"
    )
    assert verdict == Verdict("FAIL", "PATH_VIOLATION")


def test_unreadable_candidate_file_is_path_violation(value_corpus: Path) -> None:
    # 审查者的 chmod 逃逸：快照不可读条目必须是 PATH_VIOLATION，不是 SANDBOX_FAILURE。
    verdict = _with_verification(value_corpus, "import os; os.chmod('src/value.py', 0)")
    assert verdict == Verdict("FAIL", "PATH_VIOLATION")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: Windows has no FIFO special files (tracked: RFC-0026 B1)",
)
def test_fifo_in_candidate_tree_is_path_violation(value_corpus: Path) -> None:
    # 快照只 lstat 特殊文件、绝不打开，因此 FIFO 不会让 runner 阻塞。
    verdict = _with_verification(value_corpus, "import os; os.mkfifo('src/pipe')")
    assert verdict == Verdict("FAIL", "PATH_VIOLATION")


def test_unknown_oracle_outcome_outranks_later_path_violation(
    value_corpus: Path,
) -> None:
    # runner.classify 的优先级：UNKNOWN 先于任何 FAIL，即使快照随后发现写入。
    body = (
        "def value():\n"
        "    open('src/side_effect.txt', 'w').write('x')\n"
        "    raise RuntimeError('boom')\n"
    )
    assert verify(value_corpus, value_patch(body)) == Verdict(
        "UNKNOWN", "ORACLE_EXECUTION_ERROR"
    )


def test_corpus_tampering_is_sandbox_failure(value_corpus: Path) -> None:
    target = value_corpus / "oracles" / "value.py"
    body = (
        f"open({str(target)!r}, 'a').write('# tampered\\n')\n\n\n"
        "def value():\n    return 2\n"
    )
    assert verify(value_corpus, value_patch(body)) == Verdict(
        "UNKNOWN", "SANDBOX_FAILURE"
    )
