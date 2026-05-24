"""Regression tests for KI-1 fix: analyze_file must propagate detected_encoding to extractor._file_encoding.

Background: c_plugin and java_plugin declare ``self._file_encoding`` on the extractor
and use it for byte-level slicing inside ``_get_node_text_optimized()``. Prior to commit
fixing KI-1, ``create_extractor()`` returned a fresh extractor with ``_file_encoding=None``,
so byte-level extraction always fell back to UTF-8 — silently wrong for GBK/Shift-JIS files.

These tests pin the fix in place: analyze_file must set ``extractor._file_encoding``
to whatever ``read_file_safe`` returned.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.core.request import AnalysisRequest
from tree_sitter_analyzer.languages.c_plugin import CElementExtractor, CPlugin
from tree_sitter_analyzer.languages.java_plugin import (
    JavaElementExtractor,
    JavaPlugin,
)

# ---------------------------------------------------------------------------
# Pure-extractor surface — _file_encoding declaration & default
# ---------------------------------------------------------------------------


class TestExtractorEncodingAttribute:
    """C and Java extractors declare _file_encoding for byte-level slicing."""

    def test_c_extractor_default_none(self):
        extractor = CElementExtractor()
        assert hasattr(extractor, "_file_encoding")
        assert extractor._file_encoding is None

    def test_java_extractor_default_none(self):
        extractor = JavaElementExtractor()
        assert hasattr(extractor, "_file_encoding")
        assert extractor._file_encoding is None

    def test_c_extractor_accepts_encoding(self):
        extractor = CElementExtractor()
        extractor._file_encoding = "gbk"
        assert extractor._file_encoding == "gbk"

    def test_java_extractor_accepts_encoding(self):
        extractor = JavaElementExtractor()
        extractor._file_encoding = "shift_jis"
        assert extractor._file_encoding == "shift_jis"


# ---------------------------------------------------------------------------
# analyze_file propagates detected_encoding into extractor._file_encoding
# ---------------------------------------------------------------------------


class _RecordingExtractorMixin:
    """Mixin that records _file_encoding at the moment extract_* is called.

    The plugin sets ``extractor._file_encoding`` *after* construction but *before*
    extract calls. We snapshot it inside the first extract_* call so the test can
    verify the value the extractor would actually use during byte slicing.
    """

    seen_encoding: str | None = "<unset>"

    def extract_functions(self, tree, source_code):  # type: ignore[override]
        type(self).seen_encoding = self._file_encoding
        return []

    def extract_classes(self, tree, source_code):  # type: ignore[override]
        return []

    def extract_variables(self, tree, source_code):  # type: ignore[override]
        return []

    def extract_imports(self, tree, source_code):  # type: ignore[override]
        return []


class _RecordingCExtractor(_RecordingExtractorMixin, CElementExtractor):
    pass


class _RecordingJavaExtractor(_RecordingExtractorMixin, JavaElementExtractor):
    pass


@pytest.fixture
def c_source_file(tmp_path: Path) -> Path:
    src = tmp_path / "hello.c"
    src.write_text(
        '#include <stdio.h>\nint main(void) {\n    printf("hi");\n    return 0;\n}\n',
        encoding="utf-8",
    )
    return src


@pytest.fixture
def java_source_file(tmp_path: Path) -> Path:
    src = tmp_path / "Hello.java"
    src.write_text(
        "public class Hello {\n"
        "    public static void main(String[] args) {\n"
        '        System.out.println("hi");\n'
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    return src


class TestCPluginEncodingPropagation:
    def test_analyze_file_sets_extractor_file_encoding(
        self, monkeypatch: pytest.MonkeyPatch, c_source_file: Path
    ):
        """KI-1 regression: extractor._file_encoding must be set before extract calls."""
        # Spy: substitute extractor so we can capture the encoding it received.
        plugin = CPlugin()
        _RecordingCExtractor.seen_encoding = "<unset>"
        monkeypatch.setattr(plugin, "create_extractor", lambda: _RecordingCExtractor())
        # Force a known encoding through read_file_safe.
        from tree_sitter_analyzer import encoding_utils

        monkeypatch.setattr(
            encoding_utils,
            "read_file_safe",
            lambda path: (Path(path).read_text(encoding="utf-8"), "iso-8859-1"),
        )

        request = AnalysisRequest(
            file_path=str(c_source_file),
            language="c",
            include_complexity=False,
            include_details=False,
        )
        asyncio.run(plugin.analyze_file(str(c_source_file), request))

        assert _RecordingCExtractor.seen_encoding == "iso-8859-1", (
            "analyze_file must propagate detected_encoding into extractor._file_encoding "
            "before extract_* is called (KI-1 regression)."
        )

    def test_analyze_file_propagates_utf8_encoding(
        self, monkeypatch: pytest.MonkeyPatch, c_source_file: Path
    ):
        """Even for the default utf-8 path the attribute must be set, not left None."""
        plugin = CPlugin()
        _RecordingCExtractor.seen_encoding = "<unset>"
        monkeypatch.setattr(plugin, "create_extractor", lambda: _RecordingCExtractor())

        request = AnalysisRequest(
            file_path=str(c_source_file),
            language="c",
            include_complexity=False,
            include_details=False,
        )
        asyncio.run(plugin.analyze_file(str(c_source_file), request))

        assert _RecordingCExtractor.seen_encoding is not None
        assert _RecordingCExtractor.seen_encoding != "<unset>"


class TestJavaPluginEncodingPropagation:
    def test_analyze_file_sets_extractor_file_encoding(
        self, monkeypatch: pytest.MonkeyPatch, java_source_file: Path
    ):
        """KI-1 regression for Java: extractor._file_encoding must be set."""
        plugin = JavaPlugin()
        _RecordingJavaExtractor.seen_encoding = "<unset>"
        monkeypatch.setattr(
            plugin, "create_extractor", lambda: _RecordingJavaExtractor()
        )
        # Java uses the async variant; patch that one.
        from tree_sitter_analyzer import encoding_utils

        async def _fake_read(path):
            return (Path(path).read_text(encoding="utf-8"), "shift_jis")

        monkeypatch.setattr(encoding_utils, "read_file_safe_async", _fake_read)

        request = AnalysisRequest(
            file_path=str(java_source_file),
            language="java",
            include_complexity=False,
            include_details=False,
        )
        asyncio.run(plugin.analyze_file(str(java_source_file), request))

        assert _RecordingJavaExtractor.seen_encoding == "shift_jis", (
            "Java analyze_file must propagate detected_encoding into "
            "extractor._file_encoding (KI-1 regression)."
        )

    def test_analyze_file_propagates_utf8_encoding(
        self, monkeypatch: pytest.MonkeyPatch, java_source_file: Path
    ):
        plugin = JavaPlugin()
        _RecordingJavaExtractor.seen_encoding = "<unset>"
        monkeypatch.setattr(
            plugin, "create_extractor", lambda: _RecordingJavaExtractor()
        )

        request = AnalysisRequest(
            file_path=str(java_source_file),
            language="java",
            include_complexity=False,
            include_details=False,
        )
        asyncio.run(plugin.analyze_file(str(java_source_file), request))

        assert _RecordingJavaExtractor.seen_encoding is not None
        assert _RecordingJavaExtractor.seen_encoding != "<unset>"


# ---------------------------------------------------------------------------
# KI-2: PHP / Ruby extractors no longer carry the unused _file_encoding attr
# ---------------------------------------------------------------------------


class TestPhpRubyNoDeadEncodingAttr:
    """KI-2 regression: PHP/Ruby extractors had a dead _file_encoding declaration
    that was never read or written. The cleanup removed it. These tests prevent
    re-introduction via copy-paste from c/java extractors."""

    def test_php_extractor_has_no_file_encoding_attr(self):
        from tree_sitter_analyzer.languages.php_plugin import PHPElementExtractor

        extractor = PHPElementExtractor()
        # Instance must not carry an unused encoding attribute.
        assert "_file_encoding" not in vars(extractor)

    def test_ruby_extractor_has_no_file_encoding_attr(self):
        from tree_sitter_analyzer.languages.ruby_plugin import RubyElementExtractor

        extractor = RubyElementExtractor()
        assert "_file_encoding" not in vars(extractor)
