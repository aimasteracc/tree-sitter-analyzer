"""
Tests for tree_sitter_analyzer.languages.java_plugin module.

Canonical extraction tests: functions, classes, imports, variables.
All assertions pin CONCRETE values (specific names, counts, types, flags).
"""

from __future__ import annotations

import inspect
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.models import Class, Function, Variable
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_traversable_root(children=None):
    """Create a root Mock with a cursor-compatible interface.

    The returned root's ``.walk()`` yields a Mock cursor whose ``goto_*``
    methods return proper booleans so that ``java_traverse_and_extract``
    terminates instead of looping infinitely.

    Children are assigned distinct ``start_byte`` / ``end_byte`` values (if not
    already set) so that the ``(start_byte, end_byte)`` cache-key scheme in
    ``_java_traversal`` produces unique, deterministic keys.
    """
    children = list(children or [])
    root = Mock()
    root.children = children  # keep for code that accesses .children directly

    # Assign unique byte ranges for cache-key stability (only when not yet set)
    for i, child in enumerate(children):
        if isinstance(child.start_byte, Mock):
            child.start_byte = (i + 1) * 100
        if isinstance(child.end_byte, Mock):
            child.end_byte = (i + 1) * 100 + 50

    nodes = [root] + children
    state = [0]  # current cursor position index

    cursor = Mock()
    cursor.node = root  # initial position

    def _goto_first_child():
        """Descend to first child (only from root; children have no sub-children)."""
        if cursor.node is root and children:
            state[0] = 1
            cursor.node = nodes[1]
            return True
        return False

    def _goto_next_sibling():
        """Move to the next child of root."""
        if 0 < state[0] < len(nodes) - 1:
            state[0] += 1
            cursor.node = nodes[state[0]]
            return True
        return False

    def _goto_parent():
        """Climb back to root from any child."""
        if cursor.node is not root:
            state[0] = 0
            cursor.node = root
            return True
        return False

    cursor.goto_first_child = _goto_first_child
    cursor.goto_next_sibling = _goto_next_sibling
    cursor.goto_parent = _goto_parent

    root.walk.return_value = cursor
    return root


def _mock_tree(children=None):
    tree = Mock()
    root = _make_traversable_root(children)
    tree.root_node = root
    tree.language = Mock()
    return tree


# ---------------------------------------------------------------------------
# JavaElementExtractor — initialization & cache state
# ---------------------------------------------------------------------------


class TestJavaElementExtractorInit:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_extractor_is_element_extractor_subclass(self, extractor):
        assert isinstance(extractor, ElementExtractor)

    def test_required_methods_present(self, extractor):
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_initial_state_fields(self, extractor):
        assert extractor.current_package == ""
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor.imports == []
        assert isinstance(extractor._node_text_cache, dict)
        assert isinstance(extractor._processed_nodes, set)
        assert isinstance(extractor._element_cache, dict)
        assert extractor._file_encoding is None
        assert isinstance(extractor._annotation_cache, dict)
        assert isinstance(extractor._signature_cache, dict)
        assert isinstance(extractor.annotations, list)

    def test_reset_caches_clears_performance_caches(self, extractor):
        """_reset_caches() clears lookup caches but preserves self.annotations (source data)."""
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"
        extractor._annotation_cache[1] = [{"name": "Test"}]
        extractor._signature_cache[1] = "signature"
        extractor.annotations.append({"name": "Test"})

        extractor._reset_caches()

        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._annotation_cache) == 0
        assert len(extractor._signature_cache) == 0
        # annotations are source data, not cache — must survive
        assert len(extractor.annotations) == 1


# ---------------------------------------------------------------------------
# JavaElementExtractor — basic extraction (list type guarantees)
# ---------------------------------------------------------------------------


class TestJavaElementExtractorBasicExtraction:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_extract_all_return_empty_on_empty_code(self, extractor):
        """All extractors return [] for empty source and mock tree with no children."""
        tree = _mock_tree()
        assert extractor.extract_functions(tree, "") == []
        assert extractor.extract_classes(tree, "") == []
        assert extractor.extract_variables(tree, "") == []
        assert extractor.extract_imports(tree, "") == []
        assert extractor.extract_packages(tree, "") == []
        assert extractor.extract_annotations(tree, "") == []

    def test_extract_functions_no_language_returns_empty(self, extractor):
        tree = _mock_tree()
        tree.language = None
        assert extractor.extract_functions(tree, "test code") == []

    def test_extract_classes_calls_package_extraction_when_package_empty(
        self, extractor
    ):
        tree = _mock_tree()
        pkg_node = Mock()
        pkg_node.type = "package_declaration"
        cls_node = Mock()
        cls_node.type = "class_declaration"
        cls_node.children = []
        tree.root_node.children = [pkg_node, cls_node]
        extractor.current_package = ""

        with (
            patch.object(extractor, "_extract_package_from_tree") as mock_pkg,
            patch.object(extractor, "_traverse_and_extract_iterative"),
        ):
            extractor.extract_classes(tree, "")
        mock_pkg.assert_called_once_with(tree)


# ---------------------------------------------------------------------------
# JavaElementExtractor — fallback import extraction (concrete counts)
# ---------------------------------------------------------------------------


