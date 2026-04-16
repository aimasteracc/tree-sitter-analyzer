"""Tests for Java pattern analysis — lambda, stream, and Spring detection."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.analysis.java_patterns import (
    JavaPatternResult,
    LambdaInfo,
    SpringComponent,
    SpringInjection,
    StreamChain,
    analyze_java_patterns,
    extract_lambdas,
    extract_spring_patterns,
    extract_stream_chains,
)

# ---------------------------------------------------------------------------
# Lambda extraction
# ---------------------------------------------------------------------------


class TestExtractLambdas:
    """Test lambda expression extraction from Java source."""

    def test_single_param_no_parens(self) -> None:
        source = "list.forEach(x -> System.out.println(x));"
        lambdas = extract_lambdas(source)
        assert len(lambdas) == 1
        assert lambdas[0].parameters == 1
        assert "System.out.println(x)" in lambdas[0].body

    def test_multi_param_with_parens(self) -> None:
        source = "list.sort((a, b) -> a.compareTo(b));"
        lambdas = extract_lambdas(source)
        assert len(lambdas) == 1
        assert lambdas[0].parameters == 2

    def test_no_params(self) -> None:
        source = "executor.submit(() -> new Object());"
        lambdas = extract_lambdas(source)
        assert len(lambdas) == 1
        assert lambdas[0].parameters == 0

    def test_typed_parameter(self) -> None:
        source = "map.forEach((String key, String val) -> System.out.println(key));"
        lambdas = extract_lambdas(source)
        assert len(lambdas) >= 1
        typed = [la for la in lambdas if la.has_typed_params]
        assert len(typed) >= 1

    def test_method_reference_in_body(self) -> None:
        source = "list.stream().map(user -> user.getName());"
        lambdas = extract_lambdas(source)
        assert len(lambdas) >= 1
        assert any("user" in la.raw for la in lambdas)

    def test_no_lambda(self) -> None:
        source = "public void doSomething() { return; }"
        lambdas = extract_lambdas(source)
        assert len(lambdas) == 0

    def test_multiple_lambdas_on_different_lines(self) -> None:
        source = (
            "list.forEach(x -> x.process());\n"
            "map.forEach((k, v) -> System.out.println(k));\n"
        )
        lambdas = extract_lambdas(source)
        assert len(lambdas) >= 2

    def test_line_numbers_correct(self) -> None:
        source = (
            "class Foo {\n"          # line 1
            "  void bar() {\n"       # line 2
            "    f(x -> x);\n"       # line 3
            "  }\n"                  # line 4
            "}\n"                    # line 5
        )
        lambdas = extract_lambdas(source)
        assert len(lambdas) >= 1
        assert any(la.line == 3 for la in lambdas)


# ---------------------------------------------------------------------------
# Stream API extraction
# ---------------------------------------------------------------------------


class TestExtractStreamChains:
    """Test Stream API call chain extraction."""

    def test_simple_map_filter_collect(self) -> None:
        source = (
            'users.stream().filter(u -> u.isActive()).map(User::getName)'
            '.collect(Collectors.toList());'
        )
        chains = extract_stream_chains(source)
        assert len(chains) == 1
        assert chains[0].source_type == "users"
        assert "filter" in chains[0].operations
        assert "map" in chains[0].operations
        assert "collect" in chains[0].operations
        assert chains[0].is_terminal

    def test_method_reference_detection(self) -> None:
        source = "items.stream().map(Item::getId).collect(Collectors.toList());"
        chains = extract_stream_chains(source)
        assert len(chains) == 1
        assert "Item::getId" in chains[0].method_refs

    def test_no_stream(self) -> None:
        source = "List<String> names = new ArrayList<>();"
        chains = extract_stream_chains(source)
        assert len(chains) == 0

    def test_generic_source_type(self) -> None:
        source = "List<String> list = getList(); list.stream().map(String::toUpperCase).collect(Collectors.toList());"
        chains = extract_stream_chains(source)
        assert len(chains) >= 1

    def test_intermediate_operations_only(self) -> None:
        source = "items.stream().filter(x -> x > 0).map(x -> x * 2);"
        chains = extract_stream_chains(source)
        assert len(chains) >= 1
        assert "filter" in chains[0].operations
        assert "map" in chains[0].operations

    def test_chained_terminal_detection(self) -> None:
        source = "list.stream().count();"
        chains = extract_stream_chains(source)
        assert len(chains) == 1
        assert chains[0].is_terminal

    def test_line_number(self) -> None:
        source = (
            "class Foo {\n"                              # 1
            "  void bar() {\n"                            # 2
            "    list.stream().map(x -> x).collect();\n"  # 3
            "  }\n"                                       # 4
            "}\n"                                         # 5
        )
        chains = extract_stream_chains(source)
        assert len(chains) == 1
        assert chains[0].line == 3


# ---------------------------------------------------------------------------
# Spring annotation extraction
# ---------------------------------------------------------------------------


class TestExtractSpringPatterns:
    """Test Spring annotation, DI, and endpoint extraction."""

    def test_service_component(self) -> None:
        source = (
            "@Service\n"
            "public class UserService {\n"
            "}\n"
        )
        components, _, _ = extract_spring_patterns(source)
        assert len(components) == 1
        assert components[0].annotation == "Service"
        assert components[0].class_name == "UserService"
        assert components[0].is_primary

    def test_controller_component(self) -> None:
        source = (
            "@RestController\n"
            "@RequestMapping(\"/api\")\n"
            "public class ApiController {\n"
            "}\n"
        )
        components, _, _ = extract_spring_patterns(source)
        assert len(components) == 1
        assert components[0].annotation == "RestController"
        assert components[0].is_primary

    def test_repository_component(self) -> None:
        source = (
            "@Repository\n"
            "public class UserRepository {\n"
            "}\n"
        )
        components, _, _ = extract_spring_patterns(source)
        assert len(components) == 1
        assert components[0].annotation == "Repository"
        assert not components[0].is_primary

    def test_autowired_injection(self) -> None:
        source = (
            "@Service\n"
            "public class OrderService {\n"
            "    @Autowired\n"
            "    private PaymentService paymentService;\n"
            "}\n"
        )
        _, injections, _ = extract_spring_patterns(source)
        assert len(injections) == 1
        assert injections[0].field_type == "PaymentService"
        assert injections[0].annotation == "Autowired"

    def test_inject_annotation(self) -> None:
        source = (
            "public class MyBean {\n"
            "    @Inject\n"
            "    private DataSource dataSource;\n"
            "}\n"
        )
        _, injections, _ = extract_spring_patterns(source)
        assert len(injections) >= 1
        assert injections[0].annotation == "Inject"

    def test_resource_annotation(self) -> None:
        source = (
            "public class MyBean {\n"
            "    @Resource\n"
            "    private CacheManager cacheManager;\n"
            "}\n"
        )
        _, injections, _ = extract_spring_patterns(source)
        assert len(injections) >= 1
        assert injections[0].annotation == "Resource"

    def test_get_mapping_endpoint(self) -> None:
        source = (
            "@RestController\n"
            "public class UserController {\n"
            '    @GetMapping("/users")\n'
            "    public List<User> getUsers() { return null; }\n"
            "}\n"
        )
        _, _, endpoints = extract_spring_patterns(source)
        assert len(endpoints) >= 1
        methods = [e[0] for e in endpoints]
        assert "GET" in methods

    def test_post_mapping_endpoint(self) -> None:
        source = (
            "@RestController\n"
            "public class OrderController {\n"
            '    @PostMapping(path = "/orders")\n'
            "    public Order create() { return null; }\n"
            "}\n"
        )
        _, _, endpoints = extract_spring_patterns(source)
        assert len(endpoints) >= 1
        assert any(e[0] == "POST" and "/orders" in e[1] for e in endpoints)

    def test_no_spring_patterns(self) -> None:
        source = (
            "public class PlainJava {\n"
            "    private String name;\n"
            "    public String getName() { return name; }\n"
            "}\n"
        )
        components, injections, endpoints = extract_spring_patterns(source)
        assert len(components) == 0
        assert len(injections) == 0
        assert len(endpoints) == 0

    def test_multiple_components(self) -> None:
        source = (
            "@Service\n"
            "@Component\n"
            "public class MyService {\n"
            "}\n"
        )
        components, _, _ = extract_spring_patterns(source)
        assert len(components) == 2
        annotations = {c.annotation for c in components}
        assert "Service" in annotations
        assert "Component" in annotations

    def test_generic_di_field_type(self) -> None:
        source = (
            "public class Foo {\n"
            "    @Autowired\n"
            "    private List<String> names;\n"
            "}\n"
        )
        _, injections, _ = extract_spring_patterns(source)
        assert len(injections) >= 1
        assert "List" in injections[0].field_type


# ---------------------------------------------------------------------------
# Integrated analysis
# ---------------------------------------------------------------------------


class TestAnalyzeJavaPatterns:
    """Test the main analyze_java_patterns entry point."""

    def test_combined_analysis(self) -> None:
        source = (
            "@Service\n"
            "public class UserService {\n"
            "    @Autowired\n"
            "    private UserRepository repo;\n"
            "\n"
            "    public List<String> getActive() {\n"
            "        return users.stream()\n"
            "            .filter(u -> u.isActive())\n"
            "            .map(User::getName)\n"
            "            .collect(Collectors.toList());\n"
            "    }\n"
            "}\n"
        )
        result = analyze_java_patterns(source)
        assert result.lambda_count >= 1
        assert result.stream_count >= 1
        assert result.is_spring_component
        assert result.injection_count >= 1

    def test_to_dict(self) -> None:
        source = (
            "@Controller\n"
            "public class Api {\n"
            "    @Autowired\n"
            "    private Service svc;\n"
            "    void run() {\n"
            "        list.stream().map(x -> x).collect(Collectors.toList());\n"
            "    }\n"
            "}\n"
        )
        result = analyze_java_patterns(source)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "lambda_count" in d
        assert "stream_count" in d
        assert "is_spring_component" in d
        assert "injection_count" in d
        assert d["is_spring_component"] is True

    def test_empty_source(self) -> None:
        result = analyze_java_patterns("")
        assert result.lambda_count == 0
        assert result.stream_count == 0
        assert not result.is_spring_component
        assert result.injection_count == 0

    def test_realistic_spring_boot_controller(self) -> None:
        source = (
            "@RestController\n"
            "@RequestMapping(\"/api/v1\")\n"
            "public class ProductController {\n"
            "\n"
            "    @Autowired\n"
            "    private ProductService productService;\n"
            "\n"
            "    @Autowired\n"
            "    private CategoryService categoryService;\n"
            "\n"
            '    @GetMapping("/products")\n'
            "    public List<Product> listProducts() {\n"
            "        return productService.findAll().stream()\n"
            "            .filter(p -> p.isAvailable())\n"
            "            .map(Product::getName)\n"
            "            .collect(Collectors.toList());\n"
            "    }\n"
            "\n"
            '    @PostMapping(path = "/products")\n'
            "    public Product create(@RequestBody Product p) {\n"
            "        return productService.save(p);\n"
            "    }\n"
            "}\n"
        )
        result = analyze_java_patterns(source)
        assert result.is_spring_component
        assert result.injection_count == 2
        assert result.stream_count >= 1
        assert result.lambda_count >= 1
        endpoint_methods = [e[0] for e in result.spring_endpoints]
        assert "GET" in endpoint_methods
        assert "POST" in endpoint_methods


# ---------------------------------------------------------------------------
# Data class properties
# ---------------------------------------------------------------------------


class TestDataClasses:
    """Test data class constructors and properties."""

    def test_lambda_info_frozen(self) -> None:
        info = LambdaInfo(
            raw="x -> x",
            line=1,
            parameters=1,
            has_typed_params=False,
            body="x",
            method_references=(),
        )
        assert info.parameters == 1
        with pytest.raises(AttributeError):
            info.line = 2  # type: ignore[misc]

    def test_stream_chain_frozen(self) -> None:
        chain = StreamChain(
            source_type="list",
            operations=("map", "collect"),
            method_refs=("String::toUpperCase",),
            is_terminal=True,
            raw="list.stream().map(...).collect(...)",
            line=5,
        )
        assert chain.is_terminal
        with pytest.raises(AttributeError):
            chain.line = 10  # type: ignore[misc]

    def test_spring_component_frozen(self) -> None:
        comp = SpringComponent(
            annotation="Service",
            class_name="UserService",
            line=1,
            is_primary=True,
        )
        assert comp.is_primary

    def test_spring_injection_frozen(self) -> None:
        inj = SpringInjection(
            annotation="Autowired",
            field_type="UserRepository",
            line=5,
        )
        assert inj.field_type == "UserRepository"

    def test_java_pattern_result_mutable(self) -> None:
        result = JavaPatternResult()
        assert result.lambda_count == 0
        result.lambdas.append(LambdaInfo(
            raw="x -> x", line=1, parameters=1,
            has_typed_params=False, body="x", method_references=(),
        ))
        assert result.lambda_count == 1
