"""Public comparison helpers for analyze_differences."""

from compatibility_test.scripts._analyze_differences_json_metrics import (
    compare_performance_metrics,
    extract_performance_metrics,
)
from compatibility_test.scripts._analyze_differences_json_severity import (
    BREAKING_FIELDS,
    PERFORMANCE_FIELDS,
    FieldSeverityFunc,
    determine_field_severity,
    determine_severity,
)
from compatibility_test.scripts._analyze_differences_json_structure import (
    compare_json_structure,
)
from compatibility_test.scripts._analyze_differences_json_text import (
    analyze_text_difference,
    load_json_pair,
)

__all__ = [
    "BREAKING_FIELDS",
    "PERFORMANCE_FIELDS",
    "FieldSeverityFunc",
    "analyze_text_difference",
    "compare_json_structure",
    "compare_performance_metrics",
    "determine_field_severity",
    "determine_severity",
    "extract_performance_metrics",
    "load_json_pair",
]
