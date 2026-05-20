"""Tests for _language_detector_helpers.py — static config builders and path/cache helpers."""

import os
import tempfile

from tree_sitter_analyzer._language_detector_helpers import (
    build_content_pattern_weights,
    build_extension_confidence_map,
    get_cached_language,
    get_path_mtime_ns,
    normalize_detection_path,
    store_cached_language,
)


class TestBuildExtensionConfidenceMap:
    def test_returns_dict(self) -> None:
        result = build_extension_confidence_map()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_entry_structure(self) -> None:
        result = build_extension_confidence_map()
        for ext, (lang, conf) in result.items():
            assert ext.startswith("."), f"Extension {ext} should start with dot"
            assert isinstance(lang, str) and lang, f"Language for {ext} should be non-empty str"
            assert 0.0 < conf <= 1.0, f"Confidence for {ext} should be in (0, 1]"

    def test_common_extensions_present(self) -> None:
        m = build_extension_confidence_map()
        expected = {
            ".java": "java",
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".cpp": "cpp",
            ".c": "c",
            ".go": "go",
            ".rs": "rust",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
            ".yaml": "yaml",
            ".md": "markdown",
            ".json": "json",
        }
        for ext, lang in expected.items():
            assert ext in m, f"Missing extension {ext}"
            assert m[ext][0] == lang, f"Expected {ext} -> {lang}, got {m[ext][0]}"

    def test_high_confidence_for_primary_extensions(self) -> None:
        m = build_extension_confidence_map()
        assert m[".java"][1] == 0.9
        assert m[".py"][1] == 0.9
        assert m[".js"][1] == 0.9
        assert m[".ts"][1] == 0.9

    def test_ambiguous_extensions_have_lower_confidence(self) -> None:
        m = build_extension_confidence_map()
        assert m[".h"][1] < 0.9
        assert m[".m"][1] < 0.9
        assert m[".jsx"][1] < m[".js"][1]

    def test_markdown_variants(self) -> None:
        m = build_extension_confidence_map()
        for ext in (".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdx"):
            assert ext in m, f"Missing markdown variant {ext}"
            assert m[ext][0] == "markdown"

    def test_deterministic(self) -> None:
        assert build_extension_confidence_map() == build_extension_confidence_map()


class TestBuildContentPatternWeights:
    def test_returns_dict(self) -> None:
        result = build_content_pattern_weights()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_entry_structure(self) -> None:
        result = build_content_pattern_weights()
        for lang, patterns in result.items():
            assert isinstance(lang, str) and lang
            assert isinstance(patterns, list)
            for regex, weight in patterns:
                assert isinstance(regex, str), f"Pattern for {lang} should be str"
                assert 0.0 < weight <= 1.0, f"Weight for {lang} pattern should be in (0, 1]"

    def test_key_languages_have_patterns(self) -> None:
        p = build_content_pattern_weights()
        for lang in ("java", "python", "javascript", "typescript", "c", "cpp", "markdown", "html", "css"):
            assert lang in p, f"Missing patterns for {lang}"
            assert len(p[lang]) > 0, f"Empty pattern list for {lang}"

    def test_regex_patterns_compile(self) -> None:
        import re

        p = build_content_pattern_weights()
        for _lang, patterns in p.items():
            for regex, _ in patterns:
                re.compile(regex)

    def test_java_patterns(self) -> None:
        p = build_content_pattern_weights()
        java = p["java"]
        regexes = [r for r, _ in java]
        assert any("package" in r for r in regexes)
        assert any("class" in r for r in regexes)
        assert any("import" in r for r in regexes)

    def test_python_patterns(self) -> None:
        p = build_content_pattern_weights()
        py = p["python"]
        regexes = [r for r, _ in py]
        assert any("def" in r for r in regexes)
        assert any("__name__" in r for r in regexes)

    def test_markdown_patterns(self) -> None:
        p = build_content_pattern_weights()
        md = p["markdown"]
        regexes = [r for r, _ in md]
        assert any("#" in r for r in regexes)
        assert any("```" in r for r in regexes)

    def test_deterministic(self) -> None:
        assert build_content_pattern_weights() == build_content_pattern_weights()


