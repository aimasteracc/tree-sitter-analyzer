"""Tests for CodePatternsTool — regression tests for cross-language smells, G3 SQL false positives, and G4 duplicate findings."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.code_patterns_tool import CodePatternsTool

# ---------------------------------------------------------------------------
# Cross-language smell detection (regression for bugs H1 + M5)
#
# Before the fix, code_patterns called detect_code_smells with analysis=None,
# which fell back to a Python-only heuristic. JS / TS / Java long functions
# and god-classes were silently ignored even though file_health flagged them.
# ---------------------------------------------------------------------------


class TestCrossLanguageSmellDetection:
    @pytest.mark.asyncio
    async def test_code_patterns_long_method_js(self, tmp_path):
        """Bug H1 regression: a 100+ line JS function MUST surface as long_method."""
        body = "\n".join(f"  const var{i} = input + {i};" for i in range(1, 121))
        source = (
            "function longJSFunction(input) {\n"
            "  // Auto-generated long function for testing\n"
            f"{body}\n"
            "  return var100;\n"
            "}\n"
        )
        target = tmp_path / "long.js"
        target.write_text(source, encoding="utf-8")

        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["smells"],
                "output_format": "json",
            }
        )

        smells = [p for p in result["results"] if p["category"] == "smells"]
        long_methods = [p for p in smells if p["type"] == "long_method"]
        assert long_methods, (
            "expected at least one long_method smell from cross-language AST "
            f"detection, got: {smells}"
        )
        assert long_methods[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_code_patterns_god_class_js(self, tmp_path):
        """Bug M5 regression: a single 300+ line JS class MUST surface as god_class."""
        method_chunks: list[str] = []
        for i in range(1, 30):
            body = "\n".join(f"    const x{j} = {i} + {j};" for j in range(10))
            method_chunks.append(f"  method{i}() {{\n{body}\n    return x9;\n  }}")
        source = "class BigJS {\n" + "\n".join(method_chunks) + "\n}\n"

        target = tmp_path / "big_class.js"
        target.write_text(source, encoding="utf-8")

        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["smells"],
                "output_format": "json",
            }
        )

        smells = [p for p in result["results"] if p["category"] == "smells"]
        god_classes = [p for p in smells if p["type"] == "god_class"]
        assert god_classes, (
            "expected a god_class smell once the AST path is wired up; got "
            f"smells={smells}"
        )


# ---------------------------------------------------------------------------
# G3 regression — SQL-injection regex must not flag benign diagnostic f-strings.
#
# Pre-fix the regex was ``f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s``,
# which matched any f-string containing the keyword anywhere followed by
# whitespace. English text like ``f"Please update {n} call sites"`` and
# ``f"DROP this approach, use {alternative} instead"`` were reported as
# ``critical: sql_injection``. The fix tightens the body so a clause
# indicator (``FROM``, ``INTO``, ``WHERE``, ``TABLE``, ``VALUES``, ``SET``)
# must follow the SQL keyword inside the same f-string.
# ---------------------------------------------------------------------------


class TestG3SqlInjectionFalsePositives:
    @pytest.mark.asyncio
    async def test_g3_fp_please_update_call_sites(self, tmp_path):
        """``Please update {n} call sites`` is English, not SQL."""
        target = tmp_path / "msg.py"
        target.write_text(
            "def msg(n, name):\n"
            '    return f"Please update {n} call sites for {name}."\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert sql_findings == [], (
            f"benign English f-string was flagged as sql_injection: {sql_findings}"
        )

    @pytest.mark.asyncio
    async def test_g3_fp_drop_this_approach(self, tmp_path):
        """``DROP this approach`` is figurative, not a DROP TABLE."""
        target = tmp_path / "comment.py"
        target.write_text(
            "def note(alternative):\n"
            '    return f"DROP this approach, use {alternative} instead"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert sql_findings == [], (
            f"figurative ``DROP this approach`` was flagged: {sql_findings}"
        )

    @pytest.mark.asyncio
    async def test_g3_tp_select_from_users(self, tmp_path):
        """Real SQL with FROM clause MUST be flagged."""
        target = tmp_path / "real_sqli.py"
        target.write_text(
            "def lookup(user_input):\n"
            "    return f\"SELECT * FROM users WHERE name = '{user_input}'\"\n",
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert len(sql_findings) == 1, (
            "expected exactly one sql_injection finding for a SELECT-FROM-WHERE "
            f"f-string; got {sql_findings}"
        )
        assert sql_findings[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_g3_tp_insert_into_logs(self, tmp_path):
        """Real INSERT with INTO clause MUST be flagged."""
        target = tmp_path / "real_insert.py"
        target.write_text(
            'def log(val):\n    return f"INSERT INTO logs VALUES ({val})"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["security"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert len(sql_findings) == 1, (
            "expected exactly one sql_injection finding for an INSERT-INTO "
            f"f-string; got {sql_findings}"
        )


# ---------------------------------------------------------------------------
# G4 regression — code_patterns must not report the same finding twice.
#
# Pre-fix, ``_detect_smells`` re-emitted security issues as ``smell``
# entries (category=smells, id=security:<name>), AND ``_detect_security``
# emitted the canonical entry (category=security, id=<name>). The same
# underlying SQL-injection ended up listed twice in ``results`` and double-
# counted in ``critical_count``. The fix drops the smell-namespaced mirror
# when a matching security entry exists.
# ---------------------------------------------------------------------------


class TestG4NoDuplicateFindings:
    @pytest.mark.asyncio
    async def test_g4_sql_injection_appears_once(self, tmp_path):
        """A single SQL-injection line yields exactly one ``results`` entry."""
        target = tmp_path / "sqli.py"
        target.write_text(
            "def get_user(user_id):\n"
            '    return f"SELECT * FROM users WHERE id = {user_id}"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["all"],
                "output_format": "json",
            }
        )
        sql_findings = [
            p
            for p in result["results"]
            if str(p.get("type") or p.get("id") or "").endswith("sql_injection")
        ]
        assert len(sql_findings) == 1, (
            "expected exactly one sql_injection entry in results; got "
            f"{len(sql_findings)}: {sql_findings}"
        )
        # The canonical entry under ``security`` namespace must survive;
        # the smell-namespaced mirror must be dropped.
        assert sql_findings[0]["category"] == "security"

    @pytest.mark.asyncio
    async def test_g4_count_matches_results_length(self, tmp_path):
        """``count`` must equal ``len(results)`` after dedup."""
        target = tmp_path / "sqli.py"
        target.write_text(
            "def get_user(user_id):\n"
            '    return f"SELECT * FROM users WHERE id = {user_id}"\n',
            encoding="utf-8",
        )
        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["all"],
                "output_format": "json",
            }
        )
        assert result["count"] == len(result["results"])
        # critical_count should reflect ONE underlying problem, not two.
        assert result["critical_count"] == 1

    @pytest.mark.asyncio
    async def test_g4_dedup_does_not_swallow_non_security_smells(self, tmp_path):
        """Dedup must only target the security mirror, not real smells."""
        # An oversized file produces ``oversized_file`` (a real smell) plus
        # a security finding. The smell must survive even after dedup runs.
        lines = ["def f():"] + ["    x = 1"] * 1200
        lines.append('    return f"SELECT * FROM users WHERE id = {x}"')
        target = tmp_path / "big.py"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tool = CodePatternsTool(str(tmp_path))
        result = await tool.execute(
            {
                "file_path": str(target),
                "categories": ["all"],
                "output_format": "json",
            }
        )
        types = {str(p.get("type") or p.get("id") or "") for p in result["results"]}
        assert "oversized_file" in types
        # sql_injection still appears exactly once
        sql_count = sum(
            1 for p in result["results"] if p.get("type") == "sql_injection"
        )
        assert sql_count == 1
