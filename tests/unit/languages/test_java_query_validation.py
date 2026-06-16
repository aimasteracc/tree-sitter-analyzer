"""
TDD tests for Java query_code correctness.

Two categories:
  A. Existing queries broken by #match? predicate not being applied (tree-sitter 0.25+)
  B. Missing query types needed for Spring/JUnit/Java16+ codebases

Validated against:
  - spring-petclinic (Spring MVC + JPA)
  - spring-framework (spring-context, spring-tx)
  - caffeine (concurrency, volatile fields)

All tests in group A must FAIL before the predicate fix, then PASS after.
All tests in group B must FAIL before new queries are added, then PASS after.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

PETCLINIC_BASE = Path("/workspaces/claude-source-run-version/spring-petclinic")
SPRING_BASE = Path("/workspaces/claude-source-run-version/spring-framework")
CAFFEINE_BASE = Path("/workspaces/claude-source-run-version/caffeine")

OWNER_CONTROLLER = (
    PETCLINIC_BASE
    / "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"
)
VET = (
    PETCLINIC_BASE / "src/main/java/org/springframework/samples/petclinic/vet/Vet.java"
)
OWNER = (
    PETCLINIC_BASE
    / "src/main/java/org/springframework/samples/petclinic/owner/Owner.java"
)
PROXY_CACHING = (
    SPRING_BASE
    / "spring-context/src/main/java/org/springframework/cache/annotation/ProxyCachingConfiguration.java"
)
BOUNDED_LOCAL_CACHE = (
    CAFFEINE_BASE
    / "caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java"
)

pytestmark_petclinic = pytest.mark.skipif(
    not PETCLINIC_BASE.exists(), reason="spring-petclinic not cloned"
)
pytestmark_spring = pytest.mark.skipif(
    not SPRING_BASE.exists(), reason="spring-framework not cloned"
)
pytestmark_caffeine = pytest.mark.skipif(
    not CAFFEINE_BASE.exists(), reason="caffeine not cloned"
)


@pytest.fixture(scope="module")
def petclinic_server():
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

    return TreeSitterAnalyzerMCPServer(str(PETCLINIC_BASE))


@pytest.fixture(scope="module")
def spring_server():
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

    return TreeSitterAnalyzerMCPServer(str(SPRING_BASE))


@pytest.fixture(scope="module")
def caffeine_server():
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

    return TreeSitterAnalyzerMCPServer(str(CAFFEINE_BASE))


def run(coro):
    # ``asyncio.get_event_loop()`` is deprecated and raises on Python 3.14+
    # when there's no running loop. ``asyncio.run`` provides a fresh loop.
    return asyncio.run(coro)


def query(server, file_path, query_key):
    # Default response format is TOON which strips the ``results`` bulk-data
    # field; the helper asserts on the list directly, so request JSON here.
    r = run(
        server.query_tool.execute(
            {
                "file_path": str(file_path),
                "query_key": query_key,
                "output_format": "json",
            }
        )
    )
    return r.get("results", [])


# ── Group A: #match? predicate fix (broken in tree-sitter 0.25) ──────────────


@pytest.mark.skipif(not PETCLINIC_BASE.exists(), reason="spring-petclinic not cloned")
class TestMatchPredicateFix:
    """These queries use #match? — all return 0 before fix, correct count after."""

    def test_spring_controller_finds_owner_controller(self, petclinic_server):
        """spring_controller must find @Controller annotated OwnerController."""
        results = query(petclinic_server, OWNER_CONTROLLER, "spring_controller")
        # 1 @Controller match x 3 captures (spring_controller, annotation_name,
        # controller_name) — measured on upstream HEAD 2026-06-13.
        assert len(results) == 3, (
            f"spring_controller query must find OwnerController (@Controller). "
            f"Got {len(results)} results. "
            "Bug: #match? predicate not applied in tree-sitter 0.25 QueryCursor."
        )
        names = [r.get("content", "") for r in results]
        assert any("OwnerController" in n for n in names), (
            f"Expected OwnerController in results, got: {names[:3]}"
        )

    def test_jpa_entity_finds_vet(self, petclinic_server):
        """jpa_entity must find @Entity annotated Vet class."""
        results = query(petclinic_server, VET, "jpa_entity")
        # 1 @Entity match x 3 captures (jpa_entity, annotation_name,
        # entity_name) — measured on upstream HEAD 2026-06-13.
        assert len(results) == 3, (
            f"jpa_entity query must find Vet (@Entity). Got {len(results)} results. "
            "Bug: #match? predicate silently returns 0."
        )

    def test_jpa_entity_finds_owner(self, petclinic_server):
        """jpa_entity must find @Entity annotated Owner class."""
        results = query(petclinic_server, OWNER, "jpa_entity")
        # 1 @Entity match x 3 captures — measured on upstream HEAD 2026-06-13.
        assert len(results) == 3, (
            f"jpa_entity query must find Owner (@Entity). Got {len(results)} results."
        )

    def test_spring_service_not_in_controller(self, petclinic_server):
        """spring_service must NOT find @Service in OwnerController (it's @Controller)."""
        results = query(petclinic_server, OWNER_CONTROLLER, "spring_service")
        assert len(results) == 0, (
            f"spring_service must return 0 for @Controller class. Got: {len(results)}. "
            "If >0 after predicate fix, the filter is wrong."
        )

    def test_spring_controller_count_all_petclinic_controllers(self, petclinic_server):
        """spring_controller finds exactly 1 controller class in OwnerController.java."""
        results = query(petclinic_server, OWNER_CONTROLLER, "spring_controller")
        # Each match returns multiple captures (spring_controller, annotation_name,
        # controller_name). Count only the top-level class captures.
        class_captures = [
            r for r in results if r.get("capture_name") == "spring_controller"
        ]
        assert len(class_captures) == 1, (
            f"OwnerController.java has exactly 1 @Controller class. "
            f"Got {len(class_captures)} class captures (total results: {len(results)})"
        )


