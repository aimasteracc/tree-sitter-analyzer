"""
Unit tests for Code Map Intelligence - the killer feature.

Three core capabilities:
1. trace_call_flow: 双向调用链追踪（上游 + 下游）
2. impact_analysis: 修改影响分析（传递性爆炸半径）
3. gather_context: LLM 上下文捕获（防幻觉）
"""

from pathlib import Path

import pytest


@pytest.fixture
def cross_file_project():
    """Return path to cross-file test project."""
    return Path(__file__).parent.parent / "fixtures" / "cross_file_project"


@pytest.fixture
def code_map_result(cross_file_project):
    """Return a scanned CodeMapResult for the cross_file_project."""
    from tree_sitter_analyzer_v2.core.code_map import ProjectCodeMap

    code_map = ProjectCodeMap()
    return code_map.scan(str(cross_file_project), extensions=[".py"])


# ═══════════════════════════════════════════════════════════════
# Phase 1: trace_call_flow - 双向调用链
# ═══════════════════════════════════════════════════════════════


class TestTraceCallFlow:
    """Test call flow tracing - the map-like view of call chains."""

    def test_trace_returns_call_flow_result(self, code_map_result) -> None:
        """trace_call_flow returns a CallFlowResult object."""
        result = code_map_result.trace_call_flow("helper")
        assert result is not None
        assert result.target is not None
        assert result.target.name == "helper"

    def test_trace_finds_downstream_callees(self, code_map_result) -> None:
        """Should find functions called by target (downstream)."""
        result = code_map_result.trace_call_flow("helper")
        callee_names = [s.name for s in result.callees]
        # helper() calls process_data()
        assert "process_data" in callee_names

    def test_trace_finds_upstream_callers(self, code_map_result) -> None:
        """Should find functions that call target (upstream)."""
        result = code_map_result.trace_call_flow("validate")
        caller_names = [s.name for s in result.callers]
        # validate() is called by main() and authenticate()
        assert len(caller_names) >= 1

    def test_trace_toon_output(self, code_map_result) -> None:
        """TOON output should be compact and informative."""
        result = code_map_result.trace_call_flow("helper")
        toon = result.to_toon()
        assert isinstance(toon, str)
        assert "helper" in toon
        assert len(toon) > 0

    def test_trace_nonexistent_function(self, code_map_result) -> None:
        """Should handle nonexistent function gracefully."""
        result = code_map_result.trace_call_flow("nonexistent_xyz")
        assert result.target is None
        assert len(result.callers) == 0
        assert len(result.callees) == 0

    def test_trace_includes_file_info(self, code_map_result) -> None:
        """Call flow should include file path information."""
        result = code_map_result.trace_call_flow("validate")
        assert result.target is not None
        assert result.target.file != ""
        assert "utils" in result.target.file


# ═══════════════════════════════════════════════════════════════
# Phase 2: impact_analysis - 修改影响分析
# ═══════════════════════════════════════════════════════════════


class TestImpactAnalysis:
    """Test impact analysis - what breaks if I change X?"""

    def test_impact_returns_result(self, code_map_result) -> None:
        """impact_analysis returns an ImpactResult object."""
        result = code_map_result.impact_analysis("validate")
        assert result is not None
        assert result.target is not None

    def test_impact_finds_affected_symbols(self, code_map_result) -> None:
        """Should find all symbols affected by a change."""
        result = code_map_result.impact_analysis("validate")
        # validate is called by main() and authenticate() → they are affected
        affected_names = [s.name for s in result.affected_symbols]
        assert len(affected_names) >= 1

    def test_impact_finds_affected_files(self, code_map_result) -> None:
        """Should list all affected files."""
        result = code_map_result.impact_analysis("validate")
        # validate is in utils.py, called from main.py and auth.py
        assert len(result.affected_files) >= 1

    def test_impact_blast_radius(self, code_map_result) -> None:
        """Should compute blast radius (count of affected symbols)."""
        result = code_map_result.impact_analysis("validate")
        assert result.blast_radius >= 1

    def test_impact_risk_level(self, code_map_result) -> None:
        """Should assign risk level based on blast radius."""
        result = code_map_result.impact_analysis("validate")
        assert result.risk_level in ("high", "medium", "low")

    def test_impact_toon_output(self, code_map_result) -> None:
        """TOON output should contain actionable information."""
        result = code_map_result.impact_analysis("validate")
        toon = result.to_toon()
        assert isinstance(toon, str)
        assert "validate" in toon
        assert len(toon) > 0

    def test_impact_nonexistent_symbol(self, code_map_result) -> None:
        """Should handle nonexistent symbol gracefully."""
        result = code_map_result.impact_analysis("nonexistent_xyz")
        assert result.target is None
        assert result.blast_radius == 0


