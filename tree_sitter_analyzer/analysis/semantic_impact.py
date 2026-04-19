#!/usr/bin/env python3
"""
Semantic Impact Analysis

Goes beyond textual occurrence counting to assess the *semantic* impact
of code changes. Considers type hierarchy, visibility, call chain depth,
and API surface area.

Layered on top of the existing trace_impact (ripgrep) and
dependency_query (BFS graph) tools.

Analysis dimensions:
1. Type hierarchy — base class changes propagate to all subclasses
2. Visibility — public API changes have wider impact than private ones
3. Call chain depth — deeper call chains amplify blast radius
4. API surface — methods in interfaces/abstract classes affect all implementations
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from tree_sitter_analyzer.language_detector import detect_language_from_file
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

class Visibility(Enum):
    """Symbol visibility level."""

    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    PACKAGE = "package"  # default (Java) / internal (C#)

class SemanticRiskLevel(Enum):
    """Risk assessment for a proposed change."""

    SAFE = "safe"  # Local scope, no callers
    LOW = "low"  # Few callers, private scope
    MODERATE = "moderate"  # Multiple callers or protected visibility
    HIGH = "high"  # Public API, many callers, or base class
    CRITICAL = "critical"  # Core API, deep call chains, type hierarchy root

@dataclass(frozen=True)
class SymbolProfile:
    """Profile of a symbol being analyzed for semantic impact."""

    name: str
    file_path: str
    language: str
    visibility: Visibility
    is_override: bool = False
    is_abstract: bool = False
    is_interface_member: bool = False
    is_static: bool = False
    is_constructor: bool = False
    parent_class: str | None = None
    base_classes: tuple[str, ...] = ()
    annotations: tuple[str, ...] = ()

@dataclass(frozen=True)
class SemanticImpactReport:
    """Complete semantic impact analysis result."""

    symbol: str
    risk_level: SemanticRiskLevel
    risk_score: int  # 0-100
    factors: tuple[str, ...]
    caller_count: int
    visibility: Visibility
    call_chain_depth: int
    is_type_hierarchy_root: bool
    suggestions: tuple[str, ...]

# Visibility multipliers: higher = wider impact
_VISIBILITY_WEIGHTS: dict[Visibility, float] = {
    Visibility.PUBLIC: 1.0,
    Visibility.PROTECTED: 0.7,
    Visibility.PACKAGE: 0.5,
    Visibility.PRIVATE: 0.2,
}

# Risk score thresholds
_RISK_THRESHOLDS: list[tuple[int, SemanticRiskLevel]] = [
    (80, SemanticRiskLevel.CRITICAL),
    (60, SemanticRiskLevel.HIGH),
    (40, SemanticRiskLevel.MODERATE),
    (20, SemanticRiskLevel.LOW),
]

def _determine_risk_level(score: int) -> SemanticRiskLevel:
    """Map numeric risk score to a categorical risk level."""
    for threshold, level in _RISK_THRESHOLDS:
        if score >= threshold:
            return level
    return SemanticRiskLevel.SAFE

def _compute_risk_score(
    caller_count: int,
    visibility: Visibility,
    call_chain_depth: int,
    is_type_hierarchy_root: bool,
    is_abstract: bool,
    is_interface_member: bool,
    is_static: bool,
    is_constructor: bool,
    annotations: tuple[str, ...],
) -> tuple[int, tuple[str, ...]]:
    """
    Compute a composite risk score (0-100) and list of contributing factors.

    Scoring model:
        base = caller_count * visibility_weight
        modifiers add bonus points for type hierarchy, abstract, etc.
        final score is capped at 100.

    Returns:
        (score, factors) tuple
    """
    factors: list[str] = []
    score = 0.0

    # 1. Caller volume (0-50 points)
    vis_weight = _VISIBILITY_WEIGHTS.get(visibility, 0.5)
    caller_contribution = min(caller_count * vis_weight * 2.5, 50)
    score += caller_contribution
    if caller_count > 20:
        factors.append(f"High caller volume ({caller_count} callers)")
    elif caller_count > 5:
        factors.append(f"Moderate caller volume ({caller_count} callers)")

    # 2. Visibility (0-15 points)
    if visibility == Visibility.PUBLIC:
        score += 15
        factors.append("Public API surface")
    elif visibility == Visibility.PROTECTED:
        score += 10
        factors.append("Protected visibility (affects subclasses)")

    # 3. Type hierarchy (0-20 points)
    if is_type_hierarchy_root:
        score += 20
        factors.append("Base class — changes propagate to all subclasses")
    elif is_abstract:
        score += 12
        factors.append("Abstract method — must be implemented by all subclasses")
    elif is_interface_member:
        score += 15
        factors.append("Interface member — affects all implementations")

    # 4. Call chain depth (0-10 points)
    if call_chain_depth >= 4:
        score += 10
        factors.append(f"Deep call chain (depth {call_chain_depth})")
    elif call_chain_depth >= 2:
        score += 5
        factors.append(f"Moderate call chain (depth {call_chain_depth})")

    # 5. Special modifiers (0-15 points)
    if is_static:
        score += 8
        factors.append("Static member — globally accessible")

    if is_constructor:
        score += 10
        factors.append("Constructor — affects all instantiation sites")

    # 6. Framework annotations (0-10 points)
    api_annotations = {
        "Override", "RequestMapping", "GetMapping", "PostMapping",
        "DeleteMapping", "PutMapping", "PatchMapping",
        "ApiOperation", "ApiParam", "Path", "GET", "POST", "PUT", "DELETE",
        "EventHandler", "Subscribe", "EventListener",
        "Hilt", "Inject", "Singleton", "Component",
        "Autowired", "Service", "Controller", "Repository",
    }
    matching_annotations = set(annotations) & api_annotations
    if matching_annotations:
        score += min(len(matching_annotations) * 5, 10)
        factors.append(
            f"Framework annotations: {', '.join(sorted(matching_annotations))}"
        )

    # Cap at 100
    final_score = min(int(score), 100)
    return final_score, tuple(factors)

def _generate_suggestions(
    risk_level: SemanticRiskLevel,
    is_type_hierarchy_root: bool,
    is_abstract: bool,
    is_interface_member: bool,
    visibility: Visibility,
    caller_count: int,
    call_chain_depth: int,
) -> tuple[str, ...]:
    """Generate actionable suggestions based on risk assessment."""
    suggestions: list[str] = []

    if risk_level in (SemanticRiskLevel.HIGH, SemanticRiskLevel.CRITICAL):
        suggestions.append(
            "Consider deprecation strategy: add @Deprecated annotation first, "
            "then remove in a future release"
        )

    if is_type_hierarchy_root:
        suggestions.append(
            "This is a base class change. Verify all subclasses still compile "
            "and pass tests after modification"
        )

    if is_abstract or is_interface_member:
        suggestions.append(
            "Abstract/interface change affects all implementations. "
            "Consider providing a default implementation instead"
        )

    if visibility == Visibility.PUBLIC and caller_count > 20:
        suggestions.append(
            "High-impact public API. Consider maintaining backward compatibility "
            "by adding new overloaded methods instead of changing existing ones"
        )

    if call_chain_depth >= 4:
        suggestions.append(
            "Deep call chain detected. Changes may have unpredictable cascading "
            "effects. Test the full chain end-to-end"
        )

    if visibility == Visibility.PRIVATE and caller_count == 0:
        suggestions.append("Safe to modify — private scope with no external callers")

    if not suggestions:
        suggestions.append(
            "Review call sites before modifying, but risk is manageable"
        )

    return tuple(suggestions)

def analyze_semantic_impact(
    symbol: str,
    file_path: str | None = None,
    caller_count: int = 0,
    call_chain_depth: int = 0,
    profile: SymbolProfile | None = None,
) -> SemanticImpactReport:
    """
    Perform semantic impact analysis for a symbol.

    Uses both quantitative (caller count, chain depth) and qualitative
    (visibility, type hierarchy, annotations) factors to produce a
    comprehensive risk assessment.

    Args:
        symbol: Symbol name being analyzed
        file_path: Source file path (optional, used for language detection)
        caller_count: Number of callers found (from trace_impact)
        call_chain_depth: Max call chain depth (from dependency graph)
        profile: Pre-computed symbol profile (optional)

    Returns:
        SemanticImpactReport with risk assessment and suggestions
    """
    # Build or use provided profile
    if profile is None:
        language = ""
        if file_path:
            language = detect_language_from_file(file_path) or ""
        profile = SymbolProfile(
            name=symbol,
            file_path=file_path or "",
            language=language,
            visibility=Visibility.PUBLIC,  # Assume public if unknown
        )

    # Detect type hierarchy roots
    is_type_hierarchy_root = len(profile.base_classes) == 0 and (
        profile.is_abstract or profile.is_interface_member
    )

    # Compute risk score
    risk_score, factors = _compute_risk_score(
        caller_count=caller_count,
        visibility=profile.visibility,
        call_chain_depth=call_chain_depth,
        is_type_hierarchy_root=is_type_hierarchy_root,
        is_abstract=profile.is_abstract,
        is_interface_member=profile.is_interface_member,
        is_static=profile.is_static,
        is_constructor=profile.is_constructor,
        annotations=profile.annotations,
    )

    risk_level = _determine_risk_level(risk_score)

    # Generate suggestions
    suggestions = _generate_suggestions(
        risk_level=risk_level,
        is_type_hierarchy_root=is_type_hierarchy_root,
        is_abstract=profile.is_abstract,
        is_interface_member=profile.is_interface_member,
        visibility=profile.visibility,
        caller_count=caller_count,
        call_chain_depth=call_chain_depth,
    )

    return SemanticImpactReport(
        symbol=symbol,
        risk_level=risk_level,
        risk_score=risk_score,
        factors=factors,
        caller_count=caller_count,
        visibility=profile.visibility,
        call_chain_depth=call_chain_depth,
        is_type_hierarchy_root=is_type_hierarchy_root,
        suggestions=suggestions,
    )

def extract_visibility_from_element(element: Any) -> Visibility:
    """
    Extract visibility from an analysis element.

    Handles both ORM-style objects and dict representations.

    Args:
        element: Analysis element (object or dict)

    Returns:
        Visibility enum value
    """
    visibility_str = ""
    if isinstance(element, dict):
        visibility_str = element.get("visibility", "")
    else:
        visibility_str = getattr(element, "visibility", "")

    visibility_map = {
        "public": Visibility.PUBLIC,
        "protected": Visibility.PROTECTED,
        "private": Visibility.PRIVATE,
        "package": Visibility.PACKAGE,
        "internal": Visibility.PACKAGE,
        "": Visibility.PUBLIC,  # Default to public
    }
    return visibility_map.get(visibility_str.lower(), Visibility.PUBLIC)

def build_symbol_profile(
    element: Any,
    file_path: str,
    language: str,
) -> SymbolProfile:
    """
    Build a SymbolProfile from an analysis element.

    Extracts visibility, type hierarchy info, and annotations from
    an analyzed code element.

    Args:
        element: Analysis element from plugin analysis
        file_path: Source file path
        language: Detected language

    Returns:
        SymbolProfile with extracted metadata
    """
    name = ""
    visibility = Visibility.PUBLIC
    is_override = False
    is_abstract = False
    is_interface_member = False
    is_static = False
    is_constructor = False
    parent_class = None
    base_classes: tuple[str, ...] = ()
    annotations: tuple[str, ...] = ()

    if isinstance(element, dict):
        name = element.get("name", "")
        visibility = extract_visibility_from_element(element)
        is_abstract = element.get("is_abstract", False)
        is_static = element.get("is_static", False)
        parent_class = element.get("parent_class")
        base_classes = tuple(element.get("base_classes", []))
        annotations = tuple(element.get("annotations", []))
    else:
        name = getattr(element, "name", "")
        visibility = extract_visibility_from_element(element)
        is_abstract = getattr(element, "is_abstract", False)
        is_static = getattr(element, "is_static", False)
        parent_class = getattr(element, "parent_class", None)
        base_classes = tuple(getattr(element, "base_classes", ()))
        annotations = tuple(getattr(element, "annotations", ()))

    # Detect constructor
    is_constructor = (
        name
        in (
            "<init>",  # Java
            "__init__",  # Python
            "constructor",  # TypeScript/JS
            ".ctor",  # C#
        )
        or name == parent_class  # C++/Java style
    )

    # Detect interface member
    element_type = ""
    if isinstance(element, dict):
        element_type = element.get("element_type", "")
    else:
        element_type = getattr(element, "element_type", "")
    is_interface_member = "interface" in element_type.lower() if element_type else False

    return SymbolProfile(
        name=name,
        file_path=file_path,
        language=language,
        visibility=visibility,
        is_override=is_override,
        is_abstract=is_abstract,
        is_interface_member=is_interface_member,
        is_static=is_static,
        is_constructor=is_constructor,
        parent_class=parent_class,
        base_classes=base_classes,
        annotations=annotations,
    )

def report_to_dict(report: SemanticImpactReport) -> dict[str, Any]:
    """Convert report to a JSON-serializable dictionary."""
    return {
        "symbol": report.symbol,
        "risk_level": report.risk_level.value,
        "risk_score": report.risk_score,
        "factors": list(report.factors),
        "caller_count": report.caller_count,
        "visibility": report.visibility.value,
        "call_chain_depth": report.call_chain_depth,
        "is_type_hierarchy_root": report.is_type_hierarchy_root,
        "suggestions": list(report.suggestions),
    }
