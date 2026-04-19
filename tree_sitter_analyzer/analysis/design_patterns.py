#!/usr/bin/env python3
"""
Design Pattern Detection Module

Detects design patterns and anti-patterns in source code using AST analysis.
Supports creational, structural, and behavioral patterns across multiple languages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PatternType(Enum):
    """Types of design patterns that can be detected."""

    # Creational patterns
    SINGLETON = "singleton"
    FACTORY_METHOD = "factory_method"
    BUILDER = "builder"
    PROTOTYPE = "prototype"

    # Structural patterns
    ADAPTER = "adapter"
    DECORATOR = "decorator"
    PROXY = "proxy"
    COMPOSITE = "composite"

    # Behavioral patterns
    OBSERVER = "observer"
    STRATEGY = "strategy"
    COMMAND = "command"
    TEMPLATE_METHOD = "template_method"

    # Anti-patterns
    GOD_CLASS = "god_class"
    LONG_METHOD = "long_method"
    CIRCULAR_DEPENDENCY = "circular_dependency"

@dataclass(frozen=True)
class PatternMatch:
    """A detected design pattern match."""

    pattern_type: PatternType
    name: str
    file: str
    line: int
    confidence: float  # 0.0 to 1.0
    elements: dict[str, Any]
    language: str = ""
    end_line: int = 0  # Optional end line for calculating span

    @property
    def line_span(self) -> int:
        if self.end_line > 0:
            return self.end_line - self.line + 1
        return 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern_type.value,
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "confidence": self.confidence,
            "elements": self.elements,
            "language": self.language,
        }

def detect_patterns(
    classes: list[dict[str, Any]],
    functions: list[dict[str, Any]],
    file_path: str,
    language: str,
) -> list[PatternMatch]:
    """Detect design patterns in the given AST elements.

    Args:
        classes: List of class dictionaries with AST information
        functions: List of function/method dictionaries
        file_path: Path to the source file
        language: Programming language

    Returns:
        List of detected pattern matches
    """
    matches: list[PatternMatch] = []

    for cls in classes:
        # Check for Singleton pattern
        singleton_match = _check_singleton(cls, file_path, language)
        if singleton_match:
            matches.append(singleton_match)

        # Check for Factory pattern
        factory_match = _check_factory_method(cls, file_path, language)
        if factory_match:
            matches.append(factory_match)

        # Check for Observer pattern
        observer_match = _check_observer(cls, file_path, language)
        if observer_match:
            matches.append(observer_match)

        # Check for Strategy pattern
        strategy_match = _check_strategy(cls, classes, file_path, language)
        if strategy_match:
            matches.append(strategy_match)

        # Check for anti-patterns
        god_class_match = _check_god_class(cls, file_path, language)
        if god_class_match:
            matches.append(god_class_match)

    for func in functions:
        # Check for long method anti-pattern
        long_method_match = _check_long_method(func, file_path, language)
        if long_method_match:
            matches.append(long_method_match)

        # Check for Template Method pattern
        template_match = _check_template_method(func, file_path, language)
        if template_match:
            matches.append(template_match)

    return matches

def _check_singleton(
    cls: dict[str, Any], file_path: str, language: str
) -> PatternMatch | None:
    """Check if a class implements the Singleton pattern.

    Singleton indicators:
    - Private static instance field
    - Private constructor
    - Public static getInstance() or instance() method
    """
    name = cls.get("name", "")
    methods = cls.get("methods", [])
    fields = cls.get("fields", [])

    # Check for private constructor
    # In Python, the constructor is always __init__
    # In Java/C#, it's the class name
    has_private_constructor = any(
        (m.get("name", "") == name or m.get("name", "") == "__init__")
        and "private" in m.get("modifiers", [])
        for m in methods
    )

    # Check for static instance field
    has_static_instance = any(
        "static" in f.get("modifiers", [])
        and ("instance" in f.get("name", "").lower()
             or "_instance" in f.get("name", "").lower())
        for f in fields
    )

    # Check for getInstance() or instance() method (case-insensitive)
    has_get_instance = any(
        ("get_instance" in m.get("name", "").lower()
         or "getinstance" in m.get("name", "").lower()
         or "instance" in m.get("name", "").lower()
         or m.get("name", "") == name)
        and "static" in m.get("modifiers", [])
        for m in methods
    )

    # Python Singleton can also be detected by instance() method returning cached instance
    if language == "python":
        # More lenient for Python: static instance + get_instance is enough
        if has_static_instance and has_get_instance:
            confidence = 0.9
            if has_private_constructor:
                confidence = 0.95
            return PatternMatch(
                pattern_type=PatternType.SINGLETON,
                name=name,
                file=file_path,
                line=cls.get("start_line", 0),
                confidence=confidence,
                elements={
                    "class": name,
                    "has_private_constructor": has_private_constructor,
                    "has_static_instance": has_static_instance,
                    "has_get_instance": has_get_instance,
                },
                language=language,
            )

    if has_private_constructor and (has_static_instance or has_get_instance):
        confidence = 0.8
        if has_static_instance and has_get_instance:
            confidence = 0.95

        return PatternMatch(
            pattern_type=PatternType.SINGLETON,
            name=name,
            file=file_path,
            line=cls.get("start_line", 0),
            confidence=confidence,
            elements={
                "class": name,
                "has_private_constructor": has_private_constructor,
                "has_static_instance": has_static_instance,
                "has_get_instance": has_get_instance,
            },
            language=language,
        )

    return None

def _check_factory_method(
    cls: dict[str, Any], file_path: str, language: str
) -> PatternMatch | None:
    """Check if a class implements the Factory Method pattern.

    Factory Method indicators:
    - Methods named create*, make*, build*, instance*
    - Methods returning interface types or abstract classes
    """
    name = cls.get("name", "")
    methods = cls.get("methods", [])

    factory_methods = []
    for m in methods:
        method_name = m.get("name", "").lower()
        if any(keyword in method_name for keyword in
               ["create", "make", "build", "instance", "from_"]):
            factory_methods.append(m.get("name", ""))

    if factory_methods:
        return PatternMatch(
            pattern_type=PatternType.FACTORY_METHOD,
            name=name,
            file=file_path,
            line=cls.get("start_line", 0),
            confidence=0.7,
            elements={
                "class": name,
                "factory_methods": factory_methods,
            },
            language=language,
        )

    return None

def _check_observer(
    cls: dict[str, Any], file_path: str, language: str
) -> PatternMatch | None:
    """Check if a class implements the Observer pattern.

    Observer indicators:
    - Methods named addListener/removeListener/notify*
    - Or methods named attach/detach/notify
    - Or methods named register/unregister/notify
    - Or methods named subscribe/unsubscribe/notify
    """
    name = cls.get("name", "")
    methods = cls.get("methods", [])

    has_add = any(
        any(keyword in m.get("name", "").lower()
            for keyword in ["add_listener", "attach", "subscribe", "register",
                           "addlistener", "registerobserver"])
        for m in methods
    )

    has_remove = any(
        any(keyword in m.get("name", "").lower()
            for keyword in ["remove_listener", "detach", "unsubscribe", "unregister",
                           "removelistener", "removeobserver"])
        for m in methods
    )

    has_notify = any(
        "notify" in m.get("name", "").lower()
        for m in methods
    )

    if has_add and has_remove:
        confidence = 0.85
        if has_notify:
            confidence = 0.95

        return PatternMatch(
            pattern_type=PatternType.OBSERVER,
            name=name,
            file=file_path,
            line=cls.get("start_line", 0),
            confidence=confidence,
            elements={
                "class": name,
                "has_add": has_add,
                "has_remove": has_remove,
                "has_notify": has_notify,
            },
            language=language,
        )

    return None

def _check_strategy(
    cls: dict[str, Any], all_classes: list[dict[str, Any]],
    file_path: str, language: str
) -> PatternMatch | None:
    """Check if a class is part of a Strategy pattern.

    Strategy indicators:
    - Interface or abstract class with one method
    - Multiple implementations of the same interface
    - Context class that uses the strategy
    """
    name = cls.get("name", "")
    methods = cls.get("methods", [])
    modifiers = cls.get("modifiers", [])

    # Check if this is an interface or abstract class
    is_interface = "interface" in modifiers or "abstract" in cls.get("class_type", "")

    # For Python, also check if class name ends with "Strategy" or "Handler"
    is_python_strategy = language == "python" and (
        name.endswith("Strategy") or name.endswith("Handler")
    )

    # Strategy pattern: interface with single method
    if (is_interface or is_python_strategy) and len(methods) <= 3:
        # Look for implementations
        implementations = [
            c for c in all_classes
            if name in c.get("interfaces", []) or name in c.get("extends", "")
        ]

        # Also check for naming patterns (e.g., XxxCompression implementing CompressionStrategy)
        if not implementations and is_python_strategy:
            base_name = name.replace("Strategy", "").replace("Handler", "")
            implementations = [
                c for c in all_classes
                if base_name in c.get("name", "") and c.get("name", "") != name
            ]

        if len(implementations) >= 2:
            return PatternMatch(
                pattern_type=PatternType.STRATEGY,
                name=name,
                file=file_path,
                line=cls.get("start_line", 0),
                confidence=0.9,
                elements={
                    "interface": name,
                    "implementations": [c.get("name", "") for c in implementations],
                    "method": methods[0].get("name", "") if methods else "",
                },
                language=language,
            )

    return None

def _check_god_class(
    cls: dict[str, Any], file_path: str, language: str
) -> PatternMatch | None:
    """Check if a class is a God Class anti-pattern.

    God Class indicators:
    - Too many methods (>20)
    - Too many fields (>10)
    - High lines of code (>500)
    """
    name = cls.get("name", "")
    methods = cls.get("methods", [])
    fields = cls.get("fields", [])
    start_line = cls.get("start_line", 0)
    end_line = cls.get("end_line", 0)
    loc = end_line - start_line + 1

    method_count = len(methods)
    field_count = len(fields)

    # God class thresholds
    if method_count > 20 or field_count > 10 or loc > 500:
        confidence = 0.6
        if method_count > 30 or field_count > 20 or loc > 1000:
            confidence = 0.9

        return PatternMatch(
            pattern_type=PatternType.GOD_CLASS,
            name=name,
            file=file_path,
            line=start_line,
            confidence=confidence,
            elements={
                "class": name,
                "method_count": method_count,
                "field_count": field_count,
                "loc": loc,
            },
            language=language,
        )

    return None

def _check_long_method(
    func: dict[str, Any], file_path: str, language: str
) -> PatternMatch | None:
    """Check if a function/method is too long.

    Long Method indicators:
    - More than 50 lines
    - More than 10 parameters
    - High cyclomatic complexity (>10)
    """
    name = func.get("name", "")
    start_line = func.get("start_line", 0)
    end_line = func.get("end_line", 0)
    loc = end_line - start_line + 1
    parameters = func.get("parameters", [])

    param_count = len(parameters)

    # Long method thresholds
    if loc > 50 or param_count > 10:
        confidence = 0.7
        if loc > 100 or param_count > 15:
            confidence = 0.9

        return PatternMatch(
            pattern_type=PatternType.LONG_METHOD,
            name=name,
            file=file_path,
            line=start_line,
            confidence=confidence,
            elements={
                "function": name,
                "loc": loc,
                "param_count": param_count,
            },
            language=language,
        )

    return None

def _check_template_method(
    func: dict[str, Any], file_path: str, language: str
) -> PatternMatch | None:
    """Check if a method implements the Template Method pattern.

    Template Method indicators:
    - Method in abstract class
    - Calls multiple abstract methods
    """
    name = func.get("name", "")
    modifiers = func.get("modifiers", [])

    # Check if method is in an abstract class (simplified check)
    is_abstract = "abstract" in modifiers

    if is_abstract:
        # Template methods often call other methods
        # This is a simplified heuristic
        return PatternMatch(
            pattern_type=PatternType.TEMPLATE_METHOD,
            name=name,
            file=file_path,
            line=func.get("start_line", 0),
            confidence=0.6,
            elements={
                "method": name,
                "is_abstract": is_abstract,
            },
            language=language,
        )

    return None
