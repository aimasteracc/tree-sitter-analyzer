#!/usr/bin/env python3
"""
Tests for StructureCommand
"""

from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.structure_command import StructureCommand


@pytest.fixture
def mock_args():
    """Create mock args for BaseCommand initialization."""
    return Namespace(
        file_path="test.py",
        file="test.py",
        query_key=None,
        query_string=None,
        advanced=False,
        table=None,
        structure=True,
        summary=False,
        output_format="text",
        toon_use_tabs=False,
        statistics=False,
        output_file=None,
        suppress_output=False,
        format_type="full",
        language=None,
        include_details=True,
        include_complexity=True,
        include_guidance=False,
        metrics_only=False,
        output_format_param="json",
        format_type_param="full",
        language_param=None,
        filter_expression=None,
        filter=None,
        result_format="json",
        query_key_param=None,
        query_string_param=None,
    )


@pytest.fixture
def command(mock_args):
    """Create StructureCommand instance for testing."""
    return StructureCommand(mock_args)


class TestStructureCommandInit:
    """Tests for StructureCommand initialization."""

    def test_init(self, command):
        """Test StructureCommand initialization."""
        assert command is not None
        assert isinstance(command, StructureCommand)
        assert hasattr(command, "args")

    def test_init_with_args(self, mock_args):
        """Test StructureCommand initialization with args."""
        command = StructureCommand(mock_args)
        assert command.args == mock_args


