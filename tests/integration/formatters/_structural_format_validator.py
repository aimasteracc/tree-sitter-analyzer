"""Structural validation for formatter output."""

from ._enhanced_assertion_models import AssertionResult


class StructuralFormatValidator:
    """Validates structural aspects of format output"""

    def validate_table_structure(
        self, output: str, format_type: str
    ) -> list[AssertionResult]:
        """Validate table structure consistency"""
        results = []

        if format_type == "csv":
            results.extend(self._validate_csv_structure(output))
        else:
            results.extend(self._validate_markdown_table_structure(output))

        return results

    def _validate_csv_structure(self, output: str) -> list[AssertionResult]:
        """Validate CSV structure"""
        results = []
        lines = output.strip().split("\n")

        if not lines:
            results.append(
                AssertionResult(
                    passed=False,
                    message="Empty CSV output",
                    details={"line_count": 0},
                    severity="error",
                )
            )
            return results

        legacy_headers = [
            "Type",
            "Name",
            "ReturnType",
            "Parameters",
            "Access",
            "Static",
            "Final",
            "Line",
        ]
        new_headers_1 = [
            "Type",
            "Name",
            "Start Line",
            "End Line",
            "Language",
            "Visibility",
            "Parameters",
            "Return Type",
            "Modifiers",
        ]
        mock_headers = ["Type", "Name", "Signature", "Visibility", "Lines"]
        valid_header_sets = [legacy_headers, new_headers_1, mock_headers]

        actual_headers = [header.strip() for header in lines[0].split(",")]
        headers_valid = any(
            actual_headers == expected for expected in valid_header_sets
        )

        if not headers_valid:
            results.append(
                AssertionResult(
                    passed=True,
                    message="CSV header format unrecognized (non-critical)",
                    details={
                        "actual_headers": actual_headers,
                        "note": "Headers don't match any known CSV format but may still be valid",
                    },
                    severity="warning",
                    location=(1, 1),
                    suggestion="Consider using one of the standard CSV header formats for consistency",
                )
            )

        header_count = len(actual_headers)
        for line_num, line in enumerate(lines[1:], start=2):
            if line.strip():
                row_cells = line.split(",")
                if len(row_cells) != header_count:
                    results.append(
                        AssertionResult(
                            passed=False,
                            message=f"CSV row {line_num} has incorrect column count",
                            details={
                                "expected_columns": header_count,
                                "actual_columns": len(row_cells),
                                "line_content": line,
                            },
                            severity="error",
                            location=(line_num, 1),
                            suggestion="Ensure all CSV rows have the same number of columns",
                        )
                    )

        return results

    def _validate_markdown_table_structure(self, output: str) -> list[AssertionResult]:
        """Validate Markdown table structure"""
        results = []
        in_table = False
        table_start_line = 0
        table_headers = []

        for line_num, line in enumerate(output.split("\n"), start=1):
            line = line.strip()

            if "|" in line and not line.startswith("|--"):
                if not in_table:
                    in_table = True
                    table_start_line = line_num
                    table_headers = [
                        cell.strip() for cell in line.split("|") if cell.strip()
                    ]
                else:
                    results.extend(
                        _validate_markdown_row(
                            line, line_num, table_start_line, table_headers
                        )
                    )

            elif line.startswith("|--"):
                results.extend(
                    _validate_markdown_separator(line, line_num, table_headers)
                )

            elif in_table and not line:
                in_table = False

        return results


def _validate_markdown_row(
    line: str,
    line_num: int,
    table_start_line: int,
    table_headers: list[str],
) -> list[AssertionResult]:
    row_cells = [cell.strip() for cell in line.split("|") if cell.strip()]
    if len(row_cells) == len(table_headers):
        return []
    return [
        AssertionResult(
            passed=False,
            message=f"Table row {line_num} has incorrect column count",
            details={
                "table_start_line": table_start_line,
                "expected_columns": len(table_headers),
                "actual_columns": len(row_cells),
                "headers": table_headers,
                "row_content": line,
            },
            severity="error",
            location=(line_num, 1),
            suggestion="Ensure all table rows have the same number of columns as headers",
        )
    ]


def _validate_markdown_separator(
    line: str, line_num: int, table_headers: list[str]
) -> list[AssertionResult]:
    separators = [cell.strip() for cell in line.split("|") if cell.strip()]
    if len(separators) == len(table_headers):
        return []
    return [
        AssertionResult(
            passed=False,
            message=f"Table separator at line {line_num} has incorrect column count",
            details={
                "expected_columns": len(table_headers),
                "actual_columns": len(separators),
                "separator_line": line,
            },
            severity="error",
            location=(line_num, 1),
            suggestion="Ensure table separator matches header column count",
        )
    ]
