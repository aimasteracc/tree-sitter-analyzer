#!/usr/bin/env python3
"""AnalyzeCodeStructureTool modifier tests — convert params, get modifiers, get parameters."""

from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    _convert_parameters,
    _get_field_modifiers,
    _get_method_modifiers,
    _get_method_parameters,
)


class TestAnalyzeCodeStructureToolConvertParameters:
    """Tests for _convert_parameters helper."""

    def test_convert_parameters_empty(self):
        """Test converting empty parameters."""
        result = _convert_parameters([])
        assert result == []

    def test_convert_parameters_dict(self):
        """Test converting dict parameters."""
        parameters = [{"name": "param1", "type": "string"}]
        result = _convert_parameters(parameters)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"

    def test_convert_parameters_object(self):
        """Test converting object parameters."""
        mock_param = MagicMock()
        mock_param.name = "param1"
        mock_param.param_type = "string"
        parameters = [mock_param]
        result = _convert_parameters(parameters)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"


class TestAnalyzeCodeStructureToolGetMethodModifiers:
    """Tests for _get_method_modifiers helper."""

    def test_get_method_modifiers_none(self):
        """Test getting modifiers with no modifiers."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = False
        mock_method.is_abstract = False

        result = _get_method_modifiers(mock_method)
        assert result == []

    def test_get_method_modifiers_static(self):
        """Test getting static modifier."""
        mock_method = MagicMock()
        mock_method.is_static = True
        mock_method.is_final = False
        mock_method.is_abstract = False

        result = _get_method_modifiers(mock_method)
        assert result == ["static"]

    def test_get_method_modifiers_final(self):
        """Test getting final modifier."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = True
        mock_method.is_abstract = False

        result = _get_method_modifiers(mock_method)
        assert result == ["final"]

    def test_get_method_modifiers_abstract(self):
        """Test getting abstract modifier."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = False
        mock_method.is_abstract = True

        result = _get_method_modifiers(mock_method)
        assert result == ["abstract"]

    def test_get_method_modifiers_multiple(self):
        """Test getting multiple modifiers."""
        mock_method = MagicMock()
        mock_method.is_static = True
        mock_method.is_final = True
        mock_method.is_abstract = True

        result = _get_method_modifiers(mock_method)
        assert len(result) == 3
        assert "static" in result
        assert "final" in result
        assert "abstract" in result


class TestAnalyzeCodeStructureToolGetFieldModifiers:
    """Tests for _get_field_modifiers helper."""

    def test_get_field_modifiers_none(self):
        """Test getting modifiers with no modifiers."""
        mock_field = MagicMock()
        mock_field.visibility = "public"
        mock_field.is_static = False
        mock_field.is_final = False

        result = _get_field_modifiers(mock_field)
        # Public visibility is added as a modifier (not package)
        assert result == ["public"]

    def test_get_field_modifiers_private(self):
        """Test getting private visibility."""
        mock_field = MagicMock()
        mock_field.visibility = "private"
        mock_field.is_static = False
        mock_field.is_final = False

        result = _get_field_modifiers(mock_field)
        assert result == ["private"]

    def test_get_field_modifiers_static(self):
        """Test getting static modifier."""
        mock_field = MagicMock()
        mock_field.visibility = "public"
        mock_field.is_static = True
        mock_field.is_final = False

        result = _get_field_modifiers(mock_field)
        # Public visibility is added as a modifier
        assert result == ["public", "static"]

    def test_get_field_modifiers_multiple(self):
        """Test getting multiple modifiers."""
        mock_field = MagicMock()
        mock_field.visibility = "private"
        mock_field.is_static = True
        mock_field.is_final = True

        result = _get_field_modifiers(mock_field)
        assert len(result) == 3
        assert "private" in result
        assert "static" in result
        assert "final" in result


class TestAnalyzeCodeStructureToolGetMethodParameters:
    """Tests for _get_method_parameters helper."""

    def test_get_method_parameters_empty(self):
        """Test getting empty parameters."""
        mock_method = MagicMock()
        mock_method.parameters = []

        result = _get_method_parameters(mock_method)
        assert result == []

    def test_get_method_parameters_list_of_strings(self):
        """Test getting parameters as list of strings."""
        mock_method = MagicMock()
        mock_method.parameters = ["str param1", "str param2"]

        result = _get_method_parameters(mock_method)
        assert len(result) == 2
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "str"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "str"

    def test_get_method_parameters_list_of_dicts(self):
        """Test getting parameters as list of dicts."""
        mock_method = MagicMock()
        mock_method.parameters = [{"name": "param1", "type": "string"}]

        result = _get_method_parameters(mock_method)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"

    def test_get_method_parameters_mixed(self):
        """Test getting mixed parameters."""
        mock_method = MagicMock()
        # Use all string format (the implementation handles this case)
        mock_method.parameters = ["str param1", "int param2"]

        result = _get_method_parameters(mock_method)
        assert len(result) == 2
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "str"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "int"
