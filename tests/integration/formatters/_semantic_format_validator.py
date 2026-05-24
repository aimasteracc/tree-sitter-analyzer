"""Semantic validation for formatter output."""

from ._enhanced_assertion_models import AssertionResult
from ._semantic_format_parser import parse_format_elements
from ._semantic_format_rules import (
    LANGUAGE_KEYWORDS,
    validate_access_modifiers,
    validate_naming_conventions,
    validate_type_consistency,
)
from ._semantic_relationship_validator import validate_element_relationships


class SemanticFormatValidator:
    """Validates semantic correctness of format output"""

    def __init__(self):
        self.language_keywords = LANGUAGE_KEYWORDS

    def validate_semantic_consistency(
        self, format_output: str, format_type: str, language: str
    ) -> list[AssertionResult]:
        """Validate semantic consistency of format output"""
        elements = parse_format_elements(format_output, format_type)
        results = validate_element_relationships(elements, language)
        results.extend(validate_naming_conventions(elements, language))
        results.extend(validate_type_consistency(elements, language))
        results.extend(validate_access_modifiers(elements, language))
        return results
