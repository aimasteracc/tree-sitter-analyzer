#!/usr/bin/env python3
"""
Performance regression tests.

Ensures core analysis operations stay within time budgets.
Catches speed regressions across versions.

Usage:
    uv run pytest tests/benchmark/test_performance_regression.py -v
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.error_recovery import ErrorRecovery
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

# ── Time budgets (seconds) ──
BUDGET_SINGLE_FILE_PARSE_S = 1.0
BUDGET_SMALL_FILE_RECOVERY_S = 0.5
BUDGET_QUERY_S = 1.0
BUDGET_REGISTRY_LOAD_S = 3.0

# ── Test data ──

_JAVA_FILE = """
package com.example.service;

import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.stream.Collectors;

public class UserAccountService {
    private final Map<String, Account> accounts = new HashMap<>();

    public Account createAccount(String userId, String name) {
        Account account = new Account(userId, name);
        accounts.put(userId, account);
        return account;
    }

    public Account getAccount(String userId) {
        return accounts.get(userId);
    }

    public List<Account> getActiveAccounts() {
        return accounts.values().stream()
            .filter(Account::isActive)
            .collect(Collectors.toList());
    }

    public void deactivateAccount(String userId) {
        Account account = accounts.get(userId);
        if (account != null) {
            account.setActive(false);
        }
    }

    public int getAccountCount() {
        return accounts.size();
    }
}

class Account {
    private String userId;
    private String name;
    private boolean active = true;

    public Account(String userId, String name) {
        this.userId = userId;
        this.name = name;
    }

    public String getUserId() { return userId; }
    public String getName() { return name; }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
}
""".strip()

_PYTHON_FILE = '''
"""Data processing pipeline."""

import json
import os
from pathlib import Path
from typing import Any, Optional


class DataPipeline:
    """Main data processing pipeline."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.steps: list[str] = []
        self.results: dict[str, Any] = {}

    def add_step(self, name: str) -> "DataPipeline":
        self.steps.append(name)
        return self

    def execute(self, data: list[dict]) -> dict[str, Any]:
        """Execute all pipeline steps."""
        for step in self.steps:
            data = self._run_step(step, data)
        self.results = {"processed": len(data), "steps": self.steps}
        return self.results

    def _run_step(self, step: str, data: list[dict]) -> list[dict]:
        handlers = {
            "validate": self._validate,
            "transform": self._transform,
            "filter": self._filter,
        }
        handler = handlers.get(step, lambda d: d)
        return handler(data)

    def _validate(self, data: list[dict]) -> list[dict]:
        return [d for d in data if d.get("id")]

    def _transform(self, data: list[dict]) -> list[dict]:
        return [{**d, "processed": True} for d in data]

    def _filter(self, data: list[dict]) -> list[dict]:
        return [d for d in data if d.get("active", True)]


async def async_process(data: list[dict]) -> dict[str, Any]:
    """Async data processing."""
    pipeline = DataPipeline({"async": True})
    pipeline.add_step("validate").add_step("transform").add_step("filter")
    return pipeline.execute(data)


def load_config(path: str) -> dict[str, Any]:
    """Load configuration from JSON file."""
    with open(path) as f:
        return json.load(f)
