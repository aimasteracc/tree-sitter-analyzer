#!/usr/bin/env python3
"""
Property-based tests for Go support.

Covering:
- Property 1: Go Element Extraction Completeness (Requirements 1.1, 1.2, 1.3, 1.4)
- Property 7: Go-Specific Terminology (Requirements 1.8)
"""

from unittest.mock import MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter
from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor
from tree_sitter_analyzer.models import AnalysisResult, Class, Function

# --- Strategies ---


@st.composite
def go_visibilities(draw: st.DrawFn) -> str:
    """Generates Go visibility based on name capitalization."""
    # In Go, visibility is determined by capitalization
    return draw(st.sampled_from(["public", "private"]))


@st.composite
def go_types(draw: st.DrawFn) -> str:
    """Generates simple Go types."""
    return draw(
        st.sampled_from(
            [
                "string",
                "int",
                "int64",
                "float64",
                "bool",
                "error",
                "[]byte",
                "[]string",
                "map[string]interface{}",
                "*Config",
            ]
        )
    )


@st.composite
def go_function_nodes(draw: st.DrawFn) -> dict:
    """Generates a mock tree-sitter node representing a Go function."""
    # Generate name with first letter determining visibility
    # Go exported/unexported is based on ASCII uppercase/lowercase
    is_exported = draw(st.booleans())
    if is_exported:
        # Start with uppercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest
    else:
        # Start with lowercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest

    if not name:
        name = "testFunc" if not is_exported else "TestFunc"

    return_type = draw(st.one_of(st.none(), go_types()))

    # Create mock node
    node = MagicMock()
    node.type = "function_declaration"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 5, 0)
    node.start_byte = 0
    node.end_byte = 100

    # Name child
    name_node = MagicMock()
    name_node.text = name.encode("utf-8")

    # Return type child
    ret_node = None
    if return_type:
        ret_node = MagicMock()
        ret_node.text = return_type.encode("utf-8")

    # Parameters child
    params_node = MagicMock()
    params_node.children = []

    # child_by_field_name side effects
    def get_child_by_field(field: str) -> MagicMock | None:
        if field == "name":
            return name_node
        if field == "result":
            return ret_node
        if field == "parameters":
            return params_node
        return None

    node.child_by_field_name = MagicMock(side_effect=get_child_by_field)
    node.children = []

    return {
        "node": node,
        "name": name,
        "visibility": "public" if is_exported else "private",
        "return_type": return_type if return_type else "",
    }


@st.composite
def go_method_nodes(draw: st.DrawFn) -> dict:
    """Generates a mock tree-sitter node representing a Go method."""
    # Go exported/unexported is based on ASCII uppercase/lowercase
    is_exported = draw(st.booleans())
    if is_exported:
        # Start with uppercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest
    else:
        # Start with lowercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest

    if not name:
        name = "testMethod" if not is_exported else "TestMethod"

    receiver_type = draw(st.sampled_from(["*Service", "Service", "*Config", "Handler"]))

    # Create mock node
    node = MagicMock()
    node.type = "method_declaration"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 5, 0)
    node.start_byte = 0
    node.end_byte = 100

    # Name child
    name_node = MagicMock()
    name_node.text = name.encode("utf-8")

    # Receiver child
    receiver_node = MagicMock()
    receiver_node.text = f"(s {receiver_type})".encode()

    # Parameters child
    params_node = MagicMock()
    params_node.children = []

    def get_child_by_field(field: str) -> MagicMock | None:
        if field == "name":
            return name_node
        if field == "receiver":
            return receiver_node
        if field == "parameters":
            return params_node
        if field == "result":
            return None
        return None

    node.child_by_field_name = MagicMock(side_effect=get_child_by_field)
    node.children = []

    return {
        "node": node,
        "name": name,
        "visibility": "public" if is_exported else "private",
        "receiver_type": receiver_type,
    }