class TestImportFallbackExtraction:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_fallback_static_imports_count(self, extractor):
        src = """
        import static java.util.Collections.emptyList;
        import static org.junit.Assert.*;
        import static com.example.Utils.helper;
        """
        imports = extractor._extract_imports_fallback(src)
        assert len(imports) == 3

    def test_fallback_static_import_names(self, extractor):
        src = """
        import static java.util.Collections.emptyList;
        import static org.junit.Assert.*;
        import static com.example.Utils.helper;
        """
        imports = extractor._extract_imports_fallback(src)
        assert imports[0].name == "java.util.Collections"
        assert imports[0].is_static is True
        assert imports[0].is_wildcard is False
        assert imports[1].name == "org.junit.Assert"
        assert imports[1].is_static is True
        assert imports[1].is_wildcard is True
        assert imports[2].name == "com.example.Utils"
        assert imports[2].is_static is True
        assert imports[2].is_wildcard is False

    def test_fallback_normal_imports_count(self, extractor):
        src = """
        import java.util.List;
        import java.util.*;
        import javax.annotation.Nullable;
        """
        imports = extractor._extract_imports_fallback(src)
        assert len(imports) == 3

    def test_fallback_normal_import_names(self, extractor):
        src = """
        import java.util.List;
        import java.util.*;
        import javax.annotation.Nullable;
        """
        imports = extractor._extract_imports_fallback(src)
        assert imports[0].name == "java.util.List"
        assert imports[0].is_static is False
        assert imports[0].is_wildcard is False
        assert imports[1].name == "java.util"
        assert imports[1].is_static is False
        assert imports[1].is_wildcard is True
        assert imports[2].name == "javax.annotation.Nullable"
        assert imports[2].is_static is False
        assert imports[2].is_wildcard is False


# ---------------------------------------------------------------------------
# JavaElementExtractor — node text caching
# ---------------------------------------------------------------------------


class TestNodeTextCaching:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_node_text_caches_on_first_call(self, extractor):
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice",
            return_value="test text",
        ) as mock_extract:
            result1 = extractor._get_node_text_optimized(node)
            result2 = extractor._get_node_text_optimized(node)

        assert result1 == "test text"
        assert result2 == "test text"
        assert mock_extract.call_count == 1
        assert (node.start_byte, node.end_byte) in extractor._node_text_cache

    def test_node_text_fallback_on_exception(self, extractor):
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice",
            side_effect=Exception("err"),
        ):
            result = extractor._get_node_text_optimized(node)

        assert result == "test conte"

    def test_node_text_unicode_error_falls_back(self, extractor):
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        extractor.content_lines = ["test content"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice",
            side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "test"),
        ):
            result = extractor._get_node_text_optimized(node)
        assert result == "test conte"

    def test_node_text_index_error_returns_empty(self, extractor):
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (100, 0)
        node.end_point = (100, 10)
        extractor.content_lines = ["test content"]

        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice",
            side_effect=Exception("err"),
        ):
            result = extractor._get_node_text_optimized(node)
        assert result == ""


# ---------------------------------------------------------------------------
# JavaElementExtractor — _extract_class_optimized
# ---------------------------------------------------------------------------


def _build_class_mock_node() -> Mock:
    mock_node = Mock()
    mock_node.type = "class_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (10, 0)
    mock_modifiers = Mock()
    mock_modifiers.type = "modifiers"
    mock_annotation = Mock()
    mock_annotation.type = "marker_annotation"
    mock_annotation.start_point = (3, 0)
    mock_ann_identifier = Mock()
    mock_ann_identifier.type = "identifier"
    mock_annotation.children = [mock_ann_identifier]
    mock_modifiers.children = [mock_annotation]
    mock_identifier = Mock()
    mock_identifier.type = "identifier"
    mock_superclass = Mock()
    mock_superclass.type = "superclass"
    mock_interfaces = Mock()
    mock_interfaces.type = "super_interfaces"
    mock_node.children = [
        mock_modifiers,
        mock_identifier,
        mock_superclass,
        mock_interfaces,
    ]
    return mock_node


class TestExtractClassOptimized:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_class_without_name_returns_none(self, extractor):
        node = Mock()
        node.type = "class_declaration"
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        node.children = []
        assert extractor._extract_class_optimized(node) is None

    def test_class_with_none_identifier_returns_none(self, extractor):
        node = Mock()
        node.type = "class_declaration"
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        mock_id = Mock()
        mock_id.type = "identifier"
        node.children = [mock_id]
        with patch.object(extractor, "_get_node_text_optimized", return_value=None):
            assert extractor._extract_class_optimized(node) is None

    @pytest.mark.parametrize(
        "exc",
        [
            AttributeError("err"),
            ValueError("err"),
            TypeError("err"),
            RuntimeError("err"),
        ],
    )
    def test_class_exception_returns_none(self, extractor, exc):
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        node.children = []
        with patch.object(extractor, "_extract_modifiers_optimized", side_effect=exc):
            assert extractor._extract_class_optimized(node) is None

    # Full extraction field assertions are in test_java_regression.py::TestExtractorFieldValues


# ---------------------------------------------------------------------------
# JavaElementExtractor — _extract_method_optimized
# ---------------------------------------------------------------------------