'''.strip()


@pytest.fixture
def test_project():
    """Create a temporary project with test files."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "Service.java").write_text(_JAVA_FILE)
        (root / "pipeline.py").write_text(_PYTHON_FILE)
        yield str(root)


class TestPerformanceRegression:
    """Performance regression tests with time budgets."""

    @pytest.mark.asyncio
    async def test_java_parse_within_budget(self, test_project: str) -> None:
        """Java file analysis should complete within budget."""
        tool = AnalyzeCodeStructureTool(project_root=test_project)
        java_file = str(Path(test_project) / "Service.java")

        t0 = time.perf_counter()
        result = await tool.execute({"file_path": java_file, "format_type": "compact"})
        elapsed = time.perf_counter() - t0

        assert result.get("success") is True or "success: true" in str(result)
        assert elapsed < BUDGET_SINGLE_FILE_PARSE_S, (
            f"Java parse took {elapsed:.3f}s (budget: {BUDGET_SINGLE_FILE_PARSE_S}s)"
        )

    @pytest.mark.asyncio
    async def test_python_parse_within_budget(self, test_project: str) -> None:
        """Python file analysis should complete within budget."""
        tool = AnalyzeCodeStructureTool(project_root=test_project)
        py_file = str(Path(test_project) / "pipeline.py")

        t0 = time.perf_counter()
        result = await tool.execute({"file_path": py_file, "format_type": "compact"})
        elapsed = time.perf_counter() - t0

        assert result.get("success") is True or "success: true" in str(result)
        assert elapsed < BUDGET_SINGLE_FILE_PARSE_S, (
            f"Python parse took {elapsed:.3f}s (budget: {BUDGET_SINGLE_FILE_PARSE_S}s)"
        )

    @pytest.mark.asyncio
    async def test_query_within_budget(self, test_project: str) -> None:
        """Query operation should complete within budget."""
        tool = QueryTool(project_root=test_project)
        py_file = str(Path(test_project) / "pipeline.py")

        t0 = time.perf_counter()
        result = await tool.execute({"file_path": py_file, "query_key": "functions"})
        elapsed = time.perf_counter() - t0

        assert result.get("success") is True
        assert elapsed < BUDGET_QUERY_S, (
            f"Query took {elapsed:.3f}s (budget: {BUDGET_QUERY_S}s)"
        )

    def test_error_recovery_within_budget(self, test_project: str) -> None:
        """Error recovery analysis should be fast."""
        recovery = ErrorRecovery(project_root=test_project)
        java_file = str(Path(test_project) / "Service.java")

        t0 = time.perf_counter()
        result = recovery.analyze_with_fallback(java_file)
        elapsed = time.perf_counter() - t0

        assert result.get("success") is True
        assert elapsed < BUDGET_SMALL_FILE_RECOVERY_S, (
            f"Recovery took {elapsed:.3f}s (budget: {BUDGET_SMALL_FILE_RECOVERY_S}s)"
        )

    def test_plugin_registry_load_within_budget(self) -> None:
        """Loading all plugins should complete within budget."""
        from tree_sitter_analyzer.plugins.registry import PluginRegistry

        t0 = time.perf_counter()
        registry = PluginRegistry()
        registry.discover()
        all_plugins = registry.load_all()
        elapsed = time.perf_counter() - t0

        assert len(all_plugins) >= 10, f"Only {len(all_plugins)} plugins loaded"
        assert elapsed < BUDGET_REGISTRY_LOAD_S, (
            f"Plugin loading took {elapsed:.3f}s (budget: {BUDGET_REGISTRY_LOAD_S}s)"
        )

    @pytest.mark.asyncio
    async def test_no_performance_degradation_between_calls(
        self, test_project: str
    ) -> None:
        """Repeated calls should not degrade in performance (no memory leak)."""
        tool = AnalyzeCodeStructureTool(project_root=test_project)
        py_file = str(Path(test_project) / "pipeline.py")

        timings: list[float] = []
        for _ in range(5):
            t0 = time.perf_counter()
            await tool.execute({"file_path": py_file, "format_type": "compact"})
            timings.append(time.perf_counter() - t0)

        # First call may be slower (warm-up). Subsequent calls should not degrade.
        avg_later = sum(timings[1:]) / len(timings[1:])
        assert avg_later < BUDGET_SINGLE_FILE_PARSE_S, (
            f"Avg time of calls 2-5: {avg_later:.3f}s (budget: {BUDGET_SINGLE_FILE_PARSE_S}s)"
        )

    @pytest.mark.asyncio
    async def test_print_performance_summary(self, test_project: str) -> None:
        """Print a human-readable performance summary."""
        tool = AnalyzeCodeStructureTool(project_root=test_project)
        query_tool = QueryTool(project_root=test_project)

        results: dict[str, float] = {}

        # Measure Java parse
        java_file = str(Path(test_project) / "Service.java")
        t0 = time.perf_counter()
        await tool.execute({"file_path": java_file})
        results["Java parse"] = time.perf_counter() - t0

        # Measure Python parse
        py_file = str(Path(test_project) / "pipeline.py")
        t0 = time.perf_counter()
        await tool.execute({"file_path": py_file})
        results["Python parse"] = time.perf_counter() - t0

        # Measure query
        t0 = time.perf_counter()
        await query_tool.execute({"file_path": py_file, "query_key": "functions"})
        results["Python query"] = time.perf_counter() - t0

        # Measure recovery
        recovery = ErrorRecovery(project_root=test_project)
        t0 = time.perf_counter()
        recovery.analyze_with_fallback(java_file)
        results["Error recovery"] = time.perf_counter() - t0

        print("\n=== Performance Regression Summary ===")
        print(f"{'Operation':>20} | {'Time (s)':>10} | {'Budget (s)':>10} | {'Status':>8}")
        print("-" * 55)
        budgets = {
            "Java parse": BUDGET_SINGLE_FILE_PARSE_S,
            "Python parse": BUDGET_SINGLE_FILE_PARSE_S,
            "Python query": BUDGET_QUERY_S,
            "Error recovery": BUDGET_SMALL_FILE_RECOVERY_S,
        }
        for op, t in results.items():
            budget = budgets.get(op, 1.0)
            status = "OK" if t < budget else "SLOW"
            print(f"{op:>20} | {t:>10.4f} | {budget:>10.1f} | {status:>8}")