@st.composite
def go_struct_nodes(draw: st.DrawFn) -> dict:
    """Generates a mock tree-sitter node representing a Go struct."""
    # Go exported/unexported is based on ASCII uppercase/lowercase
    is_exported = draw(st.booleans())
    if is_exported:
        # Start with uppercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest
    else:
        # Start with lowercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest

    if not name:
        name = "testStruct" if not is_exported else "TestStruct"

    # Create mock type_spec node (Go uses type_spec for struct/interface)
    node = MagicMock()
    node.type = "type_spec"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 3, 0)
    node.start_byte = 0
    node.end_byte = 50

    name_node = MagicMock()
    name_node.text = name.encode("utf-8")

    type_node = MagicMock()
    type_node.type = "struct_type"
    type_node.children = []

    def get_child_by_field(field: str) -> MagicMock | None:
        if field == "name":
            return name_node
        if field == "type":
            return type_node
        return None

    node.child_by_field_name = MagicMock(side_effect=get_child_by_field)
    node.children = []

    return {
        "node": node,
        "name": name,
        "visibility": "public" if is_exported else "private",
    }


@st.composite
def go_interface_nodes(draw: st.DrawFn) -> dict:
    """Generates a mock tree-sitter node representing a Go interface."""
    # Go exported/unexported is based on ASCII uppercase/lowercase
    is_exported = draw(st.booleans())
    if is_exported:
        # Start with uppercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest
    else:
        # Start with lowercase ASCII letter, followed by alphanumeric
        first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
        rest = draw(
            st.text(
                min_size=0,
                max_size=19,
                alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            )
        )
        name = first_char + rest

    if not name:
        name = "testInterface" if not is_exported else "TestInterface"

    node = MagicMock()
    node.type = "type_spec"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 3, 0)
    node.start_byte = 0
    node.end_byte = 50

    name_node = MagicMock()
    name_node.text = name.encode("utf-8")

    type_node = MagicMock()
    type_node.type = "interface_type"
    type_node.children = []

    def get_child_by_field(field: str) -> MagicMock | None:
        if field == "name":
            return name_node
        if field == "type":
            return type_node
        return None

    node.child_by_field_name = MagicMock(side_effect=get_child_by_field)
    node.children = []

    return {
        "node": node,
        "name": name,
        "visibility": "public" if is_exported else "private",
    }