class TestExtractMethodOptimized:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_method_none_signature_returns_none(self, extractor):
        node = Mock()
        node.type = "method_declaration"
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        with patch.object(
            extractor, "_parse_method_signature_optimized", return_value=None
        ):
            assert extractor._extract_method_optimized(node) is None

    @pytest.mark.parametrize(
        "exc", [AttributeError("err"), ValueError("err"), TypeError("err")]
    )
    def test_method_exception_returns_none(self, extractor, exc):
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        with patch.object(
            extractor, "_parse_method_signature_optimized", side_effect=exc
        ):
            assert extractor._extract_method_optimized(node) is None

    def test_exception_raises_class_name_error_returns_none(self, extractor):
        node = Mock()
        node.type = "method_declaration"
        node.start_point = (0, 0)
        node.end_point = (10, 0)
        node.children = []
        with patch.object(
            extractor, "_extract_class_name", side_effect=Exception("err")
        ):
            result = extractor._extract_method_optimized(node)
        assert result is None

    # Full method/constructor field assertions in test_java_regression.py::TestExtractorFieldValues


# ---------------------------------------------------------------------------
# JavaElementExtractor — _extract_field_optimized
# ---------------------------------------------------------------------------


class TestExtractFieldOptimized:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_field_none_declaration_returns_empty_list(self, extractor):
        node = Mock()
        node.type = "field_declaration"
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        with patch.object(
            extractor, "_parse_field_declaration_optimized", return_value=None
        ):
            assert extractor._extract_field_optimized(node) == []

    @pytest.mark.parametrize(
        "exc",
        [
            AttributeError("err"),
            ValueError("err"),
            TypeError("err"),
            RuntimeError("err"),
        ],
    )
    def test_field_exception_returns_empty_list(self, extractor, exc):
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        with patch.object(
            extractor, "_parse_field_declaration_optimized", side_effect=exc
        ):
            assert extractor._extract_field_optimized(node) == []

    # Full field extraction assertions are in test_java_regression.py::TestExtractorFieldValues


# ---------------------------------------------------------------------------
# JavaElementExtractor — traverse
# ---------------------------------------------------------------------------


class TestJavaElementExtractorTraverse:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_traverse_extracts_method_and_class(self, extractor):
        child1 = Mock()
        child1.type = "method_declaration"
        child1.children = []
        child2 = Mock()
        child2.type = "class_declaration"
        child2.children = []
        root = _make_traversable_root([child1, child2])

        fn = Function(
            name="m", start_line=1, end_line=3, raw_text="void m(){}", language="java"
        )
        cls = Class(
            name="C", start_line=5, end_line=10, raw_text="class C{}", language="java"
        )

        results = []
        extractor._traverse_and_extract_iterative(
            root,
            {
                "method_declaration": Mock(return_value=fn),
                "class_declaration": Mock(return_value=cls),
            },
            results,
            "mixed",
        )
        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_uses_element_cache(self, extractor):
        child = Mock()
        child.type = "method_declaration"
        child.children = []
        child.start_byte = 10
        child.end_byte = 60
        root = _make_traversable_root([child])
        cached = Function(
            name="cached_method",
            start_line=1,
            end_line=2,
            raw_text="void cached_method(){}",
            language="java",
        )
        # Cache key format: ((start_byte, end_byte), element_type)
        extractor._element_cache[((10, 60), "method")] = cached
        mock_fn = Mock()
        results = []
        extractor._traverse_and_extract_iterative(
            root, {"method_declaration": mock_fn}, results, "method"
        )
        assert len(results) == 1
        assert results[0] == cached
        assert mock_fn.call_count == 0

    def test_traverse_field_batching_15_nodes(self, extractor):
        nodes = [Mock() for _ in range(15)]
        for i, n in enumerate(nodes):
            n.type = "field_declaration"
            n.children = []
            n.start_byte = (i + 1) * 100
            n.end_byte = (i + 1) * 100 + 50
        root = _make_traversable_root(nodes)

        def _extract(node):
            return [
                Variable(
                    name=f"f_{id(node)}",
                    start_line=1,
                    end_line=1,
                    raw_text="private String f;",
                    language="java",
                )
            ]

        results = []
        extractor._traverse_and_extract_iterative(
            root, {"field_declaration": _extract}, results, "field"
        )
        assert len(results) == 15

    def test_process_field_batch_cache_hit(self, extractor):
        node = Mock()
        node.type = "field_declaration"
        node.start_byte = 0
        node.end_byte = 30
        cached = [
            Variable(
                name="cached_field",
                start_line=1,
                end_line=1,
                raw_text="private String cached_field;",
                language="java",
            )
        ]
        # Cache key format matches _java_traversal: ((start_byte, end_byte), "field")
        extractor._element_cache[((0, 30), "field")] = cached
        mock_fn = Mock()
        results = []
        extractor._process_field_batch([node], {"field_declaration": mock_fn}, results)
        assert len(results) == 1
        assert results[0].name == "cached_field"
        assert mock_fn.call_count == 0


# ---------------------------------------------------------------------------
# JavaElementExtractor — class name extraction
# ---------------------------------------------------------------------------


class TestClassNameExtraction:
    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_extract_class_name_found(self, extractor):
        node = Mock()
        mock_id = Mock()
        mock_id.type = "identifier"
        mock_id.text = b"TestClass"
        node.children = [mock_id]
        with patch.object(
            extractor, "_get_node_text_optimized", return_value="TestClass"
        ):
            assert extractor._extract_class_name(node) == "TestClass"

    def test_extract_class_name_no_identifier(self, extractor):
        node = Mock()
        node.children = []
        assert extractor._extract_class_name(node) is None


