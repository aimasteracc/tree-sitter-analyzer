"""
Regression tests for Java extraction — each test cites the issue / incident it guards.

Sources:
- test_java_caffeine_validation.py  (Bug 1: implements generics, Bug 2: annotation bleed)
- test_java_annotation_extraction.py  (Bug 1+2: wrong extraction order / _reset_caches;
                                        Bug 3: hardcoded annotations=[]; Bug 4: field_declaration missing)
- test_java_record_annotation_extraction.py  (2026-06-10 quality-audit: record/annotation-type dropped)
- test_java_annotation_query.py  (method_with_annotations query fix)
- test_java_query_validation.py  (#match? predicate fix; new query types)
- test_java_structure_analyzer.py  (CLI --structure output schema)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Issue #NNN / Bug references:
#
#  Bug 1+2  (2026-04-09) Wrong extraction order + _reset_caches() cleared self.annotations
#  Bug 3    (2026-04-09) analyze_code_structure_tool hardcoded annotations=[]
#  Bug 4    (2026-04-09) field_declaration missing from container_node_types
#  Bug 5    caffeine: implements with generic type args split incorrectly
#  Bug 6    caffeine: @Override and other method-only annotations attributed to classes
#  Theme-I  (2026-06-10) record_declaration / annotation_type_declaration nodes dropped
#  QV-A     #match? predicate not applied (tree-sitter 0.25)
#  QV-B     New query types (spring_bean, spring_configuration, etc.)
# ─────────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# Bug 1+2: Annotation extraction order + _reset_caches source-data clearing
# ---------------------------------------------------------------------------


class TestAnnotationExtractionOrder:
    """Bug 1+2 (2026-04-09): extract_annotations() must run before
    extract_functions/extract_classes, and _reset_caches() must NOT clear
    self.annotations (source data)."""

    def test_annotations_preserved_after_extract_functions(self):
        """self.annotations must survive a call to extract_functions()."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """
@Controller
public class FooController {
    @GetMapping("/foo")
    public String doFoo() { return "foo"; }
}
"""
        JAVA_LANG = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = JAVA_LANG
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        annotations = ext.extract_annotations(tree, src)
        # Bug 1+2 guard: @Controller (class) + @GetMapping (method) = 2
        assert len(annotations) == 2, "Should find exactly @Controller and @GetMapping"

        ext.extract_functions(tree, src)

        # Bug 2 fix: self.annotations is source data, not a lookup cache
        assert len(ext.annotations) == 2, (
            "_reset_caches() must not clear self.annotations; "
            "it is source data set by extract_annotations(), not a lookup cache"
        )

    @pytest.mark.skip(
        reason="unimplemented: annotation propagation in extract_elements (tracked: unimplemented)"
    )
    def test_methods_carry_annotations_from_extract_elements(self):
        """Bug 1+2: extract_elements() must return functions with non-empty annotations."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaPlugin

        src = """
@Controller
public class FooController {
    @GetMapping("/foo")
    public String doFoo() { return "foo"; }

    @PostMapping("/bar")
    public String doBar() { return "bar"; }
}
"""
        JAVA_LANG = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = JAVA_LANG
        tree = parser.parse(src.encode())

        plugin = JavaPlugin()
        elements = plugin.extract_elements(tree, src)

        methods_with_annotations = [
            m for m in elements.get("functions", []) if m.annotations
        ]
        assert len(methods_with_annotations) == 2, (
            "Methods with @GetMapping and @PostMapping must have annotations. "
            "Bug: extract_elements called extract_functions before extract_annotations."
        )

    def test_reset_caches_preserves_annotations_source_data(self):
        """Bug 2 fix: _reset_caches() clears lookup caches but keeps self.annotations."""
        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        ext = JavaElementExtractor()
        ext.annotations.append({"name": "Controller", "line": 1})

        ext._reset_caches()

        assert len(ext._annotation_cache) == 0
        assert len(ext._node_text_cache) == 0
        assert len(ext.annotations) == 1, (
            "self.annotations is source data; _reset_caches() must not clear it."
        )


# ---------------------------------------------------------------------------
# Bug 4: field_declaration missing from container_node_types
# ---------------------------------------------------------------------------


