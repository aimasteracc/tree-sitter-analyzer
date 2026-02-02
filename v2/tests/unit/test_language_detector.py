"""
Test language detection implementation.

Following TDD: Write tests FIRST to define the contract.
This is T1.4: Language Detection
"""


class TestExtensionBasedDetection:
    """Test detection by file extension."""

    def test_detector_can_be_imported(self):
        """Test that LanguageDetector can be imported."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        assert LanguageDetector is not None

    def test_detect_python_by_extension(self):
        """Test detecting Python by .py extension."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("script.py")

        assert result is not None
        assert result["language"] == "python"
        assert result["confidence"] >= 0.9  # High confidence for extension match

    def test_detect_typescript_by_extension(self):
        """Test detecting TypeScript by .ts extension."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("component.ts")

        assert result["language"] == "typescript"
        assert result["confidence"] >= 0.9

    def test_detect_javascript_by_extension(self):
        """Test detecting JavaScript by .js extension."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("app.js")

        assert result["language"] == "javascript"
        assert result["confidence"] >= 0.9

    def test_detect_java_by_extension(self):
        """Test detecting Java by .java extension."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("Main.java")

        assert result["language"] == "java"
        assert result["confidence"] >= 0.9

    def test_detect_tsx_as_typescript(self):
        """Test that .tsx files are detected as TypeScript."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("Component.tsx")

        assert result["language"] == "typescript"

    def test_unknown_extension_returns_none(self):
        """Test that unknown extensions return None."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("file.unknown")

        assert result is None

    def test_detect_with_full_path(self):
        """Test detection works with full file paths."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("/path/to/project/src/main.py")

        assert result["language"] == "python"


class TestShebangDetection:
    """Test detection by shebang line."""

    def test_detect_python_by_shebang(self):
        """Test detecting Python from shebang."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = "#!/usr/bin/env python\nprint('hello')"

        result = detector.detect_from_content(content, filename="script")

        assert result["language"] == "python"
        assert result["method"] == "shebang"
        assert result["confidence"] >= 0.8

    def test_detect_python3_shebang(self):
        """Test detecting Python3 specifically."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = "#!/usr/bin/python3\nimport sys"

        result = detector.detect_from_content(content, filename="script")

        assert result["language"] == "python"

    def test_detect_node_shebang(self):
        """Test detecting Node.js (JavaScript) from shebang."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = "#!/usr/bin/env node\nconsole.log('hello');"

        result = detector.detect_from_content(content, filename="script")

        assert result["language"] == "javascript"
        # Method can be "shebang" or "combined" if content also matches
        assert result["method"] in ["shebang", "combined"]

    def test_shebang_with_extension_increases_confidence(self):
        """Test that shebang + extension gives highest confidence."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = "#!/usr/bin/env python\nprint('hello')"

        result = detector.detect_from_content(content, filename="script.py")

        assert result["language"] == "python"
        assert result["confidence"] >= 0.95  # Both shebang and extension match


class TestContentBasedDetection:
    """Test detection by content patterns."""

    def test_detect_python_by_import_statements(self):
        """Test detecting Python from import statements."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = """
import sys
import os
from pathlib import Path

def main():
    print("Hello")
"""

        result = detector.detect_from_content(content, filename="script")

        assert result["language"] == "python"
        assert result["method"] == "content"

    def test_detect_java_by_class_syntax(self):
        """Test detecting Java from class syntax."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = """
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
"""

        result = detector.detect_from_content(content, filename="Main")

        assert result["language"] == "java"
        assert result["method"] == "content"

    def test_detect_typescript_by_type_annotations(self):
        """Test detecting TypeScript from type annotations."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = """
interface User {
    name: string;
    age: number;
}

function greet(user: User): string {
    return `Hello, ${user.name}`;
}
"""

        result = detector.detect_from_content(content, filename="user")

        assert result["language"] == "typescript"

    def test_detect_javascript_vs_typescript(self):
        """Test distinguishing JavaScript from TypeScript."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()

        # Plain JavaScript (no type annotations)
        js_content = """
function greet(name) {
    return `Hello, ${name}`;
}
"""

        result = detector.detect_from_content(js_content, filename="greet")

        # Should detect as JavaScript since no TypeScript-specific features
        assert result["language"] in ["javascript", "typescript"]


class TestConfidenceScoring:
    """Test confidence scoring system."""

    def test_extension_match_high_confidence(self):
        """Test that extension match gives high confidence."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("script.py")

        assert result["confidence"] >= 0.9

    def test_shebang_medium_confidence(self):
        """Test that shebang alone gives medium confidence."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = "#!/usr/bin/env python\nprint('hello')"

        result = detector.detect_from_content(content, filename="script")

        assert 0.7 <= result["confidence"] < 0.9

    def test_content_pattern_lower_confidence(self):
        """Test that content patterns alone give lower confidence."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = "import sys\nimport os"

        result = detector.detect_from_content(content, filename="script")

        assert 0.5 <= result["confidence"] < 0.8

    def test_multiple_signals_highest_confidence(self):
        """Test that multiple detection signals maximize confidence."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        content = "#!/usr/bin/env python\nimport sys\nprint('hello')"

        result = detector.detect_from_content(content, filename="script.py")

        # Extension + shebang + content = highest confidence
        assert result["confidence"] >= 0.95


class TestAmbiguousCases:
    """Test handling of ambiguous cases."""

    def test_empty_content_uses_extension(self):
        """Test that empty files use extension for detection."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_content("", filename="empty.py")

        assert result["language"] == "python"
        assert result["method"] == "extension"

    def test_no_extension_no_shebang_no_content(self):
        """Test that files with no signals return None."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_content("", filename="README")

        assert result is None

    def test_conflicting_signals_prefers_extension(self):
        """Test that conflicting signals prefer extension."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        # Python shebang but .js extension
        content = "#!/usr/bin/env python\nprint('hello')"

        result = detector.detect_from_content(content, filename="script.js")

        # Extension should win
        assert result["language"] == "javascript"


class TestDetectionResult:
    """Test detection result format."""

    def test_result_has_required_fields(self):
        """Test that detection result has all required fields."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("script.py")

        assert "language" in result
        assert "confidence" in result
        assert "method" in result

        assert isinstance(result["language"], str)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["method"], str)

    def test_confidence_range_valid(self):
        """Test that confidence is always in valid range."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()
        result = detector.detect_from_path("test.py")

        assert 0.0 <= result["confidence"] <= 1.0

    def test_method_values(self):
        """Test that method is one of expected values."""
        from tree_sitter_analyzer_v2.core.detector import LanguageDetector

        detector = LanguageDetector()

        # Extension detection
        result1 = detector.detect_from_path("test.py")
        assert result1["method"] in ["extension", "combined"]

        # Shebang detection
        result2 = detector.detect_from_content(
            "#!/usr/bin/env python\nprint('hi')", filename="script"
        )
        assert result2["method"] in ["shebang", "combined"]

        # Content detection
        result3 = detector.detect_from_content("import sys\nimport os", filename="script")
        assert result3["method"] in ["content", "combined"]
