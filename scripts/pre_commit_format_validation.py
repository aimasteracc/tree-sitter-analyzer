#!/usr/bin/env python3
"""
Pre-commit hook for format validation

This script validates format output for modified files to ensure
format consistency and prevent regressions.
"""

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

# Add project root to path - needs to be before imports  # noqa: E402
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.integration.formatters.format_assertions import (  # noqa: E402
    assert_compact_format_compliance,
    assert_csv_format_compliance,
    assert_full_format_compliance,
)
from tests.integration.formatters.schema_validation import validate_format  # noqa: E402
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (  # noqa: E402
    AnalyzeCodeStructureTool,
)


class PreCommitFormatValidator:
    """Pre-commit format validator"""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.validated_files: list[str] = []

    async def validate_file(self, file_path: str) -> bool:
        """Validate format output for a single file"""
        file_path_obj = Path(file_path)

        # Skip non-source files
        if not self._is_source_file(file_path_obj):
            return True

        # Skip if file doesn't exist (deleted files)
        if not file_path_obj.exists():
            return True

        try:
            # Create temporary directory for validation
            with tempfile.TemporaryDirectory() as temp_dir:
                # Determine language
                language = self._detect_language(file_path_obj)
                if not language:
                    return True  # Skip unsupported languages

                # Test all format types
                tool = AnalyzeCodeStructureTool(project_root=temp_dir)

                for format_type in ["full", "compact", "csv"]:
                    try:
                        result = await tool.execute(
                            {
                                "file_path": str(file_path_obj.absolute()),
                                "format_type": format_type,
                                "language": language,
                            }
                        )

                        output = result["table_output"]

                        # Validate format compliance
                        if not self._validate_format_output(
                            output, format_type, file_path
                        ):
                            return False

                    except Exception as e:
                        self.errors.append(
                            f"{file_path}: {format_type} format validation failed: {e}"
                        )
                        return False

                self.validated_files.append(file_path)
                return True

        except Exception as e:
            self.errors.append(f"{file_path}: Validation failed: {e}")
            return False

    def _is_source_file(self, file_path: Path) -> bool:
        """Check if file is a source file that should be validated"""
        supported_extensions = {".py", ".java", ".ts", ".js", ".html", ".css", ".md"}
        return file_path.suffix.lower() in supported_extensions

    def _detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension"""
        extension_map = {
            ".py": "python",
            ".java": "java",
            ".ts": "typescript",
            ".js": "javascript",
            ".html": "html",
            ".css": "css",
            ".md": "markdown",
        }
        return extension_map.get(file_path.suffix.lower())

    def _validate_format_output(
        self, output: str, format_type: str, file_path: str
    ) -> bool:
        """Validate format output compliance"""
        try:
            # Schema validation
            schema_type = "csv" if format_type == "csv" else "markdown"
            validation_result = validate_format(output, schema_type)

            if not validation_result.is_valid:
                self.errors.append(
                    f"{file_path}: {format_type} format schema validation failed: "
                    f"{', '.join(validation_result.errors)}"
                )
                return False

            # Format-specific compliance validation
            if format_type == "full":
                try:
                    # Extract class name for validation
                    class_name = self._extract_class_name(output, file_path)
                    if class_name:
                        assert_full_format_compliance(output, class_name)
                except AssertionError as e:
                    self.errors.append(
                        f"{file_path}: Full format compliance failed: {e}"
                    )
                    return False

            elif format_type == "compact":
                try:
                    assert_compact_format_compliance(output)
                except AssertionError as e:
                    self.errors.append(
                        f"{file_path}: Compact format compliance failed: {e}"
                    )
                    return False

            elif format_type == "csv":
                try:
                    assert_csv_format_compliance(output)
                except AssertionError as e:
                    self.errors.append(
                        f"{file_path}: CSV format compliance failed: {e}"
                    )
                    return False

            return True

        except Exception as e:
            self.errors.append(f"{file_path}: Format validation error: {e}")
            return False

    def _extract_class_name(self, output: str, file_path: str) -> str | None:
        """Extract class name from output or file path"""
        # Try to extract from output header
        lines = output.split("\n")
        if lines and lines[0].startswith("# "):
            header = lines[0][2:]  # Remove '# '
            if "." in header:
                return header.split(".")[-1]  # Get class name from package.ClassName
            return header

        # Fallback to file name
        file_path_obj = Path(file_path)
        return file_path_obj.stem

    def get_validation_summary(self) -> dict[str, Any]:
        """Get validation summary"""
        return {
            "validated_files": len(self.validated_files),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "success": len(self.errors) == 0,
            "error_details": self.errors,
            "warning_details": self.warnings,
            "files": self.validated_files,
        }


async def main():
    """Main pre-commit validation function"""
    parser = argparse.ArgumentParser(description="Pre-commit format validation")
    parser.add_argument("files", nargs="*", help="Files to validate")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first error")

    args = parser.parse_args()

    if not args.files:
        print("No files to validate")
        return 0

    validator = PreCommitFormatValidator()

    # Validate each file
    for file_path in args.files:
        if args.verbose:
            print(f"Validating {file_path}...")

        is_valid = await validator.validate_file(file_path)

        if not is_valid:
            if args.fail_fast:
                break

    # Print summary
    summary = validator.get_validation_summary()

    if args.verbose or not summary["success"]:
        print("\nFormat Validation Summary:")
        print(f"  Files validated: {summary['validated_files']}")
        print(f"  Errors: {summary['errors']}")
        print(f"  Warnings: {summary['warnings']}")

        if summary["error_details"]:
            print("\nErrors:")
            for error in summary["error_details"]:
                print(f"  ❌ {error}")

        if summary["warning_details"]:
            print("\nWarnings:")
            for warning in summary["warning_details"]:
                print(f"  ⚠️  {warning}")

    if summary["success"]:
        if args.verbose:
            print(
                f"\n✅ All {summary['validated_files']} files passed format validation"
            )
        return 0
    else:
        print(f"\n❌ Format validation failed for {summary['errors']} error(s)")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
