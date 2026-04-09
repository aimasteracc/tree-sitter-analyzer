"""
TDD tests for Java extraction quality — validated against caffeine open source project.
(ben-manes/caffeine, production-grade caching library)

Bugs targeted:
  Bug 1: implements with generic type arguments split incorrectly
  Bug 2: @Override and other method-only annotations attributed to classes

Both tests must FAIL before the fix, then PASS after.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

CAFFEINE_BASE = Path("/workspaces/claude-source-run-version/caffeine/caffeine/src/main/java")
BOUNDED_LOCAL_CACHE = CAFFEINE_BASE / "com/github/benmanes/caffeine/cache/BoundedLocalCache.java"
REFERENCES = CAFFEINE_BASE / "com/github/benmanes/caffeine/cache/References.java"

pytestmark = pytest.mark.skipif(
    not CAFFEINE_BASE.exists(),
    reason="caffeine not cloned at expected path",
)


@pytest.fixture(scope="module")
def mcp_server():
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
    return TreeSitterAnalyzerMCPServer(str(CAFFEINE_BASE))


def call(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Bug 1: implements generics ───────────────────────────────────────────────

class TestImplementsGenerics:
    """implements with generic type parameters must be preserved as complete strings."""

    def test_implements_generic_preserved_unit(self):
        """Unit test: LocalCache<K, V> must stay as one item, not split into three."""
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

    def test_implements_multiple_generic_interfaces(self):
        """Multiple generic interfaces must each be preserved as a complete string."""
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

        # Should be exactly 3 interfaces
        assert len(implements) == 3, (
            f"Expected 3 interfaces (Runnable, Comparable<Foo<K,V>>, Serializable), "
            f"got {len(implements)}: {implements}"
        )
        assert "Runnable" in implements
        assert any("Comparable" in i for i in implements), f"Missing Comparable in {implements}"
        assert "Serializable" in implements

    def test_caffeine_bounded_local_cache_implements(self, mcp_server):
        """BoundedLocalCache must show 'LocalCache<K, V>' not split into 3 items."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(BOUNDED_LOCAL_CACHE),
        }))
        classes = r.get("elements", {}).get("classes", [])
        blc = next((c for c in classes if c.get("name") == "BoundedLocalCache"), None)
        assert blc is not None, "Should find BoundedLocalCache class"

        implements = blc.get("implements", [])
        # K and V should NOT appear as standalone interface names
        assert "K" not in implements, (
            f"'K' should not be a standalone interface name. implements={implements}"
        )
        assert "V" not in implements, (
            f"'V' should not be a standalone interface name. implements={implements}"
        )
        # LocalCache<K, V> should appear as one item
        local_cache = [i for i in implements if "LocalCache" in i]
        assert local_cache, f"LocalCache should appear in implements. Got: {implements}"
        assert "<" in local_cache[0], (
            f"LocalCache should preserve generic args, got {local_cache[0]!r}"
        )


# ─── Bug 2: @Override on classes ──────────────────────────────────────────────

class TestAnnotationAttribution:
    """@Override and other method-only annotations must never appear on classes."""

    METHOD_ONLY_ANNOTATIONS = {
        "Override", "Test", "Before", "After",
        "BeforeEach", "AfterEach", "BeforeAll", "AfterAll",
        "ParameterizedTest",
    }

    def test_override_never_on_class_unit(self):
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

        ann_names = {a.get("name") if isinstance(a, dict) else str(a)
                     for a in inner2.annotations}
        assert "Override" not in ann_names, (
            f"@Override from Inner1.toString() must not bleed into Inner2. "
            f"Inner2 annotations: {ann_names}"
        )
        assert "SuppressWarnings" in ann_names, (
            f"Inner2 should have @SuppressWarnings. Got: {ann_names}"
        )

    def test_caffeine_no_override_on_any_class(self, mcp_server):
        """No class in BoundedLocalCache should have @Override in its annotations."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(BOUNDED_LOCAL_CACHE),
        }))
        classes = r.get("elements", {}).get("classes", [])

        offenders = [
            (c.get("name"), ann.get("name"))
            for c in classes
            for ann in c.get("annotations", [])
            if ann.get("name") in self.METHOD_ONLY_ANNOTATIONS
        ]
        assert not offenders, (
            f"Method-only annotations found on classes (annotation bleeding): {offenders}. "
            "Example: BoundedEviction shows @Override because the previous inner class's "
            "last method has @Override within 2 lines of BoundedEviction's class start."
        )

    def test_references_inner_classes_clean_annotations(self, mcp_server):
        """Inner classes in References.java should have no spurious annotations."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(REFERENCES),
        }))
        classes = r.get("elements", {}).get("classes", [])

        offenders = [
            (c.get("name"), ann.get("name"))
            for c in classes
            for ann in c.get("annotations", [])
            if ann.get("name") in self.METHOD_ONLY_ANNOTATIONS
        ]
        assert not offenders, (
            f"Method-only annotations on classes in References.java: {offenders}"
        )

    def test_annotation_attribution_direct_ast(self):
        """Class annotations should come from AST modifiers, not line proximity."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        # Tight layout: @Override immediately before class declaration
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

        ann_names = {a.get("name") if isinstance(a, dict) else str(a)
                     for a in b_class.annotations}
        assert "Override" not in ann_names, (
            f"@Override from A.toString() must not bleed into class B. Got: {ann_names}"
        )
        assert "SuppressWarnings" in ann_names, (
            f"@SuppressWarnings should be on class B. Got: {ann_names}"
        )
