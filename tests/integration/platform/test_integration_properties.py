from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin
from tree_sitter_analyzer.models import SQLElement, SQLElementType
from tree_sitter_analyzer.platform_compat.adapter import CompatibilityAdapter


class TestIntegrationProperties:
    def test_output_schema_consistency(self):
        """
        Property 5: Output schema consistency
        Validates: Requirements 4.5
        """
        # We want to ensure that regardless of the adapter rules applied,
        # the output elements always have the required attributes and types.

        extractor = SQLElementExtractor()
        # Mock adapter to return various modified elements
        adapter = MagicMock(spec=CompatibilityAdapter)

        # Scenario 1: Adapter returns modified elements
        element = SQLElement(
            name="test",
            start_line=1,
            end_line=1,
            raw_text="CREATE TABLE test ...",
            sql_element_type=SQLElementType.TABLE,
            element_type="table",
        )
        adapter.adapt_elements.return_value = [element]
        extractor.set_adapter(adapter)

        # Mock tree and source code
        tree = MagicMock()
        tree.root_node = MagicMock()

        # We need to mock the internal extraction methods because they rely on tree-sitter nodes
        # which are hard to mock perfectly.
        # Instead, let's mock the _extract_* methods to populate the list,
        # then verify that adapt_elements is called and output is consistent.

        with patch.object(extractor, "_extract_sql_tables") as mock_extract:
            # The extractor calls _extract_sql_tables(node, list)
            # We simulate it adding an element
            def side_effect(node, elements):
                elements.append(element)

            mock_extract.side_effect = side_effect

            # Also mock other extractors to do nothing
            with (
                patch.object(extractor, "_extract_sql_views"),
                patch.object(extractor, "_extract_sql_procedures"),
                patch.object(extractor, "_extract_sql_functions_enhanced"),
                patch.object(extractor, "_extract_sql_triggers"),
                patch.object(extractor, "_extract_sql_indexes"),
                patch.object(
                    extractor, "_validate_and_fix_elements", side_effect=lambda x: x
                ),
            ):
                results = extractor.extract_sql_elements(tree, "source code")

                assert len(results) == 1
                res = results[0]

                # Verify schema consistency
                assert isinstance(res, SQLElement)
                assert isinstance(res.name, str)
                assert isinstance(res.start_line, int)
                assert isinstance(res.end_line, int)
                assert isinstance(res.sql_element_type, SQLElementType)
                assert hasattr(res, "columns")
                assert hasattr(res, "parameters")
                assert hasattr(res, "dependencies")

    def test_diagnostic_logging(self):
        """
        Property 11: Comprehensive diagnostic logging
        Validates: Requirements 5.2, 5.3, 5.4
        """
        with patch("tree_sitter_analyzer.languages.sql_plugin.log_debug") as mock_log:
            # Test SQLPlugin initialization logging
            # We need to mock PlatformDetector to ensure consistent behavior
            with patch(
                "tree_sitter_analyzer.languages.sql_plugin.PlatformDetector"
            ) as mock_detector:
                mock_detector.detect.return_value.platform_key = "test_platform"

                plugin = SQLPlugin(diagnostic_mode=True)

                # Verify platform info logging
                # We expect "Diagnostic: Platform detected:"
                found_platform_log = False
                for call in mock_log.call_args_list:
                    if "Diagnostic: Platform detected:" in str(call):
                        found_platform_log = True
                        break
                assert (
                    found_platform_log
                ), "Should log platform detection in diagnostic mode"

                # Test Extractor logging
                extractor = plugin.extractor
                assert extractor.diagnostic_mode

                # Mock adapter and extraction
                adapter = MagicMock(spec=CompatibilityAdapter)
                adapter.adapt_elements.return_value = []
                extractor.set_adapter(adapter)

                tree = MagicMock()
                tree.root_node = MagicMock()

                with (
                    patch.object(extractor, "_extract_sql_tables"),
                    patch.object(extractor, "_extract_sql_views"),
                    patch.object(extractor, "_extract_sql_procedures"),
                    patch.object(extractor, "_extract_sql_functions_enhanced"),
                    patch.object(extractor, "_extract_sql_triggers"),
                    patch.object(extractor, "_extract_sql_indexes"),
                    patch.object(
                        extractor, "_validate_and_fix_elements", return_value=[]
                    ),
                ):
                    extractor.extract_sql_elements(tree, "source code")

                    # Verify adaptation logging
                    # We expect "Diagnostic: Before adaptation:" and "Diagnostic: After adaptation:"
                    found_before = False
                    found_after = False
                    for call in mock_log.call_args_list:
                        if "Diagnostic: Before adaptation:" in str(call):
                            found_before = True
                        if "Diagnostic: After adaptation:" in str(call):
                            found_after = True

                    assert found_before, "Should log before adaptation"
                    assert found_after, "Should log after adaptation"

    def test_graceful_degradation(self):
        """
        Property 13: Language isolation (Graceful degradation)
        Validates: Requirements 7.1
        """
        extractor = SQLElementExtractor()
        # Mock platform info
        extractor.platform_info = MagicMock()

        # Mock _extract_sql_tables to raise an exception
        with patch.object(
            extractor, "_extract_sql_tables", side_effect=Exception("Simulated failure")
        ):
            with patch(
                "tree_sitter_analyzer.languages.sql_plugin.log_error"
            ) as mock_log:
                tree = MagicMock()
                tree.root_node = MagicMock()

                # Should not raise exception
                results = extractor.extract_sql_elements(tree, "source code")

                # Should return empty list (or partial if we had some)
                assert isinstance(results, list)

                # Should log error
                assert mock_log.called
                args, _ = mock_log.call_args_list[0]
                assert "Error during enhanced SQL extraction" in args[0]