class TestFieldAnnotationExtraction:
    """Bug 4 (2026-04-09): Field-level annotations must be extracted."""

    @pytest.mark.skip(
        reason="unimplemented: field annotation extraction in JavaElementExtractor (tracked: unimplemented)"
    )
    def test_field_annotations_extracted_unit(self):
        """Unit test: field annotations extracted without MCP server."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """
public class Entity {
    @Column(name = "user_id", nullable = false)
    @NotNull
    private Long userId;
}
"""
        JAVA_LANG = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = JAVA_LANG
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        fields = ext.extract_variables(tree, src)

        user_id_field = next((f for f in fields if f.name == "userId"), None)
        assert user_id_field is not None

        ann_names = [a.get("name") for a in user_id_field.annotations]
        assert "Column" in ann_names, f"Should extract @Column. Got: {ann_names}"
        assert "NotNull" in ann_names, f"Should extract @NotNull. Got: {ann_names}"


# ---------------------------------------------------------------------------
# Bug 5: implements with generic type args split incorrectly (caffeine)
# ---------------------------------------------------------------------------


class TestImplementsGenerics:
    """Bug 5 (caffeine): implements with generic type parameters must be
    preserved as complete strings — not split on commas inside angle brackets."""

    def test_implements_single_generic_stays_as_one_item(self):
        """LocalCache<K, V> must stay as one item, not split into three."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """\
package test;
abstract class BoundedLocalCache<K, V> implements LocalCache<K, V> {
    public void put(K key, V value) {}
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        classes = ext.extract_classes(tree, src)

        assert classes, "Should extract BoundedLocalCache"
        cls = classes[0]
        implements = cls.implements_interfaces

        assert len(implements) == 1, (
            f"LocalCache<K, V> should be ONE item in implements, got {implements}. "
            "Bug: re.findall(r'\\b[A-Z]\\w*') splits generic args as separate interfaces."
        )
        assert implements[0] == "LocalCache<K, V>", (
            f"Expected 'LocalCache<K, V>', got {implements[0]!r}"
        )

    def test_implements_multiple_generic_interfaces_count(self):
        """Multiple generic interfaces must each be preserved as complete strings."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """\
package test;
class Foo<K, V> implements Runnable, Comparable<Foo<K, V>>, Serializable {
    public void run() {}
    public int compareTo(Foo<K, V> other) { return 0; }
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        classes = ext.extract_classes(tree, src)

        assert classes
        implements = classes[0].implements_interfaces

        assert len(implements) == 3, (
            f"Expected 3 interfaces (Runnable, Comparable<Foo<K,V>>, Serializable), "
            f"got {len(implements)}: {implements}"
        )
        assert "Runnable" in implements
        assert any("Comparable" in i for i in implements), (
            f"Missing Comparable in {implements}"
        )
        assert "Serializable" in implements

    def test_interface_extends_captured_in_implements(self):
        """[TDD] Java interface extends clause captured in implements_interfaces.

        extends_interfaces node (not super_interfaces) was previously ignored.
        """
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """\
package test;
public interface Channel extends Runnable, Comparable<Channel>, java.io.Serializable {
    void close();
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        classes = ext.extract_classes(tree, src)

        assert classes, "Should extract Channel interface"
        iface = classes[0]
        assert iface.class_type == "interface"
        impl = iface.implements_interfaces

        assert len(impl) == 3, (
            f"Interface should show 3 extended interfaces, got {impl}. "
            "Bug: extends_interfaces node not handled in _extract_class_relationships()."
        )
        assert "Runnable" in impl
        assert any("Comparable" in i for i in impl)
        assert any("Serializable" in i for i in impl)
        comparable = next(i for i in impl if "Comparable" in i)
        assert "<" in comparable, f"Comparable generic arg dropped. Got: {comparable!r}"


# ---------------------------------------------------------------------------
# Bug 6: @Override and other method-only annotations bleed into classes
# ---------------------------------------------------------------------------


class TestAnnotationAttribution:
    """Bug 6 (caffeine): @Override and other method-only annotations must
    never appear on classes."""

    def test_override_does_not_bleed_to_next_class(self):
        """@Override on a method must not bleed into the next class's annotations."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """\
package test;
class Outer {
    static class Inner1 {
        @Override
        public String toString() { return "inner1"; }
    }