class TestStructureCommandExecuteAsync:
    """Tests for StructureCommand.execute_async method."""

    @pytest.mark.asyncio
    async def test_execute_async_success(self, command):
        """Test execute_async returns 0 on success."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = MagicMock(
                file_path="test.py",
                language="python",
                line_count=10,
                elements=[],
                node_count=0,
                success=True,
                analysis_time=0.1,
            )
            with patch.object(command, "_output_structure_analysis"):
                result = await command.execute_async("python")
                assert result == 0
                mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_no_analysis_result(self, command):
        """Test execute_async returns 1 when no analysis result."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = None
            result = await command.execute_async("python")
            assert result == 1
            mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_calls_output_structure_analysis(self, command):
        """Test execute_async calls _output_structure_analysis."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = MagicMock(
                file_path="test.py",
                language="python",
                line_count=10,
                elements=[],
                node_count=0,
                success=True,
                analysis_time=0.1,
            )
            with patch.object(command, "_output_structure_analysis") as mock_output:
                await command.execute_async("python")
                mock_output.assert_called_once()


class TestStructureCommandConvertToLegacyFormat:
    """Tests for StructureCommand._convert_to_legacy_format method."""

    def test_convert_to_legacy_format_empty_elements(self, command):
        """Test _convert_to_legacy_format with empty elements."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_legacy_format(analysis_result)
        assert result is not None
        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["package"] is None
        assert result["classes"] == []
        assert result["methods"] == []
        assert result["fields"] == []
        assert result["imports"] == []
        assert result["annotations"] == []

    def test_convert_to_legacy_format_with_classes(self, command):
        """Test _convert_to_legacy_format with class elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        # Create a mock element that has the correct type
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.element_type = ELEMENT_TYPE_CLASS

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [mock_class]
        analysis_result.node_count = 1
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        result = command._convert_to_legacy_format(analysis_result)
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "TestClass"
        assert result["classes"][0]["visibility"] == "public"

    def test_convert_to_legacy_format_with_methods(self, command):
        """Test _convert_to_legacy_format with method elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        # Create a mock element that has the correct type
        mock_method = MagicMock()
        mock_method.name = "testMethod"
        mock_method.visibility = "public"
        mock_method.start_line = 5
        mock_method.end_line = 10
        mock_method.element_type = ELEMENT_TYPE_FUNCTION

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [mock_method]
        analysis_result.node_count = 1
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        result = command._convert_to_legacy_format(analysis_result)
        assert len(result["methods"]) == 1
        assert result["methods"][0]["name"] == "testMethod"
        assert result["methods"][0]["visibility"] == "public"

    def test_convert_to_legacy_format_method_has_class_name_and_is_method(
        self, command
    ):
        """#742: methods[] entries must carry class_name and is_method for --advanced parity."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        mock_method = MagicMock()
        mock_method.name = "parse_file"
        mock_method.visibility = "public"
        mock_method.start_line = 10
        mock_method.end_line = 20
        mock_method.element_type = ELEMENT_TYPE_FUNCTION
        mock_method.parent_class = (
            "Parser"  # Function model uses parent_class, not class_name
        )
        mock_method.is_method = True

        analysis_result = MagicMock()
        analysis_result.file_path = "parser.py"
        analysis_result.language = "python"
        analysis_result.line_count = 50
        analysis_result.elements = [mock_method]
        analysis_result.node_count = 1
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        result = command._convert_to_legacy_format(analysis_result)
        row = result["methods"][0]
        assert row["class_name"] == "Parser"
        assert row["is_method"] is True

    def test_convert_to_legacy_format_with_fields(self, command):
        """Test _convert_to_legacy_format with field elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_VARIABLE

        # Create a mock element that has the correct type
        mock_field = MagicMock()
        mock_field.name = "testField"
        mock_field.type_annotation = "int"
        mock_field.start_line = 3
        mock_field.end_line = 3
        mock_field.element_type = ELEMENT_TYPE_VARIABLE

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [mock_field]
        analysis_result.node_count = 1
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        result = command._convert_to_legacy_format(analysis_result)
        assert len(result["fields"]) == 1
        assert result["fields"][0]["name"] == "testField"
        assert result["fields"][0]["type"] == "int"

    def test_convert_to_legacy_format_statistics(self, command):
        """Test _convert_to_legacy_format includes statistics."""
        from tree_sitter_analyzer.constants import (
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
        )

        # Create mock elements that have the correct type
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.element_type = ELEMENT_TYPE_CLASS

        mock_method = MagicMock()
        mock_method.name = "testMethod"
        mock_method.visibility = "public"
        mock_method.start_line = 5
        mock_method.end_line = 10
        mock_method.element_type = ELEMENT_TYPE_FUNCTION

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [mock_class, mock_method]
        analysis_result.node_count = 2
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        result = command._convert_to_legacy_format(analysis_result)
        stats = result["statistics"]
        assert stats["class_count"] == 1
        assert stats["method_count"] == 1
        assert stats["field_count"] == 0
        assert stats["import_count"] == 0
        assert stats["total_lines"] == 10
        assert stats["annotation_count"] == 0

    def test_convert_to_legacy_format_metadata(self, command):
        """Test _convert_to_legacy_format includes metadata."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_legacy_format(analysis_result)
        metadata = result["analysis_metadata"]
        assert metadata["language"] == "python"
        assert metadata["file_path"] == "test.py"
        assert metadata["analyzer_version"] == "2.0.0"
        assert "timestamp" in metadata


class TestStructureCommandOutputStructureAnalysis:
    """Tests for StructureCommand._output_structure_analysis method."""

    def test_output_structure_analysis_text(self, command):
        """Test _output_structure_analysis with text format."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        command.args.output_format = "text"
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.output_section"
        ) as mock_section:
            with patch(
                "tree_sitter_analyzer.cli.commands.structure_command.output_data"
            ) as mock_data:
                command._output_structure_analysis(analysis_result)
                mock_section.assert_called_once_with("Structure Analysis Results")
                assert mock_data.call_count

    def test_output_structure_analysis_json(self, command):
        """Test _output_structure_analysis with JSON format."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        command.args.output_format = "json"
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.output_json"
        ) as mock_json:
            command._output_structure_analysis(analysis_result)
            mock_json.assert_called_once()

    def test_output_structure_analysis_toon(self, command):
        """Test _output_structure_analysis with TOON format."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        command.args.output_format = "toon"
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.ToonFormatter"
        ) as mock_formatter_class:
            mock_formatter = MagicMock()
            mock_formatter.format.return_value = "formatted_output"
            mock_formatter_class.return_value = mock_formatter
            with patch("builtins.print") as mock_print:
                command._output_structure_analysis(analysis_result)
                # formatter.format is called once, and print is called once:
                # (section header is skipped for toon/json to keep output clean)
                mock_formatter_class.assert_called_once_with(use_tabs=False)
                mock_formatter.format.assert_called_once()
                assert mock_print.call_count == 1
                # The print call contains the formatted output
                assert mock_print.call_args_list[0][0][0] == "formatted_output"


