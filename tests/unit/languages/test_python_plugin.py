#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.python_plugin module.

This module tests the PythonPlugin class which provides Python language
support in the new plugin architecture.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.python_plugin import (
    PythonElementExtractor,
    PythonPlugin,
)
from tree_sitter_analyzer.models import Class, Function, Import, Variable
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


class TestPythonElementExtractor:
    """Test cases for PythonElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        """Create a PythonElementExtractor instance for testing"""
        return PythonElementExtractor()

    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_python_code(self) -> str:
        """Sample Python code for testing"""
        return '''
import os
import sys
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class Person:
    """A person with name and age"""
    name: str
    age: int = 0

class Calculator:
    """Calculator class for basic arithmetic operations"""

    def __init__(self, initial_value: int = 0):
        """Initialize calculator with initial value"""
        self.value = initial_value
        self._history = []

    def add(self, number: int) -> int:
        """Add a number to the current value"""
        self.value += number
        self._history.append(f"add {number}")
        return self.value

    def subtract(self, number: int) -> int:
        """Subtract a number from the current value"""
        self.value -= number
        self._history.append(f"subtract {number}")
        return self.value

    @property
    def history(self) -> List[str]:
        """Get calculation history"""
        return self._history.copy()

    @staticmethod
    def validate_number(value) -> bool:
        """Validate if value is a number"""
        return isinstance(value, (int, float))

    @classmethod
    def from_string(cls, value_str: str) -> 'Calculator':
        """Create calculator from string value"""
        return cls(int(value_str))

def main():
    """Main function"""
    calc = Calculator(10)
    result = calc.add(5)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
'''

    def test_extractor_initialization(self, extractor: PythonElementExtractor) -> None:
        """Test PythonElementExtractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, ElementExtractor)
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_core_elements_success(
        self, extractor: PythonElementExtractor, mock_tree: Mock
    ) -> None:
        """Test successful extraction of the core Python element families."""
        cases = (
            ("functions", {"function.definition": []}, extractor.extract_functions),
            ("classes", {"class.definition": []}, extractor.extract_classes),
            ("variables", {"variable.assignment": []}, extractor.extract_variables),
            ("imports", {"import.statement": []}, extractor.extract_imports),
        )
        for label, captures, extract in cases:
            mock_query = Mock()
            mock_tree.language.query.return_value = mock_query
            mock_query.captures.return_value = captures

            result = extract(mock_tree, "test code")

            assert isinstance(result, list), label

    def test_extract_functions_no_language(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test function extraction when language is not available"""
        mock_tree = Mock()
        mock_tree.language = None
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        functions = extractor.extract_functions(mock_tree, "test code")

        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_detailed_function_info(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test detailed function information extraction"""
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        with (
            patch.object(extractor, "_extract_name_from_node") as mock_extract_name,
            patch.object(
                extractor, "_extract_parameters_from_node"
            ) as mock_extract_params,
            patch.object(
                extractor, "_extract_decorators_from_node"
            ) as mock_extract_decorators,
            patch.object(
                extractor, "_extract_return_type_from_node"
            ) as mock_extract_return,
            patch.object(
                extractor, "_extract_docstring_from_node"
            ) as mock_extract_docstring,
            patch.object(extractor, "_extract_function_body") as mock_extract_body,
        ):
            mock_extract_name.return_value = "test_function"
            mock_extract_params.return_value = ["param1: int", "param2: str"]
            mock_extract_decorators.return_value = ["property"]
            mock_extract_return.return_value = "int"
            mock_extract_docstring.return_value = "Test function"
            mock_extract_body.return_value = "return value"

            result = extractor._extract_detailed_function_info(mock_node, "test code")

            assert result is not None
            assert isinstance(result, Function)
            assert result.name == "test_function"
            assert result.parameters == ["param1: int", "param2: str"]
            assert result.modifiers == ["property"]
            assert result.return_type == "int"

    def test_extract_detailed_class_info(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test detailed class information extraction"""
        mock_node = Mock()
        mock_node.type = "class_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []

        with (
            patch.object(extractor, "_extract_name_from_node") as mock_extract_name,
            patch.object(
                extractor, "_extract_superclasses_from_node"
            ) as mock_extract_super,
            patch.object(
                extractor, "_extract_decorators_from_node"
            ) as mock_extract_decorators,
            patch.object(
                extractor, "_extract_docstring_from_node"
            ) as mock_extract_docstring,
        ):
            mock_extract_name.return_value = "TestClass"
            mock_extract_super.return_value = ["BaseClass", "Mixin"]
            mock_extract_decorators.return_value = ["dataclass"]
            mock_extract_docstring.return_value = "Test class"

            result = extractor._extract_detailed_class_info(mock_node, "test code")

            assert result is not None
            assert isinstance(result, Class)
            assert result.name == "TestClass"
            assert result.superclass == "BaseClass"
            assert result.interfaces == ["Mixin"]
            assert result.modifiers == ["dataclass"]

    def test_extract_variable_info(self, extractor: PythonElementExtractor) -> None:
        """Test variable information extraction"""
        mock_node = Mock()
        mock_node.type = "assignment"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.children = []

        with patch.object(extractor, "_validate_node") as mock_validate:
            mock_validate.return_value = True

            result = extractor._extract_variable_info(
                mock_node, "test_var = 42", "assignment"
            )

            assert result is not None
            assert isinstance(result, Variable)
            assert result.name == "test_var"

    def test_extract_import_info(self, extractor: PythonElementExtractor) -> None:
        """Test import information extraction"""
        mock_node = Mock()
        mock_node.type = "import_statement"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 9
        mock_node.children = []

        with patch.object(extractor, "_validate_node") as mock_validate:
            mock_validate.return_value = True

            result = extractor._extract_import_info(mock_node, "import os", "import")

            assert result is not None
            assert isinstance(result, Import)
            assert "os" in result.name

    def test_extract_name_from_node(self, extractor: PythonElementExtractor) -> None:
        """Test name extraction from node"""
        mock_node = Mock()
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.start_byte = 0
        mock_identifier.end_byte = 9
        mock_node.children = [mock_identifier]

        name = extractor._extract_name_from_node(mock_node, "test_name")

        assert name == "test_name"

    def test_extract_name_from_node_no_identifier(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test name extraction when no identifier is found"""
        mock_node = Mock()
        mock_node.children = []

        name = extractor._extract_name_from_node(mock_node, "test code")

        assert name is None

    def test_extract_parameters_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test parameter extraction from function node"""
        mock_node = Mock()
        mock_params_node = Mock()
        mock_param1 = Mock()
        mock_param1.type = "identifier"
        mock_param1.start_byte = 0
        mock_param1.end_byte = 10
        mock_param2 = Mock()
        mock_param2.type = "typed_parameter"
        mock_param2.start_byte = 12
        mock_param2.end_byte = 22
        mock_params_node.children = [mock_param1, mock_param2]
        mock_params_node.type = "parameters"
        mock_node.children = [mock_params_node]

        parameters = extractor._extract_parameters_from_node(
            mock_node, "param1: int, param2: str"
        )

        assert isinstance(parameters, list)
        assert len(parameters) == 2

    def test_extract_decorators_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test decorator extraction from node"""
        mock_node = Mock()
        mock_node.parent = None

        decorators = extractor._extract_decorators_from_node(mock_node, "test code")

        assert isinstance(decorators, list)

    def test_extract_return_type_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test return type extraction from function node"""
        mock_node = Mock()
        mock_type_node = Mock()
        mock_type_node.type = "type"
        mock_type_node.start_byte = 0
        mock_type_node.end_byte = 3
        mock_node.children = [mock_type_node]

        return_type = extractor._extract_return_type_from_node(mock_node, "int")

        assert return_type == "int"

    def test_extract_docstring_from_node(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test docstring extraction from node"""
        mock_node = Mock()
        mock_block = Mock()
        mock_block.type = "block"
        mock_stmt = Mock()
        mock_stmt.type = "expression_statement"
        mock_expr = Mock()
        mock_expr.type = "string"
        mock_expr.start_byte = 0
        mock_expr.end_byte = 25
        mock_stmt.children = [mock_expr]
        mock_block.children = [mock_stmt]
        mock_node.children = [mock_block]

        with patch.object(extractor, "_validate_node") as mock_validate:
            mock_validate.return_value = True

            docstring = extractor._extract_docstring_from_node(
                mock_node, '"""This is a docstring"""'
            )

            assert docstring == "This is a docstring"

    def test_calculate_complexity(self, extractor: PythonElementExtractor) -> None:
        """Test complexity calculation"""
        simple_body = "return value"
        complex_body = """
if condition:
    for item in items:
        while running:
            try:
                process(item)
            except Exception:
                handle_error()
            finally:
                cleanup()
"""

        simple_complexity = extractor._calculate_complexity(simple_body)
        complex_complexity = extractor._calculate_complexity(complex_body)

        assert isinstance(simple_complexity, int)
        assert isinstance(complex_complexity, int)
        assert complex_complexity > simple_complexity


class TestPythonPlugin:
    """Test cases for PythonPlugin class"""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        """Create a PythonPlugin instance for testing"""
        return PythonPlugin()

    def test_plugin_initialization(self, plugin: PythonPlugin) -> None:
        """Test PythonPlugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, LanguagePlugin)
        assert hasattr(plugin, "get_language_name")
        assert hasattr(plugin, "get_file_extensions")
        assert hasattr(plugin, "create_extractor")

    def test_get_tree_sitter_language(self, plugin: PythonPlugin) -> None:
        """Test getting tree-sitter language"""
        with (
            patch("tree_sitter_python.language") as mock_language,
            patch("tree_sitter.Language") as mock_tree_sitter_language,
        ):
            mock_capsule = Mock()
            mock_language.return_value = mock_capsule

            mock_lang_obj = Mock()
            mock_tree_sitter_language.return_value = mock_lang_obj

            language = plugin.get_tree_sitter_language()

            assert language is mock_lang_obj
            mock_tree_sitter_language.assert_called_once_with(mock_capsule)

    def test_get_tree_sitter_language_caching(self, plugin: PythonPlugin) -> None:
        """Test tree-sitter language caching"""
        with (
            patch("tree_sitter_python.language") as mock_language,
            patch("tree_sitter.Language") as mock_tree_sitter_language,
        ):
            mock_capsule = Mock()
            mock_language.return_value = mock_capsule

            mock_lang_obj = Mock()
            mock_tree_sitter_language.return_value = mock_lang_obj

            # First call
            language1 = plugin.get_tree_sitter_language()

            # Second call (should use cache)
            language2 = plugin.get_tree_sitter_language()

            assert language1 is language2
            # Should only be called once due to caching
            mock_language.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin: PythonPlugin) -> None:
        """Test successful file analysis"""
        python_code = """
class TestClass:
    def test_method(self):
        print("Hello")
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_code)
            temp_path = f.name

        try:
            # Mock AnalysisRequest
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "python"
            mock_request.include_complexity = False
            mock_request.include_details = False

            result = await plugin.analyze_file(temp_path, mock_request)

            assert result is not None
            assert hasattr(result, "success")
            assert hasattr(result, "file_path")
            assert hasattr(result, "language")

        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_nonexistent(self, plugin: PythonPlugin) -> None:
        """Test analysis of non-existent file"""
        mock_request = Mock()
        mock_request.file_path = "/nonexistent/file.py"
        mock_request.language = "python"

        result = await plugin.analyze_file("/nonexistent/file.py", mock_request)

        # Should return an AnalysisResult with success=False instead of raising
        assert result is not None
        assert hasattr(result, "success")
        assert result.success is False


class TestPythonPluginErrorHandling:
    """Test error handling in PythonPlugin"""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        """Create a PythonPlugin instance for testing"""
        return PythonPlugin()

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        """Create a PythonElementExtractor instance for testing"""
        return PythonElementExtractor()

    def test_extract_functions_with_exception(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test function extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        functions = extractor.extract_functions(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_with_exception(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test class extraction with exception"""
        mock_tree = Mock()
        mock_tree.language = None  # This will cause the extraction to fail gracefully
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        classes = extractor.extract_classes(mock_tree, "test code")

        # Should handle gracefully
        assert isinstance(classes, list)
        assert len(classes) == 0

    def test_extract_detailed_function_info_with_exception(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test detailed function info extraction with exception"""
        mock_node = Mock()

        with patch.object(extractor, "_extract_name_from_node") as mock_extract_name:
            mock_extract_name.side_effect = Exception("Extraction error")

            result = extractor._extract_detailed_function_info(mock_node, "test code")

            # Should handle gracefully
            assert result is None

    def test_get_tree_sitter_language_failure(self, plugin: PythonPlugin) -> None:
        """Test tree-sitter language loading failure"""
        with patch("tree_sitter_python.language") as mock_language:
            mock_language.side_effect = ImportError("Module not found")

            language = plugin.get_tree_sitter_language()

            assert language is None

    @pytest.mark.asyncio
    async def test_analyze_file_with_exception(self, plugin: PythonPlugin) -> None:
        """Test file analysis with exception"""
        python_code = "class Test: pass"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_code)
            temp_path = f.name

        try:
            mock_request = Mock()
            mock_request.file_path = temp_path
            mock_request.language = "python"

            with patch(
                "tree_sitter_analyzer.encoding_utils.read_file_safe_async"
            ) as mock_read:
                mock_read.side_effect = Exception("Read error")

                result = await plugin.analyze_file(temp_path, mock_request)

                # Should return error result instead of raising
                assert result is not None
                assert hasattr(result, "success")
                assert result.success is False

        finally:
            os.unlink(temp_path)


class TestPythonPluginIntegration:
    """Integration tests for PythonPlugin"""

    @pytest.fixture
    def plugin(self) -> PythonPlugin:
        """Create a PythonPlugin instance for testing"""
        return PythonPlugin()

    def test_full_extraction_workflow(self, plugin: PythonPlugin) -> None:
        """Test complete extraction workflow"""
        # Test that plugin can handle complex Python code

        # Test that plugin can handle complex Python code
        extractor = plugin.create_extractor()
        assert isinstance(extractor, PythonElementExtractor)

        # Test applicability
        assert plugin.is_applicable("calculator.py") is True
        assert plugin.is_applicable("calculator.java") is False

        # Test plugin info
        info = plugin.get_plugin_info()
        assert info["language"] == "python"
        assert ".py" in info["extensions"]

    def test_plugin_consistency(self, plugin: PythonPlugin) -> None:
        """Test plugin consistency across multiple calls"""
        # Multiple calls should return consistent results
        for _ in range(5):
            assert plugin.get_language_name() == "python"
            assert ".py" in plugin.get_file_extensions()
            assert isinstance(plugin.create_extractor(), PythonElementExtractor)

    def test_extractor_consistency(self, plugin: PythonPlugin) -> None:
        """Test extractor consistency"""
        # Multiple extractors should be independent
        extractor1 = plugin.create_extractor()
        extractor2 = plugin.create_extractor()

        assert extractor1 is not extractor2
        assert isinstance(extractor1, PythonElementExtractor)
        assert isinstance(extractor2, PythonElementExtractor)

    def test_plugin_with_various_python_files(self, plugin: PythonPlugin) -> None:
        """Test plugin with various Python file types"""
        python_files = [
            "test.py",
            "test.pyi",
            "test.pyw",
            "src/test.py",
            "package/__init__.py",
            "TEST.PY",  # Case variations
            "test.Py",
        ]

        for python_file in python_files:
            assert plugin.is_applicable(python_file) is True

        non_python_files = [
            "test.java",
            "test.js",
            "test.cpp",
            "test.txt",
            "python.txt",  # Contains 'python' but wrong extension
        ]

        for non_python_file in non_python_files:
            assert plugin.is_applicable(non_python_file) is False

    def test_python_specific_features(self, plugin: PythonPlugin) -> None:
        """Test Python-specific features"""
        extractor = plugin.create_extractor()

        # Test that extractor has Python-specific methods
        assert hasattr(extractor, "_extract_decorators_from_node")
        assert hasattr(extractor, "_extract_docstring_from_node")
        assert hasattr(extractor, "_extract_return_type_from_node")

        # Test complexity calculation with Python-specific constructs
        python_complex_code = """
async def async_function():
    async with context_manager():
        async for item in async_iterator():
            if condition:
                try:
                    await process(item)
                except Exception as e:
                    logger.error(f"Error: {e}")
                finally:
                    cleanup()
"""

        complexity = extractor._calculate_complexity(python_complex_code)
        assert isinstance(complexity, int)
        assert complexity == 5  # async with + async for + if + try + except = 5

    def test_python_import_variations(self, plugin: PythonPlugin) -> None:
        """Test Python import statement variations"""
        from tree_sitter_analyzer.languages.python_plugin import PythonElementExtractor

        extractor = plugin.create_extractor()
        assert isinstance(extractor, PythonElementExtractor)


# ---------------------------------------------------------------------------
# Tests migrated from test_python_plugin_coverage_boost.py
# ---------------------------------------------------------------------------


def _parse_py(plugin, code):
    import tree_sitter

    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


class TestPythonExtractImportsManual:
    """Behavioral tests for _extract_imports_manual."""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    @pytest.fixture
    def extractor(self):
        return PythonElementExtractor()

    def test_simple_import_names(self, extractor, plugin):
        code = "import os\nimport sys\n"
        tree = _parse_py(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert len(imports) == 2
        names = [i.name for i in imports]
        assert "os" in names
        assert "sys" in names

    def test_from_import_module_and_names(self, extractor, plugin):
        code = "from os.path import join, exists\n"
        tree = _parse_py(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert len(imports) == 1
        imp = imports[0]
        assert imp.module_name == "os.path"
        assert "join" in imp.imported_names
        assert "exists" in imp.imported_names

    def test_from_import_single_module(self, extractor, plugin):
        code = "from collections import OrderedDict\n"
        tree = _parse_py(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert len(imports) == 1
        assert "collections" in imports[0].module_name

    def test_empty_code_returns_empty(self, extractor, plugin):
        code = ""
        tree = _parse_py(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert imports == []

    def test_no_imports_returns_empty(self, extractor, plugin):
        code = "x = 1\ny = 2\n"
        tree = _parse_py(plugin, code)
        imports = extractor._extract_imports_manual(tree.root_node, code)
        assert imports == []


class TestPythonExtractPackages:
    """Behavioral tests for extract_packages."""

    @pytest.fixture
    def extractor(self):
        return PythonElementExtractor()

    def test_with_init_file_returns_package_name(self, extractor):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, "mypkg")
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
                f.write("# package\n")
            with open(os.path.join(pkg_dir, "mod.py"), "w") as f:
                f.write("x = 1\n")

            extractor.current_file = os.path.join(pkg_dir, "mod.py")
            plugin = PythonPlugin()
            tree = _parse_py(plugin, "# test\n")
            packages = extractor.extract_packages(tree, "")
            assert len(packages) == 1
            assert packages[0].name == "mypkg"

    def test_no_init_file_returns_empty(self, extractor):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor.current_file = os.path.join(tmpdir, "mod.py")
            plugin = PythonPlugin()
            tree = _parse_py(plugin, "# test\n")
            packages = extractor.extract_packages(tree, "")
            assert packages == []


class TestPythonGetNodeTypeForElement:
    """Behavioral tests for _get_node_type_for_element."""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    def test_function_returns_function_definition(self, plugin):
        from tree_sitter_analyzer.models import Function

        assert (
            plugin._get_node_type_for_element(Function("f", 1, 1, "def f(): pass"))
            == "function_definition"
        )

    def test_class_returns_class_definition(self, plugin):
        from tree_sitter_analyzer.models import Class

        assert (
            plugin._get_node_type_for_element(Class("C", 1, 1, "class C: pass"))
            == "class_definition"
        )

    def test_variable_returns_assignment(self, plugin):
        from tree_sitter_analyzer.models import Variable

        assert (
            plugin._get_node_type_for_element(Variable("x", 1, 1, "x = 1"))
            == "assignment"
        )

    def test_import_returns_import_statement(self, plugin):
        from tree_sitter_analyzer.models import Import

        assert (
            plugin._get_node_type_for_element(Import("os", 1, 1, "import os"))
            == "import_statement"
        )

    def test_unknown_type_returns_unknown(self, plugin):
        assert plugin._get_node_type_for_element("not_an_element") == "unknown"


class TestPythonExtractFunctionBodyBehavioral:
    """Behavioral tests for _extract_function_body."""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    @pytest.fixture
    def extractor(self):
        return PythonElementExtractor()

    def test_function_body_contains_statements(self, extractor, plugin):
        code = "def f():\n    x = 1\n    return x\n"
        tree = _parse_py(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) == 1
        body = extractor._extract_function_body(func_nodes[0], code)
        assert "x = 1" in body


class TestPythonExtractSuperclassesBehavioral:
    """Behavioral tests for _extract_superclasses_from_node."""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    @pytest.fixture
    def extractor(self):
        return PythonElementExtractor()

    def test_with_superclass_returns_name(self, extractor, plugin):
        code = "class Child(Base):\n    pass\n"
        tree = _parse_py(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        class_nodes = find_nodes(tree.root_node, "class_definition")
        assert len(class_nodes) == 1
        supers = extractor._extract_superclasses_from_node(class_nodes[0], code)
        assert "Base" in supers


class TestPythonComplexityBehavioral:
    """Behavioral tests for _calculate_complexity with branches."""

    @pytest.fixture
    def extractor(self):
        return PythonElementExtractor()

    def test_simple_body_complexity_is_one(self, extractor):
        body = "x = 1"
        assert extractor._calculate_complexity(body) == 1

    def test_branched_body_complexity(self, extractor):
        body = "if x:\n    pass\nelif y:\n    pass\nfor i in range(10):\n    pass"
        c = extractor._calculate_complexity(body)
        assert c == 3


class TestPythonDetailedFunctionPrivacy:
    """Behavioral tests for is_private on _extract_detailed_function_info."""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    @pytest.fixture
    def extractor(self):
        return PythonElementExtractor()

    def test_dunder_method_is_not_private(self, extractor, plugin):
        code = "class C:\n    def __init__(self):\n        pass\n"
        tree = _parse_py(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) == 1
        info = extractor._extract_detailed_function_info(func_nodes[0], code)
        assert info is not None
        assert info.name == "__init__"
        assert info.is_private is False

    def test_single_underscore_method_is_private(self, extractor, plugin):
        code = "class C:\n    def _internal(self):\n        pass\n"
        tree = _parse_py(plugin, code)

        def find_nodes(node, node_type):
            result = []
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                result.extend(find_nodes(child, node_type))
            return result

        func_nodes = find_nodes(tree.root_node, "function_definition")
        assert len(func_nodes) == 1
        info = extractor._extract_detailed_function_info(func_nodes[0], code)
        assert info is not None
        assert info.name == "_internal"
        assert info.is_private is True


class TestPythonGetElementCategories:
    """Behavioral tests for get_element_categories."""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    def test_returns_required_category_keys(self, plugin):
        cats = plugin.get_element_categories()
        assert isinstance(cats, dict)
        assert "function" in cats
        assert "class" in cats
        assert "import" in cats
        assert "lambda" in cats
        assert "decorator" in cats
        assert "comprehension" in cats


class TestPythonGetSupportedQueries:
    """Behavioral tests for get_supported_queries."""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    def test_supported_queries_keys(self, plugin):
        queries = plugin.get_supported_queries()
        assert "function" in queries
        assert "class" in queries
        assert "async_function" in queries
        assert "lambda" in queries
        assert "django_model" in queries