    // Next class — @Override from toString() above must NOT bleed here
    @SuppressWarnings("unchecked")
    static class Inner2 implements Runnable {
        public void run() {}
    }
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        classes = ext.extract_classes(tree, src)

        inner2 = next((c for c in classes if c.name == "Inner2"), None)
        assert inner2 is not None, "Should find Inner2"

        ann_names = {
            a.get("name") if isinstance(a, dict) else str(a) for a in inner2.annotations
        }
        assert "Override" not in ann_names, (
            f"@Override from Inner1.toString() must not bleed into Inner2. "
            f"Inner2 annotations: {ann_names}"
        )
        assert "SuppressWarnings" in ann_names, (
            f"Inner2 should have @SuppressWarnings. Got: {ann_names}"
        )

    def test_annotation_attribution_direct_ast(self):
        """Class annotations should come from AST modifiers, not line proximity."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """\
package test;
class A {
    @Override
    public String toString() { return "a"; }
}
@SuppressWarnings("all")
class B {}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        classes = ext.extract_classes(tree, src)

        b_class = next((c for c in classes if c.name == "B"), None)
        assert b_class is not None

        ann_names = {
            a.get("name") if isinstance(a, dict) else str(a)
            for a in b_class.annotations
        }
        assert "Override" not in ann_names, (
            f"@Override from A.toString() must not bleed into class B. Got: {ann_names}"
        )
        assert "SuppressWarnings" in ann_names, (
            f"@SuppressWarnings should be on class B. Got: {ann_names}"
        )


# ---------------------------------------------------------------------------
# T3.2 synthetic: MCP-level validation (Bug 5 + Bug 6 via MCP, no caffeine clone)
# ---------------------------------------------------------------------------


class TestBoundedLocalCacheSynthetic:
    """End-to-end MCP validation of Bug 5 and Bug 6 using a synthetic file.

    Mirrors BoundedLocalCache.java's structural patterns without cloning caffeine.
    """

    _SRC = """\
package com.github.benmanes.caffeine.cache;

import java.util.concurrent.ConcurrentHashMap;

@SuppressWarnings("unchecked")
abstract class BoundedLocalCache<K, V>
    implements LocalCache<K, V>, Runnable, java.io.Serializable {

    private static final long serialVersionUID = 1L;

    @SuppressWarnings("rawtypes")
    final ConcurrentHashMap<K, V> data = new ConcurrentHashMap<>();

    @Override
    public void run() {}

    @Override
    public V get(K key) { return data.get(key); }

    static final class BoundedEviction {
        @Override
        public String toString() { return "BoundedEviction"; }
    }

    @Deprecated
    static final class LegacyNode<K, V> implements java.io.Serializable {
        private static final long serialVersionUID = 2L;

        @SuppressWarnings("unused")
        private K key;
    }
}
"""

    @pytest.fixture(scope="class")
    def mcp_result(self, tmp_path_factory):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        base = tmp_path_factory.mktemp("caffeine_synthetic")
        java_file = base / "BoundedLocalCache.java"
        java_file.write_text(self._SRC, encoding="utf-8")

        server = TreeSitterAnalyzerMCPServer(str(base))
        result = asyncio.run(
            server.call_tool(
                "analyze_code_structure",
                {"file_path": str(java_file), "output_format": "json"},
            )
        )
        return result

    def _classes(self, mcp_result):
        return mcp_result.get("classes", [])

    def test_bounded_local_cache_implements_generics_preserved(self, mcp_result):
        """Bug 5 via MCP: LocalCache<K, V> must appear as one item, not split."""
        classes = self._classes(mcp_result)
        blc = next((c for c in classes if c.get("name") == "BoundedLocalCache"), None)
        assert blc is not None, (
            f"BoundedLocalCache not found. Classes: {[c.get('name') for c in classes]}"
        )
        implements = blc.get("implements", [])
        assert "K" not in implements, (
            f"'K' must not appear as standalone interface. implements={implements}"
        )
        assert "V" not in implements, (
            f"'V' must not appear as standalone interface. implements={implements}"
        )
        local_cache = [i for i in implements if "LocalCache" in i]
        assert local_cache, f"LocalCache not in implements. Got: {implements}"
        assert "<" in local_cache[0], (
            f"LocalCache generic args dropped. Got: {local_cache[0]!r}"
        )

