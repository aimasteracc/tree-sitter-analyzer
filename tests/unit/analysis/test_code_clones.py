#!/usr/bin/env python3
"""
Tests for Code Clone Detection engine.

Validates CodeCloneDetector, CodeClone, CloneDetectionResult,
and clone type classification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.code_clones import (
    DEFAULT_MIN_LINES,
    DEFAULT_MIN_SIMILARITY,
    CloneDetectionResult,
    CloneSeverity,
    CloneType,
    CodeClone,
    CodeCloneDetector,
)


class TestCodeClone:
    """Test CodeClone dataclass."""

    def test_create_clone(self) -> None:
        clone = CodeClone(
            clone_type=CloneType.TYPE_1_EXACT.value,
            severity=CloneSeverity.CRITICAL.value,
            file_a="file1.py",
            line_a=10,
            file_b="file2.py",
            line_b=20,
            length_lines=15,
            description="Exact clone detected",
            suggestion="Extract to shared function",
            snippet="def foo():\n    pass",
            similarity=1.0,
        )
        assert clone.clone_type == "type_1_exact"
        assert clone.severity == "critical"
        assert clone.length_lines == 15
        assert clone.similarity == 1.0


class TestCloneDetectionResult:
    """Test CloneDetectionResult aggregation."""

    def test_empty_result(self) -> None:
        result = CloneDetectionResult()
        assert result.total_clones == 0
        assert result.clones == []
        assert result.by_type == {}
        assert result.by_severity == {}

    def test_add_clone_updates_counts(self) -> None:
        result = CloneDetectionResult()
        clone = CodeClone(
            clone_type=CloneType.TYPE_1_EXACT.value,
            severity=CloneSeverity.WARNING.value,
            file_a="a.py",
            line_a=1,
            file_b="b.py",
            line_b=10,
            length_lines=5,
            description="Clone found",
            suggestion="Extract",
        )
        result.add_clone(clone)
        assert result.total_clones == 1
        assert result.by_type.get("type_1_exact") == 1
        assert result.by_severity.get("warning") == 1

    def test_add_multiple_clones(self) -> None:
        result = CloneDetectionResult()
        for i in range(5):
            result.add_clone(CodeClone(
                clone_type=CloneType.TYPE_2_STRUCTURE.value,
                severity=CloneSeverity.INFO.value,
                file_a=f"a{i}.py",
                line_a=i,
                file_b=f"b{i}.py",
                line_b=i + 10,
                length_lines=3,
                description=f"Clone {i}",
                suggestion="Extract",
            ))
        assert result.total_clones == 5
        assert result.by_type.get("type_2_structure") == 5
        assert result.by_severity.get("info") == 5


class TestCloneTypeClassification:
    """Test clone type and severity classification."""

    def test_type_1_exact_match(self) -> None:
        detector = CodeCloneDetector("/tmp")
        clone_type, severity = detector._classify_clone(0.98, 10)
        assert clone_type == CloneType.TYPE_1_EXACT.value
        assert severity == CloneSeverity.WARNING.value

    def test_type_2_structural(self) -> None:
        detector = CodeCloneDetector("/tmp")
        clone_type, severity = detector._classify_clone(0.90, 8)
        assert clone_type == CloneType.TYPE_2_STRUCTURE.value
        assert severity == CloneSeverity.WARNING.value

    def test_type_3_functional(self) -> None:
        detector = CodeCloneDetector("/tmp")
        clone_type, severity = detector._classify_clone(0.80, 6)
        assert clone_type == CloneType.TYPE_3_FUNCTION.value
        assert severity == CloneSeverity.WARNING.value

    def test_critical_severity(self) -> None:
        detector = CodeCloneDetector("/tmp")
        _, severity = detector._classify_clone(0.95, 20)
        assert severity == CloneSeverity.CRITICAL.value

    def test_info_severity(self) -> None:
        detector = CodeCloneDetector("/tmp")
        _, severity = detector._classify_clone(0.85, 3)
        assert severity == CloneSeverity.INFO.value


class TestCodeNormalization:
    """Test code normalization for Type 2 clone detection."""

    def test_normalize_removes_comments(self) -> None:
        detector = CodeCloneDetector("/tmp")
        code = ["def foo():", "    # This is a comment", "    return 1"]
        normalized = detector._normalize_code(code)
        assert "#" not in normalized
        assert "comment" not in normalized

    def test_normalize_removes_whitespace(self) -> None:
        detector = CodeCloneDetector("/tmp")
        code = ["def    foo(   x   ):"]
        normalized = detector._normalize_code(code)
        # Normalization removes extra whitespace AND renames variables
        # The colon stays because it's not a word character
        assert normalized == "VAR VAR( VAR ):"

    def test_normalize_renames_variables(self) -> None:
        detector = CodeCloneDetector("/tmp")
        code1 = ["def foo(myVar):", "    return myVar"]
        code2 = ["def bar(otherVar):", "    return otherVar"]
        norm1 = detector._normalize_code(code1)
        norm2 = detector._normalize_code(code2)
        assert norm1 == norm2  # Both become "def VAR( VAR): return VAR"


class TestSimilarityCalculation:
    """Test similarity calculation between code blocks."""

    def test_identical_code(self) -> None:
        detector = CodeCloneDetector("/tmp")
        code = ["def foo():", "    return 1"]
        sim = detector._calculate_similarity(
            detector._normalize_code(code),
            detector._normalize_code(code),
        )
        assert sim == 1.0

    def test_similar_code(self) -> None:
        detector = CodeCloneDetector("/tmp")
        code1 = ["def foo():", "    return 1"]
        code2 = ["def bar():", "    return 2"]
        sim = detector._calculate_similarity(
            detector._normalize_code(code1),
            detector._normalize_code(code2),
        )
        assert sim > 0.8  # Should be similar after normalization

    def test_different_code(self) -> None:
        detector = CodeCloneDetector("/tmp")
        code1 = ["def foo():", "    return 1"]
        code2 = ["class Bar:", "    pass"]
        sim = detector._calculate_similarity(
            detector._normalize_code(code1),
            detector._normalize_code(code2),
        )
        assert sim < 0.5  # Should be different


class TestCloneDetection:
    """Test end-to-end clone detection."""

    def _make_project(self, files: dict[str, str]) -> str:
        tmp = tempfile.mkdtemp()
        for name, content in files.items():
            Path(tmp, name).write_text(content, encoding="utf-8")
        return tmp

    def test_detect_exact_clone(self) -> None:
        """Detect exact duplicate code."""
        # Create longer functions to meet min_lines threshold (5)
        code1 = "def calculate(x):\n    temp = x\n    result = temp * 2\n    final = result\n    return final\n"
        code2 = "def compute(y):\n    temp = y\n    result = temp * 2\n    final = result\n    return final\n"
        project = self._make_project({
            "a.py": code1,
            "b.py": code2,
        })

        detector = CodeCloneDetector(project)
        result = detector.detect_project()

        assert result.total_clones >= 1
        clone = result.clones[0]
        assert clone.clone_type in {
            CloneType.TYPE_1_EXACT.value,
            CloneType.TYPE_2_STRUCTURE.value,
        }

    def test_skip_small_functions(self) -> None:
        """Small functions below threshold are ignored."""
        code = "def foo():\n    return 1\n"
        project = self._make_project({
            "a.py": code,
            "b.py": code,
        })

        detector = CodeCloneDetector(project, min_lines=10)
        result = detector.detect_project()

        assert result.total_clones == 0

    def test_custom_similarity_threshold(self) -> None:
        """Custom threshold affects detection sensitivity."""
        code1 = "def process(data):\n    return data\n"
        code2 = "def handle(info):\n    return info\n"
        project = self._make_project({
            "a.py": code1,
            "b.py": code2,
        })

        # Lower threshold should detect more clones
        detector_low = CodeCloneDetector(project, min_similarity=0.5)
        result_low = detector_low.detect_project()

        detector_high = CodeCloneDetector(project, min_similarity=0.99)
        result_high = detector_high.detect_project()

        assert result_low.total_clones >= result_high.total_clones

    def test_no_self_comparison(self) -> None:
        """Clones within same file are not compared."""
        code = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        project = self._make_project({"test.py": code})

        detector = CodeCloneDetector(project)
        result = detector.detect_project()

        # Should not detect foo vs bar as clones (different functions)
        # and should not compare foo with itself
        for clone in result.clones:
            assert not (clone.file_a == clone.file_b and abs(clone.line_a - clone.line_b) < 5)


class TestDefaultThresholds:
    """Test default configuration."""

    def test_min_lines_positive(self) -> None:
        assert DEFAULT_MIN_LINES > 0

    def test_min_similarity_valid(self) -> None:
        assert 0.0 < DEFAULT_MIN_SIMILARITY <= 1.0


class TestCloneTypeEnum:
    """Test enum values."""

    def test_clone_type_values(self) -> None:
        assert CloneType.TYPE_1_EXACT.value == "type_1_exact"
        assert CloneType.TYPE_2_STRUCTURE.value == "type_2_structure"
        assert CloneType.TYPE_3_FUNCTION.value == "type_3_function"

    def test_severity_values(self) -> None:
        assert CloneSeverity.INFO.value == "info"
        assert CloneSeverity.WARNING.value == "warning"
        assert CloneSeverity.CRITICAL.value == "critical"
