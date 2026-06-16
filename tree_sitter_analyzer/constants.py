#!/usr/bin/env python3
"""
Constants for tree-sitter-analyzer

This module defines constants used throughout the project to ensure consistency.
"""

from typing import Any, cast

# Element types for unified element management system
ELEMENT_TYPE_CLASS = "class"
ELEMENT_TYPE_FUNCTION = "function"
ELEMENT_TYPE_VARIABLE = "variable"
ELEMENT_TYPE_IMPORT = "import"
ELEMENT_TYPE_PACKAGE = "package"
ELEMENT_TYPE_ANNOTATION = "annotation"
ELEMENT_TYPE_LAMBDA = "lambda"
ELEMENT_TYPE_COMPREHENSION = "comprehension"
ELEMENT_TYPE_EXPRESSION = "expression"

# SQL element types
ELEMENT_TYPE_SQL_TABLE = "table"
ELEMENT_TYPE_SQL_VIEW = "view"
ELEMENT_TYPE_SQL_PROCEDURE = "procedure"
ELEMENT_TYPE_SQL_FUNCTION = "sql_function"
ELEMENT_TYPE_SQL_TRIGGER = "trigger"
ELEMENT_TYPE_SQL_INDEX = "index"

# Element type mapping for backward compatibility
ELEMENT_TYPE_MAPPING = {
    "Class": ELEMENT_TYPE_CLASS,
    "Function": ELEMENT_TYPE_FUNCTION,
    "Variable": ELEMENT_TYPE_VARIABLE,
    "Import": ELEMENT_TYPE_IMPORT,
    "Package": ELEMENT_TYPE_PACKAGE,
    "Annotation": ELEMENT_TYPE_ANNOTATION,
    "Lambda": ELEMENT_TYPE_LAMBDA,
    "Comprehension": ELEMENT_TYPE_COMPREHENSION,
    "Expression": ELEMENT_TYPE_EXPRESSION,
}

# Legacy class name to element type mapping
LEGACY_CLASS_MAPPING = {
    "Class": ELEMENT_TYPE_CLASS,
    "Function": ELEMENT_TYPE_FUNCTION,
    "Variable": ELEMENT_TYPE_VARIABLE,
    "Import": ELEMENT_TYPE_IMPORT,
    "Package": ELEMENT_TYPE_PACKAGE,
    "Annotation": ELEMENT_TYPE_ANNOTATION,
    "Lambda": ELEMENT_TYPE_LAMBDA,
    "Comprehension": ELEMENT_TYPE_COMPREHENSION,
    "Expression": ELEMENT_TYPE_EXPRESSION,
    # SQL element mappings
    "SQLTable": ELEMENT_TYPE_SQL_TABLE,
    "SQLView": ELEMENT_TYPE_SQL_VIEW,
    "SQLProcedure": ELEMENT_TYPE_SQL_PROCEDURE,
    "SQLFunction": ELEMENT_TYPE_SQL_FUNCTION,
    "SQLTrigger": ELEMENT_TYPE_SQL_TRIGGER,
    "SQLIndex": ELEMENT_TYPE_SQL_INDEX,
}


# ---------------------------------------------------------------------------
# Canonical "what kind of edit am I about to make?" vocabulary.
#
# Single source of truth shared by BOTH edit-classification flags so they can
# never diverge again (issue #985): the CLI's --edit-type (safe-to-edit, file
# level) and --modification-guard-type (modification-guard, symbol level), plus
# the matching MCP schemas (SafeToEditTool.edit_type, ModificationGuardTool /
# edit facade modification_type).
#
# Every value here is handled by downstream logic:
#   - safe_to_edit_risk._add_edit_type_factor / build_checklist branch on the
#     file-level risk kinds and treat the rest as neutral.
#   - modification_guard_tool adds type-specific actions for the symbol-level
#     kinds (rename/signature_change/delete/behavior_change/refactor) and falls
#     through to its caller-count verdict for the rest — no value is silently
#     accepted-but-unhandled.
# Adding a value here means adding its handling in BOTH tools.
# ---------------------------------------------------------------------------
EDIT_KINDS: tuple[str, ...] = (
    "add_feature",
    "behavior_change",
    "delete",
    "fix_bug",
    "refactor",
    "rename",
    "signature_change",
)


def get_element_type(element: Any) -> str:
    """
    Get the element type from an element object.

    Args:
        element: Element object with element_type attribute or __class__.__name__

    Returns:
        Standardized element type string
    """
    if hasattr(element, "element_type"):
        return cast(str, element.element_type)

    if hasattr(element, "__class__") and hasattr(element.__class__, "__name__"):
        class_name = element.__class__.__name__
        return LEGACY_CLASS_MAPPING.get(class_name, "unknown")

    return "unknown"


def is_element_of_type(element: Any, element_type: str) -> bool:
    """
    Check if an element is of a specific type.

    Args:
        element: Element object to check
        element_type: Expected element type

    Returns:
        True if element is of the specified type
    """
    return get_element_type(element) == element_type


# ---------------------------------------------------------------------------
# Directories excluded from filesystem walks (indexing, health scoring, graph
# analysis). Shared so every walker agrees — previously each module defined its
# own near-duplicate set and they drifted.
#
# Covers VCS, language caches, AND build-artifact dirs for COMPILED languages
# (C#/.NET, Java, Rust, Go, Swift, C++). These hold generated/compiled output
# that must never be indexed and can be enormous: a C# project's bin/obj or a
# NuGet `packages/` dir makes `index full` appear to hang on an otherwise small
# project. (Dot-prefixed dirs like .vs/.git are skipped separately via a
# `name.startswith(".")` check at each call site, so they are not all listed.)
# ---------------------------------------------------------------------------
EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        # Version control
        ".git",
        ".hg",
        ".svn",
        # Python caches / envs
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
        "htmlcov",
        ".cache",
        # JS / TS
        "node_modules",
        ".next",
        ".nuxt",
        "bower_components",
        # Build artifacts — compiled languages (the index-full hang fix).
        # NOTE: "bin" is intentionally NOT here. Rust uses src/bin/*.rs for
        # first-party binary-target SOURCES; excluding "bin" at any depth would
        # prune them. C#/Eclipse "bin" holds .dll/.class (which TSA never indexes
        # anyway); their generated SOURCES live in obj/ (C#) and target/ (Java),
        # both excluded below — so dropping "bin" keeps the hang fixed.
        "obj",  # C#/.NET (incl. obj/**/*.g.cs generated sources)
        # NOTE: "packages" is intentionally NOT here. JS/TS monorepos use
        # packages/<api>/<src>/ as first-party source directories (Yarn/pnpm
        # workspaces), so excluding "packages" at any depth prunes real source.
        # C#/NuGet packages live under obj/ or vendor/ which are already excluded;
        # TSA also skips .dll/.nupkg files by extension so traversal is safe.
        "target",  # Rust, Java (Maven)
        ".gradle",  # Java (Gradle)
        "vendor",  # Go, PHP
        "Pods",  # Swift / iOS (CocoaPods)
        "DerivedData",  # Swift / Xcode
        "cmake-build-debug",  # C++ (CLion)
        "cmake-build-release",  # C++ (CLion)
        # Generic build output
        "dist",
        "build",
        "out",
        # Editors / IDE
        ".idea",
        ".vscode",
        ".vs",
        # AI tooling
        ".claude",
        ".swarm",
        ".claude-flow",
        ".opencode",
        ".agents",
        ".recon",
        # TSA's own caches
        ".ast-cache",
        ".tree-sitter-cache",
    }
)