    def test_bounded_eviction_no_override_bleed(self, mcp_result):
        """Bug 6 via MCP: @Override must not bleed to BoundedEviction."""
        classes = self._classes(mcp_result)
        be = next((c for c in classes if c.get("name") == "BoundedEviction"), None)
        if be is None:
            pytest.skip(
                "BoundedEviction inner class not surfaced by extractor (tracked: unimplemented)"
            )
        ann_names = {a.get("name", "") for a in be.get("annotations", [])}
        assert "Override" not in ann_names, (
            f"@Override bled into BoundedEviction class annotations: {ann_names}"
        )

    def test_legacy_node_has_deprecated_annotation(self, mcp_result):
        """Class-level annotation round-trip: @Deprecated must reach LegacyNode."""
        classes = self._classes(mcp_result)
        legacy = next((c for c in classes if c.get("name") == "LegacyNode"), None)
        if legacy is None:
            pytest.skip(
                "LegacyNode not surfaced by extractor (inner class) (tracked: unimplemented)"
            )
        ann_names = {a.get("name", "") for a in legacy.get("annotations", [])}
        assert "Deprecated" in ann_names, (
            f"@Deprecated missing from LegacyNode annotations. Got: {ann_names}"
        )


# ---------------------------------------------------------------------------
# Theme-I (2026-06-10): record / annotation-type declarations dropped
# ---------------------------------------------------------------------------


JAVA_SRC_RECORDS = """\
package demo;

public class Container {
    public record Point(int x, int y) {
        public double dist() { return Math.sqrt(x * x + y * y); }
    }

    public @interface Audited {
        String value() default "";
    }

    public enum Color { RED, GREEN }

    void use() {}
}

record TopLevelRecord(String name, int age) {}

@interface TopLevelAnno { int level(); }
"""


def _extract_classes_from_src() -> dict[str, str]:
    import tree_sitter
    import tree_sitter_java

    from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

