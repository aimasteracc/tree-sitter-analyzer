"""Dead-code answers must carry counted evidence (#1958).

``health action=dead`` (CLI ``--dead-code``) answered "No dead code found in
scope." when 0 functions were analyzed: an empty root, a ``path`` that matches
nothing, a scope holding only test files, or a project without an index (the
callers evidence cannot certify any candidate). An agent read that as proof.
The same contract as ``--unreachable-code`` (#1955) now applies: an answer
without evidence is ``unknown`` / ``INSUFFICIENT_EVIDENCE`` with the exact CLI
and MCP command per cause, and an answer with evidence names its counts.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

import tree_sitter_analyzer.mcp.tools.dead_code_tool as dead_mod
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.dead_code_analyzer import (
    DeadCodeResult,
    DeadFunction,
    analyze_dead_code,
)
from tree_sitter_analyzer.mcp.tools import dead_code_certify
from tree_sitter_analyzer.mcp.tools.codegraph_overview_tool import (
    CodeGraphOverviewTool,
)
from tree_sitter_analyzer.mcp.tools.dead_code_answer import (
    INSUFFICIENT_EVIDENCE,
    CertCounts,
    insufficient_evidence,
    overview_dead_answer,
    scope_evidence,
)
from tree_sitter_analyzer.mcp.tools.dead_code_tool import CodeGraphDeadCodeTool
from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

_LIB = """\
    def used():
        return 1

    def orphan():
        return 2

    def main():
        return used()
"""

_TESTS = """\
    def helper():
        return 1

    def test_one():
        assert helper() == 1
