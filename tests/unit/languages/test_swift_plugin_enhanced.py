"""Comprehensive Swift plugin extraction tests with edge cases."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from tree_sitter_analyzer.languages.swift_plugin import (
    SwiftPlugin,
    _analysis_error_result,
    _analysis_result,
    _count_tree_nodes,
    _empty_analysis_result,
    _empty_elements,
    _flatten_elements,
    _parse_swift_source,
)

try:
    import tree_sitter
    import tree_sitter_swift

    TREE_SITTER_SWIFT_AVAILABLE = True
except ImportError:
    TREE_SITTER_SWIFT_AVAILABLE = False

SWIFT_EXTENSIONS_SAMPLE = """
import UIKit
import CoreData.NSManagedObject

extension User {
    var displayName: String { name }
    func formatted() -> String { "" }
}

extension Collection where Element: Codable {
    func save() -> Bool { true }
}
""".strip()

SWIFT_ENUMS_SAMPLE = """
enum NetworkError: Error, CustomStringConvertible {
    case unauthorized(String)
    case timeout(seconds: Int)
    case serverError(code: Int, message: String)

    var description: String { "" }
    var isFatal: Bool { true }
}

indirect enum Expr {
    case literal(Int)
    case add(Expr, Expr)
    case negate(Expr)
}
""".strip()

SWIFT_NESTED_SAMPLE = """
class ViewModel {
    private let service: APIService
    private(set) var isLoading: Bool = false

    struct Config {
        let maxRetries: Int
        let timeout: Double
        static let `default` = Config(maxRetries: 3, timeout: 30.0)
    }

    enum State {
        case idle
        case loading(progress: Double)
        case loaded(data: [String])
        case error(message: String)
    }

    init(service: APIService) {
        self.service = service
    }

    func fetch() async throws -> [String] {
        isLoading = true
        defer { isLoading = false }
        return try await service.fetch()
    }

    private func handle(result: Result<[String], Error>) {
        switch result {
        case .success(let data): break
        case .failure(let error): break
        }
    }
}
""".strip()

SWIFT_PROTOCOLS_SAMPLE = """
protocol Drawable {
    var color: String { get set }
    var area: Double { get }
    static func defaultColor() -> String
    func draw(in context: RenderContext)
    func resize(by factor: Double) -> Self
}

protocol Observable: AnyObject {
    associatedtype Event
    func observe(_ handler: @escaping (Event) -> Void)
}

@available(macOS 13.0, *)
protocol ModernFeature: Drawable {
    func render() async throws
}
""".strip()

SWIFT_GENERICS_SAMPLE = """
struct Container<T: Equatable & Codable> {
    var items: [T]
    let capacity: Int

    func contains(_ item: T) -> Bool {
        items.contains(item)
    }

    mutating func append(_ item: T) {
        items.append(item)
    }

    subscript(index: Int) -> T? {
        guard index >= 0, index < items.count else { return nil }
        return items[index]
    }
}

class Repository<T, U> where T: Decodable, U: Encoder {
    let storage: [T]
    let encoder: U

    init(storage: [T], encoder: U) {
        self.storage = storage
        self.encoder = encoder
    }
}
""".strip()

SWIFT_MINIMAL_SAMPLE = ""
SWIFT_COMMENTS_ONLY = """
// This is a comment
/* block comment */
""".strip()

SWIFT_OPERATOR_SAMPLE = """
precedencegroup Chaining {
    associativity: left
    higherThan: FunctionArrow
}

infix operator <>: Chaining

func <><A>(lhs: A, rhs: (A) -> A) -> A {
    rhs(lhs)
}
""".strip()

SWIFT_PROPERTY_WRAPPERS_SAMPLE = """
@propertyWrapper
struct Clamped<T: Comparable> {
    private var value: T
    let range: ClosedRange<T>

    var wrappedValue: T {
        get { value }
        set { value = min(max(newValue, range.lowerBound), range.upperBound) }
    }

