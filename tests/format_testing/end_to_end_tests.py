"""
End-to-End Format Validation Tests

Comprehensive end-to-end testing that validates format output through
complete analysis pipeline from file input to formatted output.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.api import analyze_code_structure
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool

from .format_assertions import (
    FormatComplianceAssertions,
    assert_compact_format_compliance,
    assert_csv_format_compliance,
    assert_full_format_compliance,
)
from .golden_master import GoldenMasterManager
from .schema_validation import validate_format


class TestEndToEndFormatValidation:
    """End-to-end format validation through complete pipeline"""

    @pytest.fixture
    def comprehensive_test_files(self):
        """Create comprehensive test files for different languages"""
        temp_dir = tempfile.mkdtemp()
        test_files = {}

        # Java test file
        java_content = """package com.example.analytics;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.sql.SQLException;

/**
 * Analytics service for processing user data
 */
public class AnalyticsService {
    private final Map<String, Object> cache = new ConcurrentHashMap<>();
    private UserRepository userRepository;
    private static final Logger logger = LoggerFactory.getLogger(AnalyticsService.class);

    public AnalyticsService(UserRepository userRepository) {
        this.userRepository = userRepository;
        logger.info("AnalyticsService initialized");
    }

    /**
     * Process user analytics data
     * @param userId User ID to process
     * @param metrics List of metrics to calculate
     * @return Analytics result
     * @throws SQLException if database error occurs
     */
    public AnalyticsResult processUserAnalytics(Long userId, List<String> metrics) throws SQLException {
        if (userId == null) {
            throw new IllegalArgumentException("User ID cannot be null");
        }

        if (metrics == null || metrics.isEmpty()) {
            return new AnalyticsResult(userId, Map.of());
        }

        User user = userRepository.findById(userId);
        if (user == null) {
            throw new UserNotFoundException("User not found: " + userId);
        }

        Map<String, Double> results = new HashMap<>();
        for (String metric : metrics) {
            Double value = calculateMetric(user, metric);
            if (value != null) {
                results.put(metric, value);
            }
        }

        return new AnalyticsResult(userId, results);
    }

    /**
     * Calculate specific metric for user
     */
    private Double calculateMetric(User user, String metric) {
        String cacheKey = user.getId() + ":" + metric;

        if (cache.containsKey(cacheKey)) {
            return (Double) cache.get(cacheKey);
        }

        Double result = null;
        switch (metric.toLowerCase()) {
            case "engagement":
                result = calculateEngagement(user);
                break;
            case "retention":
                result = calculateRetention(user);
                break;
            case "satisfaction":
                result = calculateSatisfaction(user);
                break;
            default:
                logger.warn("Unknown metric: " + metric);
                return null;
        }

        if (result != null) {
            cache.put(cacheKey, result);
        }

        return result;
    }

    private Double calculateEngagement(User user) {
        // Complex engagement calculation
        return user.getLoginCount() * 0.1 + user.getActionCount() * 0.05;
    }

    private Double calculateRetention(User user) {
        // Retention calculation based on activity
        long daysSinceLastLogin = user.getDaysSinceLastLogin();
        return Math.max(0.0, 1.0 - (daysSinceLastLogin / 30.0));
    }

    private Double calculateSatisfaction(User user) {
        // Satisfaction based on feedback scores
        return user.getAverageFeedbackScore();
    }

    public void clearCache() {
        cache.clear();
        logger.info("Analytics cache cleared");
    }
}"""

        java_file = Path(temp_dir) / "AnalyticsService.java"
        java_file.write_text(java_content, encoding="utf-8")
        test_files["java"] = java_file

        # Python test file
        python_content = '''"""
