#!/usr/bin/env python3
"""
Targeted tests for language_detector.py to cover missing lines.

Covers: ambiguity resolution, C-family detection, Objective-C vs MATLAB,
        detect_language_from_file caching paths, invalid inputs, and
        PluginManager fallback paths.

Missing lines targeted:
  301, 313-320, 337, 344, 369, 371,
  402-403, 405, 408-409, 412-413, 416,
  420-450, 454-472,
  524, 531, 534-535, 545-546, 561, 563-564, 566-568,
  577, 589-595, 624, 626
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.language_detector import (
    LanguageDetector,
    detect_language_from_file,
    detector,
    is_language_supported,
)

# ---------------------------------------------------------------------------
# detect_language: ambiguous extension paths (lines 309-320)
#
# Lines 304-306 return early for extensions in self.extension_map.
# To reach lines 309-320, we need an extension that is:
#   - in EXTENSION_MAPPING (line 296 passes)
#   - NOT in extension_map (line 304 fails -> skip to 309)
#   - in AMBIGUOUS_EXTENSIONS (line 309 passes -> enter ambiguity block)
# We achieve this by adding a synthetic extension to the relevant dicts.
# ---------------------------------------------------------------------------


class TestDetectLanguageAmbiguityBranch:
    """Tests that force the ambiguity resolution branch in detect_language."""

    def _setup_ambiguous(self, det, ext, mapping_lang, candidates):
        """
        Add *ext* to EXTENSION_MAPPING and AMBIGUOUS_EXTENSIONS but NOT
        to extension_map, so that detect_language reaches lines 309-320.
        """
        det.EXTENSION_MAPPING[ext] = mapping_lang
        det.AMBIGUOUS_EXTENSIONS[ext] = candidates
        # Make sure it is NOT in extension_map
        det.extension_map.pop(ext, None)

    def _teardown_ambiguous(self, det, ext):
        det.EXTENSION_MAPPING.pop(ext, None)
        det.AMBIGUOUS_EXTENSIONS.pop(ext, None)

    def test_ambiguous_with_content_refined_differs(self):
        """Lines 313-318: content triggers _resolve_ambiguity, refined != original."""
        det = LanguageDetector()
        ext = ".tst_amb"
        self._setup_ambiguous(det, ext, "lang_a", ["lang_a", "lang_b"])

        # _resolve_ambiguity for unknown special ext -> returns candidates[0] = "lang_a"
        # refined == original -> confidence 0.7
        lang, conf = det.detect_language(f"file{ext}", "some content")
        assert lang == "lang_a"
        assert conf == 0.7  # refined == original

        self._teardown_ambiguous(det, ext)

    def test_ambiguous_with_content_refined_same_as_original(self):
        """Lines 313-318: refined == original -> confidence 0.7."""
        det = LanguageDetector()
        ext = ".tst_amb2"
        self._setup_ambiguous(det, ext, "alpha", ["alpha", "beta"])

        # Fallback: candidates[0]="alpha" == mapping_lang="alpha" -> 0.7
        lang, conf = det.detect_language(f"file{ext}", "whatever")
        assert lang == "alpha"
        assert conf == 0.7

        self._teardown_ambiguous(det, ext)

    def test_ambiguous_with_content_refined_different(self):
        """Lines 313-318: refined != original -> confidence 0.9."""
        det = LanguageDetector()
        ext = ".tst_amb3"
        # mapping says "alpha", but candidates[0] is "beta"
        det.EXTENSION_MAPPING[ext] = "alpha"
        det.AMBIGUOUS_EXTENSIONS[ext] = ["beta", "alpha"]
        det.extension_map.pop(ext, None)

        lang, conf = det.detect_language(f"file{ext}", "some content")
        # _resolve_ambiguity fallback -> candidates[0] = "beta", which != "alpha"
        assert lang == "beta"
        assert conf == 0.9

        self._teardown_ambiguous(det, ext)

    def test_ambiguous_without_content(self):
        """Line 320: ambiguous extension, no content -> confidence 0.7."""
        det = LanguageDetector()
        ext = ".tst_amb4"
        self._setup_ambiguous(det, ext, "gamma", ["gamma", "delta"])

        lang, conf = det.detect_language(f"file{ext}")
        assert lang == "gamma"
        assert conf == 0.7

        self._teardown_ambiguous(det, ext)

    def test_ambiguous_with_content_none(self):
        """Line 320: ambiguous extension, content=None -> confidence 0.7."""
        det = LanguageDetector()
        ext = ".tst_amb5"
        self._setup_ambiguous(det, ext, "epsilon", ["epsilon", "zeta"])

        lang, conf = det.detect_language(f"file{ext}", None)
        assert lang == "epsilon"
        assert conf == 0.7

        self._teardown_ambiguous(det, ext)


# ---------------------------------------------------------------------------
# detect_language: refined language blank guard (lines 316-317)
# ---------------------------------------------------------------------------


class TestDetectLanguageRefinedBlank:
    """Test guard when _resolve_ambiguity returns blank."""

    def test_resolve_ambiguity_returns_blank(self):
        """Lines 316-317: refined language is blank -> 'unknown'."""
        det = LanguageDetector()
        ext = ".tst_blank"
        det.EXTENSION_MAPPING[ext] = "somelang"
        det.AMBIGUOUS_EXTENSIONS[ext] = ["somelang", "otherlang"]
        det.extension_map.pop(ext, None)

        with patch.object(det, "_resolve_ambiguity", return_value=""):
            lang, conf = det.detect_language(f"file{ext}", "some content")
            assert lang == "unknown"
            assert conf == 0.9  # refined ("unknown") != original ("somelang")

        det.EXTENSION_MAPPING.pop(ext, None)
        det.AMBIGUOUS_EXTENSIONS.pop(ext, None)

    def test_resolve_ambiguity_returns_whitespace(self):
        """Refined language is whitespace-only -> 'unknown'."""
        det = LanguageDetector()
        ext = ".tst_ws"
        det.EXTENSION_MAPPING[ext] = "somelang"
        det.AMBIGUOUS_EXTENSIONS[ext] = ["somelang", "otherlang"]
        det.extension_map.pop(ext, None)

        with patch.object(det, "_resolve_ambiguity", return_value="   "):
            lang, conf = det.detect_language(f"file{ext}", "content")
            assert lang == "unknown"

        det.EXTENSION_MAPPING.pop(ext, None)
        det.AMBIGUOUS_EXTENSIONS.pop(ext, None)

    def test_resolve_ambiguity_returns_none(self):
        """Refined language is None -> 'unknown'."""
        det = LanguageDetector()
        ext = ".tst_none"
        det.EXTENSION_MAPPING[ext] = "somelang"
        det.AMBIGUOUS_EXTENSIONS[ext] = ["somelang", "otherlang"]
        det.extension_map.pop(ext, None)

        with patch.object(det, "_resolve_ambiguity", return_value=None):
            lang, conf = det.detect_language(f"file{ext}", "content")
            assert lang == "unknown"

        det.EXTENSION_MAPPING.pop(ext, None)
        det.AMBIGUOUS_EXTENSIONS.pop(ext, None)


# ---------------------------------------------------------------------------
# _detect_c_family (lines 420-450)
# ---------------------------------------------------------------------------


class TestDetectCFamily:
    """Tests for _detect_c_family private method."""

    def setup_method(self):
        self.det = LanguageDetector()

    def test_cpp_wins_over_c(self):
        """C++ patterns score higher than C."""
        content = (
            "#include <iostream>\nstd::cout << x;\n"
            "namespace bar {}\nclass Foo {};\ntemplate<"
        )
        result = self.det._detect_c_family(content, ["c", "cpp", "objc"])
        assert result == "cpp"

    def test_c_wins_over_cpp(self):
        """C patterns score higher than C++."""
        content = (
            '#include <stdio.h>\nprintf("hello");\n'
            "malloc(10);\ntypedef struct"
        )
        result = self.det._detect_c_family(content, ["c", "cpp", "objc"])
        assert result == "c"

    def test_objc_wins_with_strong_markers(self):
        """Objective-C patterns with heavy weight (3x) outscore C/C++."""
        content = (
            "#import <Foundation/Foundation.h>\n@interface Foo\n"
            "@implementation Bar\nNSString *s;\nalloc]"
        )
        result = self.det._detect_c_family(content, ["c", "cpp", "objc"])
        assert result == "objc"

    def test_objc_wins_but_not_in_candidates_cpp_higher(self):
        """Line 447-448: objc scores highest but NOT in candidates, cpp > c."""
        content = "@interface Foo\nstd::cout\nnamespace bar {}"
        result = self.det._detect_c_family(content, ["c", "cpp"])
        # objc_score=3, cpp_score=2, c_score=0
        # objc not in candidates -> cpp > c -> "cpp"
        assert result == "cpp"

    def test_objc_wins_but_not_in_candidates_c_higher(self):
        """Line 448: objc best but not candidate, c_score > cpp_score -> 'c'."""
        content = (
            "@interface Foo\n"
            '#include <stdio.h>\nprintf("hi");\nmalloc(10);'
        )
        result = self.det._detect_c_family(content, ["c", "cpp"])
        # objc_score = 3 (one pattern), c_score = 3 (three patterns), cpp_score = 0
        # max is objc (3), not in candidates -> c(3) > cpp(0) -> "c"
        # NOTE: dict iteration {"cpp":0, "c":3, "objc":3} -> max picks "c" first
        # But the branch at 447 checks best_language == "objc" and "objc" not in candidates
        # Then line 448 picks cpp if cpp>c else c. Here c=3 > cpp=0 -> "c"
        assert result == "c"

    def test_no_patterns_match_fallback_to_first_candidate(self):
        """Line 450: all scores zero -> returns candidates[0]."""
        content = "just some random text with no patterns"
        result = self.det._detect_c_family(content, ["c", "cpp", "objc"])
        assert result == "c"  # first candidate

    def test_cpp_single_pattern_match(self):
        """Single C++ pattern match gives cpp > 0."""
        content = "std::vector<int> v;"
        result = self.det._detect_c_family(content, ["c", "cpp", "objc"])
        assert result == "cpp"


# ---------------------------------------------------------------------------
# _detect_objc_vs_matlab (lines 454-472)
# ---------------------------------------------------------------------------


class TestDetectObjcVsMatlab:
    """Tests for _detect_objc_vs_matlab private method."""

    def setup_method(self):
        self.det = LanguageDetector()

    def test_objc_wins(self):
        """Line 467-468: Objective-C patterns outscore MATLAB."""
        content = (
            "#import <Foundation/Foundation.h>\n"
            "@interface Foo\n@implementation Bar"
        )
        result = self.det._detect_objc_vs_matlab(content, ["objc", "matlab"])
        assert result == "objc"

    def test_matlab_wins(self):
        """Line 469-470: MATLAB patterns outscore Objective-C."""
        content = "function y = foo(x)\nend;\ndisp('hello')\nclc;\nclear all"
        result = self.det._detect_objc_vs_matlab(content, ["objc", "matlab"])
        assert result == "matlab"

    def test_tie_returns_first_candidate(self):
        """Line 472: equal scores -> returns candidates[0]."""
        # One pattern from each group
        content = "#import something\nfunction something"
        result = self.det._detect_objc_vs_matlab(content, ["objc", "matlab"])
        assert result == "objc"  # candidates[0]

    def test_no_matches_returns_first_candidate(self):
        """No patterns match -> returns candidates[0]."""
        content = "random content with no markers"
        result = self.det._detect_objc_vs_matlab(content, ["objc", "matlab"])
        assert result == "objc"  # candidates[0]

    def test_matlab_exclusive_patterns(self):
        """MATLAB-only patterns with no ObjC markers."""
        content = "clc;\nclear all\ndisp('result')"
        result = self.det._detect_objc_vs_matlab(content, ["objc", "matlab"])
        assert result == "matlab"

    def test_objc_exclusive_patterns(self):
        """ObjC-only patterns with no MATLAB markers."""
        content = "@interface MyClass\nNSString *name;\nalloc]"
        result = self.det._detect_objc_vs_matlab(content, ["objc", "matlab"])
        assert result == "objc"


# ---------------------------------------------------------------------------
# _resolve_ambiguity (lines 402-416)
# ---------------------------------------------------------------------------


class TestResolveAmbiguity:
    """Tests for _resolve_ambiguity private method."""

    def setup_method(self):
        self.det = LanguageDetector()

    def test_non_ambiguous_extension(self):
        """Line 402-403: extension NOT in AMBIGUOUS_EXTENSIONS -> EXTENSION_MAPPING."""
        result = self.det._resolve_ambiguity(".py", "some content")
        assert result == "python"

    def test_non_ambiguous_unknown_extension(self):
        """Extension not in AMBIGUOUS_EXTENSIONS and not in EXTENSION_MAPPING."""
        result = self.det._resolve_ambiguity(".xyz", "some content")
        assert result == "unknown"

    def test_h_extension_dispatches_to_c_family(self):
        """Line 408-409: .h dispatches to _detect_c_family."""
        content = "#include <iostream>\nstd::string s;"
        result = self.det._resolve_ambiguity(".h", content)
        assert result == "cpp"

    def test_h_extension_c_content(self):
        """.h with C content -> c."""
        content = '#include <stdio.h>\nprintf("hi");'
        result = self.det._resolve_ambiguity(".h", content)
        assert result == "c"

    def test_m_extension_dispatches_to_objc_vs_matlab(self):
        """Line 412-413: .m dispatches to _detect_objc_vs_matlab."""
        content = "@implementation Foo\nNSString *s;"
        result = self.det._resolve_ambiguity(".m", content)
        assert result == "objc"

    def test_m_extension_matlab_content(self):
        """.m with MATLAB content."""
        content = "function y = foo(x)\nend;\ndisp('test')\nclc;"
        result = self.det._resolve_ambiguity(".m", content)
        assert result == "matlab"

    def test_sql_extension_fallback_to_first_candidate(self):
        """Line 416: .sql has no special handler -> candidates[0]."""
        result = self.det._resolve_ambiguity(".sql", "SELECT 1")
        assert result == "sql"  # AMBIGUOUS_EXTENSIONS[".sql"][0]

    def test_xml_extension_fallback_to_first_candidate(self):
        """.xml has no special handler -> candidates[0]."""
        result = self.det._resolve_ambiguity(".xml", "<root/>")
        assert result == "xml"

    def test_json_extension_fallback(self):
        """.json ambiguous -> candidates[0]."""
        result = self.det._resolve_ambiguity(".json", '{"a":1}')
        assert result == "json"


# ---------------------------------------------------------------------------
# detect_language: empty language guard (line 301)
# ---------------------------------------------------------------------------


class TestDetectLanguageEmptyLanguageGuard:
    """Test the guard against empty/blank language in EXTENSION_MAPPING."""

    def test_blank_language_in_extension_mapping(self):
        """Line 300-301: if EXTENSION_MAPPING returns blank language -> unknown."""
        det = LanguageDetector()
        det.EXTENSION_MAPPING[".blank"] = ""
        lang, conf = det.detect_language("file.blank")
        assert lang == "unknown"
        assert conf == 0.0
        del det.EXTENSION_MAPPING[".blank"]

    def test_whitespace_language_in_extension_mapping(self):
        """Whitespace-only language in mapping -> unknown."""
        det = LanguageDetector()
        det.EXTENSION_MAPPING[".ws"] = "   "
        lang, conf = det.detect_language("file.ws")
        assert lang == "unknown"
        assert conf == 0.0
        del det.EXTENSION_MAPPING[".ws"]


# ---------------------------------------------------------------------------
# detect_from_extension: invalid input (lines 337, 344)
# ---------------------------------------------------------------------------


class TestDetectFromExtensionEdgeCases:
    """Edge cases for detect_from_extension."""

    def setup_method(self):
        self.det = LanguageDetector()

    def test_none_input(self):
        """Line 337: None input returns 'unknown'."""
        result = self.det.detect_from_extension(None)
        assert result == "unknown"

    def test_non_string_input(self):
        """Line 337: non-string input returns 'unknown'."""
        result = self.det.detect_from_extension(123)
        assert result == "unknown"

    def test_empty_string(self):
        """Line 337: empty string returns 'unknown'."""
        result = self.det.detect_from_extension("")
        assert result == "unknown"

    def test_detect_from_extension_returns_blank_guard(self):
        """Line 343-344: detect_language returns blank language -> 'unknown'."""
        det = LanguageDetector()
        # Make detect_language return a blank language
        with patch.object(det, "detect_language", return_value=("", 0.5)):
            result = det.detect_from_extension("file.py")
            assert result == "unknown"

    def test_detect_from_extension_returns_whitespace_guard(self):
        """Line 343-344: detect_language returns whitespace language -> 'unknown'."""
        det = LanguageDetector()
        with patch.object(det, "detect_language", return_value=("   ", 0.5)):
            result = det.detect_from_extension("file.py")
            assert result == "unknown"


# ---------------------------------------------------------------------------
# is_supported: PluginManager fallback (lines 369, 371)
# ---------------------------------------------------------------------------


class TestIsSupportedPluginFallback:
    """Test is_supported when PluginManager import/call fails."""

    def test_supported_language_skips_plugin_check(self):
        """Language in SUPPORTED_LANGUAGES returns True immediately (line 358-359)."""
        det = LanguageDetector()
        assert det.is_supported("python") is True

    def test_unsupported_language_with_plugin_manager_failure(self):
        """Lines 369-371: PluginManager raises -> fallback to static SUPPORTED_LANGUAGES."""
        det = LanguageDetector()
        # Replace the plugins.manager module with None to force import failure
        with patch.dict(
            "sys.modules",
            {"tree_sitter_analyzer.plugins.manager": None},
        ):
            result = det.is_supported("swift")
            assert result is False

    def test_plugin_manager_general_exception(self):
        """Lines 369-371: general exception from PluginManager -> fallback."""
        det = LanguageDetector()
        mock_module = MagicMock()
        mock_module.PluginManager.side_effect = RuntimeError("boom")
        with patch.dict(
            "sys.modules",
            {"tree_sitter_analyzer.plugins.manager": mock_module},
        ):
            result = det.is_supported("nonexistent_lang")
            assert result is False


# ---------------------------------------------------------------------------
# detect_language_from_file: various cache/input paths (lines 524-598)
# ---------------------------------------------------------------------------


class TestDetectLanguageFromFile:
    """Tests for the module-level detect_language_from_file function."""

    def test_none_input(self):
        """Line 524: None input returns 'unknown'."""
        assert detect_language_from_file(None) == "unknown"

    def test_empty_string_input(self):
        """Line 524: empty string returns 'unknown'."""
        assert detect_language_from_file("") == "unknown"

    def test_non_string_input(self):
        """Line 524: non-string returns 'unknown'."""
        assert detect_language_from_file(123) == "unknown"

    def test_relative_path_with_project_root(self):
        """Line 531: relative path + project_root -> resolved against project_root."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=tempfile.gettempdir()
        ) as f:
            f.write("x = 1")
            temp_file = f.name

        try:
            temp_dir = os.path.dirname(temp_file)
            basename = os.path.basename(temp_file)
            result = detect_language_from_file(basename, project_root=temp_dir)
            assert result == "python"
        finally:
            os.unlink(temp_file)

    def test_path_resolution_exception(self):
        """Lines 534-535: Path() raises -> falls back to raw file_path."""
        # Patch Path.expanduser to raise, triggering the except branch
        with patch.object(Path, "expanduser", side_effect=RuntimeError("bad expand")):
            result = detect_language_from_file("test.py")
            # Falls back to abs_path = "test.py", then detect_from_extension works
            assert result == "python"

    def test_permission_error_on_stat(self):
        """Lines 545-546: PermissionError on os.stat -> mtime_ns stays None."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False
        ) as f:
            f.write("public class Test {}")
            temp_file = f.name

        try:
            with patch("os.stat", side_effect=PermissionError("no access")):
                result = detect_language_from_file(temp_file)
                assert result == "java"
        finally:
            os.unlink(temp_file)

    def test_os_error_on_stat(self):
        """Lines 545-546: OSError on os.stat -> mtime_ns stays None."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".cs", delete=False
        ) as f:
            f.write("class Foo {}")
            temp_file = f.name

        try:
            with patch("os.stat", side_effect=OSError("disk error")):
                result = detect_language_from_file(temp_file)
                assert result == "csharp"
        finally:
            os.unlink(temp_file)

    def test_nonexistent_file_no_cache(self):
        """File doesn't exist -> mtime_ns is None, no caching."""
        result = detect_language_from_file("/nonexistent/path/to/file.rb")
        assert result == "ruby"

    def test_result_empty_returns_unknown(self):
        """Line 577: if detector returns empty -> 'unknown'."""
        with patch.object(detector, "detect_from_extension", return_value=""):
            result = detect_language_from_file("/some/file.xyz")
            assert result == "unknown"

    def test_result_blank_returns_unknown(self):
        """Line 577: if detector returns whitespace-only -> 'unknown'."""
        with patch.object(detector, "detect_from_extension", return_value="   "):
            result = detect_language_from_file("/some/file.xyz")
            assert result == "unknown"

    def test_result_none_returns_unknown(self):
        """Line 576: if detector returns None -> 'unknown'."""
        with patch.object(detector, "detect_from_extension", return_value=None):
            result = detect_language_from_file("/some/file.xyz")
            assert result == "unknown"

    def test_cache_lookup_import_error(self):
        """Lines 563-564: ImportError on shared_cache import -> proceeds without cache."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False
        ) as f:
            f.write("var x = 1;")
            temp_file = f.name

        try:
            original_import = __import__

            def failing_import(name, *args, **kwargs):
                if "shared_cache" in str(name):
                    raise ImportError("no shared_cache")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=failing_import):
                result = detect_language_from_file(temp_file)
                assert result == "javascript"
        finally:
            os.unlink(temp_file)

    def test_cache_lookup_general_exception(self):
        """Lines 566-568: general exception during cache lookup -> debug log, continue."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ts", delete=False
        ) as f:
            f.write("let x: number = 1;")
            temp_file = f.name

        try:
            # We need to make get_shared_cache().get_language_meta() raise
            # a non-Import exception. The import itself must succeed.
            mock_cache = MagicMock()
            mock_cache.get_language_meta.side_effect = RuntimeError("cache broken")

            mock_module = MagicMock()
            mock_module.get_shared_cache.return_value = mock_cache

            with patch.dict(
                "sys.modules",
                {"tree_sitter_analyzer.mcp.utils.shared_cache": mock_module},
            ):
                result = detect_language_from_file(temp_file)
                assert result == "typescript"
        finally:
            os.unlink(temp_file)

    def test_cache_hit_with_blank_language(self):
        """Line 561: cache returns blank language -> 'unknown'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("x = 1")
            temp_file = f.name

        try:
            mtime_ns = os.stat(temp_file).st_mtime_ns
            mock_cache = MagicMock()
            mock_cache.get_language_meta.return_value = {
                "language": "   ",
                "mtime_ns": mtime_ns,
            }

            mock_module = MagicMock()
            mock_module.get_shared_cache.return_value = mock_cache

            with patch.dict(
                "sys.modules",
                {"tree_sitter_analyzer.mcp.utils.shared_cache": mock_module},
            ):
                result = detect_language_from_file(temp_file)
                assert result == "unknown"
        finally:
            os.unlink(temp_file)

    def test_cache_hit_returns_valid_language(self):
        """Lines 554-560: cache hit with matching mtime returns cached language."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("x = 1")
            temp_file = f.name

        try:
            mtime_ns = os.stat(temp_file).st_mtime_ns
            mock_cache = MagicMock()
            mock_cache.get_language_meta.return_value = {
                "language": "python",
                "mtime_ns": mtime_ns,
            }

            mock_module = MagicMock()
            mock_module.get_shared_cache.return_value = mock_cache

            with patch.dict(
                "sys.modules",
                {"tree_sitter_analyzer.mcp.utils.shared_cache": mock_module},
            ):
                result = detect_language_from_file(temp_file)
                assert result == "python"
        finally:
            os.unlink(temp_file)

    def test_cache_store_import_error(self):
        """Lines 589-591: ImportError on cache store -> silently ignored."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".go", delete=False
        ) as f:
            f.write("package main")
            temp_file = f.name

        try:
            original_import = __import__

            def selective_import(name, *args, **kwargs):
                if "shared_cache" in str(name):
                    raise ImportError("no cache module")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=selective_import):
                result = detect_language_from_file(temp_file)
                assert result == "go"
        finally:
            os.unlink(temp_file)

    def test_cache_store_general_exception(self):
        """Lines 592-595: general exception on cache store -> debug logged, ignored."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".rb", delete=False
        ) as f:
            f.write("puts 'hello'")
            temp_file = f.name

        try:
            # Make cache lookup return None (cache miss), but store raises
            mock_cache = MagicMock()
            mock_cache.get_language_meta.return_value = None
            mock_cache.set_language_meta.side_effect = RuntimeError("store failed")

            mock_module = MagicMock()
            mock_module.get_shared_cache.return_value = mock_cache

            with patch.dict(
                "sys.modules",
                {"tree_sitter_analyzer.mcp.utils.shared_cache": mock_module},
            ):
                result = detect_language_from_file(temp_file)
                assert result == "ruby"
        finally:
            os.unlink(temp_file)