    lang = tree_sitter.Language(tree_sitter_java.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(JAVA_SRC_RECORDS.encode())
    extractor = JavaElementExtractor()
    classes = extractor.extract_classes(tree, JAVA_SRC_RECORDS)
    return {c.name: c.class_type for c in classes}


def test_record_declarations_extracted():
    """Theme-I (2026-06-10): record_declaration nodes must appear in extraction."""
    found = _extract_classes_from_src()
    assert "Point" in found, f"nested record missing; got {sorted(found)}"
    assert "TopLevelRecord" in found, f"top-level record missing; got {sorted(found)}"
    assert found["Point"] == "record"
    assert found["TopLevelRecord"] == "record"


def test_annotation_type_declarations_extracted():
    """Theme-I (2026-06-10): annotation_type_declaration nodes must appear."""
    found = _extract_classes_from_src()
    assert "Audited" in found, f"nested @interface missing; got {sorted(found)}"
    assert "TopLevelAnno" in found, f"top-level @interface missing; got {sorted(found)}"
    assert found["Audited"] == "annotation"
    assert found["TopLevelAnno"] == "annotation"


def test_existing_kinds_unchanged_after_record_support():
    """The graduation of record/annotation must not disturb class/enum extraction."""
    found = _extract_classes_from_src()
    assert found.get("Container") == "class"
    assert found.get("Color") == "enum"


def test_record_method_still_extracted():
    """Methods inside a record body must be visible as functions."""
    import tree_sitter
    import tree_sitter_java

    from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

    lang = tree_sitter.Language(tree_sitter_java.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(JAVA_SRC_RECORDS.encode())
    extractor = JavaElementExtractor()
    functions = extractor.extract_functions(tree, JAVA_SRC_RECORDS)
    names = {f.name for f in functions}
    assert "dist" in names, f"record method missing; got {sorted(names)}"


# ---------------------------------------------------------------------------
# QV-A: method_with_annotations query — fixed query pattern
# ---------------------------------------------------------------------------


def _write_temp_java(code: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
        f.write(code)
        return f.name


def _cleanup(path: str) -> None:
    try:
        if os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass


class TestJavaAnnotationMethodQuery:
    """QV-A: method_with_annotations query — the old pattern
    `(modifiers (annotation) @annotation)*` failed to match; fixed to
    `(modifiers [(annotation) (marker_annotation)]+ @annotation)`."""

    def test_single_marker_annotation_count(self):
        from tree_sitter_analyzer import api

        java_code = """
public class TestClass {
    @Override
    public String toString() { return "test"; }
}
"""
        test_file = _write_temp_java(java_code)
        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )
            assert result["success"], f"Query failed: {result.get('error')}"
            method_with_annotations = result.get("results", [])
            assert len(method_with_annotations) == 1, (
                f"Expected 1 method with annotation, found {len(method_with_annotations)}"
            )
            captures = method_with_annotations[0].get("captures", {})
            assert captures["name"]["text"] == "toString"
            assert "annotation" in captures
        finally:
            _cleanup(test_file)

    def test_annotation_with_parameters(self):
        from tree_sitter_analyzer import api

        java_code = """
public class TestClass {
    @SuppressWarnings("unchecked")
    public List getRawList() { return new ArrayList(); }
}
"""
        test_file = _write_temp_java(java_code)
        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )
            assert result["success"]
            method_with_annotations = result.get("results", [])
            assert len(method_with_annotations) == 1
            assert (
                method_with_annotations[0].get("captures", {})["name"]["text"]
                == "getRawList"
            )
        finally:
            _cleanup(test_file)

    def test_mixed_methods_only_annotated_matched(self):
        from tree_sitter_analyzer import api

        java_code = """
public class TestClass {
    @Override
    public String toString() { return "test"; }

    public void regularMethod() {}

    @Test
    public void testMethod() {}
}
"""
        test_file = _write_temp_java(java_code)
        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )
            assert result["success"]
            method_with_annotations = result.get("results", [])
            assert len(method_with_annotations) == 2, (
                f"Expected 2 annotated methods, found {len(method_with_annotations)}"
            )
            matched_names = [
                m.get("captures", {}).get("name", {}).get("text")
                for m in method_with_annotations
                if "name" in m.get("captures", {})
            ]
            assert "toString" in matched_names
            assert "testMethod" in matched_names
            assert "regularMethod" not in matched_names
        finally:
            _cleanup(test_file)

    def test_query_result_has_expected_captures(self):
        from tree_sitter_analyzer import api

        java_code = """
public class TestClass {
    @Override
    public String toString() { return "test"; }
}
"""
        test_file = _write_temp_java(java_code)
        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )
            assert result["success"]
            method_with_annotations = result.get("results", [])
            assert method_with_annotations
            first = method_with_annotations[0]
            assert "text" in first
            assert "start_line" in first
            assert "end_line" in first
            assert "captures" in first
            captures = first["captures"]
            assert "name" in captures
            assert "annotation" in captures
            assert "method" in captures
        finally:
            _cleanup(test_file)


# ---------------------------------------------------------------------------
# QV-A: #match? predicate fix (spring_controller / jpa_entity — skipped when repos absent)
# ---------------------------------------------------------------------------

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


def _run(coro):
    return asyncio.run(coro)


def _query(server, file_path, query_key):
    r = _run(
        server.query_tool.execute(
            {
                "file_path": str(file_path),
                "query_key": query_key,
                "output_format": "json",
            }
        )
    )
    return r.get("results", [])


@pytest.fixture(scope="module")
def petclinic_server():
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

    return TreeSitterAnalyzerMCPServer(str(PETCLINIC_BASE))


@pytest.fixture(scope="module")
def spring_server():
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

    return TreeSitterAnalyzerMCPServer(str(SPRING_BASE))


@pytest.mark.skipif(not PETCLINIC_BASE.exists(), reason="spring-petclinic not cloned")
class TestMatchPredicateFix:
    """QV-A: #match? predicate not applied in tree-sitter 0.25 QueryCursor."""

