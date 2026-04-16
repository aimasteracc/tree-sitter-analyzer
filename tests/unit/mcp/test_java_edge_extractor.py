"""Coverage tests for Java edge extractor."""
from __future__ import annotations

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


class TestJavaEdgeExtractorSpringDI:
    """Test Spring DI field edge extraction."""

    def test_autowired_field(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "@Service\n"
            "public class OrderService {\n"
            "    @Autowired\n"
            "    private PaymentService paymentService;\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "OrderService.java", str(tmp_path))
        assert ("OrderService.java", "PaymentService") in edges

    def test_inject_field(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "public class MyBean {\n"
            "    @Inject\n"
            "    private DataSource dataSource;\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "MyBean.java", str(tmp_path))
        assert ("MyBean.java", "DataSource") in edges

    def test_resource_field(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "public class Handler {\n"
            "    @Resource\n"
            "    private CacheManager cacheManager;\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Handler.java", str(tmp_path))
        assert ("Handler.java", "CacheManager") in edges

    def test_di_third_party_filtered(self, tmp_path) -> None:
        pom = tmp_path / "pom.xml"
        pom.write_text("<groupId>com.myapp</groupId>")
        _root_cache.pop(str(tmp_path), None)
        src = (
            "import org.springframework.data.redis.RedisTemplate;\n"
            "public class Service {\n"
            "    @Autowired\n"
            "    private RedisTemplate redisTemplate;\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Service.java", str(tmp_path))
        assert all("RedisTemplate" not in e for e in edges)

    def test_di_primitive_ignored(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "public class Config {\n"
            "    @Autowired\n"
            "    private String name;\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Config.java", str(tmp_path))
        assert all("String" not in e for e in edges)


class TestJavaEdgeExtractorStreamRefs:
    """Test Stream method reference edge extraction."""

    def test_method_reference_type(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "import com.myapp.model.User;\n"
            "public class Service {\n"
            "    void run() {\n"
            "        list.stream().map(User::getName).collect();\n"
            "    }\n"
            "}\n"
        )
        pom = tmp_path / "pom.xml"
        pom.write_text("<groupId>com.myapp</groupId>")
        _root_cache.pop(str(tmp_path), None)
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Service.java", str(tmp_path))
        assert ("Service.java", "User") in edges

    def test_method_ref_java_lang_filtered(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "public class Service {\n"
            "    void run() {\n"
            "        list.stream().map(String::toUpperCase).collect();\n"
            "    }\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Service.java", str(tmp_path))
        assert all("String" not in e for e in edges)

    def test_method_ref_lowercase_ignored(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "public class Foo {\n"
            "    void run() {\n"
            "        obj.map(item::process);\n"
            "    }\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "Foo.java", str(tmp_path))
        assert all("item" not in e for e in edges)

    def test_combined_extends_di_and_refs(self, tmp_path) -> None:
        _root_cache.pop(str(tmp_path), None)
        src = (
            "import com.myapp.repo.BaseRepo;\n"
            "import com.myapp.model.Order;\n"
            "public class OrderService extends BaseRepo {\n"
            "    @Autowired\n"
            "    private PaymentGateway gateway;\n"
            "    void process() {\n"
            "        items.stream().map(Order::getId).collect();\n"
            "    }\n"
            "}\n"
        )
        ext = JavaEdgeExtractor()
        edges = ext.extract(src, "OrderService.java", str(tmp_path))
        assert ("OrderService.java", "BaseRepo") in edges
        assert ("OrderService.java", "PaymentGateway") in edges
        assert ("OrderService.java", "Order") in edges
