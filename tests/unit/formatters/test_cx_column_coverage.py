"""Tests: --advanced --table full Cx column present for Go and Bash.

LOCKED rule: exact-assertion pins only (no >= / > bounds).
Each test picks a minimal fixture with a known complexity_score and asserts
the EXACT value appears in the rendered table row.
"""

from tree_sitter_analyzer.formatters.bash_formatter import BashTableFormatter
from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixture builders
# ──────────────────────────────────────────────────────────────────────────────


def _go_data_with_func(complexity: int) -> dict:
    """Minimal Go structure dict with a single function at known complexity."""
    return {
        "file_path": "pkg/math/sample.go",
        "packages": [{"name": "math"}],
        "classes": [],
        "methods": [
            {
                "name": "Compute",
                "parameters": [{"name": "n", "type": "int"}],
                "return_type": "int",
                "line_range": {"start": 5, "end": 12},
                "complexity_score": complexity,
                "docstring": "",
            }
        ],
        "fields": [],
        "imports": [],
        "statistics": {"function_count": 1, "class_count": 0, "variable_count": 0},
    }


def _bash_data_with_func(complexity: int) -> dict:
    """Minimal Bash structure dict with a single function at known complexity."""
    return {
        "file_path": "scripts/deploy.sh",
        "classes": [],
        "methods": [
            {
                "name": "deploy",
                "parameters": [],
                "return_type": "",
                "line_range": {"start": 3, "end": 15},
                "complexity_score": complexity,
                "javadoc": "",
            }
        ],
        "fields": [],
        "imports": [],
        "statistics": {"method_count": 1, "field_count": 0},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Go formatter tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGoFormatterCxColumn:
    """Go full-table must include Cx column with exact complexity value."""

    def test_functions_header_has_cx_column(self):
        formatter = GoTableFormatter("full")
        output = formatter.format_structure(_go_data_with_func(1))
        assert "| Func | Signature | Vis | Lines | Cx | Doc |" in output

    def test_function_row_cx_value_1(self):
        """Trivial function → complexity_score == 1 → renders '| 1 |' in row."""
        formatter = GoTableFormatter("full")
        output = formatter.format_structure(_go_data_with_func(1))
        # Row must contain the exact complexity value 1
        assert "| Compute | (n int) int | exported | 5-12 | 1 | - |" in output

    def test_function_row_cx_value_5(self):
        """Function with complexity 5 → renders '| 5 |'."""
        formatter = GoTableFormatter("full")
        output = formatter.format_structure(_go_data_with_func(5))
        assert "| Compute | (n int) int | exported | 5-12 | 5 | - |" in output

    def test_methods_header_has_cx_column(self):
        """Go method table (receiver present) must also have Cx column."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "pkg/service.go",
            "packages": [{"name": "service"}],
            "classes": [],
            "methods": [
                {
                    "name": "Run",
                    "parameters": [],
                    "return_type": "error",
                    "line_range": {"start": 10, "end": 20},
                    "complexity_score": 3,
                    "docstring": "",
                    "is_method": True,
                    "receiver_type": "Service",
                }
            ],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
        }
        output = formatter.format_structure(data)
        assert "| Receiver | Func | Signature | Vis | Lines | Cx | Doc |" in output

    def test_method_row_cx_value_3(self):
        """Go method row includes exact complexity."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "pkg/service.go",
            "packages": [{"name": "service"}],
            "classes": [],
            "methods": [
                {
                    "name": "Run",
                    "parameters": [],
                    "return_type": "error",
                    "line_range": {"start": 10, "end": 20},
                    "complexity_score": 3,
                    "docstring": "",
                    "is_method": True,
                    "receiver_type": "Service",
                }
            ],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
        }
        output = formatter.format_structure(data)
        assert "| Service | Run | () error | exported | 10-20 | 3 | - |" in output

    def test_no_cx_column_absent_from_old_go_output(self):
        """Negative: the OLD 5-column header should NOT appear anymore."""
        formatter = GoTableFormatter("full")
        output = formatter.format_structure(_go_data_with_func(1))
        assert "| Func | Signature | Vis | Lines | Doc |" not in output


# ──────────────────────────────────────────────────────────────────────────────
# Bash formatter tests
# ──────────────────────────────────────────────────────────────────────────────


class TestBashFormatterCxColumn:
    """Bash full-table must include Cx column with exact complexity value."""

    def test_functions_header_has_cx_column(self):
        formatter = BashTableFormatter("full")
        output = formatter.format_structure(_bash_data_with_func(1))
        assert "| Name | Signature | Vis | Lines | Cx | Doc |" in output

    def test_function_row_cx_value_1(self):
        """Simple bash function → complexity_score == 1 → renders '| 1 |'."""
        formatter = BashTableFormatter("full")
        output = formatter.format_structure(_bash_data_with_func(1))
        assert "| deploy | () | public | 3-15 | 1 | - |" in output

    def test_function_row_cx_value_4(self):
        """Bash function with complexity 4 → renders '| 4 |'."""
        formatter = BashTableFormatter("full")
        output = formatter.format_structure(_bash_data_with_func(4))
        assert "| deploy | () | public | 3-15 | 4 | - |" in output

    def test_compact_functions_header_has_cx_column(self):
        """Compact Bash table also includes Cx column."""
        formatter = BashTableFormatter("compact")
        output = formatter.format_structure(_bash_data_with_func(2))
        assert "| Name | Sig | V | L | Cx | Doc |" in output

    def test_compact_function_row_cx_value_2(self):
        """Compact Bash row includes exact complexity 2."""
        formatter = BashTableFormatter("compact")
        output = formatter.format_structure(_bash_data_with_func(2))
        assert "| deploy | (0) | + | 3-15 | 2 | - |" in output

    def test_bash_formatter_registered(self):
        """BashTableFormatter must be reachable via FormatterRegistry."""
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

        formatter = FormatterRegistry.get_formatter_for_language("bash", "full")
        assert isinstance(formatter, BashTableFormatter)

    def test_sh_alias_registered(self):
        """'sh' language alias must also resolve to BashTableFormatter."""
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

        formatter = FormatterRegistry.get_formatter_for_language("sh", "full")
        assert isinstance(formatter, BashTableFormatter)

    def test_bash_section_header_present(self):
        """Full table must include a '## Functions' section."""
        formatter = BashTableFormatter("full")
        output = formatter.format_structure(_bash_data_with_func(1))
        assert "## Functions" in output

    def test_old_legacy_columns_absent(self):
        """OLD legacy columns (Name | Return Type | Parameters | Access | Line) must NOT appear."""
        formatter = BashTableFormatter("full")
        output = formatter.format_structure(_bash_data_with_func(1))
        assert "| Name | Return Type | Parameters | Access | Line |" not in output