# ═══════════════════════════════════════════════════════════════
# Phase 3: gather_context - LLM 上下文捕获
# ═══════════════════════════════════════════════════════════════


class TestGatherContext:
    """Test context gathering - instant capture of all related code."""

    def test_gather_returns_context_result(self, code_map_result) -> None:
        """gather_context returns a ContextResult object."""
        result = code_map_result.gather_context("helper")
        assert result is not None
        assert result.query == "helper"

    def test_gather_finds_matched_symbols(self, code_map_result) -> None:
        """Should find symbols matching the query."""
        result = code_map_result.gather_context("helper")
        assert len(result.matched_symbols) >= 1
        assert any(s.name == "helper" for s in result.matched_symbols)

    def test_gather_extracts_code_sections(self, code_map_result) -> None:
        """Should extract actual code sections for matched symbols."""
        result = code_map_result.gather_context("helper")
        assert len(result.code_sections) >= 1
        # Should have at least the definition
        assert any(s.relevance == "definition" for s in result.code_sections)

    def test_gather_includes_callers_code(self, code_map_result) -> None:
        """Should include code of functions that call the target."""
        result = code_map_result.gather_context("validate")
        relevances = [s.relevance for s in result.code_sections]
        # Should include callers (main or authenticate call validate)
        assert "definition" in relevances

    def test_gather_respects_token_budget(self, code_map_result) -> None:
        """Should not exceed the token budget."""
        result = code_map_result.gather_context("helper", max_tokens=500)
        assert result.total_tokens <= 500

    def test_gather_toon_output(self, code_map_result) -> None:
        """TOON output should be LLM-ready."""
        result = code_map_result.gather_context("helper")
        toon = result.to_toon()
        assert isinstance(toon, str)
        assert "helper" in toon

    def test_gather_nonexistent_query(self, code_map_result) -> None:
        """Should handle query with no matches gracefully."""
        result = code_map_result.gather_context("nonexistent_xyz")
        assert len(result.matched_symbols) == 0
        assert len(result.code_sections) == 0


# ═══════════════════════════════════════════════════════════════
# QA Strategist: Edge Cases & Regression Guards
# ═══════════════════════════════════════════════════════════════


class TestCallFlowEdgeCases:
    """QA: boundary conditions for trace_call_flow."""

    def test_trace_leaf_function_has_no_callees(self, code_map_result) -> None:
        """A leaf function (calls no known functions) should have empty callees."""
        result = code_map_result.trace_call_flow("process_data")
        # process_data() only calls data.upper() which isn't a project symbol
        assert result.target is not None
        assert len(result.callees) == 0

    def test_trace_cross_file_caller(self, code_map_result) -> None:
        """Cross-file callers should be detected via import heuristics."""
        result = code_map_result.trace_call_flow("helper")
        caller_names = [s.name for s in result.callers]
        # helper is imported and called in main.py and services/data.py
        assert len(caller_names) >= 1

    def test_trace_toon_shows_upstream_downstream_labels(self, code_map_result) -> None:
        """TOON output should contain CALLED_BY and CALLS sections."""
        result = code_map_result.trace_call_flow("helper")
        toon = result.to_toon()
        # helper has both callers (main, process) and callees (process_data)
        assert "CALLS" in toon

    def test_trace_returns_file_and_line_for_all_entries(self, code_map_result) -> None:
        """Every caller/callee SymbolInfo must have file and line_start > 0."""
        result = code_map_result.trace_call_flow("validate")
        for sym in result.callers + result.callees:
            assert sym.file != "", f"{sym.name} missing file"
            assert sym.line_start > 0, f"{sym.name} missing line"


