"""UTF-8 encoding regression tests for ``read_source_file`` (health scorer).

Background: ``_health_scorer_helpers.read_source_file`` previously called
``path.read_text()`` without an ``encoding`` argument. On hosts whose default
locale encoding is not UTF-8 (e.g. Windows cp1252/cp932/mbcs), decoding a
UTF-8 source file with non-ASCII bytes raised ``UnicodeDecodeError``; the
broad ``except`` swallowed it and returned ``None``, which made
``HealthScorer.score_file`` emit a false ``HealthScore(total=0.0,
dimensions={})`` (bogus grade F / ``no_data``). The fix pins UTF-8 with
``errors="replace"``.

These tests are written to be DETERMINISTIC regardless of the host's default
encoding: the regression cannot be reproduced by relying on the host locale
(a UTF-8 host would never fail pre-fix), so the locale-default failure is
simulated by monkeypatching ``Path.read_text`` to reject calls that omit an
explicit ``encoding`` — pinning the requirement that ``read_source_file``
names UTF-8 explicitly.

Traceability:
  - AC-1 / REQ-ENC-002 / REQ-ENC-005 -> test_non_ascii_file_fills_dimensions
  - AC-2 / REQ-ENC-006             -> test_ascii_only_file_score_unchanged
  - AC-3 / REQ-ENC-003             -> test_invalid_utf8_bytes_returns_str_no_exception
  - REQ-ENC-004                    -> test_nonexistent_file_returns_none
  - AC-4 / REQ-NFR-003             -> test_non_ascii_roundtrips_host_independent
  - AC-1 RED proof / REQ-ENC-001   -> test_read_text_called_with_utf8_encoding
"""

import sys
from pathlib import Path

import pytest

# Non-ASCII fixture content reused across cases (Japanese comment + string).
_NON_ASCII_SOURCE = "# 日本語コメント\nmessage = 'こんにちは世界'\nx = 1\n"


@pytest.mark.regression
def test_non_ascii_file_fills_dimensions(tmp_path):
    """AC-1 / REQ-ENC-002 / REQ-ENC-005: a UTF-8 file with non-ASCII content
    must score with a populated breakdown (not the bogus empty/F result)."""
    from tree_sitter_analyzer.health_scorer import HealthScorer

    source = tmp_path / "japanese.py"
    source.write_text(_NON_ASCII_SOURCE, encoding="utf-8")

    result = HealthScorer().score_file(str(source))

    # Pre-fix on a non-UTF-8 host: dimensions == {} and total == 0.0 (false F).
    assert len(result.dimensions) > 0, (
        f"Expected populated dimensions for a readable UTF-8 file, got "
        f"{result.dimensions}"
    )
    assert result.total > 0, (
        f"Expected a positive health total for a readable UTF-8 file, got "
        f"{result.total}"
    )


@pytest.mark.regression
def test_ascii_only_file_score_unchanged(tmp_path):
    """AC-2 / REQ-ENC-006: pure-ASCII content decodes identically under any
    default encoding, so the score must remain the expected baseline and be
    deterministic across repeated scoring."""
    from tree_sitter_analyzer.health_scorer import HealthScorer

    source = tmp_path / "ascii.py"
    source.write_text("x = 1\n", encoding="utf-8")

    first = HealthScorer().score_file(str(source))
    second = HealthScorer().score_file(str(source))

    # Single trivial line outside a git repo: every dimension scores 100.0,
    # matching tests/unit/test_health_scorer.py::test_git_hotspot_none_outside_git.
    assert first.total == 100.0, (
        f"Pure-ASCII single-line file should score 100.0, got {first.total}"
    )
    assert len(first.dimensions) > 0
    assert first.total == second.total, (
        "Scoring the same ASCII file twice must be deterministic"
    )


@pytest.mark.regression
def test_invalid_utf8_bytes_returns_str_no_exception(tmp_path):
    """AC-3 / REQ-ENC-003: a file containing bytes that are not valid UTF-8
    must NOT raise and must NOT return None — ``errors='replace'`` lets the
    decode succeed (lossy) so health scoring never falls over."""
    from tree_sitter_analyzer.registry.health_scorer_helpers import read_source_file

    source = tmp_path / "invalid.py"
    source.write_bytes(b"x = 1  # \xff\xfe invalid utf8\n")

    result = read_source_file(source)

    assert result is not None, "Invalid UTF-8 bytes must not collapse to None"
    assert isinstance(result, str), f"Expected str, got {type(result)!r}"
    assert "x = 1" in result, "The valid ASCII portion must survive decoding"


