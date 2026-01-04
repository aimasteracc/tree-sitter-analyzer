#!/usr/bin/env python3
"""
Property-based tests for YAML file extension selection.

Feature: yaml-language-support
Tests correctness properties to ensure:
- .yaml and .yml files are correctly handled by YAMLPlugin
- The language detector correctly maps these extensions to 'yaml'
- The plugin manager returns YAMLPlugin for yaml language
"""

import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.language_detector import detect_language_from_file
from tree_sitter_analyzer.languages.yaml_plugin import YAML_AVAILABLE, YAMLPlugin
from tree_sitter_analyzer.plugins.manager import PluginManager

# Strategy for valid YAML content
yaml_content_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
        min_codepoint=32,
        max_codepoint=122,
    ),
    min_size=0,
    max_size=100,
)

# Strategy for valid file names (without extension)
filename_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        min_codepoint=48,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=20,
).filter(lambda x: x and len(x.strip()) > 0 and x.isalnum())


class TestYAMLFileExtensionProperties:
    """Property-based tests for YAML file extension selection."""

    @settings(
        max_examples=100, deadline=None
    )  # Disable deadline due to I/O variability
    @given(
        filename=filename_strategy,
        extension=st.sampled_from([".yaml", ".yml"]),
        content=yaml_content_strategy,
    )
    def test_property_7_file_extension_selection_language_detection(
        self,
        filename: str,
        extension: str,
        content: str,
    ):
        """
        Feature: yaml-language-support, Property 7: File Extension Selection

        For any file with .yaml or .yml extension, the language detector SHALL
        correctly identify the language as 'yaml'.

        Validates: Requirements 3.2
        """
        # Create a temporary file with the given extension
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=extension,
            prefix=filename,
            delete=False,
        ) as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            # Property: Language detector must identify .yaml and .yml files as 'yaml'
            detected_language = detect_language_from_file(tmp_file_path)
            assert (
                detected_language == "yaml"
            ), f"File with extension '{extension}' must be detected as 'yaml', got '{detected_language}'"

        finally:
            # Clean up
            Path(tmp_file_path).unlink(missing_ok=True)

    @settings(max_examples=100)
    @given(
        extension=st.sampled_from([".yaml", ".yml"]),
    )
    def test_property_7_file_extension_selection_plugin_returns_yaml(
        self,
        extension: str,
    ):
        """
        Feature: yaml-language-support, Property 7: File Extension Selection

        For any file with .yaml or .yml extension, the YAMLPlugin SHALL report
        that it handles these extensions.

        Validates: Requirements 3.2
        """
        plugin = YAMLPlugin()

        # Property: YAMLPlugin must report .yaml and .yml in its file extensions
        extensions = plugin.get_file_extensions()
        assert isinstance(extensions, list), "get_file_extensions() must return a list"
        assert (
            extension in extensions
        ), f"YAMLPlugin must handle '{extension}' extension"

    # Windows cold-start imports can be highly variable; disable Hypothesis deadline there
    # to avoid flaky timing failures unrelated to correctness.
    @settings(max_examples=50, deadline=None if os.name == "nt" else 500)
    @given(
        filename=filename_strategy,
        extension=st.sampled_from([".yaml", ".yml"]),
    )
    def test_property_7_file_extension_selection_plugin_manager_integration(
        self,
        filename: str,
        extension: str,
    ):
        """
        Feature: yaml-language-support, Property 7: File Extension Selection

        For any file with .yaml or .yml extension, the plugin manager SHALL
        return the YAMLPlugin when queried for the 'yaml' language.

        Validates: Requirements 3.2
        """
        # Create plugin manager and load plugins
        plugin_manager = PluginManager()
        plugin_manager.load_plugins()

        # Property: Plugin manager must have a plugin for 'yaml' language
        yaml_plugin = plugin_manager.get_plugin("yaml")
        assert (
            yaml_plugin is not None
        ), "Plugin manager must have a plugin for 'yaml' language"

        # Property: The plugin must be an instance of YAMLPlugin
        assert isinstance(
            yaml_plugin, YAMLPlugin
        ), f"Plugin for 'yaml' must be YAMLPlugin, got {type(yaml_plugin)}"

        # Property: The plugin must report the correct extensions
        extensions = yaml_plugin.get_file_extensions()
        assert (
            extension in extensions
        ), f"YAML plugin must handle '{extension}' extension"

    @settings(max_examples=100)
    @given(
        extension=st.sampled_from([".yaml", ".yml"]),
    )
    def test_property_7_file_extension_selection_consistency(
        self,
        extension: str,
    ):
        """
        Feature: yaml-language-support, Property 7: File Extension Selection

        For any YAML file extension (.yaml or .yml), the extension SHALL be
        consistently recognized across multiple invocations.

        Validates: Requirements 3.2
        """
        # Create a simple YAML file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=extension,
            delete=False,
        ) as tmp_file:
            tmp_file.write("key: value\n")
            tmp_file_path = tmp_file.name

        try:
            # Property: Multiple detections must return the same result
            detections = [detect_language_from_file(tmp_file_path) for _ in range(10)]

            # All detections must be 'yaml'
            assert all(
                lang == "yaml" for lang in detections
            ), f"All detections must return 'yaml', got {set(detections)}"

            # All detections must be identical
            assert (
                len(set(detections)) == 1
            ), f"Language detection must be consistent, got {set(detections)}"

        finally:
            # Clean up
            Path(tmp_file_path).unlink(missing_ok=True)

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
    @pytest.mark.asyncio
    async def test_property_7_file_extension_selection_end_to_end_yaml(self):
        """
        Feature: yaml-language-support, Property 7: File Extension Selection

        For a file with .yaml extension, the complete analysis pipeline
        SHALL correctly process the file using the YAMLPlugin.

        Validates: Requirements 3.2
        """
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        # Create a YAML file with valid content
        yaml_content = "# Test YAML\ntest_key: test_value\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as tmp_file:
            tmp_file.write(yaml_content)
            tmp_file_path = tmp_file.name

        try:
            # Property: Language detection must identify the file as YAML
            detected_language = detect_language_from_file(tmp_file_path)
            assert (
                detected_language == "yaml"
            ), f"File must be detected as 'yaml', got '{detected_language}'"

            # Property: YAMLPlugin must be able to analyze the file
            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=tmp_file_path)
            result = await plugin.analyze_file(tmp_file_path, request)

            # Property: Analysis must succeed
            assert result.success, "Analysis must succeed for .yaml file"

            # Property: Result must indicate YAML language
            assert (
                result.language == "yaml"
            ), f"Analysis result must indicate 'yaml' language, got '{result.language}'"

        finally:
            # Clean up
            Path(tmp_file_path).unlink(missing_ok=True)

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
    @pytest.mark.asyncio
    async def test_property_7_file_extension_selection_end_to_end_yml(self):
        """
        Feature: yaml-language-support, Property 7: File Extension Selection

        For a file with .yml extension, the complete analysis pipeline
        SHALL correctly process the file using the YAMLPlugin.

        Validates: Requirements 3.2
        """
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        # Create a YAML file with valid content
        yaml_content = "# Test YAML\ntest_key: test_value\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yml",
            delete=False,
        ) as tmp_file:
            tmp_file.write(yaml_content)
            tmp_file_path = tmp_file.name

        try:
            # Property: Language detection must identify the file as YAML
            detected_language = detect_language_from_file(tmp_file_path)
            assert (
                detected_language == "yaml"
            ), f"File must be detected as 'yaml', got '{detected_language}'"

            # Property: YAMLPlugin must be able to analyze the file
            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=tmp_file_path)
            result = await plugin.analyze_file(tmp_file_path, request)

            # Property: Analysis must succeed
            assert result.success, "Analysis must succeed for .yml file"

            # Property: Result must indicate YAML language
            assert (
                result.language == "yaml"
            ), f"Analysis result must indicate 'yaml' language, got '{result.language}'"

        finally:
            # Clean up
            Path(tmp_file_path).unlink(missing_ok=True)

    @settings(max_examples=100)
    @given(
        extension=st.sampled_from([".yaml", ".yml"]),
    )
    def test_property_7_file_extension_selection_both_extensions_equivalent(
        self,
        extension: str,
    ):
        """
        Feature: yaml-language-support, Property 7: File Extension Selection

        For any YAML file, both .yaml and .yml extensions SHALL be treated
        equivalently by the system.

        Validates: Requirements 3.2
        """
        # Create files with both extensions
        yaml_content = "test: value\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as yaml_file:
            yaml_file.write(yaml_content)
            yaml_path = yaml_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False
        ) as yml_file:
            yml_file.write(yaml_content)
            yml_path = yml_file.name

        try:
            # Property: Both extensions must be detected as 'yaml'
            yaml_lang = detect_language_from_file(yaml_path)
            yml_lang = detect_language_from_file(yml_path)

            assert (
                yaml_lang == "yaml"
            ), f".yaml file must be detected as 'yaml', got '{yaml_lang}'"
            assert (
                yml_lang == "yaml"
            ), f".yml file must be detected as 'yaml', got '{yml_lang}'"

            # Property: Both must result in the same language
            assert (
                yaml_lang == yml_lang
            ), f"Both extensions must map to same language: .yaml={yaml_lang}, .yml={yml_lang}"

        finally:
            # Clean up
            Path(yaml_path).unlink(missing_ok=True)
            Path(yml_path).unlink(missing_ok=True)
