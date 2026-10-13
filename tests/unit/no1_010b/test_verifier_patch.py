"""RFC-0026 §5 B1：补丁输入、allowlist 与判定权（terminal vs provisional）。

只有在任何候选代码运行之前判定的结局才是终态；其余一律 provisional。
每个测试只断言一个精确的结果。
"""

from __future__ import annotations

from pathlib import Path

from tests.unit.no1_010b._verifier_helpers import (
    EXPECTED_NOT_IMPLEMENTED,
    GOOD_PATCH,
    diff,
    make_record,
    value_patch,
    verify,
)
from tree_sitter_analyzer.no1_010b.patch import PATCH_MAX_LINES_PER_HUNK
from tree_sitter_analyzer.no1_010b.runner import Verdict
from tree_sitter_analyzer.no1_010b.verifier import verify_patch

CONTEXT_MISMATCH = diff(
    "src/value.py", "def value():\n    return 7\n", "def value():\n    return 2\n"
)
ESCAPING_PATCH = GOOD_PATCH + diff("src-escape/evil.py", "", "EVIL = True\n")


def test_correct_patch_passes_every_implemented_check(value_corpus: Path) -> None:
    # verification 会导入 src；字节码必须重定向到 scratch，否则是 PATH_VIOLATION。
    assert verify(value_corpus, GOOD_PATCH) == Verdict("PASS")


def test_implemented_pass_is_not_a_terminal_pass(value_corpus: Path) -> None:
    assert verify_patch(make_record(), value_corpus, GOOD_PATCH).terminal is None


def test_unimplemented_checks_are_reported_exactly(value_corpus: Path) -> None:
    outcome = verify_patch(make_record(), value_corpus, GOOD_PATCH)
    assert outcome.checks_not_implemented == EXPECTED_NOT_IMPLEMENTED


def test_test_selection_task_also_reports_selection_check(value_corpus: Path) -> None:
    record = make_record(task_class="test_selection", selected_tests=["tests/a.py"])
    outcome = verify_patch(record, value_corpus, GOOD_PATCH)
    assert outcome.checks_not_implemented == (
        *EXPECTED_NOT_IMPLEMENTED,
        "test_selection",
    )


def test_oracle_verdict_after_candidate_code_is_provisional(
    value_corpus: Path,
) -> None:
    patch = value_patch("def value():\n    return 3\n")
    assert verify_patch(make_record(), value_corpus, patch).terminal is None


def test_provisional_verdict_names_the_missing_authority(value_corpus: Path) -> None:
    patch = value_patch("def value():\n    return 3\n")
    outcome = verify_patch(make_record(), value_corpus, patch)
    assert outcome.authority_requires == ("read_only_candidate_mount", "write_journal")


def test_context_mismatch_is_patch_not_applicable(value_corpus: Path) -> None:
    assert verify(value_corpus, CONTEXT_MISMATCH) == Verdict(
        "UNKNOWN", "PATCH_NOT_APPLICABLE"
    )


def test_git_apply_rejection_is_terminal(value_corpus: Path) -> None:
    outcome = verify_patch(make_record(), value_corpus, CONTEXT_MISMATCH)
    assert outcome.terminal == Verdict("UNKNOWN", "PATCH_NOT_APPLICABLE")


def test_malformed_patch_is_patch_not_applicable(value_corpus: Path) -> None:
    assert verify(value_corpus, "not a diff\n") == Verdict(
        "UNKNOWN", "PATCH_NOT_APPLICABLE"
    )


def _big_file_patch(line_count: int) -> str:
    body = "".join(f"X{index} = {index}\n" for index in range(line_count))
    return GOOD_PATCH + diff("src/big.py", "", body)


def test_hunk_exactly_at_line_limit_is_processed(value_corpus: Path) -> None:
    patch = _big_file_patch(PATCH_MAX_LINES_PER_HUNK)
    assert verify(value_corpus, patch) == Verdict("PASS")


def test_hunk_one_over_line_limit_is_patch_over_bound(value_corpus: Path) -> None:
    patch = _big_file_patch(PATCH_MAX_LINES_PER_HUNK + 1)
    assert verify(value_corpus, patch) == Verdict("UNKNOWN", "PATCH_OVER_BOUND")


def test_over_bound_patch_is_terminal(value_corpus: Path) -> None:
    patch = _big_file_patch(PATCH_MAX_LINES_PER_HUNK + 1)
    outcome = verify_patch(make_record(), value_corpus, patch)
    assert outcome.terminal == Verdict("UNKNOWN", "PATCH_OVER_BOUND")


def test_segment_escaping_path_is_path_violation(value_corpus: Path) -> None:
    assert verify(value_corpus, ESCAPING_PATCH) == Verdict("FAIL", "PATH_VIOLATION")


def test_allowlist_path_violation_is_terminal(value_corpus: Path) -> None:
    outcome = verify_patch(make_record(), value_corpus, ESCAPING_PATCH)
    assert outcome.terminal == Verdict("FAIL", "PATH_VIOLATION")


def test_outcome_exposes_a_sha256_env_digest(value_corpus: Path) -> None:
    outcome = verify_patch(make_record(), value_corpus, GOOD_PATCH)
    assert len(outcome.env_digest or "") == 64