@pytest.mark.regression
def test_nonexistent_file_returns_none(tmp_path):
    """REQ-ENC-004: a missing path must still return None (existing behaviour
    preserved — the fix changes encoding handling, not I/O-failure handling)."""
    from tree_sitter_analyzer.registry.health_scorer_helpers import read_source_file

    missing = tmp_path / "does_not_exist.py"

    assert read_source_file(missing) is None


@pytest.mark.regression
def test_non_ascii_roundtrips_host_independent(tmp_path):
    """AC-4 / REQ-NFR-003: a UTF-8 non-ASCII file must round-trip its
    non-ASCII characters back through ``read_source_file`` on any host
    (locale / PYTHONUTF8 independent), i.e. they are preserved, not mangled
    into U+FFFD replacement characters."""
    from tree_sitter_analyzer.registry.health_scorer_helpers import read_source_file

    source = tmp_path / "roundtrip.py"
    source.write_text(_NON_ASCII_SOURCE, encoding="utf-8")

    result = read_source_file(source)

    assert result is not None
    assert isinstance(result, str)
    assert "日本語" in result, (
        "Non-ASCII characters must round-trip unchanged (no lossy replacement "
        "for valid UTF-8 content)"
    )
    assert "�" not in result, (
        "Valid UTF-8 content must not yield U+FFFD replacement characters"
    )


@pytest.mark.regression
def test_read_text_called_with_utf8_encoding(tmp_path, monkeypatch):
    """AC-1 RED proof / REQ-ENC-001 (host-independent regression guard).

    Simulate a non-UTF-8 default-locale host by replacing ``Path.read_text``
    with a stub that mimics the broken behaviour: a call WITHOUT an explicit
    ``encoding`` raises ``UnicodeDecodeError`` (as cp1252/cp932 would on
    non-ASCII bytes), while a call pinning ``encoding='utf-8'`` succeeds.

    Pre-fix (``read_text()`` with no encoding) -> stub raises -> the broad
    ``except`` returns None -> this test FAILS (RED). Post-fix
    (``read_text(encoding='utf-8', errors='replace')``) -> stub returns the
    content -> GREEN. This locks the requirement that UTF-8 is named
    explicitly, so dropping the encoding in future immediately re-fails here.
    """
    from tree_sitter_analyzer.registry.health_scorer_helpers import read_source_file

    source = tmp_path / "locale_sensitive.py"
    source.write_text(_NON_ASCII_SOURCE, encoding="utf-8")

    seen_encodings: list[str | None] = []
    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        encoding = kwargs.get("encoding")
        seen_encodings.append(encoding)
        if encoding is None:
            # Emulate a non-UTF-8 locale default choking on UTF-8 bytes.
            raise UnicodeDecodeError("cp1252", b"\x00", 0, 1, "simulated")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    result = read_source_file(source)

    assert result is not None, (
        "read_source_file must pin encoding='utf-8' so it does not fall back "
        "to the locale default (which fails on non-ASCII bytes)"
    )
    assert isinstance(result, str)
    assert "utf-8" in seen_encodings, (
        f"read_source_file must call read_text with encoding='utf-8'; "
        f"observed encodings: {seen_encodings}"
    )
    assert "日本語" in result


@pytest.mark.regression
@pytest.mark.skipif(
    sys.platform != "win32",
    reason="locale-default decode failure only manifests on non-UTF-8 hosts; "
    "the host-independent guard above (monkeypatch) covers all platforms",
)
def test_score_file_non_ascii_not_false_f_on_windows(tmp_path):
    """AC-1 (Windows real-locale corroboration): on Windows, a UTF-8 file with
    non-ASCII content must produce a real score through the full
    ``score_file`` path, not the false-F empty result. Skipped off-Windows
    because the original defect cannot be reproduced via the host locale on a
    UTF-8 platform; the monkeypatch guard above is the cross-platform check."""
    from tree_sitter_analyzer.health_scorer import HealthScorer

    source = tmp_path / "windows_japanese.py"
    source.write_text(_NON_ASCII_SOURCE, encoding="utf-8")

    result = HealthScorer().score_file(str(source))

    assert result.dimensions, "Windows non-ASCII file must not yield empty dimensions"
    assert result.total > 0
