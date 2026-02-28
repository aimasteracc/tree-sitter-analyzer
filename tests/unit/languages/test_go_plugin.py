#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.go_plugin module.

This module tests the GoPlugin class which provides Go language
support in the plugin architecture.
"""

import os
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest

from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor, GoPlugin
from tree_sitter_analyzer.models import Class, Function, Package
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


@pytest.fixture
def go_plugin() -> GoPlugin:
    """Create a GoPlugin instance for testing."""
    return GoPlugin()


@pytest.fixture
def go_extractor() -> GoElementExtractor:
    """Create a GoElementExtractor instance for testing."""
    return GoElementExtractor()


@pytest.fixture
def mock_tree() -> Mock:
    """Create a mock tree-sitter tree."""
    tree = Mock()
    root_node = Mock()
    root_node.children = []
    tree.root_node = root_node
    tree.language = Mock()
    return tree


@pytest.fixture
def sample_go_code() -> str:
    """Sample Go code for testing."""
    return """
package sample

import (
    "context"
    "fmt"
)

// ErrNotFound is returned when a resource is not found.
var ErrNotFound = errors.New("resource not found")

// DefaultTimeout is the default timeout.
const DefaultTimeout = 30

// Service represents a background service.
type Service struct {
    name   string
    config *Config
}

// Reader is an interface for reading data.
type Reader interface {
    Read(p []byte) (n int, err error)
}

// NewService creates a new Service instance.
func NewService(name string, config *Config) *Service {
    return &Service{
        name:   name,
        config: config,
    }
}

// Name returns the service name.
func (s *Service) Name() string {
    return s.name
}

// process is a private helper function.
func process(data []byte) []byte {
    return data
}
"""


class TestGoPlugin:
    """Test cases for GoPlugin class."""

    def test_plugin_initialization(self, go_plugin: GoPlugin) -> None:
        """Test GoPlugin initialization."""
        assert go_plugin is not None
        assert isinstance(go_plugin, LanguagePlugin)
        assert hasattr(go_plugin, "get_language_name")
        assert hasattr(go_plugin, "get_file_extensions")
        assert hasattr(go_plugin, "create_extractor")

    def test_get_language_name(self, go_plugin: GoPlugin) -> None:
        """Test getting language name."""
        assert go_plugin.get_language_name() == "go"

    def test_get_file_extensions(self, go_plugin: GoPlugin) -> None:
        """Test getting file extensions."""
        extensions = go_plugin.get_file_extensions()
        assert isinstance(extensions, list)
        assert ".go" in extensions

    def test_create_extractor(self, go_plugin: GoPlugin) -> None:
        """Test creating element extractor."""
        extractor = go_plugin.create_extractor()
        assert isinstance(extractor, GoElementExtractor)
        assert isinstance(extractor, ElementExtractor)

    def test_get_supported_element_types(self, go_plugin: GoPlugin) -> None:
        """Test getting supported element types."""
        types = go_plugin.get_supported_element_types()
        assert isinstance(types, list)
        assert "package" in types
        assert "import" in types
        assert "function" in types
        assert "method" in types
        assert "struct" in types
        assert "interface" in types
        assert "type_alias" in types
        assert "const" in types
        assert "var" in types
        assert "goroutine" in types
        assert "channel" in types

    def test_get_queries(self, go_plugin: GoPlugin) -> None:
        """Test getting tree-sitter queries."""
        queries = go_plugin.get_queries()
        assert isinstance(queries, dict)

    def test_supports_file_go(self, go_plugin: GoPlugin) -> None:
        """Test supports_file for .go files."""
        assert go_plugin.supports_file("test.go") is True
        assert go_plugin.supports_file("main.go") is True
        assert go_plugin.supports_file("/path/to/file.go") is True
        assert go_plugin.supports_file("TEST.GO") is True  # Case insensitive

    def test_supports_file_non_go(self, go_plugin: GoPlugin) -> None:
        """Test supports_file for non-Go files."""
        assert go_plugin.supports_file("test.py") is False
        assert go_plugin.supports_file("test.rs") is False
        assert go_plugin.supports_file("test.java") is False
        assert go_plugin.supports_file("go.txt") is False

    def test_get_plugin_info(self, go_plugin: GoPlugin) -> None:
        """Test getting plugin information."""
        info = go_plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        assert info["language"] == "go"

    def test_get_tree_sitter_language_caching(self, go_plugin: GoPlugin) -> None:
        """Test tree-sitter language caching."""
        with (
            patch("tree_sitter_go.language") as mock_language,
            patch("tree_sitter.Language") as mock_language_constructor,
        ):
            mock_lang_obj = Mock()
            mock_language.return_value = mock_lang_obj
            mock_language_constructor.return_value = mock_lang_obj

            # First call
            language1 = go_plugin.get_tree_sitter_language()

            # Second call (should use cache)
            language2 = go_plugin.get_tree_sitter_language()

            assert language1 is language2

    def test_get_tree_sitter_language_import_error(self, go_plugin: GoPlugin) -> None:
        """Test tree-sitter language loading failure."""
        # Reset cache first
        go_plugin._cached_language = None

        with patch("tree_sitter_go.language", side_effect=ImportError("not found")):
            language = go_plugin.get_tree_sitter_language()
            assert language is None

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, go_plugin: GoPlugin) -> None:
        """Test successful file analysis."""
        go_code = """