# ── Group B: New query types ──────────────────────────────────────────────────


@pytest.mark.skipif(not SPRING_BASE.exists(), reason="spring-framework not cloned")
class TestSpringBeanQuery:
    """spring_bean query: @Bean annotated methods in @Configuration classes."""

    def test_spring_bean_finds_cache_advisor(self, spring_server):
        """spring_bean must find @Bean methods in ProxyCachingConfiguration."""
        results = query(spring_server, PROXY_CACHING, "spring_bean")
        # 3 @Bean matches x 3 captures (spring_bean, annotation_name,
        # method_name) — measured on upstream HEAD 2026-06-13.
        assert len(results) == 9, (
            f"ProxyCachingConfiguration has 3 @Bean methods (cacheAdvisor, "
            f"cacheOperationSource, cacheInterceptor). Got {len(results)}. "
            "Query 'spring_bean' not yet implemented."
        )
        bean_captures = [r for r in results if r.get("capture_name") == "spring_bean"]
        assert len(bean_captures) == 3, (
            f"Expected exactly 3 @Bean methods, got {len(bean_captures)}: "
            f"{[r.get('content', '')[:40] for r in bean_captures]}"
        )

    def test_spring_configuration_finds_proxy_caching(self, spring_server):
        """spring_configuration must find @Configuration classes."""
        results = query(spring_server, PROXY_CACHING, "spring_configuration")
        # 1 @Configuration match x 3 captures (spring_configuration,
        # annotation_name, class_name) — measured on upstream HEAD 2026-06-13.
        assert len(results) == 3, (
            f"ProxyCachingConfiguration is @Configuration. Got {len(results)}. "
            "Query 'spring_configuration' not yet implemented."
        )

    def test_spring_transactional_finds_transactional_methods(self, spring_server):
        """spring_transactional query must find @Transactional annotated methods."""
        # spring-tx has many @Transactional examples
        tx_file = (
            SPRING_BASE
            / "spring-tx/src/main/java/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.java"
        )
        if not tx_file.exists():
            pytest.skip("Transaction file not found")
        results = query(spring_server, tx_file, "spring_transactional")
        # The `>= 0` form was a tautology. The file declares no @Transactional
        # methods (it *parses* the annotation) — measured 0 matches on
        # upstream HEAD 2026-06-13; the query must not error.
        assert len(results) == 0, (
            f"AnnotationTransactionAttributeSource has no @Transactional "
            f"methods. Got {len(results)} results."
        )


@pytest.mark.skipif(not PETCLINIC_BASE.exists(), reason="spring-petclinic not cloned")
class TestJUnit5Queries:
    """junit5_test and related testing queries."""

    def test_junit5_test_finds_test_methods(self, petclinic_server):
        """junit5_test must find @Test annotated methods in test files."""
        test_file = (
            PETCLINIC_BASE
            / "src/test/java/org/springframework/samples/petclinic/owner/OwnerControllerTests.java"
        )
        if not test_file.exists():
            pytest.skip("Test file not found")
        results = query(petclinic_server, test_file, "junit5_test")
        # 13 @Test methods x 3 captures (junit5_test, annotation_name,
        # method_name) — measured on upstream HEAD 2026-06-13.
        assert len(results) == 39, (
            f"OwnerControllerTests has 13 @Test methods. Got {len(results)}. "
            "Query 'junit5_test' not yet implemented."
        )


@pytest.mark.skipif(not CAFFEINE_BASE.exists(), reason="caffeine not cloned")
class TestConcurrencyQueries:
    """volatile_field and other concurrency queries."""

    def test_volatile_field_finds_caffeine_fields(self, caffeine_server):
        """volatile_field must find volatile fields in BoundedLocalCache."""
        results = query(caffeine_server, BOUNDED_LOCAL_CACHE, "volatile_field")
        # 2 volatile fields x 3 captures (volatile_field, modifier,
        # field_name) — measured on upstream HEAD 2026-06-13.
        assert len(results) == 6, (
            f"BoundedLocalCache has 2 volatile fields. Got {len(results)}. "
            "Query 'volatile_field' not yet implemented."
        )


class TestJava16RecordQuery:
    """record_declaration query for Java 16+ records."""

    def test_record_declaration_unit(self):
        """record_declaration must find Java record declarations."""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        src = b"""
package test;
public record Point(int x, int y) {
    public double distance() { return Math.sqrt(x*x + y*y); }
}
"""
        # Write temp file to test
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as f:
            f.write(src)
            tmp_path = f.name

        import asyncio
        import os

        server = TreeSitterAnalyzerMCPServer(os.path.dirname(tmp_path))
        # Default response format is TOON which strips ``results``; ask for
        # JSON so we can assert on ``r["results"]`` directly.
        r = asyncio.run(
            server.query_tool.execute(
                {
                    "file_path": tmp_path,
                    "query_key": "record_declaration",
                    "output_format": "json",
                }
            )
        )
        os.unlink(tmp_path)

        results = r.get("results", [])
        # 1 record match x 2 captures (record_declaration, record_name) —
        # measured locally 2026-06-13 (this test has no external-repo gate).
        assert len(results) == 2, (
            f"Should find 'Point' record declaration. Got {len(results)}. "
            "Query 'record_declaration' not yet implemented."
        )
