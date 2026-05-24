"""Rule checks for semantic formatter validation."""

import re

from ._enhanced_assertion_models import AssertionResult, FormatElement

LANGUAGE_KEYWORDS = {
    "python": {
        "def",
        "class",
        "import",
        "from",
        "if",
        "else",
        "for",
        "while",
        "try",
        "except",
    },
    "java": {
        "public",
        "private",
        "protected",
        "class",
        "interface",
        "extends",
        "implements",
    },
    "javascript": {
        "function",
        "class",
        "const",
        "let",
        "var",
        "if",
        "else",
        "for",
        "while",
    },
    "typescript": {
        "function",
        "class",
        "interface",
        "type",
        "const",
        "let",
        "var",
        "public",
        "private",
    },
}

NAMING_RULES = {
    "python": {
        "class": r"^[A-Z][a-zA-Z0-9]*$",
        "method": r"^[a-z_][a-z0-9_]*$",
        "field": r"^[a-z_][a-z0-9_]*$",
    },
    "java": {
        "class": r"^[A-Z][a-zA-Z0-9]*$",
        "method": r"^[a-z][a-zA-Z0-9]*$",
        "field": r"^[a-z][a-zA-Z0-9]*$",
    },
    "javascript": {
        "class": r"^[A-Z][a-zA-Z0-9]*$",
        "method": r"^[a-z][a-zA-Z0-9]*$",
        "field": r"^[a-z][a-zA-Z0-9]*$",
    },
    "typescript": {
        "class": r"^[A-Z][a-zA-Z0-9]*$",
        "method": r"^[a-z][a-zA-Z0-9]*$",
        "field": r"^[a-z][a-zA-Z0-9]*$",
    },
}

TYPE_MAPPINGS = {
    "java": {
        "string": "String",
        "int": "int",
        "boolean": "boolean",
        "void": "void",
    },
    "typescript": {
        "string": "string",
        "number": "number",
        "boolean": "boolean",
        "void": "void",
    },
}

VALID_MODIFIERS = {
    "java": {"public", "private", "protected", "package"},
    "typescript": {"public", "private", "protected"},
    "python": {"public", "private"},
    "javascript": {"public"},
}


def validate_naming_conventions(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate naming conventions."""
    results = []
    rules = NAMING_RULES.get(language, {})

    for element in elements:
        result = _invalid_naming_result(element, language, rules)
        if result:
            results.append(result)

    return results


def _invalid_naming_result(
    element: FormatElement,
    language: str,
    rules: dict[str, str],
) -> AssertionResult | None:
    if element.element_type not in rules or not element.name:
        return None

    pattern = rules[element.element_type]
    if re.match(pattern, element.name):
        return None

    return AssertionResult(
        passed=False,
        message=f"Invalid {element.element_type} name '{element.name}' for {language}",
        details={
            "element_type": element.element_type,
            "element_name": element.name,
            "expected_pattern": pattern,
            "language": language,
        },
        severity="warning",
        location=(element.line_number, element.column_number),
        suggestion=f"Use {language} naming convention for {element.element_type}",
    )


def validate_type_consistency(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate type consistency."""
    if language not in TYPE_MAPPINGS:
        return []

    results = []
    valid_types = set(TYPE_MAPPINGS[language].values())

    for element in elements:
        result = _invalid_return_type_result(element, language, valid_types)
        if result:
            results.append(result)

    return results


def _invalid_return_type_result(
    element: FormatElement,
    language: str,
    valid_types: set[str],
) -> AssertionResult | None:
    return_type = element.attributes.get("return_type", "")
    if not return_type or return_type in valid_types:
        return None
    if return_type[0].isupper() or return_type in ["var", "let", "const"]:
        return None

    return AssertionResult(
        passed=False,
        message=f"Invalid return type '{return_type}' for {language}",
        details={
            "element_name": element.name,
            "return_type": return_type,
            "valid_types": list(valid_types),
            "language": language,
        },
        severity="error",
        location=(element.line_number, element.column_number),
        suggestion=f"Use valid {language} type or ensure custom type is properly defined",
    )


def validate_access_modifiers(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate access modifiers."""
    if language not in VALID_MODIFIERS:
        return []

    results = []
    valid_set = VALID_MODIFIERS[language]

    for element in elements:
        result = _invalid_access_modifier_result(element, language, valid_set)
        if result:
            results.append(result)

    return results


def _invalid_access_modifier_result(
    element: FormatElement,
    language: str,
    valid_set: set[str],
) -> AssertionResult | None:
    access = element.attributes.get("access", "")
    if not access or access in valid_set:
        return None

    return AssertionResult(
        passed=False,
        message=f"Invalid access modifier '{access}' for {language}",
        details={
            "element_name": element.name,
            "access_modifier": access,
            "valid_modifiers": list(valid_set),
            "language": language,
        },
        severity="error",
        location=(element.line_number, element.column_number),
        suggestion=f"Use valid {language} access modifier",
    )
