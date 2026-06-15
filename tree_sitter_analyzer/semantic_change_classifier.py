#!/usr/bin/env python3
"""
Semantic Change Classifier — Classify AST diff hunks into semantic categories.

Takes the raw output of the AST diff engine and produces human-readable
classifications: API change, refactor, feature, bugfix candidate, etc.

This is a NEW capability beyond what CodeGraph offers — it doesn't just
detect changes, it understands what KIND of change they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .ast_diff import (
    ASTDiffHunk,
    ASTDiffResult,
    ASTNodeKind,
    DiffKind,
)


class SemanticCategory(str, Enum):
    API_CHANGE = "api_change"
    REFACTOR = "refactor"
    FEATURE_ADDITION = "feature_addition"
    FEATURE_REMOVAL = "feature_removal"
    INTERNAL_CHANGE = "internal_change"
    IMPORT_CHANGE = "import_change"
    CONFIGURATION = "configuration"
    STYLE_CHANGE = "style_change"
    TEST_CHANGE = "test_change"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


_CATEGORY_LABELS: dict[SemanticCategory, str] = {
    SemanticCategory.API_CHANGE: "Breaking API change",
    SemanticCategory.REFACTOR: "Refactor (behavior-preserving)",
    SemanticCategory.FEATURE_ADDITION: "Feature addition",
    SemanticCategory.FEATURE_REMOVAL: "Feature/code removal",
    SemanticCategory.INTERNAL_CHANGE: "Internal implementation change",
    SemanticCategory.IMPORT_CHANGE: "Import/dependency change",
    SemanticCategory.CONFIGURATION: "Configuration change",
    SemanticCategory.STYLE_CHANGE: "Style/formatting change",
    SemanticCategory.TEST_CHANGE: "Test change",
    SemanticCategory.DOCUMENTATION: "Documentation change",
    SemanticCategory.UNKNOWN: "Unclassified change",
}

_RISK_LEVELS: dict[SemanticCategory, str] = {
    SemanticCategory.API_CHANGE: "high",
    SemanticCategory.REFACTOR: "medium",
    SemanticCategory.FEATURE_ADDITION: "medium",
    SemanticCategory.FEATURE_REMOVAL: "high",
    SemanticCategory.INTERNAL_CHANGE: "low",
    SemanticCategory.IMPORT_CHANGE: "low",
    SemanticCategory.CONFIGURATION: "medium",
    SemanticCategory.STYLE_CHANGE: "low",
    SemanticCategory.TEST_CHANGE: "low",
    SemanticCategory.DOCUMENTATION: "low",
    SemanticCategory.UNKNOWN: "medium",
}

_PUBLIC_NAME_INDICATORS = frozenset(
    {
        "export",
        "public",
        "__all__",
        "API",
        "api",
    }
)

_TEST_PATH_INDICATORS = frozenset(
    {
        "test_",
        "_test.",
        "/tests/",
        "\\tests\\",
        "/test/",
        "\\test\\",
        "spec_",
        "_spec.",
        "/spec/",
        "/__tests__/",
        "conftest",
    }
)

_DOC_EXTENSIONS = frozenset(
    {
        ".md",
        ".rst",
        ".txt",
        ".adoc",
    }
)


@dataclass
class ClassifiedHunk:
    hunk: ASTDiffHunk
    category: SemanticCategory
    confidence: float
    reason: str

    def to_dict(self, include_children: bool = False) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "label": _CATEGORY_LABELS[self.category],
            "risk": _RISK_LEVELS[self.category],
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "hunk": self.hunk.to_dict(include_children=include_children),
        }


@dataclass
class SemanticClassification:
    classifications: list[ClassifiedHunk] = field(default_factory=list)
    dominant_category: SemanticCategory = SemanticCategory.UNKNOWN
    risk_level: str = "medium"
    change_summary: str = ""
    category_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self, include_children: bool = False) -> dict[str, Any]:
        return {
            "dominant_category": self.dominant_category.value,
            "dominant_label": _CATEGORY_LABELS[self.dominant_category],
            "risk_level": self.risk_level,
            "change_summary": self.change_summary,
            "category_counts": self.category_counts,
            "classifications": [
                c.to_dict(include_children=include_children)
                for c in self.classifications
            ],
        }


def _is_test_path(file_path: str | None) -> bool:
    if file_path is None:
        return False
    lower = file_path.lower()
    return any(ind in lower for ind in _TEST_PATH_INDICATORS)


def _is_doc_path(file_path: str | None) -> bool:
    if file_path is None:
        return False
    lower = file_path.lower()
    return any(lower.endswith(ext) for ext in _DOC_EXTENSIONS)


def _is_public_name(name: str | None) -> bool:
    if not name:
        return False
    if name.startswith("_") and not name.startswith("__"):
        return False
    return True


def _has_public_indicator(text: str | None) -> bool:
    if not text:
        return False
    return any(ind in text for ind in _PUBLIC_NAME_INDICATORS)


def _classify_single_hunk(
    hunk: ASTDiffHunk,
    file_path: str | None = None,
) -> ClassifiedHunk:
    if _is_test_path(file_path):
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.TEST_CHANGE,
            confidence=0.9,
            reason="File is in test directory",
        )

    if _is_doc_path(file_path):
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.DOCUMENTATION,
            confidence=0.9,
            reason="File is a documentation file",
        )

    if hunk.node_kind == ASTNodeKind.IMPORT:
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.IMPORT_CHANGE,
            confidence=0.85,
            reason="Import/dependency change",
        )

    if hunk.diff_kind == DiffKind.SIGNATURE_CHANGED:
        node_name = _hunk_name(hunk)
        is_public = _is_public_name(node_name)
        if is_public or _has_public_indicator(_hunk_preview(hunk)):
            return ClassifiedHunk(
                hunk=hunk,
                category=SemanticCategory.API_CHANGE,
                confidence=0.85 if is_public else 0.6,
                reason=(
                    f"Public signature change on {hunk.node_kind.value} '{node_name}'"
                    if is_public
                    else "Signature change may affect external callers"
                ),
            )
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.REFACTOR,
            confidence=0.7,
            reason="Private/internal signature change",
        )

    if hunk.diff_kind == DiffKind.NODE_RENAMED:
        node_name = _hunk_name(hunk)
        is_public = _is_public_name(node_name)
        if is_public:
            return ClassifiedHunk(
                hunk=hunk,
                category=SemanticCategory.API_CHANGE,
                confidence=0.8,
                reason=f"Public {hunk.node_kind.value} renamed: possible breaking change",
            )
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.REFACTOR,
            confidence=0.75,
            reason=f"Internal {hunk.node_kind.value} renamed",
        )

    if hunk.diff_kind == DiffKind.NODE_ADDED:
        node_name = _hunk_name(hunk)
        if hunk.node_kind in (
            ASTNodeKind.FUNCTION,
            ASTNodeKind.CLASS,
            ASTNodeKind.METHOD,
        ):
            return ClassifiedHunk(
                hunk=hunk,
                category=SemanticCategory.FEATURE_ADDITION,
                confidence=0.8,
                reason=f"New {hunk.node_kind.value} '{node_name}' added",
            )
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.INTERNAL_CHANGE,
            confidence=0.6,
            reason=f"New {hunk.node_kind.value} added",
        )

    if hunk.diff_kind == DiffKind.NODE_REMOVED:
        node_name = _hunk_name(hunk)
        if hunk.node_kind in (
            ASTNodeKind.FUNCTION,
            ASTNodeKind.CLASS,
            ASTNodeKind.METHOD,
        ):
            is_public = _is_public_name(node_name)
            if is_public:
                return ClassifiedHunk(
                    hunk=hunk,
                    category=SemanticCategory.FEATURE_REMOVAL,
                    confidence=0.85,
                    reason=f"Public {hunk.node_kind.value} '{node_name}' removed — likely breaking",
                )
            return ClassifiedHunk(
                hunk=hunk,
                category=SemanticCategory.FEATURE_REMOVAL,
                confidence=0.7,
                reason=f"Internal {hunk.node_kind.value} '{node_name}' removed",
            )
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.INTERNAL_CHANGE,
            confidence=0.5,
            reason=f"{hunk.node_kind.value} removed",
        )

    if hunk.diff_kind == DiffKind.BODY_CHANGED:
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.INTERNAL_CHANGE,
            confidence=0.7,
            reason=f"Implementation body change in {hunk.node_kind.value}",
        )

    if hunk.diff_kind == DiffKind.NODE_CHANGED:
        return ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.INTERNAL_CHANGE,
            confidence=0.5,
            reason=f"Generic change in {hunk.node_kind.value}",
        )

    return ClassifiedHunk(
        hunk=hunk,
        category=SemanticCategory.UNKNOWN,
        confidence=0.3,
        reason="Unable to classify",
    )


def _hunk_name(hunk: ASTDiffHunk) -> str | None:
    if hunk.new_node and hunk.new_node.name:
        return hunk.new_node.name
    if hunk.old_node and hunk.old_node.name:
        return hunk.old_node.name
    return None


def _hunk_preview(hunk: ASTDiffHunk) -> str | None:
    if hunk.new_node and hunk.new_node.text_preview:
        return hunk.new_node.text_preview
    if hunk.old_node and hunk.old_node.text_preview:
        return hunk.old_node.text_preview
    return None


_PRIORITY_ORDER = [
    SemanticCategory.API_CHANGE,
    SemanticCategory.FEATURE_REMOVAL,
    SemanticCategory.FEATURE_ADDITION,
    SemanticCategory.REFACTOR,
    SemanticCategory.CONFIGURATION,
    SemanticCategory.IMPORT_CHANGE,
    SemanticCategory.INTERNAL_CHANGE,
    SemanticCategory.TEST_CHANGE,
    SemanticCategory.STYLE_CHANGE,
    SemanticCategory.DOCUMENTATION,
    SemanticCategory.UNKNOWN,
]


def _pick_dominant(counts: dict[SemanticCategory, int]) -> SemanticCategory:
    for cat in _PRIORITY_ORDER:
        if counts.get(cat, 0) > 0:
            return cat
    return SemanticCategory.UNKNOWN


def _compute_risk(classifications: list[ClassifiedHunk]) -> str:
    if not classifications:
        return "low"
    has_high = any(
        _RISK_LEVELS[c.category] == "high"
        for c in classifications
        if c.confidence >= 0.7
    )
    if has_high:
        return "high"
    has_medium = any(
        _RISK_LEVELS[c.category] == "medium"
        for c in classifications
        if c.confidence >= 0.6
    )
    if has_medium:
        return "medium"
    return "low"


def _build_summary(
    dominant: SemanticCategory,
    counts: dict[SemanticCategory, int],
    total: int,
) -> str:
    if total == 0:
        return "No changes detected"
    label = _CATEGORY_LABELS[dominant]
    parts: list[str] = []
    for cat in _PRIORITY_ORDER:
        n = counts.get(cat, 0)
        if n > 0:
            parts.append(f"{n} {cat.value}")
    detail = ", ".join(parts)
    return f"{label} ({total} changes: {detail})"


class SemanticChangeClassifier:
    """
    Classify AST diff results into semantic categories.

    Takes ASTDiffResult from the AST diff engine and produces
    SemanticClassification with human-readable categories, risk levels,
    and confidence scores.

    Usage:
        classifier = SemanticChangeClassifier()
        result = classifier.classify(ast_diff_result)
        print(result.change_summary)
    """

    def __init__(self, file_path: str | None = None) -> None:
        self._file_path = file_path

    def classify(self, diff_result: ASTDiffResult) -> SemanticClassification:
        if not diff_result.hunks:
            return SemanticClassification(
                dominant_category=SemanticCategory.UNKNOWN,
                risk_level="low",
                change_summary="No changes detected",
            )

        file_path = self._file_path or diff_result.new_file

        classifications: list[ClassifiedHunk] = []
        cat_counts: dict[SemanticCategory, int] = {}

        for hunk in diff_result.hunks:
            classified = _classify_single_hunk(hunk, file_path)
            classifications.append(classified)
            cat_counts[classified.category] = cat_counts.get(classified.category, 0) + 1

        dominant = _pick_dominant(cat_counts)
        risk = _compute_risk(classifications)
        summary = _build_summary(dominant, cat_counts, len(classifications))

        str_counts = {cat.value: n for cat, n in cat_counts.items()}

        return SemanticClassification(
            classifications=classifications,
            dominant_category=dominant,
            risk_level=risk,
            change_summary=summary,
            category_counts=str_counts,
        )
