#!/usr/bin/env python3
"""
Property-based tests for YAML language isolation.

Feature: yaml-language-support
Tests correctness properties to ensure:
- YAML plugin doesn't affect other language plugins
- Plugin manager maintains isolation between plugins
- YAML analysis doesn't interfere with other language analysis
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.language_detector import detect_language_from_file
from tree_sitter_analyzer.languages.yaml_plugin import YAML_AVAILABLE
from tree_sitter_analyzer.plugins.manager import PluginManager

# Strategy for simple valid code in different languages
java_code_strategy = st.just(
    """
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
"""
)

python_code_strategy = st.just(
    """
def test_function():
    print("Hello")
    return 42

class TestClass:
    def __init__(self):
        self.value = 0
"""
)

javascript_code_strategy = st.just(
    """
function testFunction() {
    console.log("Hello");
    return 42;
}

class TestClass {
    constructor() {
        this.value = 0;
    }
}
"""
)

yaml_code_strategy = st.just(
    """
# Test YAML
test_key: test_value
nested:
  key1: value1
  key2: value2
items:
  - item1
  - item2
"""
)


class TestYAMLLanguageIsolationProperties:
    """Property-based tests for YAML language isolation."""

    @settings(max_examples=50, deadline=1000)
    @given(
        java_code=java_code_strategy,
        python_code=python_code_strategy,
        yaml_code=yaml_code_strategy,
    )
    def test_property_8_language_isolation_plugin_manager(
        self,
        java_code: str,
        python_code: str,
        yaml_code: str,
    ):
        """
        Feature: yaml-language-support, Property 8: Language Isolation

        For any plugin manager instance, loading the YAML plugin SHALL NOT
        affect the availability or functionality of other language plugins.

        Validates: Requirements 3.5
        """
        # Create plugin manager and load all plugins
        manager = PluginManager()
        manager.load_plugins()

        # Property: YAML plugin should be loaded
        yaml_plugin = manager.get_plugin("yaml")
        assert (
            yaml_plugin is not None
        ), "YAML plugin must be available in plugin manager"

        # Property: Other language plugins should still be available
        java_plugin = manager.get_plugin("java")
        python_plugin = manager.get_plugin("python")
        javascript_plugin = manager.get_plugin("javascript")

        # At least some other plugins should be available
        other_plugins = [java_plugin, python_plugin, javascript_plugin]
        available_other_plugins = [p for p in other_plugins if p is not None]

        assert (
            len(available_other_plugins) > 0
        ), "Other language plugins must remain available when YAML plugin is loaded"

        # Property: Each plugin should report its correct language
        assert (
            yaml_plugin.get_language_name() == "yaml"
        ), "YAML plugin must report 'yaml' as its language"

        if java_plugin:
            assert (
                java_plugin.get_language_name() == "java"
            ), "Java plugin must still report 'java' as its language"

        if python_plugin:
            assert (
                python_plugin.get_language_name() == "python"
            ), "Python plugin must still report 'python' as its language"

        if javascript_plugin:
            assert (
                javascript_plugin.get_language_name() == "javascript"
            ), "JavaScript plugin must still report 'javascript' as its language"

    @settings(max_examples=50)
    @given(
        yaml_code=yaml_code_strategy,
    )
    def test_property_8_language_isolation_file_extensions(
        self,
        yaml_code: str,
    ):
        """
        Feature: yaml-language-support, Property 8: Language Isolation

        For any YAML plugin instance, the file extensions it handles SHALL NOT
        overlap with other language plugins' extensions.

        Validates: Requirements 3.5
        """
        # Create plugin manager and load all plugins
        manager = PluginManager()
        manager.load_plugins()

        # Get all plugins
        all_plugins = manager.get_all_plugins()

        # Property: YAML plugin should be present
        assert "yaml" in all_plugins, "YAML plugin must be loaded"

        yaml_plugin = all_plugins["yaml"]
        yaml_extensions = set(yaml_plugin.get_file_extensions())

        # Property: YAML extensions should be .yaml and .yml
        assert yaml_extensions == {
            ".yaml",
            ".yml",
        }, "YAML plugin must handle exactly .yaml and .yml extensions"

        # Property: No other plugin should claim .yaml or .yml extensions
        for language, plugin in all_plugins.items():
            if language == "yaml":
                continue

            plugin_extensions = set(plugin.get_file_extensions())
            overlap = yaml_extensions & plugin_extensions

            assert (
                len(overlap) == 0
            ), f"Plugin '{language}' must not claim YAML extensions, found overlap: {overlap}"

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
    @pytest.mark.asyncio
    async def test_property_8_language_isolation_concurrent_analysis(self):
        """
        Feature: yaml-language-support, Property 8: Language Isolation

        For any analysis session, analyzing YAML files SHALL NOT affect
        the analysis of other language files.

        Validates: Requirements 3.5
        """
        # Create temporary files for different languages
        yaml_content = "test_key: test_value\nnested:\n  key: value\n"
        python_content = "def test():\n    return 42\n"
        java_content = "public class Test {\n    public void test() {}\n}\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as yaml_file:
            yaml_file.write(yaml_content)
            yaml_path = yaml_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as python_file:
            python_file.write(python_content)
            python_path = python_file.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False
        ) as java_file:
            java_file.write(java_content)
            java_path = java_file.name

        try:
            # Create plugin manager
            manager = PluginManager()
            manager.load_plugins()

            # Analyze YAML file
            yaml_plugin = manager.get_plugin("yaml")
            assert yaml_plugin is not None, "YAML plugin must be available"

            yaml_request = AnalysisRequest(file_path=yaml_path)
            yaml_result = await yaml_plugin.analyze_file(yaml_path, yaml_request)

            # Property: YAML analysis should succeed
            assert yaml_result.success, "YAML analysis must succeed"
            assert yaml_result.language == "yaml", "YAML result must indicate 'yaml'"

            # Analyze Python file
            python_plugin = manager.get_plugin("python")
            if python_plugin:
                python_request = AnalysisRequest(file_path=python_path)
                python_result = await python_plugin.analyze_file(
                    python_path, python_request
                )

                # Property: Python analysis should still work after YAML analysis
                assert (
                    python_result.success
                ), "Python analysis must succeed after YAML analysis"
                assert (
                    python_result.language == "python"
                ), "Python result must indicate 'python'"

            # Analyze Java file
            java_plugin = manager.get_plugin("java")
            if java_plugin:
                java_request = AnalysisRequest(file_path=java_path)
                java_result = await java_plugin.analyze_file(java_path, java_request)

                # Property: Java analysis should still work after YAML analysis
                assert (
                    java_result.success
                ), "Java analysis must succeed after YAML analysis"
                assert (
                    java_result.language == "java"
                ), "Java result must indicate 'java'"

        finally:
            # Clean up
            Path(yaml_path).unlink(missing_ok=True)
            Path(python_path).unlink(missing_ok=True)
            Path(java_path).unlink(missing_ok=True)

    @settings(max_examples=50)
    @given(
        yaml_code=yaml_code_strategy,
    )
    def test_property_8_language_isolation_language_detection(
        self,
        yaml_code: str,
    ):
        """
        Feature: yaml-language-support, Property 8: Language Isolation

        For any file, the language detector SHALL correctly identify the
        language without interference from the YAML plugin.

        Validates: Requirements 3.5
        """
        # Create temporary files for different languages
        test_files = {
            "yaml": (".yaml", yaml_code),
            "python": (".py", "def test():\n    pass\n"),
            "java": (".java", "public class Test {}\n"),
            "javascript": (".js", "function test() {}\n"),
        }

        created_files = {}

        try:
            # Create all test files
            for lang, (ext, content) in test_files.items():
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=ext, delete=False
                ) as tmp_file:
                    tmp_file.write(content)
                    created_files[lang] = tmp_file.name

            # Property: Each file should be detected as its correct language
            for lang, file_path in created_files.items():
                detected = detect_language_from_file(file_path)
                assert (
                    detected == lang
                ), f"File with extension for '{lang}' must be detected as '{lang}', got '{detected}'"

        finally:
            # Clean up
            for file_path in created_files.values():
                Path(file_path).unlink(missing_ok=True)

    @settings(max_examples=50)
    @given(
        yaml_code=yaml_code_strategy,
    )
    def test_property_8_language_isolation_plugin_state(
        self,
        yaml_code: str,
    ):
        """
        Feature: yaml-language-support, Property 8: Language Isolation

        For any plugin manager, the state of the YAML plugin SHALL NOT
        affect the state of other plugins.

        Validates: Requirements 3.5
        """
        # Create plugin manager
        manager = PluginManager()
        manager.load_plugins()

        # Get initial state of all plugins
        initial_plugins = manager.get_all_plugins()
        initial_languages = set(initial_plugins.keys())

        # Property: YAML should be in the initial set
        assert "yaml" in initial_languages, "YAML plugin must be loaded"

        # Get YAML plugin and verify it works
        yaml_plugin = manager.get_plugin("yaml")
        assert yaml_plugin is not None, "YAML plugin must be retrievable"
        assert (
            yaml_plugin.get_language_name() == "yaml"
        ), "YAML plugin must report correct language"

        # Property: Other plugins should still be accessible and functional
        for language in initial_languages:
            if language == "yaml":
                continue

            plugin = manager.get_plugin(language)
            assert (
                plugin is not None
            ), f"Plugin for '{language}' must still be accessible"

            # Verify plugin still reports correct language
            reported_language = plugin.get_language_name()
            assert (
                reported_language == language
            ), f"Plugin for '{language}' must still report correct language, got '{reported_language}'"

            # Verify plugin can still create extractor
            extractor = plugin.create_extractor()
            assert (
                extractor is not None
            ), f"Plugin for '{language}' must still create extractor"

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
    @pytest.mark.asyncio
    async def test_property_8_language_isolation_multiple_yaml_analyses(self):
        """
        Feature: yaml-language-support, Property 8: Language Isolation

        For any sequence of YAML analyses, each analysis SHALL be independent
        and not affect subsequent analyses of any language.

        Validates: Requirements 3.5
        """
        # Create test files
        yaml_content1 = "key1: value1\n"
        yaml_content2 = "key2: value2\n"
        python_content = "def test():\n    return 42\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as yaml1:
            yaml1.write(yaml_content1)
            yaml1_path = yaml1.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as yaml2:
            yaml2.write(yaml_content2)
            yaml2_path = yaml2.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as python_file:
            python_file.write(python_content)
            python_path = python_file.name

        try:
            # Create plugin manager
            manager = PluginManager()
            manager.load_plugins()

            yaml_plugin = manager.get_plugin("yaml")
            python_plugin = manager.get_plugin("python")

            assert yaml_plugin is not None, "YAML plugin must be available"

            # Analyze first YAML file
            request1 = AnalysisRequest(file_path=yaml1_path)
            result1 = await yaml_plugin.analyze_file(yaml1_path, request1)
            assert result1.success, "First YAML analysis must succeed"

            # Analyze second YAML file
            request2 = AnalysisRequest(file_path=yaml2_path)
            result2 = await yaml_plugin.analyze_file(yaml2_path, request2)
            assert result2.success, "Second YAML analysis must succeed"

            # Property: Results should be independent
            assert (
                result1.file_path != result2.file_path
            ), "Results must be for different files"

            # Analyze Python file after YAML analyses
            if python_plugin:
                python_request = AnalysisRequest(file_path=python_path)
                python_result = await python_plugin.analyze_file(
                    python_path, python_request
                )

                # Property: Python analysis should work correctly after multiple YAML analyses
                assert (
                    python_result.success
                ), "Python analysis must succeed after multiple YAML analyses"
                assert (
                    python_result.language == "python"
                ), "Python result must indicate 'python'"

        finally:
            # Clean up
            Path(yaml1_path).unlink(missing_ok=True)
            Path(yaml2_path).unlink(missing_ok=True)
            Path(python_path).unlink(missing_ok=True)

    @settings(max_examples=50)
    @given(
        yaml_code=yaml_code_strategy,
    )
    def test_property_8_language_isolation_supported_element_types(
        self,
        yaml_code: str,
    ):
        """
        Feature: yaml-language-support, Property 8: Language Isolation

        For any plugin, the supported element types SHALL be specific to
        that language and not affected by the YAML plugin.

        Validates: Requirements 3.5
        """
        # Create plugin manager
        manager = PluginManager()
        manager.load_plugins()

        # Get YAML plugin element types
        yaml_plugin = manager.get_plugin("yaml")
        assert yaml_plugin is not None, "YAML plugin must be available"

        yaml_types = set(yaml_plugin.get_supported_element_types())

        # Property: YAML should have its specific element types
        expected_yaml_types = {
            "mapping",
            "sequence",
            "scalar",
            "anchor",
            "alias",
            "comment",
            "document",
        }
        assert (
            yaml_types == expected_yaml_types
        ), f"YAML plugin must support expected types, got {yaml_types}"

        # Property: Other plugins should have their own element types
        java_plugin = manager.get_plugin("java")
        if java_plugin:
            java_types = set(java_plugin.get_supported_element_types())
            # Java should have different element types
            assert (
                "class" in java_types or "method" in java_types
            ), "Java plugin must have Java-specific element types"
            # YAML-specific types should not be in Java
            yaml_specific = {"mapping", "sequence", "anchor", "alias"}
            java_yaml_overlap = java_types & yaml_specific
            assert (
                len(java_yaml_overlap) == 0
            ), f"Java plugin must not have YAML-specific types: {java_yaml_overlap}"

        python_plugin = manager.get_plugin("python")
        if python_plugin:
            python_types = set(python_plugin.get_supported_element_types())
            # Python should have different element types
            assert (
                "function" in python_types or "class" in python_types
            ), "Python plugin must have Python-specific element types"
            # YAML-specific types should not be in Python
            yaml_specific = {"mapping", "sequence", "anchor", "alias"}
            python_yaml_overlap = python_types & yaml_specific
            assert (
                len(python_yaml_overlap) == 0
            ), f"Python plugin must not have YAML-specific types: {python_yaml_overlap}"
