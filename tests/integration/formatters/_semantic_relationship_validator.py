"""Relationship checks for semantic formatter validation."""

import re

from ._enhanced_assertion_models import AssertionResult, FormatElement

BUILTIN_CLASS_REFERENCES = {"String", "Integer", "Boolean", "Object"}


def validate_element_relationships(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate relationships between parsed format elements."""
    results = []
    by_type = _group_elements_by_type(elements)

    if "class" in by_type and "method" in by_type:
        results.extend(
            _validate_class_method_relationships(
                by_type["class"], by_type["method"], language
            )
        )

    if "constructor" in by_type:
        results.extend(
            _validate_constructor_relationships(
                by_type.get("class", []), by_type["constructor"], language
            )
        )

    results.extend(validate_inheritance_relationships(elements, language))
    return results


def _group_elements_by_type(
    elements: list[FormatElement],
) -> dict[str, list[FormatElement]]:
    by_type: dict[str, list[FormatElement]] = {}
    for element in elements:
        if element.element_type not in by_type:
            by_type[element.element_type] = []
        by_type[element.element_type].append(element)
    return by_type


def _validate_class_method_relationships(
    classes: list[FormatElement],
    methods: list[FormatElement],
    language: str,
) -> list[AssertionResult]:
    results = []

    for class_elem in classes:
        class_name = class_elem.name
        class_methods = [
            method for method in methods if _is_method_in_class(method, class_name)
        ]
        if _class_missing_constructor(class_name, class_methods, language):
            results.append(
                _missing_constructor_result(class_elem, class_name, language)
            )

    return results


def _is_method_in_class(method: FormatElement, class_name: str) -> bool:
    """Check if method belongs to class (simplified heuristic)."""
    return True


def _class_missing_constructor(
    class_name: str,
    class_methods: list[FormatElement],
    language: str,
) -> bool:
    if language not in ["java", "typescript"] or not class_name:
        return False
    return not any(
        method.name == class_name or method.name == "constructor"
        for method in class_methods
    )


def _missing_constructor_result(
    class_elem: FormatElement,
    class_name: str,
    language: str,
) -> AssertionResult:
    expected_constructor = class_name if language == "java" else "constructor"
    return AssertionResult(
        passed=False,
        message=f"Class '{class_name}' missing constructor",
        details={
            "class_name": class_name,
            "class_line": class_elem.line_number,
            "expected_constructor": expected_constructor,
        },
        severity="warning",
        location=(class_elem.line_number, class_elem.column_number),
        suggestion=f"Add constructor for class '{class_name}'",
    )


def _validate_constructor_relationships(
    classes: list[FormatElement],
    constructors: list[FormatElement],
    language: str,
) -> list[AssertionResult]:
    results = []

    for constructor in constructors:
        matching_class = _matching_constructor_class(constructor, classes, language)
        if not matching_class:
            results.append(_orphan_constructor_result(constructor, classes))

    return results


def _matching_constructor_class(
    constructor: FormatElement,
    classes: list[FormatElement],
    language: str,
) -> FormatElement | None:
    for class_elem in classes:
        if language == "java" and constructor.name == class_elem.name:
            return class_elem
        if (
            language in ["typescript", "javascript"]
            and constructor.name == "constructor"
        ):
            return class_elem
    return None


def _orphan_constructor_result(
    constructor: FormatElement,
    classes: list[FormatElement],
) -> AssertionResult:
    return AssertionResult(
        passed=False,
        message=f"Constructor '{constructor.name}' has no matching class",
        details={
            "constructor_name": constructor.name,
            "constructor_line": constructor.line_number,
            "available_classes": [class_elem.name for class_elem in classes],
        },
        severity="error",
        location=(constructor.line_number, constructor.column_number),
        suggestion="Ensure constructor matches a defined class",
    )


def validate_inheritance_relationships(
    elements: list[FormatElement], language: str
) -> list[AssertionResult]:
    """Validate inheritance relationships."""
    _ = language
    class_names = {
        element.name for element in elements if element.element_type == "class"
    }
    results = []

    for element in elements:
        results.extend(_undefined_class_results(element, class_names))

    return results


def _undefined_class_results(
    element: FormatElement,
    class_names: set[str],
) -> list[AssertionResult]:
    results = []

    for text in _referenced_type_contexts(element):
        results.extend(_undefined_class_results_for_context(element, text, class_names))

    return results


def _undefined_class_results_for_context(
    element: FormatElement,
    text: str,
    class_names: set[str],
) -> list[AssertionResult]:
    results = []

    for potential_class in _potential_class_names(text):
        if _is_known_class_reference(potential_class, class_names):
            continue
        results.append(
            _undefined_class_result(element, potential_class, text, class_names)
        )

    return results


def _referenced_type_contexts(element: FormatElement) -> list[str]:
    return [
        text
        for text in [
            element.attributes.get("return_type", ""),
            element.attributes.get("parameters", ""),
        ]
        if text
    ]


def _potential_class_names(text: str) -> list[str]:
    return re.findall(r"\b[A-Z][a-zA-Z0-9]*\b", text)


def _is_known_class_reference(potential_class: str, class_names: set[str]) -> bool:
    return potential_class in class_names or potential_class in BUILTIN_CLASS_REFERENCES


def _undefined_class_result(
    element: FormatElement,
    potential_class: str,
    text: str,
    class_names: set[str],
) -> AssertionResult:
    return AssertionResult(
        passed=False,
        message=f"Reference to undefined class '{potential_class}'",
        details={
            "element_name": element.name,
            "referenced_class": potential_class,
            "context": text,
            "defined_classes": list(class_names),
        },
        severity="warning",
        location=(element.line_number, element.column_number),
        suggestion=f"Ensure class '{potential_class}' is defined or imported",
    )
