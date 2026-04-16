"""Extra tests for language_detector.py to increase coverage."""
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
    return LanguageDetector()


class TestExtensionEdgeCases:
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


class TestAmbiguousExtensions:
    def test_sql_with_content(self, det: LanguageDetector) -> None:
        language, confidence = det.detect_language("query.sql", "SELECT * FROM users;")
        assert language == "sql"
        assert confidence >= 0.7

    def test_json_with_content(self, det: LanguageDetector) -> None:
        language, confidence = det.detect_language("data.json", '{"key": "value"}')
        assert language == "json"
        assert confidence >= 0.7

    def test_h_file_cpp(self, det: LanguageDetector) -> None:
        content = "#include <iostream>\nstd::vector<int> v;"
        assert det._resolve_ambiguity(".h", content) == "cpp"

    def test_h_file_objc(self, det: LanguageDetector) -> None:
        content = "#import <Foundation/Foundation.h>\n@interface Foo : NSObject\n@end"
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


class TestCFamilyDetection:
    def test_cpp_wins(self, det: LanguageDetector) -> None:
        content = "#include <iostream>\nusing namespace std;\nclass Foo {};\nstd::string s;"
        assert det._detect_c_family(content, ["c", "cpp", "objc"]) == "cpp"

    def test_c_wins(self, det: LanguageDetector) -> None:
        content = '#include <stdio.h>\nint main() {\n  printf("hello");\n  return 0;\n}\ntypedef struct { int x; } Point;'
        assert det._detect_c_family(content, ["c", "cpp", "objc"]) == "c"

    def test_objc_wins(self, det: LanguageDetector) -> None:
        content = "#import <Foundation/Foundation.h>\n@interface Foo : NSObject\n@end\n@implementation Foo\n@end\nNSString *s = [[NSString alloc] init];"
        assert det._detect_c_family(content, ["c", "cpp", "objc"]) == "objc"

    def test_objc_not_in_candidates(self, det: LanguageDetector) -> None:
        content = "#import <Foundation/Foundation.h>\n@interface Foo\n@end"
        assert det._detect_c_family(content, ["c", "cpp"]) in ("c", "cpp")

    def test_no_patterns_matched(self, det: LanguageDetector) -> None:
        assert det._detect_c_family("// comment\n", ["c", "cpp", "objc"]) == "c"


class TestObjCvsMatlab:
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


class TestDetectFromFileEdgeCases:
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
        assert detect_language_from_file("src/main.py", project_root=str(tmp_path)) == "python"

    def test_stat_permission_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        with patch("os.stat", side_effect=PermissionError("denied")):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_stat_os_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        with patch("os.stat", side_effect=OSError("io error")):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_returns_empty_string(self) -> None:
        with patch.object(LanguageDetector, "detect_from_extension", return_value=""):
            assert detect_language_from_file("test.java") == "unknown"

    def test_returns_whitespace(self) -> None:
        with patch.object(LanguageDetector, "detect_from_extension", return_value="   "):
            assert detect_language_from_file("test.java") == "unknown"

    def test_absolute_path(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "app.py"
        py_file.write_text("pass", encoding="utf-8")
        assert detect_language_from_file(str(py_file)) == "python"

    def test_tilde_path(self) -> None:
        assert detect_language_from_file("~/nonexistent_test_file.java") == "java"

    def test_cache_import_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        import builtins
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if "shared_cache" in name:
                raise ImportError("no cache module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert detect_language_from_file(str(py_file)) == "python"

    def test_cache_store_import_error(self, tmp_path: pytest.TempPathFactory) -> None:
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1", encoding="utf-8")
        import builtins
        real_import = builtins.__import__
        call_count = {"store": 0}

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if "shared_cache" in name:
                call_count["store"] += 1
                if call_count["store"] > 1:
                    raise ImportError("no cache for store")
                mock_cache = MagicMock()
                mock_cache.get_language_meta.return_value = None
                return mock_cache
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert detect_language_from_file(str(py_file)) == "python"
