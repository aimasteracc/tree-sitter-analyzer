#!/usr/bin/env python3
"""
Improved README Statistics Auto-Update Script

Enhanced version with better error handling, configuration management,
and more robust statistics collection.
"""

import logging
import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from readme_config import ReadmeConfig


class ImprovedReadmeUpdater:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.project_root = Path(__file__).parent.parent
        self.config = ReadmeConfig()
        self.dry_run = dry_run
        self.verbose = verbose

        # Setup logging
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
        self.logger = logging.getLogger(__name__)

    def get_current_stats(self) -> dict[str, Any]:
        """Get current project statistics with better error handling"""
        stats = {}

        # 1. Get test count and coverage
        stats.update(self._get_test_stats())

        # 2. Get version information
        stats.update(self._get_version_info())

        # 3. Get BigService.java statistics
        stats.update(self._get_bigservice_stats())

        return stats

    def _get_test_stats(self) -> dict[str, Any]:
        """Get test count and coverage statistics"""
        stats = {}

        try:
            # Get test count
            result = subprocess.run(  # nosec B603
                self.config.stat_commands["test_count"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=60,
                check=False,
            )

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "collected" in line:
                        match = re.search(r"(\d+) tests? collected", line)
                        if match:
                            stats["test_count"] = int(match.group(1))
                            break

            # Get coverage
            result = subprocess.run(  # nosec B603
                self.config.stat_commands["coverage"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=180,  # Increased timeout from 120 to 180 seconds
                check=False,
            )

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "TOTAL" in line and "%" in line:
                        match = re.search(r"(\d+\.?\d*)%", line)
                        if match:
                            # Round coverage to 1 decimal place to avoid CI failures
                            raw_coverage = float(match.group(1))
                            stats["coverage"] = round(raw_coverage, 1)
                            break

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            self.logger.warning(f"Could not get test stats: {e}")
            # Use fallback values
            stats.update({"test_count": 1504, "coverage": 74.44})

        return stats

    def _get_version_info(self) -> dict[str, Any]:
        """Get version information from pyproject.toml"""
        stats = {}
        pyproject_path = self.project_root / "pyproject.toml"

        try:
            with open(pyproject_path, encoding="utf-8") as f:
                content = f.read()
                match = re.search(r'version = "([^"]+)"', content)
                if match:
                    stats["version"] = match.group(1)
        except Exception as e:
            self.logger.warning(f"Could not get version: {e}")
            stats["version"] = "0.9.4"  # Fallback

        return stats

    def _get_bigservice_stats(self) -> dict[str, Any]:
        """Get BigService.java analysis statistics"""
        stats = {}

        try:
            result = subprocess.run(  # nosec B603
                self.config.stat_commands["bigservice_analysis"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30,
                check=False,
            )

            if result.returncode == 0:
                # Parse the output for various statistics
                patterns = {
                    "bigservice_lines": r"Lines: (\d+)",
                    "bigservice_methods": r"Methods: (\d+)",
                    "bigservice_fields": r"Fields: (\d+)",
                    "bigservice_classes": r"Classes: (\d+)",
                    "bigservice_imports": r"Imports: (\d+)",
                }

                for stat_name, pattern in patterns.items():
                    match = re.search(pattern, result.stdout)
                    if match:
                        stats[stat_name] = int(match.group(1))

        except Exception as e:
            self.logger.warning(f"Could not analyze BigService.java: {e}")
            # Use fallback values
            stats.update(
                {
                    "bigservice_lines": 1419,
                    "bigservice_methods": 66,
                    "bigservice_fields": 9,
                    "bigservice_classes": 1,
                    "bigservice_imports": 8,
                }
            )

        return stats

    def _should_update_statistic(
        self, stat_name: str, current_value: Any, new_value: Any
    ) -> bool:
        """
        Check if a statistic should be updated based on tolerance range

        Args:
            stat_name: Name of the statistic
            current_value: Current value in the document
            new_value: New actual value

        Returns:
            True if update is needed, False if within tolerance
        """
        if stat_name not in self.config.tolerance_ranges:
            return current_value != new_value

        tolerance = self.config.tolerance_ranges[stat_name]

        # Handle different data types
        if isinstance(current_value, int | float) and isinstance(
            new_value, int | float
        ):
            return abs(current_value - new_value) > tolerance
        else:
            return current_value != new_value

    def _update_statistic_patterns(
        self, content: str, stats: dict[str, Any]
    ) -> tuple[str, bool]:
        """
        Update statistic patterns in content with tolerance checking

        Args:
            content: File content to update
            stats: Current statistics

        Returns:
            Tuple of (updated_content, changes_made)
        """
        changes_made = False

        for stat_config in self.config.statistics:
            stat_name = stat_config.name
            if stat_name not in stats:
                continue

            new_value = stats[stat_name]

            for pattern in stat_config.patterns:
                # Extract current value from content
                match = re.search(pattern, content)
                if match:
                    current_value = self._extract_value_from_match(match, pattern)

                    # Check if update is needed based on tolerance
                    if self._should_update_statistic(
                        stat_name, current_value, new_value
                    ):
                        # Format the new value
                        if stat_name == "coverage":
                            formatted_value = f"{new_value:.2f}"
                        else:
                            formatted_value = str(new_value)

                        # Update the content
                        if stat_name == "coverage":
                            # Handle coverage patterns with different formats
                            for coverage_pattern in stat_config.patterns:
                                if "%25" in coverage_pattern:  # Badge format
                                    new_content = re.sub(
                                        coverage_pattern,
                                        f"coverage-{formatted_value}%25",
                                        content,
                                    )
                                else:  # Text format
                                    new_content = re.sub(
                                        coverage_pattern,
                                        f"coverage: {formatted_value}%",
                                        content,
                                    )
                                if new_content != content:
                                    content = new_content
                                    changes_made = True
                        else:
                            # Handle other statistics
                            new_content = re.sub(pattern, str(new_value), content)
                            if new_content != content:
                                content = new_content
                                changes_made = True

                        self.logger.debug(
                            f"Updated {stat_name}: {current_value} -> {new_value} "
                            f"(tolerance: {self.config.tolerance_ranges.get(stat_name, 'none')})"
                        )
                    else:
                        self.logger.debug(
                            f"Skipped {stat_name} update: {current_value} vs {new_value} "
                            f"(within tolerance: {self.config.tolerance_ranges.get(stat_name, 'none')})"
                        )

        return content, changes_made

    def _extract_value_from_match(self, match: re.Match, pattern: str) -> Any:
        """Extract numeric value from regex match"""
        try:
            if "coverage" in pattern:
                # Extract coverage percentage
                if "%25" in pattern:  # Badge format
                    return float(match.group(1)) if match.groups() else 0.0
                else:  # Text format
                    return float(match.group(1)) if match.groups() else 0.0
            else:
                # Extract integer values
                return int(match.group(1)) if match.groups() else 0
        except (ValueError, IndexError):
            return 0

    def update_readme_file(self, file_path: Path, stats: dict[str, Any]) -> bool:
        """Update a specific README file with improved pattern matching and tolerance checking"""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            changes_made = False

            # Update statistic patterns with tolerance checking
            content, stat_changes = self._update_statistic_patterns(content, stats)
            changes_made = changes_made or stat_changes

            # Update JSON examples
            json_patterns = {
                '"lines_total": \\d+': f'"lines_total": {stats.get("bigservice_lines", 1419)}',
                '"lines_code": \\d+': f'"lines_code": {stats.get("bigservice_lines", 1419)}',
                '"methods": \\d+': f'"methods": {stats.get("bigservice_methods", 66)}',
                '"fields": \\d+': f'"fields": {stats.get("bigservice_fields", 9)}',
            }

            for pattern, replacement in json_patterns.items():
                new_content = re.sub(pattern, replacement, content)
                if new_content != content:
                    content = new_content
                    changes_made = True

            # Update table data
            table_pattern = (
                r"\|?\|? BigService \| class \| public \| 17-\d+ \| \d+ \| \d+ \|"
            )
            table_replacement = f"| BigService | class | public | 17-{stats.get('bigservice_lines', 1419)} | {stats.get('bigservice_methods', 66)} | {stats.get('bigservice_fields', 9)} |"

            new_content = re.sub(table_pattern, table_replacement, content)
            if new_content != content:
                content = new_content
                changes_made = True

            # Write back if changes were made and not in dry-run mode
            if changes_made and not self.dry_run:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.logger.info(f"Updated {file_path.name}")
            elif changes_made and self.dry_run:
                self.logger.info(f"Would update {file_path.name} (dry-run mode)")
            else:
                self.logger.info(f"No changes needed for {file_path.name}")

            return changes_made

        except Exception as e:
            self.logger.error(f"Error updating {file_path.name}: {e}")
            return False

    def validate_readme_content(
        self, file_path: Path, stats: dict[str, Any] = None
    ) -> list[str]:
        """Validate that README contains required patterns and correct statistics"""
        issues = []

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # First check basic pattern existence
            for name, pattern in self.config.validation_patterns.items():
                if not re.search(pattern, content):
                    issues.append(f"Missing {name} pattern in {file_path.name}")

            # If stats provided, validate actual values match
            if stats:
                issues.extend(
                    self._validate_statistics_accuracy(content, stats, file_path.name)
                )

        except Exception as e:
            issues.append(f"Could not validate {file_path.name}: {e}")

        return issues

    def _validate_statistics_accuracy(
        self, content: str, stats: dict[str, Any], filename: str
    ) -> list[str]:
        """Validate that statistics in content match actual project stats"""
        issues = []

        # Check test count in badge
        test_badge_match = re.search(r"tests-(\d+)%20passed", content)
        if test_badge_match:
            file_test_count = int(test_badge_match.group(1))
            actual_test_count = stats.get("test_count")
            if actual_test_count and file_test_count != actual_test_count:
                issues.append(
                    f"Test count mismatch in {filename}: file shows {file_test_count}, actual is {actual_test_count}"
                )

        # Check coverage in badge
        coverage_badge_match = re.search(r"coverage-(\d+\.?\d*)%25", content)
        if coverage_badge_match:
            file_coverage = float(coverage_badge_match.group(1))
            actual_coverage = stats.get("coverage")
            if actual_coverage:
                # Use the same tolerance as the update logic
                tolerance = self.config.tolerance_ranges.get("coverage", 0.1)
                if abs(file_coverage - actual_coverage) > tolerance:
                    issues.append(
                        f"Coverage mismatch in {filename}: file shows {file_coverage:.2f}%, actual is {actual_coverage:.2f}% (tolerance: {tolerance})"
                    )

        # Check BigService statistics
        bigservice_patterns = {
            "lines": (r"Lines: (\d+)", "bigservice_lines"),
            "methods": (r"Methods: (\d+)", "bigservice_methods"),
            "fields": (r"Fields: (\d+)", "bigservice_fields"),
            "classes": (r"Classes: (\d+)", "bigservice_classes"),
            "imports": (r"Imports: (\d+)", "bigservice_imports"),
        }

        for stat_name, (pattern, stat_key) in bigservice_patterns.items():
            match = re.search(pattern, content)
            if match:
                file_value = int(match.group(1))
                actual_value = stats.get(stat_key)
                if actual_value and file_value != actual_value:
                    issues.append(
                        f"BigService {stat_name} mismatch in {filename}: file shows {file_value}, actual is {actual_value}"
                    )

        # Check JSON examples consistency
        json_patterns = {
            "lines_total": r'"lines_total": (\d+)',
            "lines_code": r'"lines_code": (\d+)',
            "methods": r'"methods": (\d+)',
            "fields": r'"fields": (\d+)',
        }

        for json_field, pattern in json_patterns.items():
            matches = re.findall(pattern, content)
            if matches:
                # All instances should be the same
                unique_values = {int(m) for m in matches}
                if len(unique_values) > 1:
                    issues.append(
                        f"Inconsistent {json_field} values in JSON examples in {filename}: {unique_values}"
                    )

                # Check against actual stats
                file_value = int(matches[0])
                if json_field in ["lines_total", "lines_code"]:
                    actual_value = stats.get("bigservice_lines")
                elif json_field == "methods":
                    actual_value = stats.get("bigservice_methods")
                elif json_field == "fields":
                    actual_value = stats.get("bigservice_fields")
                else:
                    actual_value = None

                if actual_value and file_value != actual_value:
                    issues.append(
                        f"JSON {json_field} mismatch in {filename}: file shows {file_value}, actual is {actual_value}"
                    )

        return issues

    def update_all_readmes(self) -> bool:
        """Update all README files and return success status"""
        self.logger.info("Collecting current project statistics...")
        stats = self.get_current_stats()

        self.logger.info("Current stats:")
        for key, value in stats.items():
            if isinstance(value, float):
                self.logger.info(f"  - {key}: {value:.2f}")
            else:
                self.logger.info(f"  - {key}: {value}")

        if self.dry_run:
            self.logger.info("Running in dry-run mode - no files will be modified")

        self.logger.info("\nUpdating README files...")

        success = True
        files_updated = 0

        # Update each README file
        for _lang_code, filename in self.config.readme_files.items():
            file_path = self.project_root / filename

            if file_path.exists():
                if self.update_readme_file(file_path, stats):
                    files_updated += 1

                # Validate content with actual statistics
                issues = self.validate_readme_content(file_path, stats)
                if issues:
                    self.logger.warning(f"Validation issues in {filename}:")
                    for issue in issues:
                        self.logger.warning(f"  - {issue}")
                    success = False
            else:
                self.logger.warning(f"{filename} not found at {file_path}")
                success = False

        if success:
            self.logger.info(
                f"\nREADME update completed! ({files_updated} files updated)"
            )
        else:
            self.logger.error("\nREADME update completed with issues!")

        self.logger.info(
            "\nTip: Run this script after each development cycle to keep stats current."
        )

        return success


def main():
    """Main function with CLI argument support"""
    import argparse

    parser = argparse.ArgumentParser(description="Update README statistics")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate README content without updating",
    )

    args = parser.parse_args()

    updater = ImprovedReadmeUpdater(dry_run=args.dry_run, verbose=args.verbose)

    if args.validate_only:
        # Only run validation - but we need stats to validate accuracy
        print("Collecting current project statistics for validation...")
        stats = updater.get_current_stats()

        print("Current stats:")
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  - {key}: {value:.2f}")
            else:
                print(f"  - {key}: {value}")

        print("\nValidating README content and statistics...")
        all_issues = []
        for filename in updater.config.readme_files.values():
            file_path = updater.project_root / filename
            if file_path.exists():
                issues = updater.validate_readme_content(file_path, stats)
                all_issues.extend(issues)
            else:
                all_issues.append(f"File not found: {filename}")

        if all_issues:
            print("Validation issues found:")
            for issue in all_issues:
                print(f"  - {issue}")
            return 1
        else:
            print("All README files passed validation!")
            return 0
    else:
        # Run full update
        success = updater.update_all_readmes()
        return 0 if success else 1


if __name__ == "__main__":
    exit(main())
