"""CSV validation helpers for specification compliance tests."""

import csv
import io


class FormatSpecificationValidatorCsvMixin:
    """CSV-specific validation behavior for format specification tests."""

    def validate_csv_format_specification(self, output: str) -> bool:
        """Validate CSV Format specification compliance"""
        self.errors.clear()
        self.warnings.clear()

        if not self._validate_csv_structure(output):
            return False

        if not self._validate_csv_header(output):
            return False

        if not self._validate_csv_data_rows(output):
            return False

        if not self._validate_common_formatting(output):
            return False

        return len(self.errors) == 0

    def _validate_csv_structure(self, output: str) -> bool:
        """Validate CSV structure"""
        try:
            reader = csv.reader(io.StringIO(output))
            rows = list(reader)

            if len(rows) < 1:
                self.errors.append("CSV must have at least header row")
                return False

            header_cols = len(rows[0])
            self._append_inconsistent_csv_row_errors(rows, header_cols)

            return True

        except csv.Error as e:
            self.errors.append(f"Invalid CSV format: {e}")
            return False

    def _append_inconsistent_csv_row_errors(
        self, rows: list[list[str]], header_cols: int
    ) -> None:
        for i, row in enumerate(rows[1:], 1):
            if len(row) == header_cols:
                continue

            self.errors.append(
                f"Row {i} has {len(row)} columns, expected {header_cols}"
            )

    def _validate_csv_header(self, output: str) -> bool:
        """Validate CSV header compliance"""
        try:
            reader = csv.reader(io.StringIO(output))
            header = next(reader)

            expected_headers = [
                "Type",
                "Name",
                "ReturnType",
                "Parameters",
                "Access",
                "Static",
                "Final",
                "Line",
            ]

            if header != expected_headers:
                self.errors.append(
                    f"CSV header mismatch. Expected: {expected_headers}, Got: {header}"
                )
                return False

            return True

        except (csv.Error, StopIteration) as e:
            self.errors.append(f"Cannot read CSV header: {e}")
            return False

    def _validate_csv_data_rows(self, output: str) -> bool:
        """Validate CSV data rows"""
        try:
            reader = csv.reader(io.StringIO(output))
            _header = next(reader)

            for i, row in enumerate(reader, 1):
                if not self._validate_csv_row(row, i):
                    return False

            return True

        except (csv.Error, StopIteration) as e:
            self.errors.append(f"Cannot read CSV data: {e}")
            return False

    def _validate_csv_row(self, row: list[str], row_num: int) -> bool:
        """Validate individual CSV row"""
        if len(row) != 8:
            self.errors.append(f"Row {row_num} has {len(row)} columns, expected 8")
            return False

        type_val, name, return_type, parameters, access, static, final, line = row

        valid_types = [
            "class",
            "interface",
            "enum",
            "method",
            "constructor",
            "field",
            "property",
        ]
        if type_val not in valid_types:
            self.errors.append(
                f"Row {row_num}: Invalid type '{type_val}', must be one of {valid_types}"
            )

        if not name.strip():
            self.errors.append(f"Row {row_num}: Name cannot be empty")

        for field_name, field_value in [("Static", static), ("Final", final)]:
            if field_value not in ["true", "false", ""]:
                self.errors.append(
                    f"Row {row_num}: {field_name} must be 'true', 'false', or empty, got '{field_value}'"
                )

        if line.strip():
            self._append_line_number_error(line, row_num)

        if parameters.strip() and not self._validate_parameters_format(parameters):
            self.errors.append(
                f"Row {row_num}: Invalid parameters format '{parameters}'"
            )

        return True

    def _append_line_number_error(self, line: str, row_num: int) -> None:
        try:
            line_num = int(line)
        except ValueError:
            self.errors.append(f"Row {row_num}: Line must be a number, got '{line}'")
            return

        if line_num < 1:
            self.errors.append(
                f"Row {row_num}: Line number must be positive, got {line_num}"
            )

    def _validate_parameters_format(self, parameters: str) -> bool:
        """Validate parameters format: param1:type1;param2:type2"""
        if not parameters.strip():
            return True

        params = parameters.split(";")

        for param in params:
            param = param.strip()
            if ":" not in param:
                return False

            parts = param.split(":")
            if len(parts) != 2:
                return False

            name, type_name = parts
            if not name.strip() or not type_name.strip():
                return False

        return True