package main

func main() {
    fmt.Println("Hello")
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False) as f:
            f.write(go_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "go"

            result = await go_plugin.analyze_file(temp_path, mock_request)

            assert result is not None
            assert hasattr(result, "file_path")
            assert hasattr(result, "language")
            assert result.language == "go"

        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_nonexistent(self, go_plugin: GoPlugin) -> None:
        """Test analysis of non-existent file."""
        mock_request = Mock()
        mock_request.file_path = "/nonexistent/file.go"
        mock_request.language = "go"

        result = await go_plugin.analyze_file("/nonexistent/file.go", mock_request)

        assert result is not None
        assert hasattr(result, "success")
        assert result.success is False

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.languages.go_plugin.GoPlugin.get_tree_sitter_language")
    @patch("tree_sitter.Parser")
    async def test_analyze_file_integration(
        self, mock_parser_cls: Mock, mock_get_lang: Mock, go_plugin: GoPlugin
    ) -> None:
        """Test file analysis integration."""
        mock_parser = MagicMock()
        mock_parser_cls.return_value = mock_parser
        mock_tree = MagicMock()
        mock_parser.parse.return_value = mock_tree
        mock_get_lang.return_value = MagicMock()

        file_content = """
package main

func main() {
    fmt.Println("Hello")
}
"""

        with patch("tree_sitter_analyzer.encoding_utils.read_file_safe") as mock_read:
            mock_read.return_value = (file_content, "utf-8")

            result = await go_plugin.analyze_file("test.go", None)

            assert result.language == "go"


class TestGoElementExtractor:
    """Test cases for GoElementExtractor class."""

    def test_extractor_initialization(self, go_extractor: GoElementExtractor) -> None:
        """Test GoElementExtractor initialization."""
        assert go_extractor is not None
        assert isinstance(go_extractor, ElementExtractor)
        assert hasattr(go_extractor, "extract_functions")
        assert hasattr(go_extractor, "extract_classes")
        assert hasattr(go_extractor, "extract_variables")
        assert hasattr(go_extractor, "extract_imports")
        assert hasattr(go_extractor, "extract_packages")

    def test_extractor_has_go_specific_fields(
        self, go_extractor: GoElementExtractor
    ) -> None:
        """Test Go-specific extractor fields."""
        assert hasattr(go_extractor, "goroutines")
        assert hasattr(go_extractor, "channels")
        assert hasattr(go_extractor, "defers")
        assert isinstance(go_extractor.goroutines, list)
        assert isinstance(go_extractor.channels, list)
        assert isinstance(go_extractor.defers, list)

    def test_reset_caches(self, go_extractor: GoElementExtractor) -> None:
        """Test cache reset."""
        go_extractor.goroutines.append({"test": "data"})
        go_extractor.channels.append({"test": "data"})
        go_extractor.defers.append({"test": "data"})
        go_extractor._node_text_cache[1] = "cached"

        go_extractor._reset_caches()

        assert len(go_extractor.goroutines) == 0
        assert len(go_extractor.channels) == 0
        assert len(go_extractor.defers) == 0
        assert len(go_extractor._node_text_cache) == 0

    def test_extract_functions_returns_list(
        self, go_extractor: GoElementExtractor, mock_tree: Mock
    ) -> None:
        """Test extract_functions returns a list."""
        functions = go_extractor.extract_functions(mock_tree, "test code")
        assert isinstance(functions, list)

    def test_extract_classes_returns_list(
        self, go_extractor: GoElementExtractor, mock_tree: Mock
    ) -> None:
        """Test extract_classes returns a list."""
        classes = go_extractor.extract_classes(mock_tree, "test code")
        assert isinstance(classes, list)

    def test_extract_variables_returns_list(
        self, go_extractor: GoElementExtractor, mock_tree: Mock
    ) -> None:
        """Test extract_variables returns a list."""
        variables = go_extractor.extract_variables(mock_tree, "test code")
        assert isinstance(variables, list)

    def test_extract_imports_returns_list(
        self, go_extractor: GoElementExtractor, mock_tree: Mock
    ) -> None:
        """Test extract_imports returns a list."""
        imports = go_extractor.extract_imports(mock_tree, "test code")
        assert isinstance(imports, list)

    def test_extract_packages_returns_list(
        self, go_extractor: GoElementExtractor, mock_tree: Mock
    ) -> None:
        """Test extract_packages returns a list."""
        packages = go_extractor.extract_packages(mock_tree, "test code")
        assert isinstance(packages, list)


class TestGoElementExtractorEdgeCases:
    """Test edge cases for GoElementExtractor."""

    def test_empty_source_code(self, go_extractor: GoElementExtractor) -> None:
        """Test extraction with empty source code."""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        functions = go_extractor.extract_functions(mock_tree, "")
        classes = go_extractor.extract_classes(mock_tree, "")
        variables = go_extractor.extract_variables(mock_tree, "")
        imports = go_extractor.extract_imports(mock_tree, "")
        packages = go_extractor.extract_packages(mock_tree, "")

        assert functions == []
        assert classes == []
        assert variables == []
        assert imports == []
        assert packages == []

    def test_unicode_source_code(self, go_extractor: GoElementExtractor) -> None:
        """Test extraction with Unicode source code."""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        unicode_code = """
package sample

// 日本語コメント
func こんにちは() string {
    return "Hello"
}
"""
        functions = go_extractor.extract_functions(mock_tree, unicode_code)
        assert isinstance(functions, list)


class TestGoExtractorPrivateMethods:
    """Targeted unit tests for GoElementExtractor private methods using MagicMock nodes."""

    def _make_extractor(self, source: str = "") -> GoElementExtractor:
        """Return an extractor with source_code and content_lines pre-set."""
        ext = GoElementExtractor()
        ext.source_code = source
        ext.content_lines = source.split("\n")
        return ext

    def _cache(self, ext: GoElementExtractor, start: int, end: int, text: str) -> None:
        """Pre-populate the node text cache to avoid real byte extraction."""
        ext._node_text_cache[(start, end)] = text

    # ------------------------------------------------------------------ #
    # _extract_goroutine
    # ------------------------------------------------------------------ #

    def test_extract_goroutine_appends_entry(self) -> None:
        ext = self._make_extractor("go foo()")
        self._cache(ext, 0, 8, "go foo()")
        node = MagicMock()
        node.start_point = (0, 0)
        node.start_byte = 0
        node.end_byte = 8
        ext._extract_goroutine(node)
        assert len(ext.goroutines) == 1
        assert ext.goroutines[0]["line"] == 1
        assert "foo" in ext.goroutines[0]["text"]

    def test_extract_goroutine_multiple_calls_accumulate(self) -> None:
        ext = self._make_extractor("go a()\ngo b()")
        self._cache(ext, 0, 6, "go a()")
        self._cache(ext, 7, 13, "go b()")
        for start, end, line in [(0, 6, 0), (7, 13, 1)]:
            n = MagicMock()
            n.start_point = (line, 0)
            n.start_byte = start
            n.end_byte = end
            ext._extract_goroutine(n)
        assert len(ext.goroutines) == 2

    # ------------------------------------------------------------------ #
    # _extract_channel_operation
    # ------------------------------------------------------------------ #

    def test_extract_channel_operation_send_appended(self) -> None:
        ext = self._make_extractor("ch <- 1")
        self._cache(ext, 0, 7, "ch <- 1")
        node = MagicMock()
        node.start_point = (0, 0)
        node.start_byte = 0
        node.end_byte = 7
        ext._extract_channel_operation(node, "send")
        assert len(ext.channels) == 1
        assert ext.channels[0]["type"] == "send"
        assert ext.channels[0]["line"] == 1

    def test_extract_channel_operation_preserves_op_type(self) -> None:
        ext = self._make_extractor("x := <-ch")
        self._cache(ext, 0, 9, "x := <-ch")
        node = MagicMock()
        node.start_point = (0, 0)
        node.start_byte = 0
        node.end_byte = 9
        ext._extract_channel_operation(node, "receive")
        assert ext.channels[0]["type"] == "receive"

    # ------------------------------------------------------------------ #
    # _extract_defer
    # ------------------------------------------------------------------ #

    def test_extract_defer_appends_entry(self) -> None:
        ext = self._make_extractor("defer cleanup()")
        self._cache(ext, 0, 15, "defer cleanup()")
        node = MagicMock()
        node.start_point = (0, 0)
        node.start_byte = 0
        node.end_byte = 15
        ext._extract_defer(node)
        assert len(ext.defers) == 1
        assert ext.defers[0]["line"] == 1
        assert "cleanup" in ext.defers[0]["text"]

    # ------------------------------------------------------------------ #
    # _extract_docstring
    # ------------------------------------------------------------------ #

    def test_extract_docstring_single_comment_above(self) -> None:
        ext = self._make_extractor("// Foo returns bar\nfunc Foo() {}")
        node = MagicMock()
        node.start_point = (1, 0)  # "func Foo() {}" is at line index 1
        result = ext._extract_docstring(node)
        assert result == "Foo returns bar"

    def test_extract_docstring_no_comment_returns_none(self) -> None:
        ext = self._make_extractor("package main\nfunc Bar() {}")
        node = MagicMock()
        node.start_point = (1, 0)
        result = ext._extract_docstring(node)
        assert result is None

    def test_extract_docstring_at_start_of_file_returns_none(self) -> None:
        ext = self._make_extractor("func Baz() {}")
        node = MagicMock()
        node.start_point = (0, 0)
        result = ext._extract_docstring(node)
        assert result is None

    # ------------------------------------------------------------------ #
    # _extract_embedded_types
    # ------------------------------------------------------------------ #

    def test_extract_embedded_types_returns_list(self) -> None:
        ext = self._make_extractor("")
        # Build a minimal mock: struct_node -> field_declaration_list -> field_declaration
        # with only a type_identifier child (no field_identifier = embedded)
        type_child = MagicMock()
        type_child.type = "type_identifier"
        type_child.start_byte = 0
        type_child.end_byte = 8
        self._cache(ext, 0, 8, "io.Reader")

        field = MagicMock()
        field.type = "field_declaration"
        field.children = [type_child]

        field_list = MagicMock()
        field_list.type = "field_declaration_list"
        field_list.children = [field]

        struct_node = MagicMock()
        struct_node.children = [field_list]

        result = ext._extract_embedded_types(struct_node)
        assert isinstance(result, list)

    def test_extract_embedded_types_named_field_not_included(self) -> None:
        ext = self._make_extractor("")
        field_id = MagicMock()
        field_id.type = "field_identifier"

        type_child = MagicMock()
        type_child.type = "type_identifier"

        named_field = MagicMock()
        named_field.type = "field_declaration"
        named_field.children = [field_id, type_child]

        field_list = MagicMock()
        field_list.type = "field_declaration_list"
        field_list.children = [named_field]

        struct_node = MagicMock()
        struct_node.children = [field_list]

        result = ext._extract_embedded_types(struct_node)
        assert result == []

    # ------------------------------------------------------------------ #
    # _extract_var_spec
    # ------------------------------------------------------------------ #

    def test_extract_var_spec_returns_variable(self) -> None:
        ext = self._make_extractor("MyVar int")
        self._cache(ext, 0, 9, "MyVar int")  # full spec
        self._cache(ext, 0, 5, "MyVar")       # identifier
        self._cache(ext, 6, 9, "int")         # type

        id_child = MagicMock()
        id_child.type = "identifier"
        id_child.start_byte = 0
        id_child.end_byte = 5

        type_child = MagicMock()
        type_child.type = "type_identifier"
        type_child.start_byte = 6
        type_child.end_byte = 9

        node = MagicMock()
        node.start_point = (0, 0)
        node.end_point = (0, 9)
        node.start_byte = 0
        node.end_byte = 9
        node.children = [id_child, type_child]

        result = ext._extract_var_spec(node, is_const=False)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].name == "MyVar"
        assert result[0].is_constant is False

    def test_extract_var_spec_const_flag_propagated(self) -> None:
        ext = self._make_extractor("MaxRetry int")
        self._cache(ext, 0, 12, "MaxRetry int")
        self._cache(ext, 0, 8, "MaxRetry")
        self._cache(ext, 9, 12, "int")

        id_child = MagicMock()
        id_child.type = "identifier"
        id_child.start_byte = 0
        id_child.end_byte = 8

        type_child = MagicMock()
        type_child.type = "type_identifier"
        type_child.start_byte = 9
        type_child.end_byte = 12

        node = MagicMock()
        node.start_point = (0, 0)
        node.end_point = (0, 12)
        node.start_byte = 0
        node.end_byte = 12
        node.children = [id_child, type_child]

        result = ext._extract_var_spec(node, is_const=True)
        assert len(result) == 1
        assert result[0].is_constant is True

    # ------------------------------------------------------------------ #
    # _extract_import_spec
    # ------------------------------------------------------------------ #

    def test_extract_import_spec_returns_import(self) -> None:
        ext = self._make_extractor('"fmt"')
        self._cache(ext, 0, 5, '"fmt"')

        path_child = MagicMock()
        path_child.type = "interpreted_string_literal"
        path_child.start_byte = 0
        path_child.end_byte = 5

        node = MagicMock()
        node.start_point = (0, 0)
        node.end_point = (0, 5)
        node.start_byte = 0
        node.end_byte = 5
        node.children = [path_child]

        result = ext._extract_import_spec(node)
        assert result is not None
        assert result.name == "fmt"
        assert result.module_name == "fmt"

    def test_extract_import_spec_with_alias(self) -> None:
        ext = self._make_extractor('myfmt "fmt"')
        self._cache(ext, 0, 11, 'myfmt "fmt"')
        self._cache(ext, 0, 5, "myfmt")
        self._cache(ext, 6, 11, '"fmt"')

        alias_child = MagicMock()
        alias_child.type = "package_identifier"
        alias_child.start_byte = 0
        alias_child.end_byte = 5

        path_child = MagicMock()
        path_child.type = "interpreted_string_literal"
        path_child.start_byte = 6
        path_child.end_byte = 11

        node = MagicMock()
        node.start_point = (0, 0)
        node.end_point = (0, 11)
        node.start_byte = 0
        node.end_byte = 11
        node.children = [alias_child, path_child]

        result = ext._extract_import_spec(node)
        assert result is not None
        assert result.alias == "myfmt"

    # ------------------------------------------------------------------ #
    # _extract_parameters
    # ------------------------------------------------------------------ #

    def test_extract_parameters_returns_list_of_strings(self) -> None:
        ext = self._make_extractor("(name string, age int)")
        self._cache(ext, 1, 12, "name string")

        param1 = MagicMock()
        param1.type = "parameter_declaration"
        param1.start_byte = 1
        param1.end_byte = 12

        params_node = MagicMock()
        params_node.children = [param1]

        node = MagicMock()
        node.child_by_field_name.side_effect = lambda name: params_node if name == "parameters" else None

        result = ext._extract_parameters(node)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "name string"

    def test_extract_parameters_empty_when_no_params_node(self) -> None:
        ext = self._make_extractor("()")
        node = MagicMock()
        node.child_by_field_name.return_value = None
        result = ext._extract_parameters(node)
        assert result == []

    # ------------------------------------------------------------------ #
    # _extract_return_type
    # ------------------------------------------------------------------ #

    def test_extract_return_type_returns_type_string(self) -> None:
        ext = self._make_extractor("string")
        self._cache(ext, 0, 6, "string")

        result_node = MagicMock()
        result_node.start_byte = 0
        result_node.end_byte = 6

        node = MagicMock()
        node.child_by_field_name.side_effect = lambda name: result_node if name == "result" else None

        result = ext._extract_return_type(node)
        assert result == "string"

    def test_extract_return_type_returns_empty_when_no_result(self) -> None:
        ext = self._make_extractor("")
        node = MagicMock()
        node.child_by_field_name.return_value = None
        result = ext._extract_return_type(node)
        assert result == ""


