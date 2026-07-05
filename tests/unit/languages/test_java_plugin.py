"""
Tests for tree_sitter_analyzer.languages.java_plugin module.

Canonical extraction tests: functions, classes, imports, variables.
All assertions pin CONCRETE values (specific names, counts, types, flags).
"""

from __future__ import annotations

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


def _mock_tree(children=None):
    tree = Mock()
    root = Mock()
    root.children = children or []
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
        root = Mock()
        child1 = Mock()
        child1.type = "method_declaration"
        child1.children = []
        child2 = Mock()
        child2.type = "class_declaration"
        child2.children = []
        root.children = [child1, child2]

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
        root = Mock()
        child = Mock()
        child.type = "method_declaration"
        child.children = []
        root.children = [child]
        cached = Function(
            name="cached_method",
            start_line=1,
            end_line=2,
            raw_text="void cached_method(){}",
            language="java",
        )
        extractor._element_cache[(id(child), "method")] = cached
        mock_fn = Mock()
        results = []
        extractor._traverse_and_extract_iterative(
            root, {"method_declaration": mock_fn}, results, "method"
        )
        assert len(results) == 1
        assert results[0] == cached
        assert mock_fn.call_count == 0

    def test_traverse_field_batching_15_nodes(self, extractor):
        root = Mock()
        nodes = [Mock() for _ in range(15)]
        for n in nodes:
            n.type = "field_declaration"
            n.children = []
        root.children = nodes

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
        extractor._element_cache[(id(node), "field")] = cached
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
        methods = [
            "extract_functions",
            "extract_classes",
            "extract_variables",
            "extract_imports",
            "extract_packages",
            "extract_annotations",
        ]
        with patch.object(plugin, "extractor") as mock_ext:
            for m in methods:
                getattr(mock_ext, m).side_effect = Exception("err")
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
        with (
            patch.object(plugin.extractor, "extract_functions", return_value=[]),
            patch.object(plugin.extractor, "extract_classes", return_value=[]),
            patch.object(plugin.extractor, "extract_variables", return_value=[]),
            patch.object(plugin.extractor, "extract_imports", return_value=[]),
            patch.object(plugin.extractor, "extract_packages", return_value=[]),
            patch.object(plugin.extractor, "extract_annotations", return_value=[]),
        ):
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