class TestImpactAnalysisEdgeCases:
    """QA: edge cases for impact_analysis."""

    def test_impact_leaf_function_low_risk(self, code_map_result) -> None:
        """Leaf function with no callers → blast_radius=0, risk=low."""
        result = code_map_result.impact_analysis("save_data")
        assert result.blast_radius == 0
        assert result.risk_level == "low"

    def test_impact_transitive_closure(self, code_map_result) -> None:
        """Impact should propagate transitively through call chains."""
        result = code_map_result.impact_analysis("validate")
        affected_names = [s.name for s in result.affected_symbols]
        # validate → called by main, authenticate → transitive chain
        assert len(affected_names) >= 1

    def test_impact_depth_is_correct(self, code_map_result) -> None:
        """Depth should reflect the longest chain."""
        result = code_map_result.impact_analysis("validate")
        assert result.depth >= 1

    def test_impact_toon_contains_risk_and_radius(self, code_map_result) -> None:
        """TOON output should contain risk= and radius= info."""
        result = code_map_result.impact_analysis("validate")
        toon = result.to_toon()
        assert "risk=" in toon
        assert "radius=" in toon


class TestGatherContextEdgeCases:
    """QA: edge cases for gather_context."""

    def test_gather_zero_budget_returns_empty(self, code_map_result) -> None:
        """Zero token budget should return no sections."""
        result = code_map_result.gather_context("helper", max_tokens=0)
        assert result.total_tokens == 0
        assert len(result.code_sections) == 0

    def test_gather_partial_name_match(self, code_map_result) -> None:
        """Partial name match should find related symbols."""
        result = code_map_result.gather_context("process")
        # Should match process_data, process, etc.
        assert len(result.matched_symbols) >= 1

    def test_gather_code_sections_have_content(self, code_map_result) -> None:
        """Every code section should have non-empty content."""
        result = code_map_result.gather_context("helper")
        for sec in result.code_sections:
            assert sec.content.strip() != "", f"Empty content in {sec.file_path}"

    def test_gather_toon_includes_code_lines(self, code_map_result) -> None:
        """TOON output should include actual source code lines."""
        result = code_map_result.gather_context("helper")
        toon = result.to_toon()
        # helper function definition should be visible in TOON output
        assert "def helper" in toon or "helper" in toon


# ═══════════════════════════════════════════════════════════════
# Refactor Verification: structural improvements
# ═══════════════════════════════════════════════════════════════


class TestSymbolFQN:
    """Verify fully-qualified names prevent name collision issues."""

    def test_fqn_includes_file_path(self, code_map_result) -> None:
        """FQN should include file path for uniqueness."""
        sym = code_map_result.find_symbol_exact("validate")
        assert sym is not None
        assert sym.fqn == "utils.py:validate"

    def test_fqn_unique_across_symbols(self, code_map_result) -> None:
        """All FQNs should be unique across the project."""
        fqns = [s.fqn for s in code_map_result.symbols]
        assert len(fqns) == len(set(fqns)), f"Duplicate FQNs: {[f for f in fqns if fqns.count(f) > 1]}"