class TestGoElementExtractionProperties:
    """Property tests for Go element extraction completeness."""

    @given(data=go_function_nodes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_1_go_function_extraction_completeness(self, data: dict) -> None:
        """
        Property 1: Go Element Extraction Completeness (Functions)

        Validates that given a well-formed function node, the extractor correctly
        populates the Function model with Go-specific attributes.
        Requirements: 1.1, 1.2
        """
        extractor = GoElementExtractor()
        extractor.source_code = "package main\n\nfunc test() {}"
        extractor.content_lines = extractor.source_code.split("\n")

        def mock_get_text(n: MagicMock) -> str:
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            func = extractor._extract_function(data["node"])

            assert func is not None
            assert func.name == data["name"]
            assert func.language == "go"
            assert func.visibility == data["visibility"]
            assert func.return_type == data["return_type"]

    @given(data=go_method_nodes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_1_go_method_extraction_completeness(self, data: dict) -> None:
        """
        Property 1: Go Element Extraction Completeness (Methods)

        Validates that given a well-formed method node, the extractor correctly
        populates the Function model with Go-specific method attributes.
        Requirements: 1.2 (methods with receiver)
        """
        extractor = GoElementExtractor()
        extractor.source_code = "package main\n\nfunc (s *Service) test() {}"
        extractor.content_lines = extractor.source_code.split("\n")

        def mock_get_text(n: MagicMock) -> str:
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            method = extractor._extract_method(data["node"])

            assert method is not None
            assert method.name == data["name"]
            assert method.language == "go"
            assert method.visibility == data["visibility"]
            # Check Go-specific method attributes
            assert getattr(method, "is_method", False) is True
            assert getattr(method, "receiver_type", None) is not None

    @given(data=go_struct_nodes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_1_go_struct_extraction_completeness(self, data: dict) -> None:
        """
        Property 1: Go Element Extraction Completeness (Structs)

        Validates that given a well-formed struct node, the extractor correctly
        populates the Class model.
        Requirements: 1.3
        """
        extractor = GoElementExtractor()
        extractor.source_code = "package main\n\ntype Test struct {}"
        extractor.content_lines = extractor.source_code.split("\n")

        def mock_get_text(n: MagicMock) -> str:
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            cls = extractor._extract_type_spec(data["node"])

            assert cls is not None
            assert cls.name == data["name"]
            assert cls.class_type == "struct"
            assert cls.language == "go"
            assert cls.visibility == data["visibility"]

    @given(data=go_interface_nodes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_1_go_interface_extraction_completeness(self, data: dict) -> None:
        """
        Property 1: Go Element Extraction Completeness (Interfaces)

        Validates that given a well-formed interface node, the extractor correctly
        populates the Class model.
        Requirements: 1.4
        """
        extractor = GoElementExtractor()
        extractor.source_code = "package main\n\ntype Test interface {}"
        extractor.content_lines = extractor.source_code.split("\n")

        def mock_get_text(n: MagicMock) -> str:
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            cls = extractor._extract_type_spec(data["node"])

            assert cls is not None
            assert cls.name == data["name"]
            assert cls.class_type == "interface"
            assert cls.language == "go"
            assert cls.visibility == data["visibility"]


class TestGoTerminologyProperties:
    """Property tests for Go-specific terminology."""

    @given(
        funcs=st.lists(
            st.builds(
                Function,
                name=st.text(min_size=1),
                start_line=st.integers(1),
                end_line=st.integers(1),
            ),
            max_size=5,
        ),
        structs=st.lists(
            st.builds(
                Class,
                name=st.text(min_size=1),
                start_line=st.integers(1),
                end_line=st.integers(1),
                class_type=st.just("struct"),
            ),
            max_size=5,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_go_terminology_full_format(
        self, funcs: list[Function], structs: list[Class]
    ) -> None:
        """
        Property 7: Go-Specific Terminology (Full Format)

        Validates that the Go formatter output contains Go-specific terminology
        like 'package', 'func', 'struct', 'interface'.
        Requirements: 1.8
        """
        result = AnalysisResult(
            file_path="test.go",
            language="go",
            elements=funcs + structs,
            line_count=100,
        )

        formatter = GoTableFormatter()
        output = formatter.format_table(result.to_dict(), table_type="full")

        # Go-specific terminology checks
        if funcs:
            assert "## Functions" in output
            assert "| Func |" in output or "Func" in output

        if structs:
            assert "## Structs" in output

        # Check for Go-specific section headers
        assert "## Package Info" in output or "Package" in output

    @given(
        funcs=st.lists(
            st.builds(
                Function,
                name=st.text(min_size=1),
                start_line=st.integers(1),
                end_line=st.integers(1),
            ),
            max_size=5,
        )
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_go_terminology_compact_format(
        self, funcs: list[Function]
    ) -> None:
        """
        Property 7: Go-Specific Terminology (Compact Format)

        Validates that the Go compact formatter uses Go-specific short forms.
        Requirements: 1.8
        """
        result = AnalysisResult(
            file_path="test.go",
            language="go",
            elements=funcs,
            line_count=100,
        )

        formatter = GoTableFormatter()
        output = formatter.format_summary(result.to_dict())

        # Compact Go terminology
        if funcs:
            assert "## Funcs" in output or "Func" in output

        # Should use "Package" not "Module"
        assert "Module" not in output or "Package" in output

    @given(
        interfaces=st.lists(
            st.builds(
                Class,
                name=st.text(min_size=1),
                start_line=st.integers(1),
                end_line=st.integers(1),
                class_type=st.just("interface"),
            ),
            max_size=3,
        )
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_property_7_go_interface_terminology(self, interfaces: list[Class]) -> None:
        """
        Property 7: Go-Specific Terminology (Interfaces)

        Validates interface-specific Go terminology.
        Requirements: 1.8
        """
        result = AnalysisResult(
            file_path="test.go",
            language="go",
            elements=interfaces,
            line_count=100,
        )

        formatter = GoTableFormatter()
        output = formatter.format_table(result.to_dict(), table_type="full")

        if interfaces:
            assert "## Interfaces" in output

    def test_property_7_go_visibility_terminology(self) -> None:
        """
        Property 7: Go-Specific Terminology (Visibility)

        Validates that Go uses 'exported/unexported' visibility terms.
        Requirements: 1.8
        """
        # Create functions with different visibility
        exported_func = Function(
            name="ExportedFunc",
            start_line=1,
            end_line=3,
        )
        unexported_func = Function(
            name="unexportedFunc",
            start_line=5,
            end_line=7,
        )

        result = AnalysisResult(
            file_path="test.go",
            language="go",
            elements=[exported_func, unexported_func],
            line_count=100,
        )

        formatter = GoTableFormatter()
        output = formatter.format_table(result.to_dict(), table_type="full")

        # Go uses 'exported' and 'unexported' terminology
        # The formatter should show visibility in table
        assert "Vis" in output or "exported" in output or "unexported" in output