# ---------------------------------------------------------------------------
# is_language_supported: module-level function (lines 624, 626)
# ---------------------------------------------------------------------------


class TestIsLanguageSupportedModuleLevel:
    """Tests for the module-level is_language_supported function."""

    def test_supported_language(self):
        """Known supported language returns True."""
        assert is_language_supported("python") is True
        assert is_language_supported("java") is True

    def test_unsupported_language(self):
        """Unknown language returns False (exercises PluginManager path)."""
        assert is_language_supported("brainfuck") is False

    def test_plugin_manager_exception_fallback(self):
        """Lines 624-626: PluginManager raises -> fallback to detector.is_supported."""
        mock_module = MagicMock()
        mock_module.PluginManager.side_effect = RuntimeError("plugin error")

        with patch.dict(
            "sys.modules",
            {"tree_sitter_analyzer.plugins.manager": mock_module},
        ):
            # "nonexistent_xyz" is not in SUPPORTED_LANGUAGES
            result = is_language_supported("nonexistent_xyz")
            assert result is False


# ---------------------------------------------------------------------------
# detect_language_from_file: additional caching paths
# ---------------------------------------------------------------------------


class TestDetectLanguageFromFileCachePaths:
    """Test caching paths in detect_language_from_file more thoroughly."""

    def test_existing_file_detected_correctly(self):
        """Normal path: existing file is detected and result returned."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".kt", delete=False
        ) as f:
            f.write("fun main() {}")
            temp_file = f.name

        try:
            result = detect_language_from_file(temp_file)
            assert result == "kotlin"
        finally:
            os.unlink(temp_file)

    def test_expanduser_tilde_path(self):
        """Path with ~ gets expanded correctly (non-existent file, no cache)."""
        result = detect_language_from_file("~/project/main.py")
        assert result == "python"

    def test_yaml_detection(self):
        """Test .yml detection through detect_language_from_file."""
        result = detect_language_from_file("/some/path/config.yml")
        assert result == "yaml"

    def test_json_detection(self):
        """Test .json detection through detect_language_from_file."""
        result = detect_language_from_file("/config/settings.json")
        assert result == "json"

    def test_absolute_path_with_project_root(self):
        """Absolute path + project_root -> project_root ignored for absolute path."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False
        ) as f:
            f.write("class Test {}")
            temp_file = f.name

        try:
            result = detect_language_from_file(
                temp_file, project_root="/some/project"
            )
            assert result == "java"
        finally:
            os.unlink(temp_file)


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestAdditionalEdgeCases:
    """Additional edge cases to maximise coverage."""

    def test_detect_language_h_via_extension_map(self):
        """
        .h is in extension_map so detect_language returns early at line 306.
        This verifies the early-return path for ambiguous extensions in extension_map.
        """
        det = LanguageDetector()
        lang, conf = det.detect_language("header.h")
        assert lang == "c"
        assert conf == 0.7  # from extension_map

    def test_detect_language_m_via_extension_map(self):
        """.m in extension_map returns early with objectivec/0.7."""
        det = LanguageDetector()
        lang, conf = det.detect_language("file.m")
        # EXTENSION_MAPPING[".m"] = "objc", extension_map[".m"] = ("objectivec", 0.7)
        assert lang == "objc"
        assert conf == 0.7

    def test_detect_language_sql_via_extension_map(self):
        """.sql in extension_map returns early."""
        det = LanguageDetector()
        lang, conf = det.detect_language("query.sql")
        assert lang == "sql"
        assert conf == 0.9

    def test_c_family_tie_between_c_and_cpp(self):
        """C and C++ both score 1, objc scores 0 -> max returns first (cpp or c)."""
        det = LanguageDetector()
        # One C pattern, one C++ pattern
        content = "#include <stdio.h>\nstd::string s;"
        result = det._detect_c_family(content, ["c", "cpp", "objc"])
        assert result in ("c", "cpp")

    def test_objc_vs_matlab_both_zero(self):
        """Neither ObjC nor MATLAB patterns match -> candidates[0]."""
        det = LanguageDetector()
        result = det._detect_objc_vs_matlab("no patterns here", ["matlab", "objc"])
        assert result == "matlab"  # candidates[0]
