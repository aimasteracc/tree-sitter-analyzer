#!/usr/bin/env python3
"""Tests for intelligence output formatters."""

from tree_sitter_analyzer.intelligence.formatters import (
    format_architecture_report,
    format_impact_result,
    format_trace_result,
)


class TestFormatTraceResult:
    def test_summary_format_definition(self):
        data = {
            "symbol": "login",
            "definitions": [
                {
                    "name": "login",
                    "file_path": "auth.py",
                    "line": 10,
                    "symbol_type": "function",
                    "parameters": ["user", "pw"],
                }
            ],
            "usages": [],
            "call_chain": {"callers": [], "callees": []},
            "inheritance": [],
        }
        result = format_trace_result(data, "summary")
        assert "login" in result
        assert "auth.py" in result

    def test_json_format(self):
        data = {
            "symbol": "foo",
            "definitions": [],
            "usages": [],
            "call_chain": {"callers": [], "callees": []},
            "inheritance": [],
        }
        result = format_trace_result(data, "json")
        import json

        parsed = json.loads(result)
        assert parsed["symbol"] == "foo"

    def test_tree_format(self):
        data = {
            "symbol": "bar",
            "definitions": [
                {
                    "name": "bar",
                    "file_path": "b.py",
                    "line": 1,
                    "symbol_type": "function",
                }
            ],
            "usages": [],
            "call_chain": {"callers": [], "callees": []},
            "inheritance": [],
        }
        result = format_trace_result(data, "tree")
        assert "bar" in result


class TestFormatImpactResult:
    def test_summary_format(self):
        data = {
            "target": "foo",
            "change_type": "signature_change",
            "risk_level": "high",
            "direct_impacts": [],
            "transitive_impacts": [],
            "affected_tests": [],
            "total_affected_files": 0,
        }
        result = format_impact_result(data, "summary")
        assert "foo" in result
        assert "high" in result.lower() or "HIGH" in result

    def test_json_format(self):
        data = {
            "target": "foo",
            "change_type": "rename",
            "risk_level": "low",
            "direct_impacts": [],
            "transitive_impacts": [],
            "affected_tests": [],
            "total_affected_files": 0,
        }
        import json

        result = format_impact_result(data, "json")
        parsed = json.loads(result)
        assert parsed["target"] == "foo"


class TestFormatArchitectureReport:
    def test_summary_format(self):
        data = {
            "path": "src/",
            "score": 72,
            "cycles": [],
            "layer_violations": [],
            "god_classes": [],
            "dead_symbols": [],
            "module_metrics": {},
            "coupling_matrix": {},
        }
        result = format_architecture_report(data, "summary")
        assert "72" in result

    def test_json_format(self):
        data = {
            "path": "src/",
            "score": 85,
            "cycles": [],
            "layer_violations": [],
            "god_classes": [],
            "dead_symbols": [],
            "module_metrics": {},
            "coupling_matrix": {},
        }
        import json

        result = format_architecture_report(data, "json")
        parsed = json.loads(result)
        assert parsed["score"] == 85