class TestStructureCommandOutputTextFormat:
    """Tests for StructureCommand._output_text_format method."""

    def test_output_text_format_basic(self, command):
        """Test _output_text_format with basic structure."""
        structure_dict = {
            "file_path": "test.py",
            "language": "python",
            "package": None,
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "annotations": [],
            "statistics": {
                "class_count": 0,
                "method_count": 0,
                "field_count": 0,
                "import_count": 0,
                "total_lines": 10,
                "annotation_count": 0,
            },
        }
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.output_data"
        ) as mock_data:
            command._output_text_format(structure_dict)
            assert mock_data.call_count

    def test_output_text_format_with_package(self, command):
        """Test _output_text_format with package."""
        structure_dict = {
            "file_path": "test.py",
            "language": "python",
            "package": {"name": "com.example", "line_range": (1, 1)},
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "annotations": [],
            "statistics": {
                "class_count": 0,
                "method_count": 0,
                "field_count": 0,
                "import_count": 0,
                "total_lines": 10,
                "annotation_count": 0,
            },
        }
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.output_data"
        ) as mock_data:
            command._output_text_format(structure_dict)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Package: com.example" in call for call in calls)

    def test_output_text_format_with_classes(self, command):
        """Test _output_text_format with classes."""
        structure_dict = {
            "file_path": "test.py",
            "language": "python",
            "package": None,
            "classes": [{"name": "TestClass"}],
            "methods": [],
            "fields": [],
            "imports": [],
            "annotations": [],
            "statistics": {
                "class_count": 1,
                "method_count": 0,
                "field_count": 0,
                "import_count": 0,
                "total_lines": 10,
                "annotation_count": 0,
            },
        }
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.output_data"
        ) as mock_data:
            command._output_text_format(structure_dict)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Classes:" in call for call in calls)
            assert any("TestClass" in call for call in calls)

    def test_output_text_format_with_methods(self, command):
        """Test _output_text_format with methods."""
        structure_dict = {
            "file_path": "test.py",
            "language": "python",
            "package": None,
            "classes": [],
            "methods": [{"name": "testMethod"}],
            "fields": [],
            "imports": [],
            "annotations": [],
            "statistics": {
                "class_count": 0,
                "method_count": 1,
                "field_count": 0,
                "import_count": 0,
                "total_lines": 10,
                "annotation_count": 0,
            },
        }
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.output_data"
        ) as mock_data:
            command._output_text_format(structure_dict)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Methods:" in call for call in calls)
            assert any("testMethod" in call for call in calls)

    def test_output_text_format_with_fields(self, command):
        """Test _output_text_format with fields."""
        structure_dict = {
            "file_path": "test.py",
            "language": "python",
            "package": None,
            "classes": [],
            "methods": [],
            "fields": [{"name": "testField"}],
            "imports": [],
            "annotations": [],
            "statistics": {
                "class_count": 0,
                "method_count": 0,
                "field_count": 1,
                "import_count": 0,
                "total_lines": 10,
                "annotation_count": 0,
            },
        }
        with patch(
            "tree_sitter_analyzer.cli.commands.structure_command.output_data"
        ) as mock_data:
            command._output_text_format(structure_dict)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Fields:" in call for call in calls)
            assert any("testField" in call for call in calls)


class TestR37aaStructureCanonicalEnvelope:
    """r37aa (dogfood): CLI ``--structure`` was the third CLI surface
    (after --advanced r37y and --summary r37z) emitting all-None
    envelope keys. This test pins the canonical contract.
    """

    def test_structure_emits_canonical_envelope(self, command):
        from unittest.mock import MagicMock

        analysis_result = MagicMock()
        analysis_result.file_path = "/test/foo.py"
        analysis_result.language = "python"
        analysis_result.line_count = 100
        analysis_result.elements = []
        analysis_result.analysis_time = 0.5

        legacy = command._convert_to_legacy_format(analysis_result)
        assert legacy.get("verdict") == "INFO"
        assert isinstance(legacy.get("summary_line"), str)
        assert legacy["summary_line"]
        assert legacy["agent_summary"]["verdict"] == "INFO"
        assert legacy["agent_summary"]["summary_line"] == legacy["summary_line"]
        # File path and language must appear in headline.
        assert "/test/foo.py" in legacy["summary_line"]
        assert "(python)" in legacy["summary_line"]

    def test_structure_success_key_present(self, command):
        from unittest.mock import MagicMock

        analysis_result = MagicMock()
        analysis_result.file_path = "/test/foo.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = []
        analysis_result.analysis_time = 0.0

        legacy = command._convert_to_legacy_format(analysis_result)
        assert legacy.get("success") is True

    def test_method_row_class_name_uses_parent_class_field(self, command):
        """Codex P2 #742: real Function elements store owner in parent_class, not class_name.

        Verifies the row builder reads the correct field, not a mock attribute.
        """

        from tree_sitter_analyzer.models import Function

        # Build a real Function element the same way extractors do
        fn = Function(
            name="parse",
            visibility="public",
            start_line=5,
            end_line=10,
            is_method=True,
            parent_class="Parser",
        )
        row = StructureCommand._legacy_method_row(fn)
        assert row["class_name"] == "Parser", (
            "class_name must come from parent_class, not a missing class_name attribute"
        )
        assert row["is_method"] is True