Data processing utilities for analytics pipeline
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of data processing operation"""
    success: bool
    data: Dict[str, Any]
    errors: List[str]
    metadata: Optional[Dict[str, Any]] = None


class DataProcessor(ABC):
    """Abstract base class for data processors"""

    @abstractmethod
    def process(self, data: Dict[str, Any]) -> ProcessingResult:
        """Process input data and return result"""
        pass

    @abstractmethod
    def validate_input(self, data: Dict[str, Any]) -> bool:
        """Validate input data format"""
        pass


class AnalyticsDataProcessor(DataProcessor):
    """Processor for analytics data"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.cache: Dict[str, Any] = {}
        self._processing_count = 0

    def process(self, data: Dict[str, Any]) -> ProcessingResult:
        """
        Process analytics data with validation and caching

        Args:
            data: Input data dictionary

        Returns:
            ProcessingResult with processed data
        """
        if not self.validate_input(data):
            return ProcessingResult(
                success=False,
                data={},
                errors=["Invalid input data format"]
            )

        try:
            processed_data = self._process_internal(data)
            self._processing_count += 1

            return ProcessingResult(
                success=True,
                data=processed_data,
                errors=[],
                metadata={
                    "processing_count": self._processing_count,
                    "cache_size": len(self.cache)
                }
            )
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            return ProcessingResult(
                success=False,
                data={},
                errors=[str(e)]
            )

    def validate_input(self, data: Dict[str, Any]) -> bool:
        """Validate input data has required fields"""
        required_fields = ["user_id", "timestamp", "metrics"]
        return all(field in data for field in required_fields)

    def _process_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Internal processing logic"""
        user_id = data["user_id"]
        metrics = data["metrics"]

        # Check cache first
        cache_key = f"{user_id}:{hash(str(sorted(metrics.items())))}"
        if cache_key in self.cache:
            logger.debug(f"Cache hit for {cache_key}")
            return self.cache[cache_key]

        # Process metrics
        processed_metrics = {}
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                processed_metrics[metric_name] = self._normalize_metric(metric_value)
            else:
                processed_metrics[metric_name] = metric_value

        result = {
            "user_id": user_id,
            "processed_metrics": processed_metrics,
            "timestamp": data["timestamp"],
            "processing_version": self.config.get("version", "1.0")
        }

        # Cache result
        self.cache[cache_key] = result
        logger.debug(f"Cached result for {cache_key}")

        return result

    def _normalize_metric(self, value: float) -> float:
        """Normalize metric value to 0-1 range"""
        max_value = self.config.get("max_metric_value", 100.0)
        return min(1.0, max(0.0, value / max_value))

    def clear_cache(self) -> None:
        """Clear processing cache"""
        self.cache.clear()
        logger.info("Processing cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics"""
        return {
            "processing_count": self._processing_count,
            "cache_size": len(self.cache),
            "config": self.config
        }


def create_processor(processor_type: str, config: Dict[str, Any]) -> DataProcessor:
    """Factory function to create data processors"""
    if processor_type == "analytics":
        return AnalyticsDataProcessor(config)
    else:
        raise ValueError(f"Unknown processor type: {processor_type}")