class TestGoPluginIntegration:
    """Integration tests for GoPlugin."""

    @pytest.fixture
    def plugin(self) -> GoPlugin:
        """Create a GoPlugin instance for testing."""
        return GoPlugin()

    def test_full_extraction_workflow(self, plugin: GoPlugin) -> None:
        """Test complete extraction workflow."""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, GoElementExtractor)

        # Test supports_file
        assert plugin.supports_file("main.go") is True
        assert plugin.supports_file("main.py") is False

        # Test plugin info
        info = plugin.get_plugin_info()
        assert info["language"] == "go"
        assert ".go" in info["extensions"]

    def test_plugin_consistency(self, plugin: GoPlugin) -> None:
        """Test plugin consistency across multiple calls."""
        for _ in range(5):
            assert plugin.get_language_name() == "go"
            assert ".go" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), GoElementExtractor)

    def test_extractor_independence(self, plugin: GoPlugin) -> None:
        """Test that extractors are independent instances."""
        extractor1 = plugin.create_extractor()
        extractor2 = plugin.create_extractor()

        assert extractor1 is not extractor2
        assert isinstance(extractor1, GoElementExtractor)
        assert isinstance(extractor2, GoElementExtractor)

    def test_plugin_with_various_go_files(self, plugin: GoPlugin) -> None:
        """Test plugin with various Go file paths."""
        go_files = [
            "main.go",
            "cmd/app/main.go",
            "/path/to/file.go",
            "TEST.GO",
            "test.Go",
        ]

        for go_file in go_files:
            assert plugin.supports_file(go_file) is True

        non_go_files = [
            "test.py",
            "test.rs",
            "test.java",
            "go.txt",
            "test.gohtml",
        ]

        for non_go_file in non_go_files:
            assert plugin.supports_file(non_go_file) is False