# ---------------------------------------------------------------------------
# JavaPlugin — initialization & interface
# ---------------------------------------------------------------------------


class TestJavaPluginInit:
    @pytest.fixture
    def plugin(self):
        return JavaPlugin()

    def test_plugin_is_language_plugin_subclass(self, plugin):
        assert isinstance(plugin, LanguagePlugin)

    def test_plugin_required_methods(self, plugin):
        assert hasattr(plugin, "get_language_name")
        assert hasattr(plugin, "get_file_extensions")
        assert hasattr(plugin, "create_extractor")

    def test_language_is_java(self, plugin):
        assert plugin.language == "java"

    def test_java_extension_supported(self, plugin):
        assert ".java" in plugin.supported_extensions

    def test_get_plugin_info_returns_java(self, plugin):
        info = plugin.get_plugin_info()
        assert info["language"] == "java"
        assert ".java" in info["extensions"]


# ---------------------------------------------------------------------------
# JavaPlugin — language caching
# ---------------------------------------------------------------------------


class TestJavaPluginLanguage:
    @pytest.fixture
    def plugin(self):
        return JavaPlugin()

    def test_get_tree_sitter_language_returns_mock(self, plugin):
        with (
            patch("tree_sitter_java.language") as mock_lang,
            patch("tree_sitter.Language") as mock_lang_cls,
        ):
            mock_obj = Mock()
            mock_lang.return_value = mock_obj
            mock_lang_cls.return_value = mock_obj
            result = plugin.get_tree_sitter_language()
        assert result is mock_obj

    def test_language_caching_calls_once(self, plugin):
        with (
            patch("tree_sitter_java.language") as mock_lang,
            patch("tree_sitter.Language") as mock_lang_cls,
        ):
            mock_obj = Mock()
            mock_lang.return_value = mock_obj
            mock_lang_cls.return_value = mock_obj
            lang1 = plugin.get_tree_sitter_language()
            lang2 = plugin.get_tree_sitter_language()
        assert lang1 is lang2
        mock_lang.assert_called_once()

    def test_language_import_error_returns_none(self, plugin):
        with patch("tree_sitter_java.language", side_effect=ImportError("not found")):
            result = plugin.get_tree_sitter_language()
        assert result is None


# ---------------------------------------------------------------------------
# JavaPlugin — is_applicable
# ---------------------------------------------------------------------------


class TestJavaPluginIsApplicable:
    @pytest.fixture
    def plugin(self):
        return JavaPlugin()

    def test_java_files_are_applicable(self, plugin):
        for path in [
            "Test.java",
            "com/example/Test.java",
            "src/main/java/Test.java",
            "TEST.JAVA",
            "test.Java",
        ]:
            assert plugin.is_applicable(path) is True, path

    def test_non_java_files_not_applicable(self, plugin):
        for path in [
            "test.py",
            "test.js",
            "test.cpp",
            "test.txt",
            "java.txt",
        ]:
            assert plugin.is_applicable(path) is False, path


# ---------------------------------------------------------------------------
# JavaPlugin — extract_elements error handling
# ---------------------------------------------------------------------------


class TestJavaPluginExtractElements:
    @pytest.fixture
    def plugin(self):
        return JavaPlugin()

    def test_extract_elements_none_tree_returns_empty_dicts(self, plugin):
        result = plugin.extract_elements(None, "public class Test {}")
        expected_keys = {
            "functions",
            "classes",
            "variables",
            "imports",
            "packages",
            "annotations",
        }
        assert expected_keys <= set(result.keys())
        for key in expected_keys:
            assert result[key] == []

    def test_extract_elements_invalid_tree_returns_empty(self, plugin):
        tree = Mock()
        tree.root_node = None
        result = plugin.extract_elements(tree, "public class Test {}")
        expected_keys = {
            "functions",
            "classes",
            "variables",
            "imports",
            "packages",
            "annotations",
        }
        for key in expected_keys:
            assert result[key] == []

    def test_extract_elements_exception_falls_back_to_empty(self, plugin):
        tree = _mock_tree()
        mock_ext = Mock()
        for m in [
            "extract_functions",
            "extract_classes",
            "extract_variables",
            "extract_imports",
            "extract_packages",
            "extract_annotations",
        ]:
            getattr(mock_ext, m).side_effect = Exception("err")
        # Patch create_extractor — extract_elements calls this, not self.extractor
        with patch.object(plugin, "create_extractor", return_value=mock_ext):
            result = plugin.extract_elements(tree, "public class Test {}")
        for key in {
            "functions",
            "classes",
            "variables",
            "imports",
            "packages",
            "annotations",
        }:
            assert result[key] == []

    def test_extract_elements_with_mocked_return_values(self, plugin):
        tree = _mock_tree()
        mock_ext = Mock()
        mock_ext.extract_functions.return_value = []
        mock_ext.extract_classes.return_value = []
        mock_ext.extract_variables.return_value = []
        mock_ext.extract_imports.return_value = []
        mock_ext.extract_packages.return_value = []
        mock_ext.extract_annotations.return_value = []
        # Patch create_extractor — extract_elements calls this, not self.extractor
        with patch.object(plugin, "create_extractor", return_value=mock_ext):
            result = plugin.extract_elements(tree, "public class Test {}")
        assert "functions" in result
        assert "classes" in result


