"""Self-tests for scripts/check_loose_assertions.py.

RED-first: each test was written before the corresponding production code
path was implemented, ensuring the logic is exercised by the tests and not
just green by accident.

Coverage scenarios:
- Multiline assert with >= is caught  (the primary blind spot of the old grep)
- Inline assert with >= is caught
- Inline assert with > 0 is caught
- Exemption marker on the same line exempts the assert
- Exemption marker on the closing paren of a multiline assert also exempts
- assert == N is NOT flagged (exact assertion)
- String literal ">=" is NOT flagged (AST parses it as a string, not a compare)
- len() >= N is caught
- Property test file is skipped
- Baseline counter counts violations correctly
- check_file returns no violations for a clean file
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the module under test from the scripts directory
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _PROJECT_ROOT / "scripts" / "check_loose_assertions.py"

_spec = importlib.util.spec_from_file_location("check_loose_assertions", _SCRIPT_PATH)
assert _spec is not None, f"Cannot find {_SCRIPT_PATH}"
_checker = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["check_loose_assertions"] = _checker
_spec.loader.exec_module(_checker)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _violations_in_source(source: str) -> list[_checker.Violation]:
    """Parse *source* as a synthetic test file and return violations."""
    import os
    import tempfile

    # Write to a temp file so check_file can read it
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(source)
        tmp_path = Path(tmp.name)
    try:
        return _checker.check_file(tmp_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_multiline_assert_gte_is_caught() -> None:
    """Multiline assert with >= should be flagged — the primary blind spot."""
    source = textwrap.dedent("""\
        def test_example():
            result = [1, 2, 3]
            assert (
                len(result)
                >= 2
            )
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 1


def test_inline_assert_gte_is_caught() -> None:
    source = textwrap.dedent("""\
        def test_example():
            count = 5
            assert count >= 1
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 1


def test_inline_assert_gt_zero_is_caught() -> None:
    source = textwrap.dedent("""\
        def test_example():
            count = 5
            assert count > 0
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 1


def test_len_gte_is_caught() -> None:
    source = textwrap.dedent("""\
        def test_example():
            items = [1, 2, 3]
            assert len(items) >= 1
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 1


def test_exemption_marker_on_same_line_exempts() -> None:
    """# ratchet: nondeterministic on the assert line should suppress it."""
    source = textwrap.dedent("""\
        def test_example():
            count = 5
            assert count >= 1  # ratchet: nondeterministic timing-sensitive
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 0


def test_exemption_marker_on_closing_paren_of_multiline_exempts() -> None:
    """Marker on the closing line of a multiline assert should also exempt."""
    source = textwrap.dedent("""\
        def test_example():
            result = [1, 2, 3]
            assert (
                len(result)
                >= 2
            )  # ratchet: nondeterministic depends on platform
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 0


def test_exact_equality_assert_not_flagged() -> None:
    """assert x == N is an exact assertion — must never be flagged."""
    source = textwrap.dedent("""\
        def test_example():
            count = 5
            assert count == 5
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 0


def test_string_literal_gte_not_flagged() -> None:
    """A '>=' inside a string literal is not a loose comparison."""
    source = textwrap.dedent("""\
        def test_example():
            assert "requires >= 3.10" in "requires >= 3.10"
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 0


def test_clean_file_returns_no_violations(tmp_path: Path) -> None:
    clean = tmp_path / "test_clean.py"
    clean.write_text(
        textwrap.dedent("""\
            def test_exact():
                assert 1 + 1 == 2

            def test_negative():
                assert not False
        """),
        encoding="utf-8",
    )
    assert _checker.check_file(clean) == []


def test_baseline_counter_counts_violations(tmp_path: Path) -> None:
    """count_baseline should return the exact number of loose asserts."""
    # Two files, three violations total (one file has 2, other has 1)
    (tmp_path / "test_a.py").write_text(
        textwrap.dedent("""\
            def test_one():
                assert x >= 1

            def test_two():
                assert y > 0
        """),
        encoding="utf-8",
    )
    (tmp_path / "test_b.py").write_text(
        textwrap.dedent("""\
            def test_three():
                assert len(z) >= 3
        """),
        encoding="utf-8",
    )
    assert _checker.count_baseline(tmp_path) == 3


def test_property_file_skipped_in_baseline(tmp_path: Path) -> None:
    """Files matching *propert* (case-insensitive) should be skipped."""
    (tmp_path / "test_property_something.py").write_text(
        textwrap.dedent("""\
            def test_prop():
                assert x >= 1
        """),
        encoding="utf-8",
    )
    assert _checker.count_baseline(tmp_path) == 0


def test_multiple_violations_in_one_file() -> None:
    source = textwrap.dedent("""\
        def test_a():
            assert count >= 1

        def test_b():
            assert result > 0

        def test_c():
            assert len(items) >= 2
    """)
    violations = _violations_in_source(source)
    assert len(violations) == 3
