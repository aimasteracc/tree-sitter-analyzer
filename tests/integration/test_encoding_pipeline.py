"""Integration test: encoding detection -> conversion -> parse -> output pipeline."""

from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.encoding_utils import detect_encoding


class TestEncodingPipeline:
    def test_utf8_file(self, tmp_path: Path) -> None:
        p = tmp_path / "utf8.py"
        p.write_text("def hello(): pass\n", encoding="utf-8")
        enc = detect_encoding(p.read_bytes(), file_path=str(p))
        assert enc == "utf-8"

    def test_latin1_file(self, tmp_path: Path) -> None:
        p = tmp_path / "latin1.py"
        p.write_text("name = 'café'\n", encoding="latin-1")
        enc = detect_encoding(p.read_bytes(), file_path=str(p))
        assert enc == "utf-8"

    def test_shift_jis_file(self, tmp_path: Path) -> None:
        p = tmp_path / "shift_jis.py"
        raw = "# 日本語コメント\nx = 1\n".encode("shift_jis")
        p.write_bytes(raw)
        enc = detect_encoding(p.read_bytes(), file_path=str(p))
        assert enc == "utf-8"

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.py"
        p.write_bytes(b"")
        enc = detect_encoding(p.read_bytes(), file_path=str(p))
        assert enc == "utf-8"

    def test_binary_file(self, tmp_path: Path) -> None:
        p = tmp_path / "binary.py"
        p.write_bytes(b"\x00\x01\x02\x03")
        enc = detect_encoding(p.read_bytes(), file_path=str(p))
        assert enc == "utf-8"