"""


def _write(root: Path, rel: str, code: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


async def _dead(root: Path, **extra: Any) -> dict[str, Any]:
    tool = CodeGraphDeadCodeTool(project_root=str(root))
    return await tool.execute({"mode": "dead_functions", **extra})


def _assert_unknown(resp: dict[str, Any], cause: str) -> None:
    assert resp["success"] is False
    assert resp["status"] == "unknown"
    assert resp["error_code"] == INSUFFICIENT_EVIDENCE
    assert resp["insufficient_evidence_reason"] == cause
    assert "No dead code found" not in resp["next_step"]


class TestAnalyzerCountsFunctions:
    def test_function_files_and_index_flag(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", _LIB)
        _write(tmp_path, "tests/test_a.py", _TESTS)

        result = analyze_dead_code(
            str(tmp_path), include_unused_imports=False, include_variables=False
        )

        files = {k.replace("\\", "/"): v for k, v in result.function_files.items()}
        assert files == {"pkg/a.py": 3, "tests/test_a.py": 2}
        assert result.indexed is False


class TestScopeEvidence:
    _FILES = {"pkg/a.py": 3, "pkg/sub/b.py": 2, "tests/test_a.py": 4, "c.py": 1}

    def test_whole_project_skips_test_files(self) -> None:
        ev = scope_evidence(self._FILES, path=None, include_tests=False, indexed=True)

        assert ev.project_functions == 10
        assert ev.functions_in_scope == 6
        assert ev.files_in_scope == 3
        assert ev.test_functions_in_scope == 4

    def test_include_tests_counts_them(self) -> None:
        ev = scope_evidence(self._FILES, path=None, include_tests=True, indexed=True)

        assert ev.functions_in_scope == 10
        assert ev.test_functions_in_scope == 0

    def test_path_scope_and_prefixes(self) -> None:
        ev = scope_evidence(self._FILES, path="pkg", include_tests=False, indexed=True)

        assert ev.functions_in_scope == 5
        assert ev.files_in_scope == 2
        # One level below the scope, so a budget hint can name a narrower path.
        assert ev.prefixes == (("pkg/a.py", 3), ("pkg/sub", 2))

    def test_to_stats(self) -> None:
        ev = scope_evidence(self._FILES, path="pkg", include_tests=False, indexed=False)

        assert ev.to_stats() == {
            "functions_in_scope": 5,
            "files_in_scope": 2,
            "test_functions_in_scope": 0,
            "index_used": False,
        }


class TestInsufficientEvidence:
    def _ev(self, files: dict[str, int], **kw: Any) -> Any:
        kw.setdefault("path", None)
        kw.setdefault("include_tests", False)
        kw.setdefault("indexed", True)
        return scope_evidence(files, **kw)

    def test_known_answer_is_none(self) -> None:
        ev = self._ev({"a.py": 2})

        assert insufficient_evidence(ev, CertCounts(1, 1, 0), "/r") is None
        assert insufficient_evidence(ev, CertCounts(0, 0, 0), "/r") is None
        # Every candidate asked and none certified: possibly_dead carries why.
        assert insufficient_evidence(ev, CertCounts(3, 0, 0), "/r") is None

    def test_no_functions_overview_names_overview_command(self) -> None:
        cause, step = insufficient_evidence(
            self._ev({}), CertCounts(0, 0, 0), "/r", surface="overview"
        )

        assert cause == "NO_FUNCTIONS"
        assert '--codegraph-overview --project-root "<source dir>"' in step
        assert "health action=overview" in step

    def test_budget_names_a_narrower_path(self) -> None:
        cause, step = insufficient_evidence(
            self._ev({"pkg/a.py": 4, "lib/b.py": 1}), CertCounts(5, 0, 5), "/r"
        )

        assert cause == "CERTIFICATION_BUDGET"
        assert '--dead-code-path "pkg"' in step
        assert 'health action=dead path="pkg"' in step

    def test_no_index_overview_reruns_overview(self) -> None:
        cause, step = insufficient_evidence(
            self._ev({"a.py": 2}, indexed=False),
            CertCounts(2, 0, 0),
            "/r",
            surface="overview",
        )

        assert cause == "NO_INDEX"
        assert '--full-index --project-root "/r"' in step
        assert "health action=overview" in step

    def test_overview_answer_names_certified_count(self) -> None:
        ev = self._ev({"a.py": 4, "b.py": 1})

        status, step, cause = overview_dead_answer(
            ev, CertCounts(3, 2, 0), "/r", "certified"
        )

        assert (status, cause) == ("certified", None)
        assert step == "2 certified dead of 5 function(s) in 2 file(s) analyzed."

    def test_empty_scope_with_only_test_prefixes(self) -> None:
        cause, step = insufficient_evidence(
            self._ev({"tests/test_a.py": 2}, path="nope"), CertCounts(0, 0, 0), "/r"
        )

        assert cause == "EMPTY_SCOPE"
        assert "--dead-code-include-tests" in step


class TestDeadToolUnknown:
    @pytest.mark.asyncio
    async def test_empty_root(self, tmp_path: Path) -> None:
        resp = await _dead(tmp_path)

        _assert_unknown(resp, "NO_FUNCTIONS")
        assert '--dead-code --project-root "<source dir>"' in resp["next_step"]
        assert "set_project_path" in resp["next_step"]
        assert resp["stats"]["functions_in_scope"] == 0

    @pytest.mark.asyncio
    async def test_path_matches_nothing(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", _LIB)

        resp = await _dead(tmp_path, path="nonexistent")

        _assert_unknown(resp, "EMPTY_SCOPE")
        assert '--dead-code-path "pkg"' in resp["next_step"]
        assert 'health action=dead path="pkg"' in resp["next_step"]

    @pytest.mark.asyncio
    async def test_tests_only_scope(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", _LIB)
        _write(tmp_path, "tests/test_a.py", _TESTS)

        resp = await _dead(tmp_path, path="tests")

        _assert_unknown(resp, "TESTS_ONLY")
        step = resp["next_step"]
        assert '--dead-code-include-tests --dead-code-path "tests"' in step
        assert 'include_test_files=true path="tests"' in step
        assert resp["stats"]["test_functions_in_scope"] == 2

    @pytest.mark.asyncio
    async def test_tests_only_project(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_a.py", _TESTS)

        resp = await _dead(tmp_path)

        _assert_unknown(resp, "TESTS_ONLY")
        assert "--dead-code-path" not in resp["next_step"]

    @pytest.mark.asyncio
    async def test_no_index(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", _LIB)

        resp = await _dead(tmp_path)

        _assert_unknown(resp, "NO_INDEX")
        step = resp["next_step"]
        assert f'--full-index --project-root "{tmp_path}"' in step
        assert "index action=full" in step
        assert resp["stats"]["index_used"] is False

    @pytest.mark.asyncio
    async def test_health_facade_empty_root(self, tmp_path: Path) -> None:
        facade = build_health_facade(str(tmp_path))

        resp = await facade.execute({"action": "dead"})

        assert resp["success"] is False
        assert resp["error_code"] == INSUFFICIENT_EVIDENCE
        assert "health action=dead" in resp["next_step"]


def _ref(name: str, file: str = "pkg/a.py") -> FunctionRef:
    return FunctionRef(
        file_path=file, name=name, start_line=1, end_line=2, language="python"
    )


def _fake(dead: list[str], **kw: Any) -> DeadCodeResult:
    return DeadCodeResult(
        dead_functions=[
            DeadFunction(function=_ref(n), reason="orphan_no_callers_no_callees")
            for n in dead
        ],
        unused_imports=[],
        unreferenced_variables=[],
        stats={"total_functions": 7, "total_call_edges": 3},
        function_files={"pkg/a.py": 5, "pkg/b.py": 2},
        indexed=kw.get("indexed", True),
    )


def _patch(monkeypatch: pytest.MonkeyPatch, result: DeadCodeResult, cert: Any) -> None:
    monkeypatch.setattr(dead_mod, "analyze_dead_code", lambda *a, **k: result)

    async def fake_certify(_root: str, funcs: Any, **_kw: Any) -> Any:
        return cert(list(funcs))

    monkeypatch.setattr(dead_code_certify, "certify", fake_certify)


def _all_certified(funcs: list[FunctionRef]) -> Any:
    return dead_code_certify.Certification(
        verdicts={f: dead_code_certify.Verdict(True) for f in funcs}
    )


class TestDeadToolWithEvidence:
    @pytest.mark.asyncio
    async def test_none_found_names_counts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch, _fake([]), _all_certified)

        resp = await _dead(tmp_path)

        assert resp["success"] is True
        assert resp["status"] == "none_found"
        assert "7 function(s) in 2 file(s)" in resp["next_step"]
        assert resp["stats"]["functions_in_scope"] == 7
        assert resp["stats"]["files_in_scope"] == 2

    @pytest.mark.asyncio
    async def test_found_names_counts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch, _fake(["gone"]), _all_certified)

        resp = await _dead(tmp_path)

        assert resp["success"] is True
        assert resp["status"] == "dead_code_found"
        assert "of 7 function(s) in 2 file(s)" in resp["next_step"]

    @pytest.mark.asyncio
    async def test_budget_exhausted_is_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(
            monkeypatch,
            _fake(["a", "b"]),
            lambda funcs: dead_code_certify.Certification(unchecked=funcs),
        )

        resp = await _dead(tmp_path)

        _assert_unknown(resp, "CERTIFICATION_BUDGET")
        assert '--dead-code-path "pkg"' in resp["next_step"]

    @pytest.mark.asyncio
    async def test_imports_mode_keeps_plain_answer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch, _fake([]), _all_certified)

        resp = await _dead(tmp_path, mode="unused_imports")

        assert resp["success"] is True
        assert resp["status"] == "none_found"
        assert "No unused imports or unreferenced variables" in resp["next_step"]


class TestIndexedProject:
    @pytest.mark.asyncio
    async def test_indexed_answer_has_counts(self, tmp_path: Path) -> None:
        from tests.unit._index_refresh_support import _refresh_index

        _write(tmp_path, "pkg/a.py", _LIB)
        await _refresh_index(tmp_path)

        resp = await _dead(tmp_path)

        assert resp["success"] is True
        assert resp["status"] in ("dead_code_found", "none_found")
        assert resp["stats"]["index_used"] is True
        assert resp["stats"]["functions_in_scope"] == 3
        assert "3 function(s) in 1 file(s)" in resp["next_step"]


class TestOverview:
    @pytest.mark.asyncio
    async def test_empty_root_is_unknown(self, tmp_path: Path) -> None:
        resp = await CodeGraphOverviewTool(str(tmp_path)).execute({})

        _assert_unknown(resp, "NO_FUNCTIONS")
        assert "--codegraph-overview" in resp["next_step"]
        assert resp["dead_code_status"] == "unknown"

    @pytest.mark.asyncio
    async def test_no_index_dead_section_is_unknown(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", _LIB)

        resp = await CodeGraphOverviewTool(str(tmp_path)).execute({})

        assert resp["success"] is True  # entry points / hubs still hold
        assert resp["dead_code_status"] == "unknown"
        assert resp["dead_code_evidence"]["insufficient_evidence_reason"] == "NO_INDEX"
        assert "--full-index" in resp["dead_code_next_step"]
        assert "--full-index" in resp["agent_summary"]["next_step"]

    @pytest.mark.asyncio
    async def test_tests_only_dead_section_is_unknown(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_a.py", _TESTS)

        resp = await CodeGraphOverviewTool(str(tmp_path)).execute({})

        assert resp["dead_code_status"] == "unknown"
        assert "--dead-code-include-tests" in resp["dead_code_next_step"]

    @pytest.mark.asyncio
    async def test_evidence_counts_reported(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", "def main():\n    return 1\n")

        resp = await CodeGraphOverviewTool(str(tmp_path)).execute({})

        evidence = resp["dead_code_evidence"]
        assert resp["dead_code_status"] == "certified"
        assert evidence["functions_analyzed"] == 1
        assert evidence["files_analyzed"] == 1
        assert "1 function(s) in 1 file(s)" in resp["dead_code_next_step"]
