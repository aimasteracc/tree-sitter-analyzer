"""Extra tests for language_detector.py to increase coverage to 85%+."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.language_detector import (
    LanguageDetector,
    detect_language_from_file,
    is_language_supported,
)


@pytest.fixture
def det() -> LanguageDetector:
    """Provide a fresh LanguageDetector instance."""
    return LanguageDetector()


# ---------------------------------------------------------------------------
# Line 307 -- extension maps to empty / whitespace-only language
# ---------------------------------------------------------------------------


class TestExtensionEdgeCases:
    """Tests for extension mapping edge cases."""

    def test_extension_maps_to_empty_string(self, det: LanguageDetector) -> None:
        det.EXTENSION_MAPPING[".blank"] = ""
        language, confidence = det.detect_language("file.blank")
        assert language == "unknown"
        assert confidence == 0.0

    def test_extension_maps_to_whitespace(self, det: LanguageDetector) -> None:
        det.EXTENSION_MAPPING[".spaces"] = "   "
        language, confidence = det.detect_language("file.spaces")
        assert language == "unknown"
        assert confidence == 0.0

    def test_detect_from_extension_none(self, det: LanguageDetector) -> None:
        assert det.detect_from_extension(None) == "unknown"  # type: ignore[arg-type]

    def test_detect_from_extension_non_string(self, det: LanguageDetector) -> None:
        assert det.detect_from_extension(42) == "unknown"  # type: ignore[arg-type]

    def test_detect_from_extension_empty(self, det: LanguageDetector) -> None:
        assert det.detect_from_extension("") == "unknown"


# ---------------------------------------------------------------------------
# Lines 319-326 -- ambiguous extension with content resolution.
# To reach these lines, an extension must be in EXTENSION_MAPPING and
# AMBIGUOUS_EXTENSIONS but NOT in extension_map. We remove it from
# extension_map to trigger the ambiguity path.
# ---------------------------------------------------------------------------


class TestAmbiguousResolution:
    """Tests for ambiguous extension resolution via detect_language."""

    def _remove_from_ext_map(self, det: LanguageDetector, ext: str) -> None:
        det.extension_map.pop(ext, None)

    def test_sql_with_content_resolves_to_same(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".sql")
        language, confidence = det.detect_language("query.sql", "SELECT 1")
        assert language == "sql"
        assert confidence == 0.7

    def test_sql_without_content_returns_lower_confidence(
        self, det: LanguageDetector
    ) -> None:
        self._remove_from_ext_map(det, ".sql")
        language, confidence = det.detect_language("query.sql", None)
        assert language == "sql"
        assert confidence == 0.7

    def test_refines_to_different_language(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".sql")
        with patch.object(det, "_resolve_ambiguity", return_value="plsql"):
            language, confidence = det.detect_language("query.sql", "content")
            assert language == "plsql"
            assert confidence == 0.9

    def test_refines_to_empty_becomes_unknown(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".sql")
        with patch.object(det, "_resolve_ambiguity", return_value=""):
            language, confidence = det.detect_language("query.sql", "content")
            assert language == "unknown"
            assert confidence == 0.9

    def test_refines_to_whitespace_becomes_unknown(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".sql")
        with patch.object(det, "_resolve_ambiguity", return_value="   "):
            language, confidence = det.detect_language("query.sql", "content")
            assert language == "unknown"
            assert confidence == 0.9

    def test_h_with_cpp_content_resolves(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".h")
        content = "#include <iostream>\nstd::vector<int> v;\nusing namespace std;"
        language, confidence = det.detect_language("header.h", content)
        assert language == "cpp"
        assert confidence == 0.9

    def test_h_with_no_match_returns_default(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".h")
        language, confidence = det.detect_language("header.h", "// plain comment")
        assert language == "c"
        assert confidence == 0.7

    def test_m_with_matlab_content_resolves(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".m")
        content = "function r = f(x)\n  clc;\n  clear all;\n  r = x;\n  disp(r);\nend;"
        language, confidence = det.detect_language("script.m", content)
        assert language == "matlab"
        assert confidence == 0.9

    def test_json_with_content_falls_through(self, det: LanguageDetector) -> None:
        self._remove_from_ext_map(det, ".json")
        language, confidence = det.detect_language("data.json", '{"key": 1}')
        assert language == "json"
        assert confidence == 0.7


# ---------------------------------------------------------------------------
# Lines 375-377 -- is_supported plugin fallback on exception
# ---------------------------------------------------------------------------


class TestIsSupportedPluginFallback:
    """Tests for is_supported when PluginManager fails."""

    def test_import_error_falls_back_to_static(self, det: LanguageDetector) -> None:
        with patch.dict("sys.modules", {"tree_sitter_analyzer.plugins": None}):
            with patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                create=True,
                side_effect=ImportError("no plugins"),
            ):
                assert det.is_supported("java") is True

    def test_runtime_error_falls_back_to_static(self, det: LanguageDetector) -> None:
        with patch(
            "tree_sitter_analyzer.plugins.manager.PluginManager",
            side_effect=RuntimeError("plugin error"),
        ):
            assert det.is_supported("java") is True
            assert det.is_supported("brainfuck") is False


# ---------------------------------------------------------------------------
# Lines 411-422 -- _resolve_ambiguity .h, .m, and fallback branches
# ---------------------------------------------------------------------------


class TestResolveAmbiguity:
    """Tests for _resolve_ambiguity method."""

    def test_h_file_cpp(self, det: LanguageDetector) -> None:
        content = "#include <iostream>\nstd::vector<int> v;"
        assert det._resolve_ambiguity(".h", content) == "cpp"

    def test_h_file_c(self, det: LanguageDetector) -> None:
        content = '#include <stdio.h>\nprintf("hello");\ntypedef struct { int x; } Foo;\nmalloc(sizeof(Foo));'
        assert det._resolve_ambiguity(".h", content) == "c"

    def test_h_file_objc(self, det: LanguageDetector) -> None:
        content = "#import <Foundation/Foundation.h>\n@interface Foo : NSObject\n@end\nNSString *s = [[NSString alloc] init];"
        assert det._resolve_ambiguity(".h", content) == "objc"

    def test_m_file_objc(self, det: LanguageDetector) -> None:
        content = '#import "Foo.h"\n@implementation Foo\n@end'
        assert det._resolve_ambiguity(".m", content) == "objc"

    def test_m_file_matlab(self, det: LanguageDetector) -> None:
        content = "function result = calc(a, b)\n  clc;\n  clear all;\n  result = a + b;\nend;"
        assert det._resolve_ambiguity(".m", content) == "matlab"

    def test_sql_fallback(self, det: LanguageDetector) -> None:
        assert det._resolve_ambiguity(".sql", "SELECT 1") == "sql"

    def test_xml_fallback(self, det: LanguageDetector) -> None:
        assert det._resolve_ambiguity(".xml", "<root/>") == "xml"

    def test_json_fallback(self, det: LanguageDetector) -> None:
        assert det._resolve_ambiguity(".json", '{"a": 1}') == "json"

    def test_non_ambiguous_returns_mapping(self, det: LanguageDetector) -> None:
        assert det._resolve_ambiguity(".java", "class Foo {}") == "java"

    def test_unknown_extension_returns_unknown(self, det: LanguageDetector) -> None:
        assert det._resolve_ambiguity(".zzz", "content") == "unknown"


# ---------------------------------------------------------------------------
# Lines 434, 440 -- _detect_c_family score accumulation
# ---------------------------------------------------------------------------


class TestCFamilyDetection:
    """Tests for _detect_c_family method."""

    def test_cpp_wins(self, det: LanguageDetector) -> None:
        content = "#include <iostream>\nusing namespace std;\nclass Foo {};\nstd::string s;"
        assert det._detect_c_family(content, ["c", "cpp", "objc"]) == "cpp"

    def test_c_wins(self, det: LanguageDetector) -> None:
        content = '#include <stdio.h>\nint main() {\n  printf("hello");\n  return 0;\n}\ntypedef struct { int x; } Point;\nmalloc(sizeof(int));'
        assert det._detect_c_family(content, ["c", "cpp", "objc"]) == "c"

    def test_objc_wins(self, det: LanguageDetector) -> None:
        content = "#import <Foundation/Foundation.h>\n@interface Foo : NSObject\n@end\n@implementation Foo\n@end\nNSString *s = [[NSString alloc] init];"
        assert det._detect_c_family(content, ["c", "cpp", "objc"]) == "objc"

    def test_objc_not_in_candidates(self, det: LanguageDetector) -> None:
        content = "#import <Foundation/Foundation.h>\n@interface Foo\n@end"
        assert det._detect_c_family(content, ["c", "cpp"]) in ("c", "cpp")

    def test_no_patterns_matched(self, det: LanguageDetector) -> None:
        assert det._detect_c_family("// comment\n", ["c", "cpp", "objc"]) == "c"


# ---------------------------------------------------------------------------
# Lines 466, 471, 474, 476 -- _detect_objc_vs_matlab
# ---------------------------------------------------------------------------


class TestObjCvsMatlab:
    """Tests for _detect_objc_vs_matlab method."""

    def test_objc_wins(self, det: LanguageDetector) -> None:
        content = '#import "Foo.h"\n@interface Foo\n@end\n@implementation Foo\n@end'
        assert det._detect_objc_vs_matlab(content, ["objc", "matlab"]) == "objc"

    def test_matlab_wins(self, det: LanguageDetector) -> None:
        content = "function r = f(x)\n  clc;\n  clear all;\n  r = x;\n  disp(r);\nend;"
        assert det._detect_objc_vs_matlab(content, ["objc", "matlab"]) == "matlab"

    def test_tie_returns_first(self, det: LanguageDetector) -> None:
        assert det._detect_objc_vs_matlab("plain", ["objc", "matlab"]) == "objc"

    def test_tie_custom_candidates(self, det: LanguageDetector) -> None:
        assert det._detect_objc_vs_matlab("plain", ["matlab", "objc"]) == "matlab"


# ---------------------------------------------------------------------------
# Lines 530, 537, 540-541 -- detect_language_from_file input handling
# ---------------------------------------------------------------------------


class TestDetectFromFileInput:
    """Tests for detect_language_from_file with various inputs."""

    def test_none_input(self) -> None:
        assert detect_language_from_file(None) == "unknown"  # type: ignore[arg-type]

    def test_empty_input(self) -> None:
        assert detect_language_from_file("") == "unknown"

    def test_non_string_input(self) -> None:
        assert detect_language_from_file(12345) == "unknown"  # type: ignore[arg-type]

    def test_relative_with_project_root(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "src" / "main.py"
        py_file.parent.mkdir(parents=True, exist_ok=True)
        py_file.write_text("print('hello')", encoding="utf-8")
        assert (
            detect_language_from_file("src/main.py", project_root=str(tmp_path))
            == "python"
        )

    def test_tilde_path(self) -> None:
        assert detect_language_from_file("~/nonexistent_test_file.java") == "java"

    def test_path_resolution_exception(self) -> None:
        """Path.expanduser raises -> except clause uses raw file_path."""
        from pathlib import Path

        def failing_expanduser(self: Path) -> Path:
            raise ValueError("bad path")

        with patch.object(Path, "expanduser", failing_expanduser):
            result = detect_language_from_file("test.java")
            assert result == "java"


# ---------------------------------------------------------------------------
# Lines 551-552 -- os.stat permission error handling
# ---------------------------------------------------------------------------


class TestStatErrors:
    """Tests for os.stat error handling in detect_language_from_file."""

    def test_permission_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        with patch("os.stat", side_effect=PermissionError("denied")):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_os_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        with patch("os.stat", side_effect=OSError("io error")):
            assert detect_language_from_file(str(py_file)) == "python"


# ---------------------------------------------------------------------------
# Lines 567-574 -- cache lookup failure paths
# ---------------------------------------------------------------------------


class TestCacheLookupFailures:
    """Tests for cache lookup failure handling."""

    def test_import_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            side_effect=ImportError("no cache"),
        ):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_runtime_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            side_effect=RuntimeError("cache exploded"),
        ):
            assert detect_language_from_file(str(py_file)) == "python"


# ---------------------------------------------------------------------------
# Line 583 -- detect_from_extension returns empty/whitespace
# ---------------------------------------------------------------------------


class TestDetectFromFileResultValidation:
    """Tests for result validation in detect_language_from_file."""

    def test_returns_empty_string(self) -> None:
        with patch.object(
            LanguageDetector, "detect_from_extension", return_value=""
        ):
            assert detect_language_from_file("test.java") == "unknown"

    def test_returns_whitespace(self) -> None:
        with patch.object(
            LanguageDetector, "detect_from_extension", return_value="   "
        ):
            assert detect_language_from_file("test.java") == "unknown"


# ---------------------------------------------------------------------------
# Lines 595-601 -- cache store failure paths
# ---------------------------------------------------------------------------


class TestCacheStoreFailures:
    """Tests for cache store failure handling."""

    def test_general_exception(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")

        mock_cache = MagicMock()
        mock_cache.get_language_meta.return_value = None
        mock_cache.set_language_meta.side_effect = RuntimeError("store failed")

        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            return_value=mock_cache,
        ):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_import_error_on_store(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")

        call_count = {"n": 0}
        mock_cache = MagicMock()

        def fake_get_shared_cache() -> MagicMock:
            call_count["n"] += 1
            if call_count["n"] == 1:
                mock_cache.get_language_meta.return_value = None
                return mock_cache
            raise ImportError("no cache for store")

        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            side_effect=fake_get_shared_cache,
        ):
            assert detect_language_from_file(str(py_file)) == "python"


# ---------------------------------------------------------------------------
# Lines 630-632 -- is_language_supported plugin fallback
# ---------------------------------------------------------------------------


class TestIsLanguageSupportedGlobal:
    """Tests for the global is_language_supported function."""

    def test_plugin_exception_falls_back(self) -> None:
        with patch(
            "tree_sitter_analyzer.plugins.manager.PluginManager",
            side_effect=RuntimeError("plugin load failed"),
        ):
            assert is_language_supported("java") is True
            assert is_language_supported("brainfuck") is False


# ---------------------------------------------------------------------------
# Cache hit scenarios for detect_language_from_file
# ---------------------------------------------------------------------------


class TestCacheHitScenarios:
    """Tests for cache hit handling in detect_language_from_file."""

    def test_valid_cached_language(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "cached.py"
        py_file.write_text("x = 1", encoding="utf-8")
        mtime_ns = os.stat(py_file).st_mtime_ns

        mock_cache = MagicMock()
        mock_cache.get_language_meta.return_value = {
            "mtime_ns": mtime_ns,
            "language": "python",
        }

        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            return_value=mock_cache,
        ):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_whitespace_language_returns_unknown(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        py_file = tmp_path / "bad.py"
        py_file.write_text("x = 1", encoding="utf-8")
        mtime_ns = os.stat(py_file).st_mtime_ns

        mock_cache = MagicMock()
        mock_cache.get_language_meta.return_value = {
            "mtime_ns": mtime_ns,
            "language": "   ",
        }

        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            return_value=mock_cache,
        ):
            assert detect_language_from_file(str(py_file)) == "unknown"

    def test_non_string_language_is_cache_miss(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        py_file = tmp_path / "bad2.py"
        py_file.write_text("x = 1", encoding="utf-8")
        mtime_ns = os.stat(py_file).st_mtime_ns

        mock_cache = MagicMock()
        mock_cache.get_language_meta.return_value = {
            "mtime_ns": mtime_ns,
            "language": 123,
        }

        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            return_value=mock_cache,
        ):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_empty_string_language_returns_unknown(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        py_file = tmp_path / "empty.py"
        py_file.write_text("x = 1", encoding="utf-8")
        mtime_ns = os.stat(py_file).st_mtime_ns

        mock_cache = MagicMock()
        mock_cache.get_language_meta.return_value = {
            "mtime_ns": mtime_ns,
            "language": "",
        }

        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            return_value=mock_cache,
        ):
            assert detect_language_from_file(str(py_file)) == "unknown"

    def test_mtime_mismatch_triggers_redetect(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        py_file = tmp_path / "changed.py"
        py_file.write_text("x = 1", encoding="utf-8")

        mock_cache = MagicMock()
        mock_cache.get_language_meta.return_value = {
            "mtime_ns": 0,
            "language": "python",
        }
        mock_cache.set_language_meta.return_value = None

        with patch(
            "tree_sitter_analyzer.mcp.utils.shared_cache.get_shared_cache",
            return_value=mock_cache,
        ):
            assert detect_language_from_file(str(py_file)) == "python"
            mock_cache.set_language_meta.assert_called_once()

    def test_with_project_root(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "app.py"
        py_file.write_text("pass", encoding="utf-8")
        assert (
            detect_language_from_file(str(py_file), project_root=str(tmp_path))
            == "python"
        )