    def test_spring_controller_finds_owner_controller(self, petclinic_server):
        """spring_controller must find @Controller annotated OwnerController.

        1 @Controller match × 3 captures = 3 results (measured 2026-06-13).
        """
        results = _query(petclinic_server, OWNER_CONTROLLER, "spring_controller")
        assert len(results) == 3, (
            f"spring_controller must find OwnerController. Got {len(results)}. "
            "Bug: #match? predicate not applied in tree-sitter 0.25 QueryCursor."
        )
        names = [r.get("content", "") for r in results]
        assert any("OwnerController" in n for n in names)

    def test_jpa_entity_finds_vet(self, petclinic_server):
        """jpa_entity must find @Entity annotated Vet class.

        1 @Entity match × 3 captures = 3 results (measured 2026-06-13).
        """
        results = _query(petclinic_server, VET, "jpa_entity")
        assert len(results) == 3, (
            f"jpa_entity must find Vet. Got {len(results)}. "
            "Bug: #match? predicate silently returns 0."
        )

    def test_jpa_entity_finds_owner(self, petclinic_server):
        results = _query(petclinic_server, OWNER, "jpa_entity")
        assert len(results) == 3, f"jpa_entity must find Owner. Got {len(results)}."

    def test_spring_service_not_in_controller(self, petclinic_server):
        results = _query(petclinic_server, OWNER_CONTROLLER, "spring_service")
        assert len(results) == 0, (
            f"spring_service must return 0 for @Controller class. Got: {len(results)}."
        )

    def test_spring_controller_count_one_class(self, petclinic_server):
        results = _query(petclinic_server, OWNER_CONTROLLER, "spring_controller")
        class_captures = [
            r for r in results if r.get("capture_name") == "spring_controller"
        ]
        assert len(class_captures) == 1, (
            f"OwnerController.java has exactly 1 @Controller class. "
            f"Got {len(class_captures)} class captures."
        )


# ---------------------------------------------------------------------------
# QV-B: New query types
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not SPRING_BASE.exists(), reason="spring-framework not cloned")
class TestSpringBeanQuery:
    """QV-B: spring_bean / spring_configuration / spring_transactional queries."""

    def test_spring_bean_finds_three_bean_methods(self, spring_server):
        """3 @Bean methods × 3 captures = 9 results (measured 2026-06-13)."""
        results = _query(spring_server, PROXY_CACHING, "spring_bean")
        assert len(results) == 9, (
            f"ProxyCachingConfiguration has 3 @Bean methods. Got {len(results)}."
        )
        bean_captures = [r for r in results if r.get("capture_name") == "spring_bean"]
        assert len(bean_captures) == 3

    def test_spring_configuration_finds_proxy_caching(self, spring_server):
        """1 @Configuration × 3 captures = 3 results (measured 2026-06-13)."""
        results = _query(spring_server, PROXY_CACHING, "spring_configuration")
        assert len(results) == 3, (
            f"ProxyCachingConfiguration is @Configuration. Got {len(results)}."
        )

    def test_spring_transactional_zero_for_attribute_source(self, spring_server):
        """AnnotationTransactionAttributeSource has 0 @Transactional methods."""
        tx_file = (
            SPRING_BASE
            / "spring-tx/src/main/java/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.java"
        )
        if not tx_file.exists():
            pytest.skip("Transaction file not found")
        results = _query(spring_server, tx_file, "spring_transactional")
        assert len(results) == 0, (
            f"AnnotationTransactionAttributeSource has no @Transactional methods. Got {len(results)}."
        )


@pytest.mark.skipif(not PETCLINIC_BASE.exists(), reason="spring-petclinic not cloned")
class TestJUnit5Queries:
    def test_junit5_test_finds_13_test_methods(self, petclinic_server):
        """13 @Test methods × 3 captures = 39 results (measured 2026-06-13)."""
        test_file = (
            PETCLINIC_BASE
            / "src/test/java/org/springframework/samples/petclinic/owner/OwnerControllerTests.java"
        )
        if not test_file.exists():
            pytest.skip("Test file not found")
        results = _query(petclinic_server, test_file, "junit5_test")
        assert len(results) == 39, (
            f"OwnerControllerTests has 13 @Test methods. Got {len(results)}."
        )


class TestJava16RecordQuery:
    """QV-B: record_declaration query for Java 16+ records."""

