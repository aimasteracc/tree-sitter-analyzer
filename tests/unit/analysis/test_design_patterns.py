#!/usr/bin/env python3
"""Tests for design pattern detection module."""

from __future__ import annotations

from tree_sitter_analyzer.analysis.design_patterns import (
    PatternMatch,
    PatternType,
    _check_factory_method,
    _check_god_class,
    _check_long_method,
    _check_observer,
    _check_singleton,
    _check_strategy,
    _check_template_method,
    detect_patterns,
)


class TestDetectPatterns:
    """Test the main detect_patterns function."""

    def test_empty_input(self):
        """Test with empty class and function lists."""
        matches = detect_patterns([], [], "test.py", "python")
        assert matches == []

    def test_returns_pattern_matches(self):
        """Test that detect_patterns returns PatternMatch objects."""
        classes = [
            {
                "name": "Test",
                "start_line": 1,
                "end_line": 10,
                "methods": [],
                "fields": [],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        functions = []

        matches = detect_patterns(classes, functions, "test.py", "python")
        # Should return empty list for non-matching classes
        assert isinstance(matches, list)
        for match in matches:
            assert isinstance(match, PatternMatch)


class TestCheckSingleton:
    """Test Singleton pattern detection."""

    def test_no_singleton(self):
        """Test class without Singleton pattern."""
        cls = {
            "name": "RegularClass",
            "start_line": 1,
            "methods": [{"name": "RegularClass", "modifiers": ["public"]}],
            "fields": [],
        }
        result = _check_singleton(cls, "test.java", "java")
        assert result is None

    def test_singleton_with_private_constructor(self):
        """Test Singleton with private constructor and getInstance."""
        cls = {
            "name": "Singleton",
            "start_line": 1,
            "methods": [
                {"name": "Singleton", "modifiers": ["private"]},
                {"name": "getInstance", "modifiers": ["public", "static"]},
            ],
            "fields": [{"name": "instance", "modifiers": ["private", "static"]}],
        }
        result = _check_singleton(cls, "test.java", "java")
        assert result is not None
        assert result.pattern_type == PatternType.SINGLETON
        assert result.confidence == 0.95
        assert result.elements["has_private_constructor"] is True
        assert result.elements["has_static_instance"] is True
        assert result.elements["has_get_instance"] is True

    def test_singleton_partial_match(self):
        """Test Singleton with only private constructor."""
        cls = {
            "name": "PartialSingleton",
            "start_line": 1,
            "methods": [{"name": "PartialSingleton", "modifiers": ["private"]}],
            "fields": [],
        }
        result = _check_singleton(cls, "test.java", "java")
        assert result is None


class TestCheckFactoryMethod:
    """Test Factory Method pattern detection."""

    def test_no_factory(self):
        """Test class without Factory pattern."""
        cls = {
            "name": "RegularClass",
            "start_line": 1,
            "methods": [{"name": "doSomething", "modifiers": []}],
        }
        result = _check_factory_method(cls, "test.py", "python")
        assert result is None

    def test_factory_with_create_method(self):
        """Test Factory with create* method."""
        cls = {
            "name": "Factory",
            "start_line": 1,
            "methods": [{"name": "createProduct", "modifiers": []}],
        }
        result = _check_factory_method(cls, "test.py", "python")
        assert result is not None
        assert result.pattern_type == PatternType.FACTORY_METHOD
        assert "createproduct" in result.elements["factory_methods"][0].lower()

    def test_factory_with_make_method(self):
        """Test Factory with make* method."""
        cls = {
            "name": "Builder",
            "start_line": 1,
            "methods": [{"name": "makeObject", "modifiers": []}],
        }
        result = _check_factory_method(cls, "test.java", "java")
        assert result is not None
        assert result.pattern_type == PatternType.FACTORY_METHOD

    def test_factory_with_build_method(self):
        """Test Factory with build* method."""
        cls = {
            "name": "Director",
            "start_line": 1,
            "methods": [{"name": "build", "modifiers": []}],
        }
        result = _check_factory_method(cls, "test.py", "python")
        assert result is not None
        assert result.pattern_type == PatternType.FACTORY_METHOD


class TestCheckObserver:
    """Test Observer pattern detection."""

    def test_no_observer(self):
        """Test class without Observer pattern."""
        cls = {
            "name": "RegularClass",
            "start_line": 1,
            "methods": [{"name": "doSomething", "modifiers": []}],
        }
        result = _check_observer(cls, "test.java", "java")
        assert result is None

    def test_observer_with_listeners(self):
        """Test Observer with addListener/removeListener."""
        cls = {
            "name": "Subject",
            "start_line": 1,
            "methods": [
                {"name": "addListener", "modifiers": []},
                {"name": "removeListener", "modifiers": []},
            ],
        }
        result = _check_observer(cls, "test.java", "java")
        assert result is not None
        assert result.pattern_type == PatternType.OBSERVER
        assert result.elements["has_add"] is True
        assert result.elements["has_remove"] is True
        assert result.confidence == 0.85

    def test_observer_with_notify(self):
        """Test Observer with notify method."""
        cls = {
            "name": "EventEmitter",
            "start_line": 1,
            "methods": [
                {"name": "addListener", "modifiers": []},
                {"name": "removeListener", "modifiers": []},
                {"name": "notifyObservers", "modifiers": []},
            ],
        }
        result = _check_observer(cls, "test.js", "javascript")
        assert result is not None
        assert result.pattern_type == PatternType.OBSERVER
        assert result.elements["has_notify"] is True
        assert result.confidence == 0.95

    def test_observer_with_attach_detach(self):
        """Test Observer with attach/detach methods."""
        cls = {
            "name": "Observable",
            "start_line": 1,
            "methods": [
                {"name": "attach", "modifiers": []},
                {"name": "detach", "modifiers": []},
            ],
        }
        result = _check_observer(cls, "test.py", "python")
        assert result is not None
        assert result.pattern_type == PatternType.OBSERVER


class TestCheckStrategy:
    """Test Strategy pattern detection."""

    def test_no_strategy(self):
        """Test class without Strategy pattern."""
        cls = {
            "name": "RegularClass",
            "start_line": 1,
            "methods": [{"name": "doSomething", "modifiers": []}],
            "modifiers": [],
            "interfaces": [],
            "extends": "",
        }
        all_classes = [cls]
        result = _check_strategy(cls, all_classes, "test.py", "python")
        assert result is None

    def test_strategy_with_implementations(self):
        """Test Strategy with interface and implementations."""
        interface = {
            "name": "SortStrategy",
            "start_line": 1,
            "methods": [{"name": "sort", "modifiers": []}],
            "modifiers": ["interface"],
            "interfaces": [],
            "extends": "",
        }
        impl1 = {
            "name": "BubbleSort",
            "start_line": 10,
            "methods": [],
            "modifiers": [],
            "interfaces": ["SortStrategy"],
            "extends": "",
        }
        impl2 = {
            "name": "QuickSort",
            "start_line": 20,
            "methods": [],
            "modifiers": [],
            "interfaces": ["SortStrategy"],
            "extends": "",
        }
        all_classes = [interface, impl1, impl2]

        result = _check_strategy(interface, all_classes, "test.java", "java")
        assert result is not None
        assert result.pattern_type == PatternType.STRATEGY
        assert result.elements["interface"] == "SortStrategy"
        assert len(result.elements["implementations"]) == 2


class TestCheckGodClass:
    """Test God Class anti-pattern detection."""

    def test_not_god_class(self):
        """Test normal class."""
        cls = {
            "name": "NormalClass",
            "start_line": 1,
            "end_line": 50,
            "methods": [{"name": "method1"}] * 5,
            "fields": [{"name": "field1"}] * 5,
        }
        result = _check_god_class(cls, "test.py", "python")
        assert result is None

    def test_god_class_by_method_count(self):
        """Test God Class detected by method count."""
        methods = [{"name": f"method{i}"} for i in range(25)]
        cls = {
            "name": "GodClass",
            "start_line": 1,
            "end_line": 100,
            "methods": methods,
            "fields": [],
        }
        result = _check_god_class(cls, "test.py", "python")
        assert result is not None
        assert result.pattern_type == PatternType.GOD_CLASS
        assert result.elements["method_count"] == 25

    def test_god_class_by_field_count(self):
        """Test God Class detected by field count."""
        fields = [{"name": f"field{i}"} for i in range(15)]
        cls = {
            "name": "DataClass",
            "start_line": 1,
            "end_line": 50,
            "methods": [],
            "fields": fields,
        }
        result = _check_god_class(cls, "test.java", "java")
        assert result is not None
        assert result.pattern_type == PatternType.GOD_CLASS
        assert result.elements["field_count"] == 15

    def test_god_class_by_loc(self):
        """Test God Class detected by lines of code."""
        cls = {
            "name": "HugeClass",
            "start_line": 1,
            "end_line": 600,
            "methods": [],
            "fields": [],
        }
        result = _check_god_class(cls, "test.py", "python")
        assert result is not None
        assert result.pattern_type == PatternType.GOD_CLASS
        assert result.elements["loc"] == 600


class TestCheckLongMethod:
    """Test Long Method anti-pattern detection."""

    def test_not_long_method(self):
        """Test normal method."""
        func = {
            "name": "shortMethod",
            "start_line": 1,
            "end_line": 30,
            "parameters": [{"name": "param1"}],
        }
        result = _check_long_method(func, "test.py", "python")
        assert result is None

    def test_long_method_by_loc(self):
        """Test Long Method detected by LOC."""
        func = {
            "name": "longMethod",
            "start_line": 1,
            "end_line": 60,
            "parameters": [],
        }
        result = _check_long_method(func, "test.py", "python")
        assert result is not None
        assert result.pattern_type == PatternType.LONG_METHOD
        assert result.elements["loc"] == 60

    def test_long_method_by_param_count(self):
        """Test Long Method detected by parameter count."""
        params = [{"name": f"param{i}"} for i in range(12)]
        func = {
            "name": "parameterizedMethod",
            "start_line": 1,
            "end_line": 30,
            "parameters": params,
        }
        result = _check_long_method(func, "test.java", "java")
        assert result is not None
        assert result.pattern_type == PatternType.LONG_METHOD
        assert result.elements["param_count"] == 12


class TestCheckTemplateMethod:
    """Test Template Method pattern detection."""

    def test_no_template_method(self):
        """Test non-abstract method."""
        func = {
            "name": "regularMethod",
            "modifiers": [],
        }
        result = _check_template_method(func, "test.py", "python")
        assert result is None

    def test_template_method_abstract(self):
        """Test abstract method as potential template method."""
        func = {
            "name": "templateMethod",
            "modifiers": ["abstract"],
        }
        result = _check_template_method(func, "test.java", "java")
        assert result is not None
        assert result.pattern_type == PatternType.TEMPLATE_METHOD
        assert result.elements["is_abstract"] is True


class TestPatternMatch:
    """Test PatternMatch dataclass."""

    def test_to_dict(self):
        """Test to_dict method."""
        match = PatternMatch(
            pattern_type=PatternType.SINGLETON,
            name="TestSingleton",
            file="test.py",
            line=10,
            confidence=0.95,
            elements={"test": "value"},
            language="python",
        )
        result = match.to_dict()
        assert result["pattern"] == "singleton"
        assert result["name"] == "TestSingleton"
        assert result["file"] == "test.py"
        assert result["line"] == 10
        assert result["confidence"] == 0.95
        assert result["elements"] == {"test": "value"}
        assert result["language"] == "python"

    def test_line_span_property(self):
        """Test line_span property calculation."""
        match = PatternMatch(
            pattern_type=PatternType.SINGLETON,
            name="Test",
            file="test.py",
            line=10,
            confidence=1.0,
            elements={},
        )
        # line_span is end_line - start_line + 1, but we only have start_line
        # This will fail if the property is used incorrectly
        assert match.line_span == 1  # Default when end_line not set
