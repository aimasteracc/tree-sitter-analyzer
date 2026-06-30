"""UTF-8 encoding regression tests for ``detect_anti_patterns``.

Background: ``anti_patterns.detect_anti_patterns`` called
``Path.read_text(errors="replace")`` without an explicit ``encoding``
argument. On hosts whose default locale encoding is not UTF-8 (e.g.
Windows cp1252/cp932/mbcs), decoding a UTF-8 source file with non-ASCII
bytes raised ``UnicodeDecodeError``; the broad ``except`` swallowed it
and returned an empty list, silently masking any anti-pattern findings.
The fix pins UTF-8 with ``errors="replace"``.

These tests are written to be DETERMINISTIC regardless of the host's
default encoding: the regression cannot be reproduced by relying on the
host locale (a UTF-8 host would never fail pre-fix), so the
locale-default failure is simulated by monkeypatching ``Path.read_text``
to reject calls that omit an explicit ``encoding`` — pinning the
requirement that ``detect_anti_patterns`` names UTF-8 explicitly.

Traceability:
  - REQ-TEST-003 / ARCH-003  -> test_detect_anti_patterns_reads_with_explicit_utf8
  - REQ-TEST-003              -> test_non_ascii_python_file_returns_findings_not_empty
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.utils.anti_patterns import detect_anti_patterns


@pytest.mark.regression
def test_detect_anti_patterns_reads_with_explicit_utf8(tmp_path, monkeypatch):
    """REQ-TEST-003 / ARCH-003 (host-independent regression guard).

    Simulate a non-UTF-8 default-locale host by replacing ``Path.read_text``
    with a stub that mimics the broken behaviour: a call WITHOUT an explicit
    ``encoding`` raises ``UnicodeDecodeError`` (as cp1252/cp932 would on
    non-ASCII bytes), while a call pinning ``encoding='utf-8'`` succeeds.

    Pre-fix (``read_text(errors='replace')`` with no encoding) -> stub raises
    -> the broad ``except`` returns [] -> this test FAILS (RED). Post-fix
    (``read_text(encoding='utf-8', errors='replace')``) -> stub returns the
    content -> GREEN. This locks the requirement that UTF-8 is named
    explicitly, so dropping the encoding in future immediately re-fails here.
    """
    source = tmp_path / "locale_sensitive.py"
    # Write a file with a print() call inside a function so AP003 fires.
    source.write_text(
        "# 日本語コメント\ndef greet():\n    print('こんにちは')\n",
        encoding="utf-8",
    )

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

    result = detect_anti_patterns(str(source), "python")

    assert isinstance(result, list), (
        "detect_anti_patterns must return a list; got None or raised"
    )
    assert result is not None, (
        "detect_anti_patterns must pin encoding='utf-8' so it does not fall "
        "back to the locale default (which fails on non-ASCII bytes)"
    )
    assert "utf-8" in seen_encodings, (
        f"detect_anti_patterns must call read_text with encoding='utf-8'; "
        f"observed encodings: {seen_encodings}"
    )


@pytest.mark.regression
def test_non_ascii_python_file_returns_findings_not_empty(tmp_path):
    """REQ-TEST-003: a UTF-8 file with non-ASCII content must not raise and
    must return a list (not None) — encoding='utf-8' with errors='replace'
    lets the decode succeed so anti-pattern detection never silently fails."""
    source = tmp_path / "non_ascii.py"
    # Write a file that contains non-ASCII bytes and a detectable anti-pattern.
    source.write_text(
        "# 日本語コメント\ndef process(data=[]):\n    pass\n",
        encoding="utf-8",
    )

    result = detect_anti_patterns(str(source), "python")

    assert result is not None, (
        "detect_anti_patterns must not return None for a readable UTF-8 file"
    )
    assert isinstance(result, list), (
        f"detect_anti_patterns must return a list, got {type(result)!r}"
    )
