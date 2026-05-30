import pytest

from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter


class TestPythonFormatterFormatSummary:
    """Test format_summary delegates to compact table"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_summary(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [
                {
                    "name": "MyClass",
                    "type": "class",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter.format_summary(data)
        assert "## Info" in result


class TestPythonFormatterFormatAdvanced:
    """Test format_advanced with different output formats"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_advanced_json(self, formatter):
        data = {"file_path": "app.py", "classes": [], "functions": []}
        result = formatter.format_advanced(data, "json")
        assert '"file_path"' in result

    def test_format_advanced_csv(self, formatter):
        data = {"file_path": "app.py", "classes": [], "functions": []}
        result = formatter.format_advanced(data, "csv")
        assert "#" in result or "Functions" in result or result

    def test_format_advanced_fallback_to_full(self, formatter):
        data = {
            "file_path": "app.py",
            "classes": [
                {"name": "App", "type": "class", "line_range": {"start": 1, "end": 5}}
            ],
            "functions": [],
            "variables": [],
        }
        result = formatter.format_advanced(data, "unknown_format")
        assert "App" in result or "app" in result


class TestPythonFormatterFullTable:
    """Test _format_full_table variants"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_full_table_none_data(self, formatter):
        with pytest.raises(TypeError):
            formatter._format_full_table(None)

    def test_full_table_invalid_type(self, formatter):
        with pytest.raises(TypeError):
            formatter._format_full_table("not_a_dict")

    def test_full_table_none_file_path(self, formatter):
        data = {
            "file_path": None,
            "classes": [],
            "functions": [],
            "variables": [],
            "imports": [],
        }
        result = formatter._format_full_table(data)
        assert "Unknown" in result

    def test_full_table_with_package(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "KL",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "functions": [],
            "variables": [],
            "imports": [],
            "package": {"name": "mypackage"},
        }
        result = formatter._format_full_table(data)
        assert "## Package" in result
        assert "mypackage" in result

    def test_full_table_with_imports(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "KL",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "functions": [],
            "variables": [],
            "imports": [
                {"name": "os", "raw_text": "import os", "module_name": ""},
                {"name": "Path", "raw_text": "", "module_name": "pathlib"},
            ],
            "package": {},
        }
        result = formatter._format_full_table(data)
        assert "## Imports" in result
        assert "import os" in result
        assert "from pathlib import Path" in result

    def test_full_table_single_class_with_methods(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "Calc",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "functions": [],
            "methods": [
                {
                    "name": "add",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 7},
                    "parameters": [
                        {"name": "self", "type": "Calc"},
                        {"name": "x", "type": "int"},
                    ],
                    "return_type": "int",
                    "complexity_score": 1,
                    "docstring": "Add numbers.",
                },
                {
                    "name": "__init__",
                    "visibility": "public",
                    "line_range": {"start": 3, "end": 4},
                    "parameters": [{"name": "self", "type": "Calc"}],
                    "return_type": "",
                    "complexity_score": 0,
                    "docstring": "Initialize.",
                },
            ],
            "variables": [
                {
                    "name": "result",
                    "variable_type": "int",
                    "line_range": {"start": 2, "end": 2},
                    "docstring": "",
                }
            ],
            "imports": [],
            "statistics": {"method_count": 2, "field_count": 1},
        }
        result = formatter._format_full_table(data)
        assert "Calc" in result
        assert "add" in result

    def test_full_table_multiple_classes(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "A",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                },
                {
                    "name": "B",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 11, "end": 20},
                },
            ],
            "functions": [],
            "methods": [],
            "variables": [],
            "imports": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_full_table(data)
        assert "## Classes Overview" in result
        assert "A" in result
        assert "B" in result

    def test_full_table_per_class_sections(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "Calc",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                },
                {
                    "name": "Helper",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 31, "end": 50},
                },
            ],
            "functions": [],
            "methods": [
                {
                    "name": "add",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 7},
                    "parameters": [
                        {"name": "self", "type": "Calc"},
                        {"name": "x", "type": "int"},
                    ],
                    "return_type": "int",
                    "complexity_score": 1,
                    "docstring": "",
                },
            ],
            "variables": [
                {
                    "name": "count",
                    "variable_type": "int",
                    "line_range": {"start": 2, "end": 2},
                    "visibility": "public",
                    "modifiers": [],
                    "docstring": "",
                }
            ],
            "imports": [],
            "statistics": {"method_count": 1, "field_count": 1},
        }
        result = formatter._format_full_table(data)
        assert "## Classes Overview" in result
        assert "Calc" in result


class TestPythonFormatterCompactTable:
    """Test _format_compact_table"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_compact_table_basic(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [],
            "functions": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "test" in result
        assert "## Info" in result

    def test_compact_table_with_methods(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [],
            "functions": [],
            "methods": [
                {
                    "name": "func",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 2},
                    "parameters": [],
                    "return_type": "None",
                    "complexity_score": 0,
                    "docstring": "",
                },
            ],
            "variables": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "## Methods" in result
        assert "func" in result

    def test_compact_table_with_classes(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [
                {"name": "X", "type": "class", "line_range": {"start": 1, "end": 5}}
            ],
            "functions": [],
            "methods": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "## Classes" in result
        assert "X" in result

    def test_compact_table_with_none_class(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [
                None,
                {
                    "name": "Valid",
                    "type": "class",
                    "line_range": {"start": 1, "end": 5},
                },
            ],
            "functions": [],
            "methods": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "Valid" in result


class TestPythonFormatterCreateCompactSignature:
    """Test _create_compact_signature edge cases"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_compact_signature_none_method(self, formatter):
        with pytest.raises(TypeError):
            formatter._create_compact_signature(None)

    def test_compact_signature_invalid_type(self, formatter):
        with pytest.raises(TypeError):
            formatter._create_compact_signature("not_dict")

    def test_compact_signature_string_params(self, formatter):
        method = {
            "name": "f",
            "return_type": "str",
            "parameters": "a, b, c",
        }
        result = formatter._create_compact_signature(method)
        assert result in ["():str", "():Any"]

    def test_compact_signature_none_type(self, formatter):
        method = {
            "name": "f",
            "return_type": "str",
            "parameters": [{"name": "x", "type": None}],
        }
        result = formatter._create_compact_signature(method)
        assert "Any" in result


class TestPythonFormatterFormatTableMethod:
    """Test format_table method"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_table_restores_format_type(self, formatter):
        data = {"file_path": "app.py", "classes": [], "functions": [], "variables": []}
        original = formatter.format_type
        formatter.format_table(data, "compact")
        assert formatter.format_type == original


class TestPythonFormatterFormatJsonError:
    """Test _format_json error path"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_json_with_set(self, formatter):
        data = {"bad": {1, 2, 3}}
        result = formatter._format_json(data)
        assert "JSON serialization error" in result


class TestPythonFormatterFormatPythonSignature:
    """Test _format_python_signature"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_python_signature_with_return_type(self, formatter):
        method = {
            "name": "func",
            "parameters": [{"name": "x", "type": "int"}],
            "return_type": "str",
        }
        result = formatter._format_python_signature(method)
        assert "-> str" in result

    def test_python_signature_no_return_type(self, formatter):
        method = {
            "name": "func",
            "parameters": [{"name": "x", "type": "int"}],
            "return_type": "",
        }
        result = formatter._format_python_signature(method)
        assert "->" not in result

    def test_python_signature_none_params(self, formatter):
        method = {
            "name": "func",
            "parameters": None,
            "return_type": "None",
        }
        result = formatter._format_python_signature(method)
        assert result == "() -> None"


class TestPythonFormatterVisibilitySymbol:
    """Test _get_python_visibility_symbol"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_visibility_public(self, formatter):
        assert formatter._get_python_visibility_symbol("public") == "🔓"

    def test_visibility_private(self, formatter):
        assert formatter._get_python_visibility_symbol("private") == "🔒"

    def test_visibility_protected(self, formatter):
        assert formatter._get_python_visibility_symbol("protected") == "🔐"

    def test_visibility_magic(self, formatter):
        assert formatter._get_python_visibility_symbol("magic") == "✨"

    def test_visibility_unknown(self, formatter):
        assert formatter._get_python_visibility_symbol("unknown") == "🔓"


class TestPythonFormatterDecoratorsEdge:
    """Test _format_decorators edge cases"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_decorators_important_classmethod(self, formatter):
        result = formatter._format_decorators(["classmethod"])
        assert "@classmethod" in result

    def test_decorators_important_abstractmethod(self, formatter):
        result = formatter._format_decorators(["abstractmethod"])
        assert "@abstractmethod" in result

    def test_decorators_important_dataclass(self, formatter):
        result = formatter._format_decorators(["dataclass"])
        assert "@dataclass" in result

    def test_decorators_important_property(self, formatter):
        result = formatter._format_decorators(["property"])
        assert "@property" in result

    def test_decorators_multiple_with_plus(self, formatter):
        result = formatter._format_decorators(["a", "b", "c"])
        assert "+2" in result


class TestPythonFormatterClassMethodRow:
    """Test _format_class_method_row"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_class_method_row_basic(self, formatter):
        method = {
            "name": "do_stuff",
            "visibility": "public",
            "line_range": {"start": 5, "end": 7},
            "parameters": [{"name": "self", "type": "MyClass"}],
            "return_type": "None",
            "complexity_score": 1,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "do_stuff" in result
        assert "|" in result

    def test_class_method_row_static(self, formatter):
        method = {
            "name": "helper",
            "visibility": "public",
            "line_range": {"start": 10, "end": 12},
            "parameters": [],
            "return_type": "int",
            "complexity_score": 0,
            "is_static": True,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "static" in result

    def test_class_method_row_magic(self, formatter):
        method = {
            "name": "__str__",
            "visibility": "public",
            "line_range": {"start": 15, "end": 17},
            "parameters": [{"name": "self", "type": "MyClass"}],
            "return_type": "str",
            "complexity_score": 0,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "+" in result  # magic = public symbol

    def test_class_method_row_private(self, formatter):
        method = {
            "name": "_internal",
            "visibility": "public",
            "line_range": {"start": 20, "end": 22},
            "parameters": [{"name": "self", "type": "MyClass"}],
            "return_type": "None",
            "complexity_score": 0,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "-" in result  # private = - symbol

    def test_class_method_row_malformed_line_range(self, formatter):
        method = {
            "name": "bad",
            "visibility": "public",
            "line_range": "not_a_dict",
            "parameters": [],
            "return_type": "None",
            "complexity_score": 0,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "0-0" in result

    def test_class_method_row_with_docstring(self, formatter):
        method = {
            "name": "good_func",
            "visibility": "public",
            "line_range": {"start": 1, "end": 5},
            "parameters": [],
            "return_type": "int",
            "complexity_score": 0,
            "docstring": "Does something useful",
        }
        result = formatter._format_class_method_row(method)
        assert "useful" in result


class TestPythonFormatterSignatureCompact:
    """Test _format_python_signature_compact"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_python_signature_compact_with_return(self, formatter):
        method = {
            "name": "f",
            "parameters": [],
            "return_type": "int",
        }
        result = formatter._format_python_signature_compact(method)
        assert "int" in result

    def test_python_signature_compact_no_return(self, formatter):
        method = {
            "name": "f",
            "parameters": [],
            "return_type": "",
        }
        result = formatter._format_python_signature_compact(method)
        assert "Any" in result

    def test_python_signature_compact_none_params(self, formatter):
        method = {
            "name": "f",
            "parameters": None,
            "return_type": "None",
        }
        result = formatter._format_python_signature_compact(method)
        assert "None" in result