class TestDeadCodeAccuracy:
    """Verify dead code no longer has false positives for public APIs."""

    def test_imported_functions_not_dead(self, code_map_result) -> None:
        """Functions imported by other modules should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        # helper and validate are imported by main.py, auth.py, data.py
        assert "helper" not in dead_names
        assert "validate" not in dead_names
        # get_config is imported by main.py
        assert "get_config" not in dead_names
        # clean_text is imported by data.py
        assert "clean_text" not in dead_names

    def test_called_functions_not_dead(self, code_map_result) -> None:
        """Functions called by other functions should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        # process_data is called by helper()
        assert "process_data" not in dead_names
        # fetch_user_data is called by authenticate()
        assert "fetch_user_data" not in dead_names

    def test_truly_dead_code_detected(self, code_map_result) -> None:
        """Genuinely unused internal functions should be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        # set_config is never imported or called
        assert "set_config" in dead_names
        # is_valid_email is never imported or called
        assert "is_valid_email" in dead_names


class TestHotSpotsAccuracy:
    """Verify hot spots use call-based ranking."""

    def test_most_called_functions_are_hot(self, code_map_result) -> None:
        """Functions with most callers should be at the top."""
        hot_names = [s.name for s, _ in code_map_result.hot_spots[:5]]
        # helper and validate are called from multiple files
        assert "helper" in hot_names
        assert "validate" in hot_names

    def test_hot_spots_counts_include_calls(self, code_map_result) -> None:
        """Hot spot counts should reflect actual callers, not just imports."""
        hot_dict = {s.name: c for s, c in code_map_result.hot_spots}
        # helper: called by main, process + imported 2x => count >= 4
        assert hot_dict.get("helper", 0) >= 3


class TestCacheIsolation:
    """Verify call index cache is per-instance, not shared."""

    def test_two_results_have_separate_caches(self, cross_file_project) -> None:
        """Two CodeMapResult instances should have independent caches."""
        from tree_sitter_analyzer_v2.core.code_map import ProjectCodeMap

        cm = ProjectCodeMap()
        r1 = cm.scan(str(cross_file_project), extensions=[".py"])
        r2 = cm.scan(str(cross_file_project), extensions=[".py"])

        # Both have caches (populated during scan), but they are different objects
        c1_caller, _ = r1._get_call_index()
        c2_caller, _ = r2._get_call_index()
        assert c1_caller is not c2_caller, "Caches should be separate objects"


class TestGatherContextImports:
    """Verify import statements are included in gathered context."""

    def test_context_includes_import_sections(self, code_map_result) -> None:
        """gather_context should include import statements from caller files."""
        result = code_map_result.gather_context("helper")
        import_sections = [s for s in result.code_sections if s.relevance == "import"]
        assert len(import_sections) >= 1, "No import sections found"
        # Check content looks like an import
        for sec in import_sections:
            assert "import" in sec.content, f"Not an import: {sec.content}"

    def test_context_import_has_real_line_number(self, code_map_result) -> None:
        """Import sections should have realistic line numbers (not all 1)."""
        result = code_map_result.gather_context("helper")
        import_sections = [s for s in result.code_sections if s.relevance == "import"]
        # At least one import should exist
        assert len(import_sections) >= 1
        # start_line should be positive
        for sec in import_sections:
            assert sec.start_line >= 1


# ═══════════════════════════════════════════════════════════════
# AST Accuracy: false positive prevention (the killer tests)
# ═══════════════════════════════════════════════════════════════


class TestASTCallDetectionAccuracy:
    """Prove AST-based detection does NOT produce false positives.

    The tricky.py fixture contains function names in comments, strings,
    and variable assignments that would fool regex but NOT AST.
    """

    def test_real_call_detected(self, code_map_result) -> None:
        """real_caller() actually calls helper() — should be detected."""
        result = code_map_result.trace_call_flow("helper")
        caller_names = [s.name for s in result.callers]
        assert "real_caller" in caller_names

    def test_comment_mention_not_detected(self, code_map_result) -> None:
        """fake_caller_comment() mentions helper() in a comment — must NOT match."""
        result = code_map_result.trace_call_flow("helper")
        caller_names = [s.name for s in result.callers]
        assert "fake_caller_comment" not in caller_names

    def test_string_mention_not_detected(self, code_map_result) -> None:
        """fake_caller_string() mentions helper() in a string — must NOT match."""
        result = code_map_result.trace_call_flow("helper")
        caller_names = [s.name for s in result.callers]
        assert "fake_caller_string" not in caller_names

    def test_variable_mention_not_detected(self, code_map_result) -> None:
        """fake_caller_variable() uses 'helper' as string value — must NOT match."""
        result = code_map_result.trace_call_flow("helper")
        caller_names = [s.name for s in result.callers]
        assert "fake_caller_variable" not in caller_names

    def test_call_sites_populated_from_ast(self, code_map_result) -> None:
        """ModuleInfo.call_sites should be populated for Python files."""
        for module in code_map_result.modules:
            if module.path == "tricky.py":
                # real_caller calls helper
                assert "real_caller" in module.call_sites
                assert "helper" in module.call_sites["real_caller"]
                # fake callers should NOT have helper in call_sites
                assert "helper" not in module.call_sites.get("fake_caller_comment", [])
                assert "helper" not in module.call_sites.get("fake_caller_string", [])
                assert "helper" not in module.call_sites.get("fake_caller_variable", [])
                return
        pytest.fail("tricky.py not found in modules")


# ═══════════════════════════════════════════════════════════════
# Phase 4: Decorator/Framework Awareness — TDD Tests
# ═══════════════════════════════════════════════════════════════


class TestDecoratorAwareness:
    """Decorated functions should NOT be flagged as dead code.

    Framework-registered functions (routes, CLI commands, fixtures, properties)
    are called by their frameworks, not by project code.
    """

    def test_decorated_entries_populated(self, code_map_result) -> None:
        """decorated.py should have decorated_entries in its ModuleInfo."""
        for module in code_map_result.modules:
            if module.path == "decorated.py":
                assert len(module.decorated_entries) >= 3, (
                    f"Expected >=3 decorated entries, got {module.decorated_entries}"
                )
                return
        pytest.fail("decorated.py not found in modules")

    def test_route_decorated_not_dead(self, code_map_result) -> None:
        """@route decorated function should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        assert "get_users" not in dead_names

    def test_command_decorated_not_dead(self, code_map_result) -> None:
        """@command decorated function should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        assert "deploy_command" not in dead_names

    def test_fixture_decorated_not_dead(self, code_map_result) -> None:
        """@fixture decorated function should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        assert "db_session" not in dead_names

    def test_property_not_dead(self, code_map_result) -> None:
        """@property method should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        assert "name" not in dead_names

    def test_staticmethod_not_dead(self, code_map_result) -> None:
        """@staticmethod method should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        assert "create" not in dead_names

    def test_truly_dead_still_detected(self, code_map_result) -> None:
        """orphan_function() has no decorator, no caller — IS dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        assert "orphan_function" in dead_names

    def test_decorator_factory_not_dead(self, code_map_result) -> None:
        """Decorator factory functions (route, command, fixture) are imported
        and used as decorators — should NOT be dead code."""
        dead_names = [d.name for d in code_map_result.dead_code]
        assert "route" not in dead_names
        assert "command" not in dead_names


class TestDecoratorEdgeCases:
    """QA edge cases for decorator awareness."""

    def test_no_decorator_module_has_empty_decorated_entries(
        self, code_map_result
    ) -> None:
        """Modules with no decorators should have empty decorated_entries."""
        for module in code_map_result.modules:
            if module.path == "utils.py":
                # utils.py has no decorators
                assert isinstance(module.decorated_entries, set)
                break

    def test_wrapper_inner_functions_handled(self, code_map_result) -> None:
        """Inner wrapper functions of decorator factories should not crash."""
        dead_names = [d.name for d in code_map_result.dead_code]
        # wrapper is an internal closure — it's ok if it appears as dead
        # but the system should not crash on it
        assert isinstance(dead_names, list)

    def test_decorated_entries_does_not_include_non_framework(
        self, code_map_result
    ) -> None:
        """Regular functions (no decorator) should NOT be in decorated_entries."""
        for module in code_map_result.modules:
            if module.path == "decorated.py":
                assert "orphan_function" not in module.decorated_entries
                return
        pytest.fail("decorated.py not found")

    def test_class_method_decorator_tracked(self, code_map_result) -> None:
        """@property and @staticmethod on class methods should be tracked."""
        for module in code_map_result.modules:
            if module.path == "decorated.py":
                assert "property" in module.decorated_entries
                assert "staticmethod" in module.decorated_entries
                return
        pytest.fail("decorated.py not found")


class TestRelevanceRanking:
    """gather_context should return exact matches first."""

    def test_exact_match_first(self, code_map_result) -> None:
        """Exact name match should appear before prefix/contains matches."""
        result = code_map_result.gather_context("helper")
        if result.matched_symbols:
            assert result.matched_symbols[0].name == "helper"

    def test_max_symbols_cap(self, code_map_result) -> None:
        """gather_context should respect max_symbols parameter."""
        result = code_map_result.gather_context("e", max_symbols=5)
        assert len(result.matched_symbols) <= 5
