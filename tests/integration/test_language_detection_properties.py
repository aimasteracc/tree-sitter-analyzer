#!/usr/bin/env python3
"""
Property-based tests for language auto-detection.

Covering:
- Property 4: Language Auto-Detection (Requirements 4.6)
- Property 5: Output Format Consistency (Requirements 4.8)
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.language_detector import LanguageDetector
from tree_sitter_analyzer.models import AnalysisResult, Class, Function

# --- Strategies ---


@st.composite
def file_paths_with_extensions(draw: st.DrawFn) -> tuple[str, str]:
    """Generates file paths with known extensions and their expected languages."""
    language_extensions = {
        "go": [".go"],
        "rust": [".rs"],
        "kotlin": [".kt", ".kts"],
        "python": [".py", ".pyw", ".pyi"],
        "javascript": [".js", ".mjs", ".cjs"],
        "typescript": [".ts", ".mts", ".cts"],
        "java": [".java"],
    }

    language = draw(st.sampled_from(list(language_extensions.keys())))
    extension = draw(st.sampled_from(language_extensions[language]))

    # Generate a valid filename
    filename = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65
            ),
        )
    )

    if not filename:
        filename = "file"

    # Generate optional directory path
    include_path = draw(st.booleans())
    if include_path:
        dir_parts = draw(
            st.lists(
                st.text(
                    min_size=1,
                    max_size=10,
                    alphabet=st.characters(
                        whitelist_categories=("Ll", "Nd"), min_codepoint=97
                    ),
                ),
                min_size=1,
                max_size=3,
            )
        )
        dir_parts = [p for p in dir_parts if p]
        if dir_parts:
            path = "/".join(dir_parts) + "/" + filename + extension
        else:
            path = filename + extension
    else:
        path = filename + extension

    return (path, language)


@st.composite
def go_file_paths(draw: st.DrawFn) -> str:
    """Generates Go file paths."""
    filename = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65
            ),
        )
    )
    if not filename:
        filename = "main"
    return filename + ".go"


@st.composite
def rust_file_paths(draw: st.DrawFn) -> str:
    """Generates Rust file paths."""
    filename = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), min_codepoint=97),
        )
    )
    if not filename:
        filename = "lib"
    return filename + ".rs"


@st.composite
def kotlin_file_paths(draw: st.DrawFn) -> str:
    """Generates Kotlin file paths."""
    filename = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65
            ),
        )
    )
    if not filename:
        filename = "Main"
    extension = draw(st.sampled_from([".kt", ".kts"]))
    return filename + extension


class TestLanguageAutoDetectionProperties:
    """Property tests for language auto-detection (Property 4)."""

    @given(data=file_paths_with_extensions())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_property_4_language_detection_by_extension(
        self, data: tuple[str, str]
    ) -> None:
        """
        Property 4: Language Auto-Detection

        Validates that the language detector correctly identifies language
        from file extensions.
        Requirements: 4.6
        """
        file_path, expected_language = data

        detector = LanguageDetector()
        result = detector.detect_language(file_path)

        # Handle both tuple (language, confidence) and string return formats
        detected = result[0] if isinstance(result, tuple) else result

        assert (
            detected == expected_language
        ), f"Expected {expected_language} for {file_path}, got {detected}"

    @given(path=go_file_paths())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_4_go_file_detection(self, path: str) -> None:
        """
        Property 4: Go File Detection

        Validates that .go files are correctly detected as Go.
        Requirements: 4.6
        """
        detector = LanguageDetector()
        result = detector.detect_language(path)
        detected = result[0] if isinstance(result, tuple) else result

        assert detected == "go", f"Expected 'go' for {path}, got {detected}"

    @given(path=rust_file_paths())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_4_rust_file_detection(self, path: str) -> None:
        """
        Property 4: Rust File Detection

        Validates that .rs files are correctly detected as Rust.
        Requirements: 4.6
        """
        detector = LanguageDetector()
        result = detector.detect_language(path)
        detected = result[0] if isinstance(result, tuple) else result

        assert detected == "rust", f"Expected 'rust' for {path}, got {detected}"

    @given(path=kotlin_file_paths())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_4_kotlin_file_detection(self, path: str) -> None:
        """
        Property 4: Kotlin File Detection

        Validates that .kt and .kts files are correctly detected as Kotlin.
        Requirements: 4.6
        """
        detector = LanguageDetector()
        result = detector.detect_language(path)
        detected = result[0] if isinstance(result, tuple) else result

        assert detected == "kotlin", f"Expected 'kotlin' for {path}, got {detected}"

    def test_property_4_case_insensitivity(self) -> None:
        """
        Property 4: Case Insensitivity

        Validates that language detection is case-insensitive.
        Requirements: 4.6
        """
        detector = LanguageDetector()

        # Test various case combinations
        test_cases = [
            ("main.GO", "go"),
            ("lib.RS", "rust"),
            ("Main.KT", "kotlin"),
            ("test.Go", "go"),
            ("test.Rs", "rust"),
            ("test.Kt", "kotlin"),
        ]

        for file_path, expected in test_cases:
            result = detector.detect_language(file_path)
            detected = result[0] if isinstance(result, tuple) else result
            assert (
                detected == expected
            ), f"Expected {expected} for {file_path}, got {detected}"


class TestOutputFormatConsistencyProperties:
    """Property tests for output format consistency (Property 5)."""

    @given(
        funcs=st.lists(
            st.builds(
                Function,
                name=st.text(min_size=1, max_size=20),
                start_line=st.integers(1, 100),
                end_line=st.integers(1, 100),
            ),
            max_size=5,
        ),
        classes=st.lists(
            st.builds(
                Class,
                name=st.text(min_size=1, max_size=20),
                start_line=st.integers(1, 100),
                end_line=st.integers(1, 100),
            ),
            max_size=5,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_property_5_go_output_format_consistency(
        self, funcs: list[Function], classes: list[Class]
    ) -> None:
        """
        Property 5: Output Format Consistency (Go)

        Validates that Go analysis results can be formatted in all output formats.
        Requirements: 4.8
        """
        from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter

        result = AnalysisResult(
            file_path="test.go",
            language="go",
            elements=funcs + classes,
            line_count=100,
        )

        formatter = GoTableFormatter()

        # Test all formats
        full_output = formatter.format_table(result.to_dict(), table_type="full")
        compact_output = formatter.format_summary(result.to_dict())

        # Verify outputs are non-empty strings
        assert isinstance(full_output, str)
        assert isinstance(compact_output, str)
        assert len(full_output) > 0
        assert len(compact_output) > 0

    @given(
        funcs=st.lists(
            st.builds(
                Function,
                name=st.text(min_size=1, max_size=20),
                start_line=st.integers(1, 100),
                end_line=st.integers(1, 100),
            ),
            max_size=5,
        ),
        classes=st.lists(
            st.builds(
                Class,
                name=st.text(min_size=1, max_size=20),
                start_line=st.integers(1, 100),
                end_line=st.integers(1, 100),
            ),
            max_size=5,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_property_5_rust_output_format_consistency(
        self, funcs: list[Function], classes: list[Class]
    ) -> None:
        """
        Property 5: Output Format Consistency (Rust)

        Validates that Rust analysis results can be formatted in all output formats.
        Requirements: 4.8
        """
        from tree_sitter_analyzer.formatters.rust_formatter import RustTableFormatter

        result = AnalysisResult(
            file_path="test.rs",
            language="rust",
            elements=funcs + classes,
            line_count=100,
        )

        formatter = RustTableFormatter()

        # Test all formats
        full_output = formatter.format_table(result.to_dict(), table_type="full")
        compact_output = formatter.format_summary(result.to_dict())

        # Verify outputs are non-empty strings
        assert isinstance(full_output, str)
        assert isinstance(compact_output, str)
        assert len(full_output) > 0
        assert len(compact_output) > 0

    @given(
        funcs=st.lists(
            st.builds(
                Function,
                name=st.text(min_size=1, max_size=20),
                start_line=st.integers(1, 100),
                end_line=st.integers(1, 100),
            ),
            max_size=5,
        ),
        classes=st.lists(
            st.builds(
                Class,
                name=st.text(min_size=1, max_size=20),
                start_line=st.integers(1, 100),
                end_line=st.integers(1, 100),
            ),
            max_size=5,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_property_5_kotlin_output_format_consistency(
        self, funcs: list[Function], classes: list[Class]
    ) -> None:
        """
        Property 5: Output Format Consistency (Kotlin)

        Validates that Kotlin analysis results can be formatted in all output formats.
        Requirements: 4.8
        """
        from tree_sitter_analyzer.formatters.kotlin_formatter import (
            KotlinTableFormatter,
        )

        result = AnalysisResult(
            file_path="test.kt",
            language="kotlin",
            elements=funcs + classes,
            line_count=100,
        )

        formatter = KotlinTableFormatter()

        # Test all formats
        full_output = formatter.format_table(result.to_dict(), table_type="full")
        compact_output = formatter.format_summary(result.to_dict())

        # Verify outputs are non-empty strings
        assert isinstance(full_output, str)
        assert isinstance(compact_output, str)
        assert len(full_output) > 0
        assert len(compact_output) > 0

    @given(
        language=st.sampled_from(["go", "rust", "kotlin"]),
        funcs=st.lists(
            st.builds(
                Function,
                name=st.text(min_size=1, max_size=20),
                start_line=st.integers(1, 100),
                end_line=st.integers(1, 100),
            ),
            max_size=3,
        ),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_property_5_cross_language_format_structure(
        self, language: str, funcs: list[Function]
    ) -> None:
        """
        Property 5: Cross-Language Format Structure

        Validates that all languages produce structurally similar outputs.
        Requirements: 4.8
        """
        from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter
        from tree_sitter_analyzer.formatters.kotlin_formatter import (
            KotlinTableFormatter,
        )
        from tree_sitter_analyzer.formatters.rust_formatter import RustTableFormatter

        extensions = {"go": ".go", "rust": ".rs", "kotlin": ".kt"}
        formatters = {
            "go": GoTableFormatter,
            "rust": RustTableFormatter,
            "kotlin": KotlinTableFormatter,
        }

        result = AnalysisResult(
            file_path=f"test{extensions[language]}",
            language=language,
            elements=funcs,
            line_count=100,
        )

        formatter = formatters[language]()
        full_output = formatter.format_table(result.to_dict(), table_type="full")

        # All outputs should be markdown-like with headers
        assert "#" in full_output, f"Expected markdown headers in {language} output"

        # All outputs should have tables (pipe characters)
        if funcs:
            assert "|" in full_output, f"Expected table format in {language} output"