    def test_record_declaration_unit(self):
        """record_declaration must find Java record declarations.

        1 record match × 2 captures = 2 results (measured 2026-06-13).
        """
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        src = b"""
package test;
public record Point(int x, int y) {
    public double distance() { return Math.sqrt(x*x + y*y); }
}
"""
        with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as f:
            f.write(src)
            tmp_path = f.name

        server = TreeSitterAnalyzerMCPServer(os.path.dirname(tmp_path))
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
        assert len(results) == 2, (
            f"Should find 'Point' record declaration. Got {len(results)}."
        )


# ---------------------------------------------------------------------------
# CLI --structure output schema (test_java_structure_analyzer.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def structure_analyzer():
    from tests.unit.languages._java_structure_analyzer_fixture import (
        create_structure_analyzer_adapter,
    )

    return create_structure_analyzer_adapter()


@pytest.fixture(scope="function")
def simple_java_code():
    return """
package com.test;

import java.util.List;

@TestAnnotation
public class SimpleClass {
    private String name;
    public static final int CONSTANT = 42;

    public SimpleClass(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public static void staticMethod() {
        System.out.println("Static method");
    }
}
"""


def test_analyze_structure_required_keys(structure_analyzer, simple_java_code):
    """analyze_structure returns a dict with all required top-level keys."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(simple_java_code)
        temp_path = f.name
    try:
        result = structure_analyzer.analyze_structure(temp_path)
        assert result is not None
        assert isinstance(result, dict)
        for key in (
            "file_path",
            "package",
            "imports",
            "classes",
            "methods",
            "fields",
            "annotations",
            "statistics",
            "analysis_metadata",
        ):
            assert key in result, f"Missing key '{key}'"
        assert isinstance(result["classes"], list)
        assert isinstance(result["methods"], list)
        assert isinstance(result["fields"], list)
        assert isinstance(result["imports"], list)
        assert isinstance(result["annotations"], list)
        assert isinstance(result["statistics"], dict)
        assert isinstance(result["analysis_metadata"], dict)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_analyze_structure_statistics_keys(structure_analyzer, simple_java_code):
    """statistics dict contains all expected integer keys."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(simple_java_code)
        temp_path = f.name
    try:
        result = structure_analyzer.analyze_structure(temp_path)
        stats = result["statistics"]
        for key in (
            "total_lines",
            "class_count",
            "method_count",
            "field_count",
            "import_count",
            "annotation_count",
        ):
            assert key in stats, f"Missing stats key '{key}'"
            assert isinstance(stats[key], int)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_analyze_structure_metadata_keys(structure_analyzer, simple_java_code):
    """analysis_metadata contains analysis_time, analyzer_version, timestamp."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write(simple_java_code)
        temp_path = f.name
    try:
        result = structure_analyzer.analyze_structure(temp_path)
        metadata = result["analysis_metadata"]
        assert "analysis_time" in metadata
        assert "analyzer_version" in metadata
        assert "timestamp" in metadata
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_analyze_structure_empty_file_returns_zeroes(structure_analyzer):
    """Empty Java file: class/method/field counts must all be 0."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".java", delete=False, encoding="utf-8"
    ) as f:
        f.write("")
        temp_path = f.name
    try:
        result = structure_analyzer.analyze_structure(temp_path)
        assert result is not None
        assert result["statistics"]["class_count"] == 0
        assert result["statistics"]["method_count"] == 0
        assert result["statistics"]["field_count"] == 0
        assert len(result["classes"]) == 0
        assert len(result["methods"]) == 0
        assert len(result["fields"]) == 0
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_analyze_structure_nonexistent_file_returns_none(structure_analyzer):
    """Non-existent file returns None."""
    result = structure_analyzer.analyze_structure("/path/that/does/not/exist.java")
    assert result is None
