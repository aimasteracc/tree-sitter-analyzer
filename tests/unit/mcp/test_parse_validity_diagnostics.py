"""Focused tests for parse/encoding diagnostics used by outline tools."""

from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.mcp.tools.utils import parse_validity


def test_file_byte_diagnostics_ignores_missing_and_empty_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    empty = tmp_path / "empty.py"
    empty.write_bytes(b"")

    assert parse_validity._file_byte_diagnostics(str(missing)) == {}
    assert parse_validity._file_byte_diagnostics(str(empty)) == {}


def test_file_byte_diagnostics_degrades_on_read_error(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "unreadable.py"
    target.write_text("def ok():\n    return 1\n", encoding="utf-8")

    def _raise_os_error(self: Path) -> bytes:
        raise OSError("cannot read")

    monkeypatch.setattr(Path, "read_bytes", _raise_os_error)

    assert parse_validity._file_byte_diagnostics(str(target)) == {}


def test_file_byte_diagnostics_reports_decode_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "bad.py"
    target.write_bytes(b"\xff")
    monkeypatch.setattr(
        parse_validity.EncodingManager,
        "detect_encoding",
        lambda raw, path: "bad-codec",
    )
    monkeypatch.setattr(
        parse_validity.EncodingManager,
        "safe_decode",
        lambda raw, encoding: "replacement \ufffd",
    )

    assert parse_validity._file_byte_diagnostics(str(target)) == {
        "non_utf8_bytes": True,
        "decode_replacement": True,
        "encoding_warning": True,
        "encoding_warnings": ["non_utf8_bytes", "decode_replacement"],
        "detected_encoding": "bad-codec",
    }


def test_decode_replacement_falls_back_when_safe_decode_raises(monkeypatch) -> None:
    def _raise_decode_error(raw: bytes, encoding: str) -> str:
        raise RuntimeError("decoder failed")

    monkeypatch.setattr(
        parse_validity.EncodingManager,
        "safe_decode",
        _raise_decode_error,
    )

    assert parse_validity._decode_replacement_used(b"\xff", "bad-codec") is True


def test_attach_input_diagnostics_tolerates_non_dict_agent_summary(
    tmp_path: Path,
) -> None:
    target = tmp_path / "latin1.py"
    target.write_bytes("def café():\n    return 'ok'\n".encode("cp1252"))
    result = {"language": "python", "agent_summary": "not-a-dict"}

    GetCodeOutlineTool._attach_input_diagnostics(result, str(target))

    assert result["verdict"] == "WARN"
    assert result["encoding_warning"] is True
    assert result["agent_summary"] == "not-a-dict"
