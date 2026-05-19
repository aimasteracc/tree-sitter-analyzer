"""Java plugin integration tests."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaPlugin


class TestJavaPlugin:
    """Test Java plugin functionality"""

    @pytest.fixture
    def plugin(self):
        """Create a Java plugin instance"""
        return JavaPlugin()

    def test_plugin_initialization(self, plugin):
        """Test plugin initialization"""
        assert plugin.language == "java"
        assert ".java" in plugin.supported_extensions

    def test_plugin_extract_elements(self, plugin):
        """Test plugin element extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        source_code = "public class Test {}"

        # Mock extractor methods
        with patch.object(plugin.extractor, "extract_functions") as mock_functions:
            with patch.object(plugin.extractor, "extract_classes") as mock_classes:
                with patch.object(
                    plugin.extractor, "extract_variables"
                ) as mock_variables:
                    with patch.object(
                        plugin.extractor, "extract_imports"
                    ) as mock_imports:
                        with patch.object(
                            plugin.extractor, "extract_packages"
                        ) as mock_packages:
                            with patch.object(
                                plugin.extractor, "extract_annotations"
                            ) as mock_annotations:
                                mock_functions.return_value = []
                                mock_classes.return_value = []
                                mock_variables.return_value = []
                                mock_imports.return_value = []
                                mock_packages.return_value = []
                                mock_annotations.return_value = []

                                result = plugin.extract_elements(mock_tree, source_code)

                                assert "functions" in result
                                assert "classes" in result
                                assert "variables" in result
                                assert "imports" in result
                                assert "packages" in result
                                assert "annotations" in result

    def test_plugin_with_invalid_tree(self, plugin):
        """Test plugin behavior with invalid tree"""
        # Test with None tree
        result = plugin.extract_elements(None, "public class Test {}")
        expected_keys = {
            "functions",
            "classes",
            "variables",
            "imports",
            "packages",
            "annotations",
        }
        assert set(result.keys()) == expected_keys

        # All should be empty lists
        for key in expected_keys:
            assert result[key] == []

    def test_plugin_with_extraction_errors(self, plugin):
        """Test plugin behavior when extraction methods raise errors"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Mock extractor to raise exceptions
        with patch.object(plugin.extractor, "extract_functions") as mock_functions:
            with patch.object(plugin.extractor, "extract_classes") as mock_classes:
                with patch.object(
                    plugin.extractor, "extract_variables"
                ) as mock_variables:
                    with patch.object(
                        plugin.extractor, "extract_imports"
                    ) as mock_imports:
                        with patch.object(
                            plugin.extractor, "extract_packages"
                        ) as mock_packages:
                            with patch.object(
                                plugin.extractor, "extract_annotations"
                            ) as mock_annotations:
                                mock_functions.side_effect = Exception(
                                    "Function extraction error"
                                )
                                mock_classes.side_effect = Exception(
                                    "Class extraction error"
                                )
                                mock_variables.side_effect = Exception(
                                    "Variable extraction error"
                                )
                                mock_imports.side_effect = Exception(
                                    "Import extraction error"
                                )
                                mock_packages.side_effect = Exception(
                                    "Package extraction error"
                                )
                                mock_annotations.side_effect = Exception(
                                    "Annotation extraction error"
                                )

                                # Should handle exceptions gracefully
                                result = plugin.extract_elements(
                                    mock_tree, "public class Test {}"
                                )

                                # Should return empty lists instead of crashing
                                expected_keys = {
                                    "functions",
                                    "classes",
                                    "variables",
                                    "imports",
                                    "packages",
                                    "annotations",
                                }
                                assert set(result.keys()) == expected_keys
                                for key in expected_keys:
                                    assert result[key] == []

    def test_concurrent_extraction_simulation(self, plugin):
        """Test simulation of concurrent extraction"""
        import threading
        import time

        results = []
        errors = []

        def worker():
            try:
                mock_tree = Mock()
                mock_tree.root_node = Mock()
                mock_tree.root_node.children = []

                for i in range(5):
                    result = plugin.extract_elements(
                        mock_tree, f"public class Test{i} {{}}"
                    )
                    results.append(result)
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _i in range(3):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should not have any errors
        assert len(errors) == 0
        assert len(results) == 15  # 3 threads * 5 operations each