# ---------------------------------------------------------------------------
# JavaPlugin — analyze_file
# ---------------------------------------------------------------------------


class TestJavaPluginAnalyzeFile:
    @pytest.fixture
    def plugin(self):
        return JavaPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin):
        java_code = """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name
        try:
            mock_req = Mock()
            mock_req.file_path = temp_path
            mock_req.language = "java"
            mock_req.include_complexity = False
            mock_req.include_details = False
            result = await plugin.analyze_file(temp_path, mock_req)
            assert result is not None
            assert hasattr(result, "success")
            assert hasattr(result, "file_path")
            assert hasattr(result, "language")
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file_returns_failure(self, plugin):
        mock_req = Mock()
        mock_req.file_path = "/nonexistent/file.java"
        mock_req.language = "java"
        result = await plugin.analyze_file("/nonexistent/file.java", mock_req)
        assert result is not None
        assert result.success is False

    @pytest.mark.asyncio
    async def test_analyze_file_read_error_returns_failure(self, plugin):
        java_code = "public class Test {}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name
        try:
            mock_req = Mock()
            mock_req.file_path = temp_path
            mock_req.language = "java"
            with patch(
                "tree_sitter_analyzer.encoding_utils.read_file_safe_async",
                side_effect=Exception("Read error"),
            ):
                result = await plugin.analyze_file(temp_path, mock_req)
            assert result is not None
            assert result.success is False
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# JavaPlugin — consistency
# ---------------------------------------------------------------------------


class TestJavaPluginConsistency:
    @pytest.fixture
    def plugin(self):
        return JavaPlugin()

    def test_create_extractor_returns_java_element_extractor(self, plugin):
        assert isinstance(plugin.create_extractor(), JavaElementExtractor)

    def test_repeated_calls_give_consistent_results(self, plugin):
        for _ in range(5):
            assert plugin.get_language_name() == "java"
            assert ".java" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), JavaElementExtractor)

    def test_multiple_extractors_are_independent(self, plugin):
        e1 = plugin.create_extractor()
        e2 = plugin.create_extractor()
        assert e1 is not e2
        assert isinstance(e1, JavaElementExtractor)
        assert isinstance(e2, JavaElementExtractor)


def _parse_java_treewalk(src):
    """解析真实 Java 语法；核心 grammar 缺失必须失败。"""
    import tree_sitter

    language = JavaPlugin().get_tree_sitter_language()
    if language is None:
        pytest.fail("PR #1350：测试必需的 tree-sitter-java grammar 缺失或加载失败。")
    parser = tree_sitter.Parser(language)
    tree = parser.parse(src.encode())
    assert tree.root_node.has_error is False
    return tree


def _java_treewalk_nodes(tree, node_type):
    """用完整游标遍历定位独立提取器的输入节点。"""
    cursor = tree.walk()
    nodes = []
    while True:
        if cursor.node.type == node_type:
            nodes.append(cursor.node)
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                return nodes


class TestCursorApiTraversal:
    def test_no_direct_children_access(self):
        from tree_sitter_analyzer.languages import _java_traversal

        assert "reversed(" not in inspect.getsource(_java_traversal)

    def test_named_descendants_inside_control_flow(self):
        # PR #1350：控制流与任意表达式不能截断 named 后代遍历。
        from tree_sitter_analyzer.languages._java_traversal import (
            java_traverse_and_extract,
        )

        tree = _parse_java_treewalk(
            "class Foo { void run() { if (ready) { stream.map(x -> x); } } }"
        )
        results = []
        java_traverse_and_extract(
            tree.root_node,
            {"identifier": lambda n: n.text.decode()},
            results,
            "identifier",
            set(),
            {},
            log_warning_func=Mock(),
            log_debug_func=Mock(),
        )
        assert results == ["Foo", "run", "ready", "stream", "map", "x", "x"]

    def test_subtree_traversal_does_not_visit_sibling_method(self):
        from tree_sitter_analyzer.languages._java_traversal import (
            java_traverse_and_extract,
        )

        tree = _parse_java_treewalk("class Foo { void first() {} void second() {} }")
        root = _java_treewalk_nodes(tree, "method_declaration")[0]
        results = []
        java_traverse_and_extract(
            root,
            {"identifier": lambda n: n.text.decode()},
            results,
            "identifier",
            set(),
            {},
            log_warning_func=Mock(),
            log_debug_func=Mock(),
        )
        assert results == ["first"]


class TestLambdaExtraction:
    _SRC = """class Foo {
        void run() {
            Runnable r = () -> System.out.println("hello");
            java.util.function.Function<String, Integer> f = s -> s.length();
            java.util.function.BiFunction<Integer, Integer, Integer> add = (x, y) -> x + y;
        }
    }"""

    def test_lambda_extracted_as_function(self):
        from tree_sitter_analyzer.languages._java_element import extract_lambda_function

        nodes = _java_treewalk_nodes(
            _parse_java_treewalk(self._SRC), "lambda_expression"
        )
        assert len(nodes) == 3
        result = extract_lambda_function(
            nodes[0], lambda n: n.text.decode(), self._SRC.splitlines()
        )
        assert (result.name, result.is_method, result.language) == (
            "<lambda>",
            True,
            "java",
        )

    def test_lambda_parameters_extracted(self):
        from tree_sitter_analyzer.languages._java_element import extract_lambda_function

        nodes = _java_treewalk_nodes(
            _parse_java_treewalk(self._SRC), "lambda_expression"
        )
        assert len(nodes) == 3
        result = extract_lambda_function(
            nodes[2], lambda n: n.text.decode(), self._SRC.splitlines()
        )
        assert result.parameters == ["x", "y"]

    @pytest.mark.parametrize(
        ("declaration", "expected"),
        [
            ("()", []),
            ("x", ["x"]),
            ("(x)", ["x"]),
            ("(x, y)", ["x", "y"]),
            ("(String text, int count)", ["String text", "int count"]),
            (
                "(@Deprecated String text, final int count)",
                ["@Deprecated String text", "final int count"],
            ),
            ("(var value)", ["var value"]),
            (
                "(java.util.Map<String, Integer> value)",
                ["java.util.Map<String, Integer> value"],
            ),
            ("(String... values)", ["String... values"]),
        ],
    )
    def test_public_lambda_parameter_forms(self, declaration, expected):
        # PR #1350：保留完整参数文本，尤其不能把合法 varargs 误报成零参数。
        src = f"class Demo {{ void run() {{ consume({declaration} -> work()); }} }}"
        functions = JavaElementExtractor().extract_functions(
            _parse_java_treewalk(src), src
        )
        assert [(f.name, f.parameters) for f in functions] == [
            ("run", []),
            ("<lambda>", expected),
        ]

    @pytest.mark.parametrize(
        ("statement", "parameters"),
        [
            ("stream.map(x -> x);", [["x"]]),
            ("consume(() -> work());", [[]]),
            ("Object f = (x -> x);", [["x"]]),
            ("Object f = flag ? x -> x : y -> y;", [["x"], ["y"]]),
            ("consume((flag ? (x -> wrap(() -> x)) : (y -> y)));", [["x"], [], ["y"]]),
            ("f = x -> x;", [["x"]]),
            ("return x -> x;", [["x"]]),
            ("consume((Runnable) () -> work());", [[]]),
            ("boolean same = ((Runnable) (() -> work())) == other;", [[]]),
            (
                "Runnable[] tasks = new Runnable[]{() -> work(), () -> work()};",
                [[], []],
            ),
            ("consume(new Runnable[]{() -> work()}[0]);", [[]]),
            ("if (ready) consume(() -> work());", [[]]),
            ("for (Runnable r : new Runnable[]{() -> work()}) consume(r);", [[]]),
            ("Object f = switch (n) { default -> (Runnable) () -> work(); };", [[]]),
        ],
    )
    def test_nested_expression_lambdas(self, statement, parameters):
        # PR #1350：公开提取入口必须穿透所有表达式与控制流，且不重复。
        src = f"class Foo {{ void run() {{ {statement} }} }}"
        functions = JavaElementExtractor().extract_functions(
            _parse_java_treewalk(src), src
        )
        assert [f.name for f in functions] == ["run"] + ["<lambda>"] * len(parameters)
        assert [f.parameters for f in functions if f.name == "<lambda>"] == parameters


class TestStaticInitializerExtraction:
    _SRC = """class InitDemo {
        static final int X;
        static { X = 1; }
        static { System.out.println("second static init"); }
    }"""

    def test_static_initializer_extracted(self):
        from tree_sitter_analyzer.languages._java_element import (
            extract_static_initializer,
        )

        nodes = _java_treewalk_nodes(
            _parse_java_treewalk(self._SRC), "static_initializer"
        )
        assert len(nodes) == 2
        result = extract_static_initializer(nodes[0], self._SRC.splitlines())
        assert (result.name, result.is_static, result.is_method) == (
            "<static_initializer>",
            True,
            True,
        )

    def test_multiple_static_initializers(self):
        from tree_sitter_analyzer.languages._java_element import (
            extract_static_initializer,
        )

        nodes = _java_treewalk_nodes(
            _parse_java_treewalk(self._SRC), "static_initializer"
        )
        assert len(nodes) == 2
        results = [extract_static_initializer(n, self._SRC.splitlines()) for n in nodes]
        assert [r.start_line for r in results] == [3, 4]

    def test_static_initializer_via_extract_functions(self):
        functions = JavaElementExtractor().extract_functions(
            _parse_java_treewalk(self._SRC), self._SRC
        )
        assert [f.name for f in functions] == [
            "<static_initializer>",
            "<static_initializer>",
        ]


class TestAnonymousClassExtraction:
    def test_anonymous_class_extracted(self):
        from tree_sitter_analyzer.languages._java_element import extract_anonymous_class

        src = "class Demo { void run() { Runnable r = new Runnable() { public void run() {} }; } }"
        nodes = _java_treewalk_nodes(
            _parse_java_treewalk(src), "object_creation_expression"
        )
        bodies = [c for n in nodes for c in n.children if c.type == "class_body"]
        assert len(bodies) == 1
        result = extract_anonymous_class(
            bodies[0], lambda n: n.text.decode(), src.splitlines(), ""
        )
        assert (result.name, result.class_type, result.is_nested) == (
            "<anonymous>",
            "anonymous",
            True,
        )


class TestCompactConstructorExtraction:
    _SRC = """record Range(int min, int max) {
        Range { if (min > max) throw new IllegalArgumentException("min > max"); }
    }"""

    def test_compact_constructor_extracted(self):
        from tree_sitter_analyzer.languages._java_element import (
            extract_compact_constructor,
        )

        nodes = _java_treewalk_nodes(
            _parse_java_treewalk(self._SRC), "compact_constructor_declaration"
        )
        assert len(nodes) == 1
        result = extract_compact_constructor(
            nodes[0], lambda n: n.text.decode(), self._SRC.splitlines()
        )
        assert (result.name, result.is_constructor) == ("Range", True)

    def test_compact_constructor_via_extract_functions(self):
        functions = JavaElementExtractor().extract_functions(
            _parse_java_treewalk(self._SRC), self._SRC
        )
        assert [f.name for f in functions if f.is_constructor] == ["Range"]


class TestSealedClassPermits:
    def test_permits_clause_in_interfaces(self):
        src = "sealed class Shape permits Circle, Rectangle {} final class Circle extends Shape {} final class Rectangle extends Shape {}"
        classes = JavaElementExtractor().extract_classes(_parse_java_treewalk(src), src)
        sealed = next(c for c in classes if c.name == "Shape")
        assert sealed.interfaces == ["Circle", "Rectangle"]


class TestGenericTypeExtraction:
    _SRC = """import java.util.Map;
        import java.util.List;
        class GenericDemo {
            public Map<String, List<Integer>> getMap() { return null; }
            Map<String, Integer> simpleMap;
        }"""

    def test_nested_generic_type_complete_text(self):
        functions = JavaElementExtractor().extract_functions(
            _parse_java_treewalk(self._SRC), self._SRC
        )
        assert [(f.name, f.return_type) for f in functions] == [
            ("getMap", "Map<String, List<Integer>>")
        ]

    def test_field_generic_type_complete_text(self):
        variables = JavaElementExtractor().extract_variables(
            _parse_java_treewalk(self._SRC), self._SRC
        )
        assert [(v.name, v.variable_type) for v in variables] == [
            ("simpleMap", "Map<String, Integer>")
        ]


class TestJavadocAst:
    _SRC = """class Documented {
        /** Returns the answer. */
        public int getAnswer() { return 42; }
        public String noDoc() { return "x"; }
    }"""

    def test_javadoc_from_ast_sibling(self):
        from tree_sitter_analyzer.languages._java_element import (
            _extract_javadoc_from_node,
        )

        nodes = _java_treewalk_nodes(
            _parse_java_treewalk(self._SRC), "method_declaration"
        )
        assert len(nodes) == 2
        assert nodes[0].child_by_field_name("name").text == b"getAnswer"
        doc = _extract_javadoc_from_node(nodes[0], lambda n: n.text.decode())
        assert "Returns the answer" in doc

    def test_javadoc_fallback_when_no_block_comment(self):
        functions = JavaElementExtractor().extract_functions(
            _parse_java_treewalk(self._SRC), self._SRC
        )
        assert next(f for f in functions if f.name == "noDoc").docstring is None


class TestAnonymousClassViaExtractClasses:
    _SRC = (
        "public class Outer { Runnable r = new Runnable() { public void run() {} }; }"
    )

    def test_anonymous_class_via_extract_classes(self):
        classes = JavaElementExtractor().extract_classes(
            _parse_java_treewalk(self._SRC), self._SRC
        )
        assert [
            (c.name, c.is_nested) for c in classes if c.class_type == "anonymous"
        ] == [("<anonymous>", True)]

    def test_regular_classes_not_affected(self):
        classes = JavaElementExtractor().extract_classes(
            _parse_java_treewalk(self._SRC), self._SRC
        )
        assert [(c.name, c.class_type) for c in classes if c.name == "Outer"] == [
            ("Outer", "class")
        ]


class TestModuleDeclarationExtraction:
    def test_module_declaration_extracted(self):
        src = "module com.example { }"
        packages = JavaElementExtractor().extract_packages(
            _parse_java_treewalk(src), src
        )
        assert [p.name for p in packages] == ["com.example"]

    def test_module_declaration_language_field(self):
        src = "module com.example { }"
        packages = JavaElementExtractor().extract_packages(
            _parse_java_treewalk(src), src
        )
        assert [(p.name, p.language) for p in packages] == [("com.example", "java")]

    def test_reused_extractor_does_not_reuse_module_name(self):
        # PR #1350：等长模块名占据相同字节范围，不得复用上一份源码的文本缓存。
        extractor = JavaElementExtractor()
        names = []
        for src in ("open module one.api {}", "open module two.api {}"):
            packages = extractor.extract_packages(_parse_java_treewalk(src), src)
            names.append([(p.name, p.language) for p in packages])
        assert names == [[("one.api", "java")], [("two.api", "java")]]

    def test_public_module_with_directives_is_not_a_package_list(self):
        src = "open module app.core { requires java.base; exports app.api; uses app.Service; }"
        elements = JavaPlugin().extract_elements(_parse_java_treewalk(src), src)
        assert [(p.name, p.start_line, p.end_line) for p in elements["packages"]] == [
            ("app.core", 1, 1)
        ]
        assert elements["functions"] == []
        assert elements["classes"] == []

    @pytest.mark.parametrize(
        "source", ["module app.core {}", "open module app.core { exports app.api; }"]
    )
    def test_exported_package_helper_agrees_with_plugin(self, source):
        # PR #1350：已导出的 standalone helper 与插件模块入口必须保持一致。
        from tree_sitter_analyzer.languages.java_helpers import extract_java_packages

        tree = _parse_java_treewalk(source)
        standalone = extract_java_packages(tree, lambda node: node.text.decode("utf-8"))
        plugin = JavaPlugin().extract_elements(tree, source)["packages"]
        assert [(p.name, p.language, p.start_line, p.end_line) for p in standalone] == [
            ("app.core", "java", 1, 1)
        ]
        assert [(p.name, p.language, p.start_line, p.end_line) for p in plugin] == [
            ("app.core", "java", 1, 1)
        ]


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("int min, int max", ["int min", "int max"]),
        (
            "@Deprecated String value, int... rest",
            ["@Deprecated String value", "int... rest"],
        ),
        ("", []),
    ],
)
def test_public_record_compact_constructor_has_header_parameters(header, expected):
    # PR #1350：紧凑构造器的隐式参数来自 record 头，不是空参数构造器。
    src = f"public record Data({header}) {{ @Deprecated public Data {{ if (true) work(); }} }}"
    elements = JavaPlugin().extract_elements(_parse_java_treewalk(src), src)
    assert [(c.name, c.class_type) for c in elements["classes"]] == [("Data", "record")]
    assert len(elements["functions"]) == 1
    constructor = elements["functions"][0]
    assert (
        constructor.name,
        constructor.is_constructor,
        constructor.parameters,
        constructor.visibility,
        constructor.complexity_score,
    ) == ("Data", True, expected, "public", 2)
    assert [a["name"] for a in constructor.annotations] == ["Deprecated"]


def test_public_annotation_ownership_does_not_bleed_to_neighbors():
    # PR #1350：同一行的类、方法与参数注解应按 AST 所属节点归属。
    src = '@interface Flag { String value() default "x"; } @Flag("demo") class Demo { @Deprecated void run(@Flag("arg") String arg) {} void plain() {} }'
    elements = JavaPlugin().extract_elements(_parse_java_treewalk(src), src)
    assert [
        (c.name, c.class_type, [a["name"] for a in c.annotations])
        for c in elements["classes"]
    ] == [("Flag", "annotation", []), ("Demo", "class", ["Flag"])]
    assert [
        (f.name, [a["name"] for a in f.annotations]) for f in elements["functions"]
    ] == [("run", ["Deprecated"]), ("plain", [])]


@pytest.mark.parametrize("src", ["module { }", "record { }", "@"])
def test_public_malformed_java_does_not_invent_elements(src):
    # PR #1350：使用真实错误树验证公开容错入口，不伪造 Node 异常。
    import tree_sitter

    parser = tree_sitter.Parser(JavaPlugin().get_tree_sitter_language())
    tree = parser.parse(src.encode())
    assert tree.root_node.has_error is True
    assert JavaPlugin().extract_elements(tree, src) == {
        "functions": [],
        "classes": [],
        "variables": [],
        "imports": [],
        "packages": [],
        "annotations": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("open module app.core { requires java.base; }", [("Package", "app.core")]),
        ("record R(int value) { R {} }", [("Function", "R"), ("Class", "R")]),
        ("@Deprecated class Demo {}", [("Class", "Demo")]),
    ],
)
async def test_modern_java_through_analyze_file(tmp_path, source, expected):
    # PR #1350：实际文件入口必须走同一提取链，不能只让测试兼容入口可用。
    from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

    path = tmp_path / "Example.java"
    path.write_text(source, encoding="utf-8")
    result = await JavaPlugin().analyze_file(
        str(path), AnalysisRequest(file_path=str(path))
    )
    assert (result.success, result.language, result.source_code) == (
        True,
        "java",
        source,
    )
    assert [
        (type(element).__name__, element.name) for element in result.elements
    ] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [AttributeError, TypeError])
@pytest.mark.parametrize(
    ("source", "parent_type"),
    [
        ("class Demo { void run() { consume(x -> x); } }", "lambda_expression"),
        ("record R(int value) { R {} }", "compact_constructor_declaration"),
        ("module app.core {}", "module_declaration"),
    ],
)
async def test_leaf_protocol_error_reaches_plugin_boundary(
    tmp_path, monkeypatch, source, parent_type, error_type
):
    # PR #1350：树由真实 parser 生成；仅注入已绑定文本适配器的程序错误，不能静默少报元素。
    from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

    read_text = JavaElementExtractor._get_node_text_optimized

    def broken_adapter(self, node):
        if node.parent is not None and node.parent.type == parent_type:
            raise error_type("broken node-text adapter")
        return read_text(self, node)

    monkeypatch.setattr(
        JavaElementExtractor, "_get_node_text_optimized", broken_adapter
    )
    path = tmp_path / "Example.java"
    path.write_text(source, encoding="utf-8")
    result = await JavaPlugin().analyze_file(
        str(path), AnalysisRequest(file_path=str(path))
    )
    assert (result.success, result.error_message, result.elements) == (
        False,
        "broken node-text adapter",
        [],
    )


def test_exported_module_helper_propagates_adapter_protocol_error():
    # PR #1350：保留导出入口，但不把适配器错误伪装成不存在模块。
    from tree_sitter_analyzer.languages.java_helpers import extract_java_packages

    tree = _parse_java_treewalk("module app.core {}")

    def broken_adapter(node):
        assert node.text == b"app.core"
        raise TypeError("broken node-text adapter")

    with pytest.raises(TypeError, match="^broken node-text adapter$"):
        extract_java_packages(tree, broken_adapter)
