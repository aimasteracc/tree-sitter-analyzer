"""Tree-sitter based pattern analysis for refactoring suggestions."""

from __future__ import annotations

from typing import Any

from .element_extractor import get_classes, get_functions
from .refactoring_suggestions_classes import find_class_extractions
from .refactoring_suggestions_helpers import make_pattern


def analyze_treesitter_patterns(
    source: str,
    analysis: Any,
    include_extractions: bool,
    pattern_rules: list[dict[str, Any]],
    extraction_rules: list[dict[str, Any]],
    file_path: str | None = None,
) -> list[dict[str, Any]]:
    """Analyze file using tree-sitter extracted elements for pattern detection."""
    suggestions: list[dict[str, Any]] = []
    line_count = len(source.splitlines())

    if line_count > pattern_rules[0]["threshold"]:
        suggestions.append(
            make_pattern(
                pattern_rules[0],
                actual=line_count,
                priority_score=min(100, line_count // 10),
            )
        )

    if not analysis:
        return suggestions

    for func in get_functions(analysis):
        if func["lines"] <= pattern_rules[1]["threshold"]:
            continue
        suggestions.append(
            make_pattern(
                pattern_rules[1],
                name=func["name"],
                actual=func["lines"],
                line_range=(func["line"], func["end_line"]),
                priority_score=min(90, func["lines"]),
            )
        )

    if include_extractions:
        suggestions.extend(
            find_class_extractions(
                get_classes(analysis),
                extraction_rules[3],
                extraction_rules[1],
                file_path,
            )
        )

    return suggestions
