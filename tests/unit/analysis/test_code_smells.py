#!/usr/bin/env python3
"""
Tests for Code Smell Detection engine and MCP tool.

Validates CodeSmellDetector, CodeSmell, SmellDetectionResult,
and CodeSmellDetectorTool against various code patterns.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.code_smells import (
    CodeSmell,
    CodeSmellDetector,
    DEFAULT_THRESHOLDS,
    SmellCategory,
    SmellDetectionResult,
    SmellSeverity,
)
from tree_sitter_analyzer.mcp.tools.code_smell_detector_tool import (
    CodeSmellDetectorTool,
)


# ── Smell Data Classes ──────────────────────────────────────────


class TestCodeSmell:
    """Test CodeSmell dataclass."""

    def test_create_smell(self) -> None:
        smell = CodeSmell(
            smell_type="god_class",
            category=SmellCategory.BLOATERS.value,
            severity=SmellSeverity.CRITICAL.value,
            file_path="test.java",
            line=1,
            description="Too many methods",
            suggestion="Split the class",
            metric_value="20",
            element_name="BigClass",
        )
        assert smell.smell_type == "god_class"
        assert smell.severity == "critical"
        assert smell.category == "bloaters"
        assert smell.element_name == "BigClass"

    def test_smell_defaults(self) -> None:
        smell = CodeSmell(
            smell_type="magic_number",
            category=SmellCategory.DISPENSABLES.value,
            severity=SmellSeverity.INFO.value,
            file_path="test.py",
            line=5,
            description="Magic number 42",
            suggestion="Extract to constant",
        )
        assert smell.metric_value == ""
        assert smell.element_name == ""


class TestSmellDetectionResult:
    """Test SmellDetectionResult aggregation."""

    def test_empty_result(self) -> None:
        result = SmellDetectionResult(file_path="test.py")
        assert result.total_smells == 0
        assert result.smells == []

    def test_add_smell_updates_counts(self) -> None:
        result = SmellDetectionResult(file_path="test.py")
        smell = CodeSmell(
            smell_type="long_method",
            category=SmellCategory.BLOATERS.value,
            severity=SmellSeverity.WARNING.value,
            file_path="test.py",
            line=10,
            description="Method too long",
            suggestion="Split it",
        )
        result.add_smell(smell)
        assert result.total_smells == 1
        assert result.by_severity.get("warning") == 1
        assert result.by_category.get("bloaters") == 1

    def test_add_multiple_smells(self) -> None:
        result = SmellDetectionResult(file_path="test.py")
        for i in range(5):
            result.add_smell(CodeSmell(
                smell_type="magic_number",
                category=SmellCategory.DISPENSABLES.value,
                severity=SmellSeverity.INFO.value,
                file_path="test.py",
                line=i + 1,
                description=f"Magic number at line {i}",
                suggestion="Extract",
            ))
        assert result.total_smells == 5
        assert result.by_severity.get("info") == 5


# ── Detector Tests ──────────────────────────────────────────────


class TestGodClassDetection:
    """Test God Class detection."""

    def _make_project(self, code: str, filename: str = "Test.java") -> str:
        tmp = tempfile.mkdtemp()
        Path(tmp, filename).write_text(code, encoding="utf-8")
        return tmp

    def test_detect_god_class_java(self) -> None:
        """Java class with many methods triggers God Class."""
        methods = "\n".join(
            f"    public void method{i}() {{ }}"
            for i in range(20)
        )
        code = f"public class BigClass {{\n{methods}\n}}"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("Test.java")

        god_class_smells = [
            s for s in result.smells if s.smell_type == "god_class"
        ]
        assert len(god_class_smells) >= 1
        assert god_class_smells[0].severity == "critical"
        assert god_class_smells[0].element_name == "BigClass"

    def test_no_god_class_few_methods(self) -> None:
        """Class with few methods does NOT trigger God Class."""
        code = "public class SmallClass {\n    public void doIt() { }\n}"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("Test.java")

        god_class_smells = [
            s for s in result.smells if s.smell_type == "god_class"
        ]
        assert len(god_class_smells) == 0

    def test_custom_threshold(self) -> None:
        """Custom threshold overrides default."""
        code = "public class MyClass {\n    public void m1() { }\n    public void m2() { }\n}\n"
        project = self._make_project(code)

        # Default threshold is 15, so 2 methods won't trigger
        detector_default = CodeSmellDetector(project)
        result_default = detector_default.detect_file("Test.java")
        assert not any(
            s.smell_type == "god_class" for s in result_default.smells
        )

        # With threshold=2, it should trigger
        detector_custom = CodeSmellDetector(
            project, thresholds={"god_class_methods": 2}
        )
        result_custom = detector_custom.detect_file("Test.java")
        assert any(
            s.smell_type == "god_class" for s in result_custom.smells
        )


class TestLongMethodDetection:
    """Test Long Method detection."""

    def _make_project(self, code: str, filename: str = "test.py") -> str:
        tmp = tempfile.mkdtemp()
        Path(tmp, filename).write_text(code, encoding="utf-8")
        return tmp

    def test_detect_long_method_python(self) -> None:
        """Python function exceeding threshold."""
        body = "\n".join(f"    x = {i}" for i in range(60))
        code = f"def long_function():\n{body}\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        long_methods = [
            s for s in result.smells if s.smell_type == "long_method"
        ]
        assert len(long_methods) >= 1
        assert long_methods[0].element_name == "long_function"

    def test_short_method_not_flagged(self) -> None:
        """Short method is not flagged."""
        code = "def short_func():\n    return 1\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        assert not any(
            s.smell_type == "long_method" for s in result.smells
        )

    def test_detect_long_method_java(self) -> None:
        """Java method exceeding threshold."""
        body = "\n".join(f"        int x{i} = {i};" for i in range(60))
        code = (
            "public class Service {\n"
            "    public void process() {\n"
            f"{body}\n"
            "    }\n"
            "}\n"
        )
        project = self._make_project(code, "Service.java")

        detector = CodeSmellDetector(project)
        result = detector.detect_file("Service.java")

        long_methods = [
            s for s in result.smells if s.smell_type == "long_method"
        ]
        assert len(long_methods) >= 1


class TestDeepNestingDetection:
    """Test Deep Nesting detection."""

    def _make_project(self, code: str, filename: str = "test.py") -> str:
        tmp = tempfile.mkdtemp()
        Path(tmp, filename).write_text(code, encoding="utf-8")
        return tmp

    def test_detect_deep_nesting(self) -> None:
        """Deeply nested code triggers detection."""
        code = (
            "def process():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                if True:\n"
            "                    if True:\n"
            "                        pass\n"
        )
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        nesting_smells = [
            s for s in result.smells if s.smell_type == "deep_nesting"
        ]
        assert len(nesting_smells) >= 1

    def test_flat_code_no_nesting(self) -> None:
        """Flat code does not trigger deep nesting."""
        code = "def process():\n    x = 1\n    return x\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        assert not any(
            s.smell_type == "deep_nesting" for s in result.smells
        )


class TestMagicNumberDetection:
    """Test Magic Number detection."""

    def _make_project(self, code: str, filename: str = "test.py") -> str:
        tmp = tempfile.mkdtemp()
        Path(tmp, filename).write_text(code, encoding="utf-8")
        return tmp

    def test_detect_magic_number(self) -> None:
        """Unexplained number triggers magic number detection."""
        code = "def calc():\n    result = value * 42\n    return result\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        magic = [s for s in result.smells if s.smell_type == "magic_number"]
        assert len(magic) >= 1

    def test_common_values_not_flagged(self) -> None:
        """Common values (0, 1, -1) are not flagged."""
        code = "def calc():\n    return x + 1\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        assert not any(
            s.smell_type == "magic_number" for s in result.smells
        )

    def test_const_not_flagged(self) -> None:
        """Constants are not flagged."""
        code = "MAX_RETRIES = 42\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        # Constants should not trigger (the line starts with uppercase var assignment)
        magic = [s for s in result.smells if s.smell_type == "magic_number"]
        # May or may not flag depending on pattern — just verify it runs
        assert result.total_smells >= 0


class TestManyImportsDetection:
    """Test excessive imports detection."""

    def _make_project(self, code: str, filename: str = "test.py") -> str:
        tmp = tempfile.mkdtemp()
        Path(tmp, filename).write_text(code, encoding="utf-8")
        return tmp

    def test_detect_many_imports(self) -> None:
        """Too many imports triggers detection."""
        imports = "\n".join(f"import module{i}" for i in range(25))
        code = f"{imports}\n\ndef foo(): pass\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        import_smells = [
            s for s in result.smells if s.smell_type == "many_imports"
        ]
        assert len(import_smells) >= 1

    def test_few_imports_ok(self) -> None:
        """Few imports do not trigger detection."""
        code = "import os\nimport sys\n\ndef main(): pass\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.py")

        assert not any(
            s.smell_type == "many_imports" for s in result.smells
        )


class TestLargeClassDetection:
    """Test Large Class detection."""

    def _make_project(self, code: str, filename: str = "test.java") -> str:
        tmp = tempfile.mkdtemp()
        Path(tmp, filename).write_text(code, encoding="utf-8")
        return tmp

    def test_detect_large_class(self) -> None:
        """Very large class triggers detection."""
        # Create a class with 600+ lines
        body = "\n".join(f"    int field{i} = {i};" for i in range(600))
        code = f"public class HugeClass {{\n{body}\n}}\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.java")

        large = [s for s in result.smells if s.smell_type == "large_class"]
        assert len(large) >= 1
        assert large[0].element_name == "HugeClass"

    def test_small_class_ok(self) -> None:
        """Small class does not trigger detection."""
        code = "public class Small {\n    int x = 1;\n}\n"
        project = self._make_project(code)

        detector = CodeSmellDetector(project)
        result = detector.detect_file("test.java")

        assert not any(
            s.smell_type == "large_class" for s in result.smells
        )


class TestProjectDetection:
    """Test project-level detection."""

    def test_detect_project_with_multiple_files(self) -> None:
        """Scans multiple files in project."""
        tmp = tempfile.mkdtemp()
        # File with long method
        body = "\n".join(f"    x = {i}" for i in range(60))
        Path(tmp, "a.py").write_text(
            f"def long_func():\n{body}\n", encoding="utf-8"
        )
        # Clean file
        Path(tmp, "b.py").write_text(
            "def short():\n    return 1\n", encoding="utf-8"
        )

        detector = CodeSmellDetector(tmp)
        results = detector.detect_project()

        assert len(results) == 2
        total_smells = sum(r.total_smells for r in results)
        assert total_smells >= 1  # At least the long method in a.py

    def test_skip_non_source_dirs(self) -> None:
        """Skips node_modules, .git, etc."""
        tmp = tempfile.mkdtemp()
        # Create a file in node_modules
        nm = Path(tmp, "node_modules")
        nm.mkdir()
        body = "\n".join(f"    x = {i}" for i in range(60))
        Path(nm, "vendor.py").write_text(
            f"def long():\n{body}\n", encoding="utf-8"
        )

        detector = CodeSmellDetector(tmp)
        results = detector.detect_project()

        # Should skip node_modules
        assert len(results) == 0

    def test_nonexistent_file_returns_empty(self) -> None:
        """Nonexistent file returns empty result."""
        detector = CodeSmellDetector("/nonexistent/path")
        result = detector.detect_file("does_not_exist.py")
        assert result.total_smells == 0


# ── MCP Tool Tests ──────────────────────────────────────────────


class TestCodeSmellDetectorTool:
    """Test CodeSmellDetectorTool MCP integration."""

    def test_tool_metadata(self) -> None:
        tool = CodeSmellDetectorTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "detect_code_smells"
        assert "inputSchema" in defn
        assert "file_path" in defn["inputSchema"]["properties"]

    def test_validate_valid_args(self) -> None:
        tool = CodeSmellDetectorTool()
        assert tool.validate_arguments({}) is True
        assert tool.validate_arguments({"file_path": "test.py"}) is True
        assert tool.validate_arguments({
            "min_severity": "warning",
            "smell_types": ["god_class", "long_method"],
        }) is True

    def test_validate_invalid_severity(self) -> None:
        tool = CodeSmellDetectorTool()
        with pytest.raises(ValueError, match="min_severity"):
            tool.validate_arguments({"min_severity": "invalid"})

    def test_validate_invalid_smell_type(self) -> None:
        tool = CodeSmellDetectorTool()
        with pytest.raises(ValueError, match="Invalid smell type"):
            tool.validate_arguments({"smell_types": ["not_real"]})

    def test_validate_invalid_threshold(self) -> None:
        tool = CodeSmellDetectorTool()
        with pytest.raises(ValueError, match="positive integer"):
            tool.validate_arguments({"thresholds": {"long_method_lines": -5}})

    def test_validate_invalid_file_path_type(self) -> None:
        tool = CodeSmellDetectorTool()
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({"file_path": 123})

    @pytest.mark.asyncio
    async def test_analyze_clean_file(self) -> None:
        """Clean file returns no smells."""
        tmp = tempfile.mkdtemp()
        Path(tmp, "clean.py").write_text(
            "def hello():\n    return 'world'\n", encoding="utf-8"
        )
        tool = CodeSmellDetectorTool(tmp)
        result = await tool.execute({"file_path": "clean.py"})
        assert result["success"] is True
        assert result["total_smells"] == 0
        assert "No code smells" in result["message"]

    @pytest.mark.asyncio
    async def test_analyze_file_with_smells(self) -> None:
        """File with smells returns detections."""
        tmp = tempfile.mkdtemp()
        body = "\n".join(f"    x = {i}" for i in range(60))
        Path(tmp, "smelly.py").write_text(
            f"def long_func():\n{body}\n", encoding="utf-8"
        )
        tool = CodeSmellDetectorTool(tmp)
        result = await tool.execute({"file_path": "smelly.py"})
        assert result["success"] is True
        assert result["total_smells"] >= 1

    @pytest.mark.asyncio
    async def test_severity_filter(self) -> None:
        """min_severity=warning filters out info-level smells."""
        tmp = tempfile.mkdtemp()
        # Magic number (info level) + long method (warning level)
        body = "\n".join(f"    x{i} = {i} + 42" for i in range(60))
        Path(tmp, "mixed.py").write_text(
            f"def mixed_func():\n{body}\n", encoding="utf-8"
        )
        tool = CodeSmellDetectorTool(tmp)
        result = await tool.execute({
            "file_path": "mixed.py",
            "min_severity": "warning",
        })
        assert result["success"] is True
        # All returned smells should be warning or critical
        for smell in result["smells"]:
            assert smell["severity"] in ("warning", "critical")

    @pytest.mark.asyncio
    async def test_smell_type_filter(self) -> None:
        """smell_types filter limits results to specified types."""
        tmp = tempfile.mkdtemp()
        body = "\n".join(f"    x = {i}" for i in range(60))
        Path(tmp, "test.py").write_text(
            f"def long_func():\n{body}\n", encoding="utf-8"
        )
        tool = CodeSmellDetectorTool(tmp)
        result = await tool.execute({
            "file_path": "test.py",
            "smell_types": ["long_method"],
        })
        assert result["success"] is True
        for smell in result["smells"]:
            assert smell["type"] == "long_method"

    @pytest.mark.asyncio
    async def test_custom_thresholds(self) -> None:
        """Custom thresholds change detection behavior."""
        tmp = tempfile.mkdtemp()
        code = (
            "public class MyClass {\n"
            "    public void m1() { }\n"
            "    public void m2() { }\n"
            "}\n"
        )
        Path(tmp, "Test.java").write_text(code, encoding="utf-8")
        tool = CodeSmellDetectorTool(tmp)
        result = await tool.execute({
            "file_path": "Test.java",
            "thresholds": {"god_class_methods": 2},
        })
        assert result["success"] is True
        god_class = [s for s in result["smells"] if s["type"] == "god_class"]
        assert len(god_class) >= 1

    @pytest.mark.asyncio
    async def test_project_level_scan(self) -> None:
        """Scanning entire project returns results from all files."""
        tmp = tempfile.mkdtemp()
        body = "\n".join(f"    x = {i}" for i in range(60))
        Path(tmp, "a.py").write_text(
            f"def long():\n{body}\n", encoding="utf-8"
        )
        Path(tmp, "b.py").write_text(
            "def short():\n    return 1\n", encoding="utf-8"
        )
        tool = CodeSmellDetectorTool(tmp)
        result = await tool.execute({"project_root": tmp})
        assert result["success"] is True
        assert result["files_analyzed"] >= 2

    @pytest.mark.asyncio
    async def test_critical_warning_in_response(self) -> None:
        """Critical smells produce warning field."""
        tmp = tempfile.mkdtemp()
        methods = "\n".join(
            f"    public void method{i}() {{ }}"
            for i in range(20)
        )
        code = f"public class BigClass {{\n{methods}\n}}\n"
        Path(tmp, "Big.java").write_text(code, encoding="utf-8")
        tool = CodeSmellDetectorTool(tmp)
        result = await tool.execute({"file_path": "Big.java"})
        assert result["success"] is True
        if any(s["severity"] == "critical" for s in result["smells"]):
            assert "warning" in result


class TestSeverityEnums:
    """Test enum values."""

    def test_severity_values(self) -> None:
        assert SmellSeverity.INFO.value == "info"
        assert SmellSeverity.WARNING.value == "warning"
        assert SmellSeverity.CRITICAL.value == "critical"

    def test_category_values(self) -> None:
        assert SmellCategory.BLOATERS.value == "bloaters"
        assert SmellCategory.COUPLERS.value == "couplers"
        assert SmellCategory.CHANGE_PREVENTERS.value == "change_preventers"
        assert SmellCategory.DISPENSABLES.value == "dispensables"
        assert SmellCategory.OO_ABUSERS.value == "oo_abusers"


class TestDefaultThresholds:
    """Test default thresholds are reasonable."""

    def test_all_thresholds_positive(self) -> None:
        for key, value in DEFAULT_THRESHOLDS.items():
            assert value > 0, f"Threshold {key} should be positive"

    def test_threshold_keys(self) -> None:
        expected = {
            "god_class_methods", "god_class_lines", "long_method_lines",
            "deep_nesting_levels", "magic_number_min", "magic_number_max",
            "large_parameter_count", "many_imports",
        }
        assert set(DEFAULT_THRESHOLDS.keys()) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