class TestNormalizeDetectionPath:
    def test_absolute_path_unchanged_no_root(self) -> None:
        result = normalize_detection_path("/abs/path/to/file.py", None)
        assert result == "/abs/path/to/file.py"

    def test_relative_path_with_root(self) -> None:
        result = normalize_detection_path("src/file.py", "/project")
        assert result.endswith("src/file.py")
        assert os.path.isabs(result)

    def test_tilde_expansion(self) -> None:
        result = normalize_detection_path("~/test.py", None)
        assert "~" not in result
        assert os.path.isabs(result)

    def test_tilde_with_root(self) -> None:
        result = normalize_detection_path("~/test.py", "/project")
        assert "~" not in result

    def test_absolute_path_ignores_root(self) -> None:
        result = normalize_detection_path("/abs/file.py", "/project")
        assert result == "/abs/file.py"

    def test_empty_string(self) -> None:
        result = normalize_detection_path("", None)
        assert isinstance(result, str)

    def test_dot_path(self) -> None:
        result = normalize_detection_path(".", None)
        assert os.path.isabs(result)

    def test_double_dot_path_with_root(self) -> None:
        result = normalize_detection_path("../file.py", "/project/src")
        assert os.path.isabs(result)

    def test_exception_fallback(self) -> None:
        result = normalize_detection_path("\x00", None)
        assert isinstance(result, str)


class TestGetPathMtimeNs:
    def test_existing_file(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x")
            f.flush()
            path = f.name
        try:
            result = get_path_mtime_ns(path)
            assert result is not None
            assert isinstance(result, int)
            assert result > 0
        finally:
            os.unlink(path)

    def test_nonexistent_file(self) -> None:
        result = get_path_mtime_ns("/nonexistent/path/to/file.py")
        assert result is None

    def test_directory(self) -> None:
        result = get_path_mtime_ns(tempfile.gettempdir())
        assert result is not None
        assert isinstance(result, int)

    def test_permission_error_returns_none(self) -> None:
        import unittest.mock

        with unittest.mock.patch("os.path.exists", side_effect=PermissionError("denied")):
            result = get_path_mtime_ns("/some/path")
            assert result is None

    def test_os_error_returns_none(self) -> None:
        import unittest.mock

        with unittest.mock.patch("os.path.exists", side_effect=OSError("fail")):
            result = get_path_mtime_ns("/some/path")
            assert result is None


class TestCachedLanguage:
    def test_get_nonexistent_key(self) -> None:
        result = get_cached_language("/nonexistent/file.py", 12345, None)
        assert result is None or isinstance(result, str)

    def test_store_and_retrieve(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(b"print('hello')")
            f.flush()
            path = f.name
        try:
            mtime = get_path_mtime_ns(path)
            assert mtime is not None
            store_cached_language(path, "python", mtime, None)
            result = get_cached_language(path, mtime, None)
            assert result is None or result == "python"
        finally:
            os.unlink(path)

    def test_store_with_none_mtime_is_noop(self) -> None:
        store_cached_language("/any/path.py", "python", None, None)

    def test_get_with_wrong_mtime(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(b"x")
            f.flush()
            path = f.name
        try:
            real_mtime = get_path_mtime_ns(path)
            assert real_mtime is not None
            store_cached_language(path, "python", real_mtime, None)
            result = get_cached_language(path, real_mtime + 999999, None)
            assert result is None or result == "python"
        finally:
            os.unlink(path)

    def test_store_with_project_root(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(b"x")
            f.flush()
            path = f.name
        try:
            mtime = get_path_mtime_ns(path)
            assert mtime is not None
            store_cached_language(path, "python", mtime, "/project/root")
            result = get_cached_language(path, mtime, "/project/root")
            assert result is None or result == "python"
        finally:
            os.unlink(path)