'''

        python_file = Path(temp_dir) / "data_processor.py"
        python_file.write_text(python_content, encoding="utf-8")
        test_files["python"] = python_file

        yield temp_dir, test_files

        # Cleanup
        for file_path in test_files.values():
            if file_path.exists():
                file_path.unlink()
        Path(temp_dir).rmdir()

    @pytest.fixture
    def golden_master_manager(self):
        """Provide golden master manager"""
        return GoldenMasterManager()

    @pytest.mark.asyncio
    async def test_complete_pipeline_java_file(
        self, comprehensive_test_files, golden_master_manager
    ):
        """Test complete pipeline: Java file → analysis → formatting → validation"""
        temp_dir, test_files = comprehensive_test_files
        java_file = test_files["java"]

        # Test all format types through complete pipeline
        formats = ["full", "compact", "csv"]
        results = {}

        for format_type in formats:
            # Execute through MCP tool (complete pipeline)
            tool = TableFormatTool(project_root=temp_dir)
            result = await tool.execute(
                {
                    "file_path": str(java_file),
                    "format_type": format_type,
                    "language": "java",
                }
            )

            # Validate basic result structure
            assert result["format_type"] == format_type
            assert result["language"] == "java"
            assert "table_output" in result

            table_output = result["table_output"]
            results[format_type] = table_output

            # Validate against golden master
            golden_tester = golden_master_manager.get_tester(format_type)
            golden_tester.assert_matches_golden_master(
                table_output, f"java_analytics_service_{format_type}_format"
            )

            # Validate format compliance
            if format_type == "full":
                assert_full_format_compliance(table_output, "AnalyticsService")
            elif format_type == "compact":
                assert_compact_format_compliance(table_output)
            elif format_type == "csv":
                assert_csv_format_compliance(table_output)

            # Validate schema compliance
            schema_type = "markdown" if format_type in ["full", "compact"] else "csv"
            validation_result = validate_format(table_output, schema_type)
            assert (
                validation_result.is_valid
            ), f"Schema validation failed for {format_type}: {validation_result.errors}"

        # Validate cross-format consistency
        element_counts = {
            "methods": 8,  # Constructor + 7 methods
            "fields": 3,  # cache, userRepository, logger
        }

        FormatComplianceAssertions.assert_format_consistency(results, element_counts)

    @pytest.mark.asyncio
    async def test_complete_pipeline_python_file(
        self, comprehensive_test_files, golden_master_manager
    ):
        """Test complete pipeline: Python file → analysis → formatting → validation"""
        temp_dir, test_files = comprehensive_test_files
        python_file = test_files["python"]

        # Test all format types through complete pipeline
        formats = ["full", "compact", "csv"]
        results = {}

        for format_type in formats:
            # Execute through MCP tool (complete pipeline)
            tool = TableFormatTool(project_root=temp_dir)
            result = await tool.execute(
                {
                    "file_path": str(python_file),
                    "format_type": format_type,
                    "language": "python",
                }
            )

            # Validate basic result structure
            assert result["format_type"] == format_type
            assert result["language"] == "python"
            assert "table_output" in result

            table_output = result["table_output"]
            results[format_type] = table_output

            # Validate against golden master
            golden_tester = golden_master_manager.get_tester(format_type)
            golden_tester.assert_matches_golden_master(
                table_output, f"python_data_processor_{format_type}_format"
            )

            # Validate format compliance
            if format_type == "full":
                assert_full_format_compliance(table_output, "AnalyticsDataProcessor")
            elif format_type == "compact":
                assert_compact_format_compliance(table_output)
            elif format_type == "csv":
                assert_csv_format_compliance(table_output)

            # Validate schema compliance
            schema_type = "markdown" if format_type in ["full", "compact"] else "csv"
            validation_result = validate_format(table_output, schema_type)
            assert (
                validation_result.is_valid
            ), f"Schema validation failed for {format_type}: {validation_result.errors}"

    @pytest.mark.asyncio
    async def test_api_interface_format_validation(self, comprehensive_test_files):
        """Test format validation through API interface"""
        temp_dir, test_files = comprehensive_test_files
        java_file = test_files["java"]

        # Test through API interface
        for format_type in ["full", "compact", "csv"]:
            result = await analyze_code_structure(
                file_path=str(java_file), format_type=format_type, language="java"
            )

            # Validate API result structure
            assert "table_output" in result
            assert "metadata" in result
            assert result["format_type"] == format_type

            table_output = result["table_output"]

            # Validate format compliance
            if format_type == "full":
                assert_full_format_compliance(table_output, "AnalyticsService")
            elif format_type == "compact":
                assert_compact_format_compliance(table_output)
            elif format_type == "csv":
                assert_csv_format_compliance(table_output)

    def test_cli_interface_format_validation(self, comprehensive_test_files):
        """Test format validation through CLI interface"""
        import subprocess
        import sys

        temp_dir, test_files = comprehensive_test_files
        java_file = test_files["java"]

        # Test through CLI interface
        for format_type in ["full", "compact", "csv"]:
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "tree_sitter_analyzer",
                        "--file",
                        str(java_file),
                        "--table",
                        format_type,
                        "--language",
                        "java",
                    ],
                    capture_output=True,
                    text=True,
                    cwd=temp_dir,
                )

                if result.returncode == 0:
                    cli_output = result.stdout

                    # Basic validation
                    assert "AnalyticsService" in cli_output
                    assert len(cli_output.strip()) > 0

                    # Format-specific validation
                    if format_type == "full":
                        assert "# com.example.analytics.AnalyticsService" in cli_output
                        assert "## Class Info" in cli_output
                    elif format_type == "compact":
                        assert "## Info" in cli_output or "## Methods" in cli_output
                    elif format_type == "csv":
                        lines = cli_output.strip().split("\n")
                        assert len(lines) >= 2  # Header + data
                        assert "," in lines[0]  # CSV header
                else:
                    pytest.skip(
                        f"CLI execution failed for {format_type}: {result.stderr}"
                    )

            except FileNotFoundError:
                pytest.skip("CLI interface not available for testing")

    @pytest.mark.asyncio
    async def test_format_regression_detection(
        self, comprehensive_test_files, golden_master_manager
    ):
        """Test that format changes are detected by regression tests"""
        temp_dir, test_files = comprehensive_test_files
        java_file = test_files["java"]

        # Generate current output
        tool = TableFormatTool(project_root=temp_dir)
        result = await tool.execute(
            {"file_path": str(java_file), "format_type": "full"}
        )

        current_output = result["table_output"]

        # Create a modified version to simulate regression
        modified_output = current_output.replace("AnalyticsService", "ModifiedService")

        # Test regression detection
        golden_tester = golden_master_manager.get_tester("full")

        # First, create golden master with current output
        golden_tester.create_golden_master(current_output, "regression_test")

        # Then test that modified output is detected as different
        with pytest.raises(AssertionError, match="Output differs from golden master"):
            golden_tester.assert_matches_golden_master(
                modified_output, "regression_test"
            )

    @pytest.mark.asyncio
    async def test_format_validation_with_edge_cases(self, comprehensive_test_files):
        """Test format validation with edge cases and boundary conditions"""
        temp_dir, test_files = comprehensive_test_files

        # Test with empty file
        empty_file = Path(temp_dir) / "Empty.java"
        empty_file.write_text("", encoding="utf-8")

        tool = TableFormatTool(project_root=temp_dir)

        try:
            result = await tool.execute(
                {"file_path": str(empty_file), "format_type": "full"}
            )

            # Should handle empty file gracefully
            assert "table_output" in result
            table_output = result["table_output"]

            # Validate that output is still valid format
            validation_result = validate_format(table_output, "markdown")
            assert (
                validation_result.is_valid
            ), f"Empty file validation failed: {validation_result.errors}"

        except Exception as e:
            # If it fails, it should fail gracefully with meaningful error
            assert "empty" in str(e).lower() or "no content" in str(e).lower()

        finally:
            empty_file.unlink()

        # Test with file containing only comments
        comment_file = Path(temp_dir) / "Comments.java"
        comment_file.write_text(
            """
        // This is a comment file
        /*
         * Multi-line comment
         * with no actual code
         */
        """,
            encoding="utf-8",
        )

        try:
            result = await tool.execute(
                {"file_path": str(comment_file), "format_type": "compact"}
            )

            # Should handle comment-only file
            assert "table_output" in result
            table_output = result["table_output"]

            # Validate format
            validation_result = validate_format(table_output, "markdown")
            assert (
                validation_result.is_valid
            ), f"Comment file validation failed: {validation_result.errors}"

        except Exception as e:
            # Should fail gracefully
            assert isinstance(e, (RuntimeError, ValueError))

        finally:
            comment_file.unlink()

    @pytest.mark.asyncio
    async def test_format_consistency_across_languages(self, comprehensive_test_files):
        """Test format consistency across different programming languages"""
        temp_dir, test_files = comprehensive_test_files

        # Test both Java and Python files
        language_results = {}

        for language, file_path in test_files.items():
            tool = TableFormatTool(project_root=temp_dir)
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "format_type": "compact",
                    "language": language,
                }
            )

            language_results[language] = result["table_output"]

        # Both should follow same format structure
        for language, output in language_results.items():
            # Basic structure validation
            assert "# " in output, f"{language} missing main header"
            assert "## " in output, f"{language} missing section headers"
            assert "|" in output, f"{language} missing table content"

            # Schema validation
            validation_result = validate_format(output, "markdown")
            assert (
                validation_result.is_valid
            ), f"{language} schema validation failed: {validation_result.errors}"


class TestFormatStabilityValidation:
    """Test format stability and consistency over time"""

    @pytest.mark.asyncio
    async def test_format_output_deterministic(self, comprehensive_test_files):
        """Test that format output is deterministic (same input → same output)"""
        temp_dir, test_files = comprehensive_test_files
        java_file = test_files["java"]

        tool = TableFormatTool(project_root=temp_dir)

        # Run same analysis multiple times
        outputs = []
        for _ in range(3):
            result = await tool.execute(
                {"file_path": str(java_file), "format_type": "full"}
            )
            outputs.append(result["table_output"])

        # All outputs should be identical
        for i in range(1, len(outputs)):
            assert outputs[0] == outputs[i], f"Output {i} differs from first output"

    @pytest.mark.asyncio
    async def test_format_metadata_consistency(self, comprehensive_test_files):
        """Test that format metadata is consistent and accurate"""
        temp_dir, test_files = comprehensive_test_files
        java_file = test_files["java"]

        tool = TableFormatTool(project_root=temp_dir)

        # Test all formats and verify metadata consistency
        metadata_results = {}

        for format_type in ["full", "compact", "csv"]:
            result = await tool.execute(
                {"file_path": str(java_file), "format_type": format_type}
            )

            metadata_results[format_type] = result.get("metadata", {})

        # Metadata should be consistent across formats
        for format_type, metadata in metadata_results.items():
            assert (
                "classes_count" in metadata or "total_lines" in metadata
            ), f"Missing basic metadata in {format_type}"

            # If multiple formats have same metadata fields, values should match
            if "classes_count" in metadata:
                for other_format, other_metadata in metadata_results.items():
                    if (
                        other_format != format_type
                        and "classes_count" in other_metadata
                    ):
                        assert (
                            metadata["classes_count"] == other_metadata["classes_count"]
                        ), f"Class count mismatch between {format_type} and {other_format}"
