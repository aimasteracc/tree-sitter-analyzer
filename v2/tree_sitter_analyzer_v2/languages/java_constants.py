"""
Java language constants — framework annotations and keyword sets.

Extracted from java_parser.py to keep the parser module focused
on parsing logic (< 800 lines target).
"""

from __future__ import annotations

# Framework-specific annotation sets

SPRING_ANNOTATIONS: frozenset[str] = frozenset({
    "RestController",
    "Controller",
    "Service",
    "Repository",
    "Component",
    "Configuration",
    "Bean",
    "Autowired",
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PatchMapping",
})

JPA_ANNOTATIONS: frozenset[str] = frozenset({
    "Entity",
    "Table",
    "Id",
    "GeneratedValue",
    "Column",
    "OneToMany",
    "ManyToOne",
    "ManyToMany",
    "OneToOne",
})

LOMBOK_ANNOTATIONS: frozenset[str] = frozenset({
    "Data",
    "Getter",
    "Setter",
    "Builder",
    "Value",
    "NoArgsConstructor",
    "AllArgsConstructor",
    "RequiredArgsConstructor",
})

# Spring web-specific annotations (subset of SPRING_ANNOTATIONS)
SPRING_WEB_ANNOTATIONS: frozenset[str] = frozenset({
    "RestController",
    "Controller",
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PatchMapping",
})

# Java complexity keywords (for cyclomatic complexity calculation)
COMPLEXITY_KEYWORDS: frozenset[str] = frozenset({
    "if_statement",
    "while_statement",
    "for_statement",
    "enhanced_for_statement",
    "catch_clause",
    "ternary_expression",
    "switch_expression",
    "switch_block_statement_group",
    "lambda_expression",
    "throw_statement",
})

# Logical operators that increase complexity
COMPLEXITY_OPERATORS: frozenset[str] = frozenset({
    "&&",
    "||",
})
