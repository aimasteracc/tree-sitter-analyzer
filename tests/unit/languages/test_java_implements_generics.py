#!/usr/bin/env python3
"""Test Java implements generics parsing - Bug 1 from fix-java-implements-generics-and-annotation-attribution

Bug 1: implements with generic type arguments split incorrectly
  - `LocalCache<K, V>` should be preserved as one item
  - NOT split into `["LocalCache", "K", "V"]`

TDD Order: Write FAILING tests first, then implement fixes
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_java as ts_java

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor


class TestImplementsGenerics:
    """implements with generic type parameters must be preserved as complete strings."""

    def test_implements_generic_preserved_unit(self):
        """Unit test: LocalCache<K, V> must stay as one item, not split into three."""
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

    def test_implements_nested_generics(self):
        """Nested generics in implements must be preserved as complete strings."""
        src = """\
package test;
class Bar implements Function<Stream<CacheEntry<K,V>>, Map<K,V>> {
    public Map<K,V> apply(Stream<CacheEntry<K,V>> s) { return null; }
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        classes = ext.extract_classes(tree, src)

        assert classes, "Should extract Bar"
        cls = classes[0]
        implements = cls.implements_interfaces

        assert len(implements) == 1, (
            f"Function<Stream<CacheEntry<K,V>>, Map<K,V>> should be ONE item, got {implements}"
        )
        # The nested generic should be preserved
        assert "Function<" in implements[0], (
            f"Expected Function<...> with generic args, got {implements[0]!r}"
        )

    def test_implements_multiple_generic_interfaces(self):
        """Multiple generic interfaces must each be preserved as a complete string."""
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

        assert classes, "Should extract Foo"
        cls = classes[0]
        implements = cls.implements_interfaces

        assert len(implements) == 3, f"Should have 3 interfaces, got {len(implements)}: {implements}"
        assert "Runnable" in implements
        assert "Comparable<Foo<K, V>>" in implements, (
            f"Comparable<Foo<K, V>> should be one item, got {implements}"
        )
        assert "Serializable" in implements

    def test_split_type_list_respects_angle_brackets(self):
        """Direct test of _split_type_list helper method."""
        ext = JavaElementExtractor()

        # Simple case - no generics
        assert ext._split_type_list("implements Runnable, Serializable") == [
            "Runnable", "Serializable"
        ]

        # Single generic interface
        result = ext._split_type_list("implements LocalCache<K, V>")
        assert result == ["LocalCache<K, V>"], f"Expected ['LocalCache<K, V>'], got {result}"

        # Multiple interfaces with generics
        result = ext._split_type_list("implements Runnable, Comparable<Foo<K, V>>, Serializable")
        assert result == ["Runnable", "Comparable<Foo<K, V>>", "Serializable"], (
            f"Generic args should be preserved, got {result}"
        )

        # Deeply nested generics
        result = ext._split_type_list("implements Function<Stream<CacheEntry<K,V>>, Map<K,V>>")
        assert len(result) == 1, f"Should be one item, got {result}"
        assert "Function<" in result[0], f"Should preserve nested generics, got {result[0]}"

    def test_split_type_list_strips_keywords(self):
        """Test that leading keywords like 'implements' are stripped."""
        ext = JavaElementExtractor()

        # With 'implements' prefix
        result = ext._split_type_list("implements Runnable, Serializable")
        assert "implements" not in result[0], f"'implements' keyword should be stripped, got {result}"
        assert result == ["Runnable", "Serializable"]

        # With 'extends' prefix
        result = ext._split_type_list("extends Foo, Bar")
        assert "extends" not in result[0], f"'extends' keyword should be stripped, got {result}"
        assert result == ["Foo", "Bar"]
