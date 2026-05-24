"""
Enhanced Format Assertions

Provides highly specific and detailed assertion capabilities for format validation.
Includes semantic validation, structural analysis, and content-aware assertions.
"""

from typing import Any

from ._content_aware_validator import ContentAwareValidator
from ._enhanced_assertion_models import AssertionResult, FormatElement
from ._enhanced_assertion_reports import build_assertion_report
from ._enhanced_assertions_assert_mixin import EnhancedFormatAssertionsAssertMixin
from ._semantic_format_validator import SemanticFormatValidator
from ._structural_format_validator import StructuralFormatValidator
from .format_assertions import FormatComplianceAssertions

__all__ = [
    "AssertionResult",
    "ContentAwareValidator",
    "EnhancedAssertions",
    "EnhancedFormatAssertions",
    "FormatElement",
    "SemanticFormatValidator",
    "StructuralFormatValidator",
]


class EnhancedFormatAssertions(
    EnhancedFormatAssertionsAssertMixin, FormatComplianceAssertions
):
    """Enhanced format assertions with semantic and structural validation"""

    def __init__(self):
        super().__init__()
        self.semantic_validator = SemanticFormatValidator()
        self.structural_validator = StructuralFormatValidator()
        self.content_validator = ContentAwareValidator()


class EnhancedAssertions:
    """Main enhanced assertions class that integrates all validation components"""

    def __init__(self):
        self.semantic_validator = SemanticFormatValidator()
        self.structural_validator = StructuralFormatValidator()
        self.content_validator = ContentAwareValidator()

    def validate_format_output(
        self, output: str, format_type: str, language: str = "python"
    ) -> dict[str, Any]:
        """Comprehensive format output validation"""

        all_results = []

        # Semantic validation
        semantic_results = self.semantic_validator.validate_semantic_consistency(
            output, format_type, language
        )
        all_results.extend(semantic_results)

        # Structural validation
        structural_results = self.structural_validator.validate_table_structure(
            output, format_type
        )
        all_results.extend(structural_results)

        # Content validation
        content_results = self.content_validator.validate_content_accuracy(
            output, format_type, language
        )
        all_results.extend(content_results)

        # Analyze results
        analysis = build_assertion_report(all_results)

        return {
            "valid": analysis["summary"]["failed_assertions"] == 0,
            "issues": [r.message for r in all_results if not r.passed],
            "analysis": analysis,
            "total_checks": len(all_results),
            "passed_checks": analysis["summary"]["passed_assertions"],
            "failed_checks": analysis["summary"]["failed_assertions"],
        }