@pytest.mark.asyncio
async def test_full_flow_go() -> None:
    """Basic integration test with sample code."""
    try:
        import tree_sitter_go  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter-go not installed")

    plugin = GoPlugin()

    code = """
package sample

import (
    "context"
    "fmt"
)

// Config holds configuration options.
type Config struct {
    Host    string
    Port    int
    Timeout int
}

// Reader is an interface for reading data.
type Reader interface {
    Read(p []byte) (n int, err error)
}

// DefaultTimeout is the default timeout.
const DefaultTimeout = 30

// ErrNotFound is returned when not found.
var ErrNotFound = errors.New("not found")

// NewConfig creates a new Config instance.
func NewConfig() *Config {
    return &Config{
        Host: "localhost",
        Port: 8080,
    }
}

// Service represents a service.
type Service struct {
    config *Config
}

// Start starts the service.
func (s *Service) Start(ctx context.Context) error {
    go s.run(ctx)
    return nil
}

// run is the main service loop.
func (s *Service) run(ctx context.Context) {
    fmt.Println("running")
}
"""

    with patch(
        "tree_sitter_analyzer.encoding_utils.read_file_safe",
        return_value=(code, "utf-8"),
    ):
        result = await plugin.analyze_file("test.go", None)

        assert result.language == "go"
        assert len(result.elements) > 0

        # Check for specific elements
        funcs = [e for e in result.elements if isinstance(e, Function)]
        classes = [e for e in result.elements if isinstance(e, Class)]

        # Check functions
        func_names = [f.name for f in funcs]
        assert "NewConfig" in func_names
        assert "Start" in func_names
        assert "run" in func_names

        # Check structs/interfaces
        class_names = [c.name for c in classes]
        assert "Config" in class_names
        assert "Reader" in class_names
        assert "Service" in class_names

        # Check visibility
        new_config = next(f for f in funcs if f.name == "NewConfig")
        assert new_config.visibility == "public"

        run_func = next(f for f in funcs if f.name == "run")
        assert run_func.visibility == "private"

        # Check method receiver
        start_method = next(f for f in funcs if f.name == "Start")
        assert getattr(start_method, "is_method", False) is True
        assert getattr(start_method, "receiver_type", None) is not None

        # Check packages
        packages = [e for e in result.elements if isinstance(e, Package)]
        assert len(packages) > 0
        assert packages[0].name == "sample"

        # Check Go-specific metadata (goroutines)
        assert hasattr(result, "goroutines")
        assert len(result.goroutines) > 0  # Should detect "go s.run(ctx)"