    init(wrappedValue: T, _ range: ClosedRange<T>) {
        self.value = min(max(wrappedValue, range.lowerBound), range.upperBound)
        self.range = range
    }
}
""".strip()


def _swift_parser():
    language = tree_sitter.Language(tree_sitter_swift.language())
    parser = tree_sitter.Parser()
    parser.language = language
    return parser


@pytest.fixture
def plugin() -> SwiftPlugin:
    return SwiftPlugin()


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftExtensionExtraction:
    def test_extension_types(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_EXTENSIONS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(
            tree, SWIFT_EXTENSIONS_SAMPLE
        )
        ext_classes = [c for c in classes if c.class_type == "extension"]
        assert len(ext_classes) >= 1

    def test_extension_functions(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_EXTENSIONS_SAMPLE.encode("utf-8"))
        functions = plugin.create_extractor().extract_functions(
            tree, SWIFT_EXTENSIONS_SAMPLE
        )
        names = {f.name for f in functions}
        assert "formatted" in names or "save" in names

    def test_extension_variables(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_EXTENSIONS_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_EXTENSIONS_SAMPLE
        )
        var_names = {v.name for v in variables}
        assert "displayName" in var_names

    def test_import_with_submodule(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_EXTENSIONS_SAMPLE.encode("utf-8"))
        imports = plugin.create_extractor().extract_imports(
            tree, SWIFT_EXTENSIONS_SAMPLE
        )
        modules = {imp.module_name for imp in imports}
        assert "UIKit" in modules
        assert any("CoreData" in m for m in modules)


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftEnumExtraction:
    def test_enum_declaration(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_ENUMS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(tree, SWIFT_ENUMS_SAMPLE)
        enum_types = [c for c in classes if c.class_type == "enum"]
        assert len(enum_types) >= 1

    def test_enum_with_interfaces(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_ENUMS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(tree, SWIFT_ENUMS_SAMPLE)
        error_enum = next((c for c in classes if c.name == "NetworkError"), None)
        assert error_enum is not None
        assert (
            "Error" in error_enum.interfaces
            or "CustomStringConvertible" in error_enum.interfaces
        )

    def test_enum_properties(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_ENUMS_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_ENUMS_SAMPLE
        )
        var_names = {v.name for v in variables}
        assert "description" in var_names
        assert "isFatal" in var_names

    def test_indirect_enum(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_ENUMS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(tree, SWIFT_ENUMS_SAMPLE)
        names = {c.name for c in classes}
        assert "Expr" in names


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftNestedDeclarations:
    def test_nested_types(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_NESTED_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(tree, SWIFT_NESTED_SAMPLE)
        names = {c.name for c in classes}
        assert "ViewModel" in names
        assert "Config" in names
        assert "State" in names

    def test_private_property(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_NESTED_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_NESTED_SAMPLE
        )
        service_var = next((v for v in variables if v.name == "service"), None)
        assert service_var is not None
        assert service_var.is_constant is True

    def test_private_set_property(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_NESTED_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_NESTED_SAMPLE
        )
        loading_var = next((v for v in variables if v.name == "isLoading"), None)
        assert loading_var is not None
        assert loading_var.is_constant is False

    def test_async_function(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_NESTED_SAMPLE.encode("utf-8"))
        functions = plugin.create_extractor().extract_functions(
            tree, SWIFT_NESTED_SAMPLE
        )
        fetch_fn = next((f for f in functions if f.name == "fetch"), None)
        assert fetch_fn is not None
        assert fetch_fn.is_async is True

    def test_init_extraction(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_NESTED_SAMPLE.encode("utf-8"))
        functions = plugin.create_extractor().extract_functions(
            tree, SWIFT_NESTED_SAMPLE
        )
        inits = [f for f in functions if f.is_constructor]
        assert len(inits) >= 1

    def test_private_function(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_NESTED_SAMPLE.encode("utf-8"))
        functions = plugin.create_extractor().extract_functions(
            tree, SWIFT_NESTED_SAMPLE
        )
        handle_fn = next((f for f in functions if f.name == "handle"), None)
        assert handle_fn is not None
        assert handle_fn.is_private is True

    def test_static_property(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_NESTED_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_NESTED_SAMPLE
        )
        default_var = next((v for v in variables if v.name == "default"), None)
        if default_var is not None:
            assert default_var.is_static is True


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftProtocols:
    def test_protocol_declaration(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_PROTOCOLS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(
            tree, SWIFT_PROTOCOLS_SAMPLE
        )
        protocols = [c for c in classes if c.class_type == "protocol"]
        assert len(protocols) >= 1

    def test_protocol_properties(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_PROTOCOLS_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_PROTOCOLS_SAMPLE
        )
        var_names = {v.name for v in variables}
        assert "color" in var_names
        assert "area" in var_names

    def test_protocol_functions(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_PROTOCOLS_SAMPLE.encode("utf-8"))
        functions = plugin.create_extractor().extract_functions(
            tree, SWIFT_PROTOCOLS_SAMPLE
        )
        names = {f.name for f in functions}
        assert "draw" in names
        assert "resize" in names
        assert "defaultColor" in names

    def test_protocol_inheritance(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_PROTOCOLS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(
            tree, SWIFT_PROTOCOLS_SAMPLE
        )
        modern = next((c for c in classes if c.name == "ModernFeature"), None)
        if modern is not None:
            assert "Drawable" in modern.interfaces or len(modern.interfaces) >= 1


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftGenerics:
    def test_generic_struct(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_GENERICS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(tree, SWIFT_GENERICS_SAMPLE)
        container = next((c for c in classes if c.name == "Container"), None)
        assert container is not None
        assert container.class_type == "struct"

    def test_generic_class(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_GENERICS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(tree, SWIFT_GENERICS_SAMPLE)
        repo = next((c for c in classes if c.name == "Repository"), None)
        assert repo is not None
        assert repo.class_type == "class"

    def test_generic_functions(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_GENERICS_SAMPLE.encode("utf-8"))
        functions = plugin.create_extractor().extract_functions(
            tree, SWIFT_GENERICS_SAMPLE
        )
        names = {f.name for f in functions}
        assert "contains" in names
        assert "append" in names

    def test_generic_properties(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_GENERICS_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_GENERICS_SAMPLE
        )
        var_names = {v.name for v in variables}
        assert "items" in var_names
        assert "capacity" in var_names


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftEmptyAndMinimal:
    def test_empty_file(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(b"")
        elements = plugin.extract_elements(tree, "")
        assert elements["functions"] == []
        assert elements["classes"] == []
        assert elements["variables"] == []
        assert elements["imports"] == []

    def test_comments_only(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_COMMENTS_ONLY.encode("utf-8"))
        elements = plugin.extract_elements(tree, SWIFT_COMMENTS_ONLY)
        assert elements["functions"] == []
        assert elements["classes"] == []


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftPropertyWrappers:
    def test_property_wrapper_struct(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_PROPERTY_WRAPPERS_SAMPLE.encode("utf-8"))
        classes = plugin.create_extractor().extract_classes(
            tree, SWIFT_PROPERTY_WRAPPERS_SAMPLE
        )
        clamped = next((c for c in classes if c.name == "Clamped"), None)
        assert clamped is not None
        assert clamped.class_type == "struct"

    def test_property_wrapper_init(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_PROPERTY_WRAPPERS_SAMPLE.encode("utf-8"))
        functions = plugin.create_extractor().extract_functions(
            tree, SWIFT_PROPERTY_WRAPPERS_SAMPLE
        )
        inits = [f for f in functions if f.is_constructor]
        assert len(inits) >= 1

    def test_property_wrapper_computed(self, plugin: SwiftPlugin) -> None:
        tree = _swift_parser().parse(SWIFT_PROPERTY_WRAPPERS_SAMPLE.encode("utf-8"))
        variables = plugin.create_extractor().extract_variables(
            tree, SWIFT_PROPERTY_WRAPPERS_SAMPLE
        )
        var_names = {v.name for v in variables}
        assert "wrappedValue" in var_names
        assert "value" in var_names
        assert "range" in var_names


class TestSwiftModuleLevelFunctions:
    def test_empty_elements(self) -> None:
        result = _empty_elements()
        assert result == {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
        }

    def test_flatten_elements(self) -> None:
        elements = {
            "functions": ["f1"],
            "classes": ["c1", "c2"],
            "variables": ["v1"],
            "imports": ["i1", "i2", "i3"],
        }
        flat = _flatten_elements(elements)
        assert len(flat) == 7

    def test_flatten_elements_missing_keys(self) -> None:
        flat = _flatten_elements({})
        assert flat == []

    def test_flatten_elements_partial(self) -> None:
        flat = _flatten_elements({"functions": ["f1"], "classes": []})
        assert flat == ["f1"]

    def test_empty_analysis_result(self) -> None:
        result = _empty_analysis_result("test.swift", "line1\nline2")
        assert result.file_path == "test.swift"
        assert result.language == "swift"
        assert result.line_count == 2
        assert result.elements == []

    def test_analysis_error_result(self) -> None:
        result = _analysis_error_result("err.swift", "something broke")
        assert result.file_path == "err.swift"
        assert result.language == "swift"
        assert result.success is False
        assert result.error_message == "something broke"
        assert result.line_count == 0

    @pytest.mark.skipif(
        not TREE_SITTER_SWIFT_AVAILABLE,
        reason="tree-sitter-swift not installed",
    )
    def test_analysis_result_with_tree(self) -> None:
        language = tree_sitter.Language(tree_sitter_swift.language())
        parser = tree_sitter.Parser()
        parser.language = language
        tree = parser.parse(b"struct Foo {}")
        elements_dict = {"functions": [], "classes": [], "variables": [], "imports": []}
        result = _analysis_result("test.swift", "struct Foo {}", tree, elements_dict)
        assert result.file_path == "test.swift"
        assert result.language == "swift"
        assert result.node_count > 0

    @pytest.mark.skipif(
        not TREE_SITTER_SWIFT_AVAILABLE,
        reason="tree-sitter-swift not installed",
    )
    def test_parse_swift_source(self) -> None:
        language = tree_sitter.Language(tree_sitter_swift.language())
        tree = _parse_swift_source(language, "let x = 1")
        assert tree is not None
        assert tree.root_node is not None

    @pytest.mark.skipif(
        not TREE_SITTER_SWIFT_AVAILABLE,
        reason="tree-sitter-swift not installed",
    )
    def test_count_tree_nodes(self) -> None:
        language = tree_sitter.Language(tree_sitter_swift.language())
        tree = _parse_swift_source(language, "let x = 1")
        count = _count_tree_nodes(tree.root_node)
        assert count >= 1


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftAnalyzerIntegration:
    @pytest.mark.asyncio
    async def test_analyze_file_with_nested_types(
        self, plugin: SwiftPlugin, tmp_path
    ) -> None:
        source = tmp_path / "Nested.swift"
        source.write_text(SWIFT_NESTED_SAMPLE, encoding="utf-8")
        result = await plugin.analyze_file(str(source), Mock())
        assert result.success is True
        assert result.language == "swift"
        assert result.node_count > 0
        element_names = {e.name for e in result.elements}
        assert "ViewModel" in element_names

    @pytest.mark.asyncio
    async def test_analyze_file_with_generics(
        self, plugin: SwiftPlugin, tmp_path
    ) -> None:
        source = tmp_path / "Generic.swift"
        source.write_text(SWIFT_GENERICS_SAMPLE, encoding="utf-8")
        result = await plugin.analyze_file(str(source), Mock())
        assert result.success is True
        element_names = {e.name for e in result.elements}
        assert "Container" in element_names
        assert "Repository" in element_names

    @pytest.mark.asyncio
    async def test_analyze_empty_file(self, plugin: SwiftPlugin, tmp_path) -> None:
        source = tmp_path / "Empty.swift"
        source.write_text("", encoding="utf-8")
        result = await plugin.analyze_file(str(source), Mock())
        assert result.success is True
        assert result.elements == []

    @pytest.mark.asyncio
    async def test_analyze_binary_file(self, plugin: SwiftPlugin, tmp_path) -> None:
        source = tmp_path / "Binary.swift"
        source.write_bytes(b"\x00\x01\x02\xff\xfe")
        result = await plugin.analyze_file(str(source), Mock())
        assert result.language == "swift"

    @pytest.mark.asyncio
    async def test_analyze_unicode_file(self, plugin: SwiftPlugin, tmp_path) -> None:
        swift_code = 'let greeting = "Hello World"'
        source = tmp_path / "Unicode.swift"
        source.write_text(swift_code, encoding="utf-8")
        result = await plugin.analyze_file(str(source), Mock())
        assert result.success is True


class TestSwiftPluginInterface:
    def test_get_tree_sitter_language_import_error(self, plugin: SwiftPlugin) -> None:
        import sys

        original = sys.modules.get("tree_sitter_swift")
        sys.modules["tree_sitter_swift"] = None
        try:
            result = plugin.get_tree_sitter_language()
            assert result is None
        finally:
            if original is not None:
                sys.modules["tree_sitter_swift"] = original
            else:
                del sys.modules["tree_sitter_swift"]

    def test_extract_elements_caches_language(self, plugin: SwiftPlugin) -> None:
        plugin._cached_language = Mock()
        assert plugin.get_tree_sitter_language() is plugin._cached_language
