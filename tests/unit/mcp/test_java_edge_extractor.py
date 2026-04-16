"""Coverage tests for Java edge extractor."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.utils.edge_extractors.java import (
    JavaEdgeExtractor,
    _detect_java_root_packages,
    _root_cache,
)


class TestJavaEdgeExtractorExtends:
    def test_extends_custom_class(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = "public class Foo extends Bar { }"
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert ("Foo.java", "Bar") in edges

    def test_extends_java_lang_filtered(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = "public class Foo extends Exception { }"
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert len(edges) == 0

    def test_extends_short_generic_filtered(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = "public class Foo<T extends Comparable<T>> { }"
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert all("Comparable" not in e for e in edges)

    def test_extends_imported_third_party_filtered(self, tmp_path) -> None:
        pom = tmp_path / "pom.xml"
        pom.write_text("<groupId>com.myapp</groupId>")
        _root_cache.pop(str(tmp_path), None)

        src = "import org.apache.http.HttpClient;\npublic class Foo extends HttpClient { }"
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert len(edges) == 0


class TestJavaEdgeExtractorImplements:
    def test_implements_custom_interface(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = "public class Foo implements MyInterface { }"
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert ("Foo.java", "MyInterface") in edges

    def test_implements_java_lang_filtered(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = "public class Foo implements Runnable { }"
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert len(edges) == 0

    def test_implements_multiple(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = "public class Foo implements Alpha, Beta, Gamma {\n}"
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert ("Foo.java", "Alpha") in edges
        assert ("Foo.java", "Beta") in edges
        assert ("Foo.java", "Gamma") in edges


class TestDetectRootPackages:
    def test_with_pom_xml(self, tmp_path) -> None:
        pom = tmp_path / "pom.xml"
        pom.write_text("<project><groupId>com.example</groupId></project>")
        _root_cache.pop(str(tmp_path), None)

        result = _detect_java_root_packages(str(tmp_path))
        assert "com.example" in result

    def test_with_gradle(self, tmp_path) -> None:
        gradle = tmp_path / "build.gradle"
        gradle.write_text('group = "com.gradle.app"')
        _root_cache.pop(str(tmp_path), None)

        result = _detect_java_root_packages(str(tmp_path))
        assert "com.gradle.app" in result

    def test_empty_project(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        result = _detect_java_root_packages(str(tmp_path))
        assert isinstance(result, frozenset)
        assert len(result) == 0
