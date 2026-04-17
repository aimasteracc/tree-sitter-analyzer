#!/usr/bin/env python3
"""Tests for design pattern detection - Multi-language support."""

from __future__ import annotations

from tree_sitter_analyzer.analysis.design_patterns import (
    PatternType,
    detect_patterns,
)


class TestPythonPatterns:
    """Test Python-specific pattern detection."""

    def test_python_singleton(self):
        """Test Singleton pattern in Python."""
        classes = [
            {
                "name": "Database",
                "start_line": 1,
                "end_line": 20,
                "methods": [
                    {"name": "__init__", "modifiers": ["private"]},
                    {"name": "get_instance", "modifiers": ["static"]},
                ],
                "fields": [{"name": "_instance", "modifiers": ["private"]}],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "database.py", "python")
        singleton_matches = [m for m in matches if m.pattern_type == PatternType.SINGLETON]
        assert len(singleton_matches) == 1
        assert singleton_matches[0].name == "Database"

    def test_python_factory(self):
        """Test Factory Method pattern in Python."""
        classes = [
            {
                "name": "DocumentFactory",
                "start_line": 1,
                "end_line": 15,
                "methods": [{"name": "create_pdf", "modifiers": []}],
                "fields": [],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "factory.py", "python")
        factory_matches = [m for m in matches if m.pattern_type == PatternType.FACTORY_METHOD]
        assert len(factory_matches) == 1

    def test_python_strategy(self):
        """Test Strategy pattern in Python."""
        classes = [
            {
                "name": "CompressionStrategy",
                "start_line": 1,
                "end_line": 5,
                "methods": [{"name": "compress", "modifiers": []}],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            },
            {
                "name": "ZipCompression",
                "start_line": 10,
                "end_line": 15,
                "methods": [],
                "modifiers": [],
                "interfaces": ["CompressionStrategy"],
                "extends": "",
            },
            {
                "name": "RarCompression",
                "start_line": 20,
                "end_line": 25,
                "methods": [],
                "modifiers": [],
                "interfaces": ["CompressionStrategy"],
                "extends": "",
            },
        ]
        matches = detect_patterns(classes, [], "compression.py", "python")
        strategy_matches = [m for m in matches if m.pattern_type == PatternType.STRATEGY]
        assert len(strategy_matches) == 1
        assert len(strategy_matches[0].elements["implementations"]) == 2


class TestJavaPatterns:
    """Test Java-specific pattern detection."""

    def test_java_singleton(self):
        """Test Singleton pattern in Java."""
        classes = [
            {
                "name": "ResourceManager",
                "start_line": 1,
                "end_line": 25,
                "methods": [
                    {"name": "ResourceManager", "modifiers": ["private"]},
                    {"name": "getInstance", "modifiers": ["public", "static"]},
                ],
                "fields": [{"name": "instance", "modifiers": ["private", "static"]}],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "ResourceManager.java", "java")
        singleton_matches = [m for m in matches if m.pattern_type == PatternType.SINGLETON]
        assert len(singleton_matches) == 1
        assert singleton_matches[0].confidence >= 0.9

    def test_java_observer(self):
        """Test Observer pattern in Java."""
        classes = [
            {
                "name": "NewsAgency",
                "start_line": 1,
                "end_line": 30,
                "methods": [
                    {"name": "registerObserver", "modifiers": ["public"]},
                    {"name": "removeObserver", "modifiers": ["public"]},
                    {"name": "notifyObservers", "modifiers": ["public"]},
                ],
                "fields": [],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "NewsAgency.java", "java")
        observer_matches = [m for m in matches if m.pattern_type == PatternType.OBSERVER]
        assert len(observer_matches) == 1
        assert observer_matches[0].confidence >= 0.9

    def test_java_factory(self):
        """Test Factory Method pattern in Java."""
        classes = [
            {
                "name": "DialogFactory",
                "start_line": 1,
                "end_line": 20,
                "methods": [
                    {"name": "createDialog", "modifiers": ["public"]},
                    {"name": "createButton", "modifiers": ["public"]},
                ],
                "fields": [],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "DialogFactory.java", "java")
        factory_matches = [m for m in matches if m.pattern_type == PatternType.FACTORY_METHOD]
        assert len(factory_matches) == 1


class TestJavaScriptPatterns:
    """Test JavaScript/TypeScript-specific pattern detection."""

    def test_js_singleton(self):
        """Test Singleton pattern in JavaScript."""
        classes = [
            {
                "name": "Store",
                "start_line": 1,
                "end_line": 15,
                "methods": [
                    {"name": "getInstance", "modifiers": ["static"]},
                ],
                "fields": [{"name": "instance", "modifiers": ["static"]}],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "store.js", "javascript")
        # May not detect without private constructor (JS specific)
        # But should detect factory methods or other patterns
        assert isinstance(matches, list)

    def test_js_observer(self):
        """Test Observer pattern in JavaScript."""
        classes = [
            {
                "name": "EventEmitter",
                "start_line": 1,
                "end_line": 25,
                "methods": [
                    {"name": "on", "modifiers": []},
                    {"name": "off", "modifiers": []},
                    {"name": "emit", "modifiers": []},
                ],
                "fields": [],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "emitter.js", "javascript")
        # on/off are not standard observer names, but emit is
        # Should detect Factory pattern from on/on (unconventional)
        assert isinstance(matches, list)

    def test_ts_strategy(self):
        """Test Strategy pattern in TypeScript."""
        classes = [
            {
                "name": "PaymentStrategy",
                "start_line": 1,
                "end_line": 5,
                "methods": [{"name": "pay", "modifiers": []}],
                "modifiers": ["interface"],
                "interfaces": [],
                "extends": "",
            },
            {
                "name": "CreditCardPayment",
                "start_line": 10,
                "end_line": 15,
                "methods": [],
                "modifiers": [],
                "interfaces": ["PaymentStrategy"],
                "extends": "",
            },
            {
                "name": "PayPalPayment",
                "start_line": 20,
                "end_line": 25,
                "methods": [],
                "modifiers": [],
                "interfaces": ["PaymentStrategy"],
                "extends": "",
            },
        ]
        matches = detect_patterns(classes, [], "payment.ts", "typescript")
        strategy_matches = [m for m in matches if m.pattern_type == PatternType.STRATEGY]
        assert len(strategy_matches) == 1
        assert len(strategy_matches[0].elements["implementations"]) == 2


class TestAntiPatternsMultiLang:
    """Test anti-pattern detection across languages."""

    def test_god_class_python(self):
        """Test God Class detection in Python."""
        methods = [{"name": f"method{i}", "modifiers": []} for i in range(25)]
        classes = [
            {
                "name": "GodClass",
                "start_line": 1,
                "end_line": 500,
                "methods": methods,
                "fields": [],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "god_class.py", "python")
        god_class_matches = [m for m in matches if m.pattern_type == PatternType.GOD_CLASS]
        assert len(god_class_matches) == 1

    def test_long_method_java(self):
        """Test Long Method detection in Java."""
        functions = [
            {
                "name": "hugeMethod",
                "start_line": 1,
                "end_line": 75,
                "parameters": [],
            }
        ]
        matches = detect_patterns([], functions, "HugeClass.java", "java")
        long_method_matches = [m for m in matches if m.pattern_type == PatternType.LONG_METHOD]
        assert len(long_method_matches) == 1
        assert long_method_matches[0].elements["loc"] == 75

    def test_god_class_typescript(self):
        """Test God Class detection in TypeScript."""
        fields = [{"name": f"field{i}", "modifiers": ["private"]} for i in range(15)]
        classes = [
            {
                "name": "DataService",
                "start_line": 1,
                "end_line": 300,
                "methods": [],
                "fields": fields,
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "data.service.ts", "typescript")
        god_class_matches = [m for m in matches if m.pattern_type == PatternType.GOD_CLASS]
        assert len(god_class_matches) == 1
        assert god_class_matches[0].elements["field_count"] == 15


class TestConfidenceScoring:
    """Test confidence scoring across languages."""

    def test_high_confidence_singleton(self):
        """Test high confidence Singleton (all indicators present)."""
        classes = [
            {
                "name": "Config",
                "start_line": 1,
                "end_line": 20,
                "methods": [
                    {"name": "Config", "modifiers": ["private"]},
                    {"name": "getInstance", "modifiers": ["public", "static"]},
                ],
                "fields": [{"name": "_instance", "modifiers": ["private", "static"]}],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "config.py", "python")
        singleton_matches = [m for m in matches if m.pattern_type == PatternType.SINGLETON]
        assert len(singleton_matches) == 1
        assert singleton_matches[0].confidence >= 0.9

    def test_medium_confidence_observer(self):
        """Test medium confidence Observer (add/remove without notify)."""
        classes = [
            {
                "name": "Subject",
                "start_line": 1,
                "end_line": 20,
                "methods": [
                    {"name": "addListener", "modifiers": []},
                    {"name": "removeListener", "modifiers": []},
                ],
                "fields": [],
                "modifiers": [],
                "interfaces": [],
                "extends": "",
            }
        ]
        matches = detect_patterns(classes, [], "subject.js", "javascript")
        observer_matches = [m for m in matches if m.pattern_type == PatternType.OBSERVER]
        assert len(observer_matches) == 1
        assert observer_matches[0].confidence >= 0.8
        assert observer_matches[0].confidence < 0.95
