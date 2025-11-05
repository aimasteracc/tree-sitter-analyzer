"""
Golden Master Testing Framework

Provides utilities for golden master testing to prevent format regressions.
Golden masters are reference outputs that serve as the source of truth for
format validation.
"""

import difflib
import hashlib
from pathlib import Path

import pytest


class GoldenMasterTester:
    """Golden master testing framework for format validation"""

    def __init__(self, format_type: str, test_data_dir: Path | None = None):
        """
        Initialize golden master tester

        Args:
            format_type: Format type (full, compact, csv)
            test_data_dir: Base directory for test data (defaults to tests/golden_masters)
        """
        self.format_type = format_type
        if test_data_dir is None:
            test_data_dir = Path(__file__).parent.parent / "golden_masters"
        self.reference_dir = test_data_dir / format_type
        self.reference_dir.mkdir(parents=True, exist_ok=True)

    def assert_matches_golden_master(
        self, actual_output: str, test_name: str, update_golden: bool = False
    ) -> None:
        """
        Compare actual output against golden master reference

        Args:
            actual_output: The actual output to validate
            test_name: Name of the test case
            update_golden: If True, update the golden master with actual output

        Raises:
            AssertionError: If output doesn't match golden master
        """
        golden_file = self.reference_dir / f"{test_name}.{self._get_file_extension()}"

        if update_golden or not golden_file.exists():
            # Create or update golden master
            golden_file.write_text(actual_output, encoding="utf-8")
            if not golden_file.exists():
                pytest.skip(f"Created golden master: {golden_file}")
            return

        expected = golden_file.read_text(encoding="utf-8")
        if actual_output != expected:
            # Generate detailed diff and fail
            diff = self._generate_diff(expected, actual_output, test_name)
            pytest.fail(f"Output differs from golden master:\n{diff}")

    def get_golden_master_content(self, test_name: str) -> str | None:
        """
        Get the content of a golden master file

        Args:
            test_name: Name of the test case

        Returns:
            Content of golden master file, or None if not found
        """
        golden_file = self.reference_dir / f"{test_name}.{self._get_file_extension()}"
        if golden_file.exists():
            return golden_file.read_text(encoding="utf-8")
        return None

    def create_golden_master(self, content: str, test_name: str) -> Path:
        """
        Create a new golden master file

        Args:
            content: Content to write to golden master
            test_name: Name of the test case

        Returns:
            Path to created golden master file
        """
        golden_file = self.reference_dir / f"{test_name}.{self._get_file_extension()}"
        golden_file.write_text(content, encoding="utf-8")
        return golden_file

    def get_content_hash(self, content: str) -> str:
        """
        Generate hash of content for change detection

        Args:
            content: Content to hash

        Returns:
            SHA256 hash of content
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _get_file_extension(self) -> str:
        """Get appropriate file extension for format type"""
        extension_map = {"full": "md", "compact": "md", "csv": "csv", "json": "json"}
        return extension_map.get(self.format_type, "txt")

    def _generate_diff(self, expected: str, actual: str, test_name: str) -> str:
        """
        Generate detailed diff between expected and actual output

        Args:
            expected: Expected output
            actual: Actual output
            test_name: Name of test case

        Returns:
            Formatted diff string
        """
        expected_lines = expected.splitlines(keepends=True)
        actual_lines = actual.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                expected_lines,
                actual_lines,
                fromfile=f"golden_master/{test_name}.{self._get_file_extension()}",
                tofile=f"actual_output/{test_name}.{self._get_file_extension()}",
                lineterm="",
            )
        )

        if not diff_lines:
            return "No differences found (this shouldn't happen)"

        # Add summary information
        summary = [
            f"Golden Master Comparison Failed for: {test_name}",
            f"Format Type: {self.format_type}",
            f"Expected Length: {len(expected)} chars",
            f"Actual Length: {len(actual)} chars",
            f"Expected Hash: {self.get_content_hash(expected)}",
            f"Actual Hash: {self.get_content_hash(actual)}",
            "",
            "Detailed Diff:",
            "",
        ]

        return "\n".join(summary + diff_lines)


class GoldenMasterManager:
    """Manager for multiple golden master testers"""

    def __init__(self, test_data_dir: Path | None = None):
        """
        Initialize golden master manager

        Args:
            test_data_dir: Base directory for test data
        """
        self.test_data_dir = (
            test_data_dir or Path(__file__).parent.parent / "golden_masters"
        )
        self._testers: dict[str, GoldenMasterTester] = {}

    def get_tester(self, format_type: str) -> GoldenMasterTester:
        """
        Get or create a golden master tester for format type

        Args:
            format_type: Format type (full, compact, csv)

        Returns:
            GoldenMasterTester instance
        """
        if format_type not in self._testers:
            self._testers[format_type] = GoldenMasterTester(
                format_type, self.test_data_dir
            )
        return self._testers[format_type]

    def validate_all_formats(
        self, outputs: dict[str, str], test_name: str, update_golden: bool = False
    ) -> None:
        """
        Validate outputs for all formats against golden masters

        Args:
            outputs: Dictionary mapping format_type to output content
            test_name: Name of the test case
            update_golden: If True, update golden masters
        """
        for format_type, output in outputs.items():
            tester = self.get_tester(format_type)
            tester.assert_matches_golden_master(output, test_name, update_golden)

    def create_test_suite_golden_masters(
        self, test_cases: dict[str, dict[str, str]], overwrite: bool = False
    ) -> dict[str, dict[str, Path]]:
        """
        Create golden masters for a complete test suite

        Args:
            test_cases: Nested dict {test_name: {format_type: content}}
            overwrite: If True, overwrite existing golden masters

        Returns:
            Dictionary mapping test_name -> format_type -> golden_master_path
        """
        created_files = {}

        for test_name, format_outputs in test_cases.items():
            created_files[test_name] = {}
            for format_type, content in format_outputs.items():
                tester = self.get_tester(format_type)
                golden_file = (
                    tester.reference_dir / f"{test_name}.{tester._get_file_extension()}"
                )

                if overwrite or not golden_file.exists():
                    created_path = tester.create_golden_master(content, test_name)
                    created_files[test_name][format_type] = created_path
                else:
                    created_files[test_name][format_type] = golden_file

        return created_files


# Pytest fixtures for golden master testing
@pytest.fixture
def golden_master_manager():
    """Fixture providing GoldenMasterManager instance"""
    return GoldenMasterManager()


@pytest.fixture
def full_format_golden_tester():
    """Fixture providing golden master tester for full format"""
    return GoldenMasterTester("full")


@pytest.fixture
def compact_format_golden_tester():
    """Fixture providing golden master tester for compact format"""
    return GoldenMasterTester("compact")


@pytest.fixture
def csv_format_golden_tester():
    """Fixture providing golden master tester for CSV format"""
    return GoldenMasterTester("csv")
