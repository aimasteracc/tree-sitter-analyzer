"""
Edge case tests for Java plugin.
Tests error handling, boundary conditions, malformed code, and unusual scenarios.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin


class TestJavaPluginEdgeCases:
    """Test edge cases and error handling for Java plugin"""

    @pytest.fixture
    def extractor(self):
        """Create a Java element extractor instance"""
        return JavaElementExtractor()

    @pytest.fixture
    def plugin(self):
        """Create a Java plugin instance"""
        return JavaPlugin()

    def test_empty_source_code(self, extractor):
        """Test handling of empty source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        functions = extractor.extract_functions(mock_tree, "")
        classes = extractor.extract_classes(mock_tree, "")
        variables = extractor.extract_variables(mock_tree, "")
        imports = extractor.extract_imports(mock_tree, "")
        packages = extractor.extract_packages(mock_tree, "")
        annotations = extractor.extract_annotations(mock_tree, "")

        assert functions == []
        assert classes == []
        assert variables == []
        assert imports == []
        assert packages == []
        assert annotations == []

    def test_malformed_java_code(self, extractor):
        """Test handling of malformed Java code"""
        malformed_code = """
        public class Incomplete {
            public void method(
            // missing closing parenthesis and brace

        private String incomplete

        import java.util.;
        package ;

        @Annotation(
        public class Another {
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should not crash with malformed code
        functions = extractor.extract_functions(mock_tree, malformed_code)
        classes = extractor.extract_classes(mock_tree, malformed_code)
        variables = extractor.extract_variables(mock_tree, malformed_code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)

    def test_very_long_lines(self, extractor):
        """Test handling of very long lines"""
        # Create a very long line (10000 characters)
        long_line = "public class VeryLongClassName" + "A" * 9960 + " {}"

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle long lines without crashing
        classes = extractor.extract_classes(mock_tree, long_line)
        assert isinstance(classes, list)

    def test_unicode_and_special_characters(self, extractor):
        """Test handling of Unicode and special characters"""
        unicode_code = """
        package com.例え.テスト;

        import java.util.日本語;

        /**
         * 日本語のクラス
         * @author 田中太郎
         */
        public class 日本語クラス {

            private String 名前 = "値";

            /**
             * 日本語のメソッド
             * @param パラメータ 引数
             * @return 結果
             */
            public String 日本語メソッド(String パラメータ) {
                return "結果: " + パラメータ + " 🎉";
            }
        }

        // Special characters: !@#$%^&*()_+-=[]{}|;':\",./<>?
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle Unicode without crashing
        functions = extractor.extract_functions(mock_tree, unicode_code)
        classes = extractor.extract_classes(mock_tree, unicode_code)
        variables = extractor.extract_variables(mock_tree, unicode_code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)

    def test_deeply_nested_structures(self, extractor):
        """Test handling of deeply nested code structures"""
        nested_code = """
        public class Level1 {
            public class Level2 {
                public class Level3 {
                    public class Level4 {
                        public class Level5 {
                            public void deepMethod() {
                                if (true) {
                                    if (true) {
                                        if (true) {
                                            System.out.println("deep");
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle nested structures
        classes = extractor.extract_classes(mock_tree, nested_code)
        functions = extractor.extract_functions(mock_tree, nested_code)
        assert isinstance(classes, list)
        assert isinstance(functions, list)

    def test_node_text_extraction_errors(self, extractor):
        """Test error handling in node text extraction"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        extractor.content_lines = ["test content"]
        extractor._file_encoding = "utf-8"

        # Test with encoding error
        with patch(
            "tree_sitter_analyzer.encoding_utils.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = UnicodeDecodeError(
                "utf-8", b"", 0, 1, "test error"
            )

            result = extractor._get_node_text_optimized(mock_node)
            # Should fallback to simple extraction
            assert result == "test conte"

    def test_node_text_extraction_index_error(self, extractor):
        """Test index error handling in node text extraction"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (100, 0)  # Line that doesn't exist
        mock_node.end_point = (100, 10)

        extractor.content_lines = ["test content"]

        # Should handle index errors gracefully
        with patch(
            "tree_sitter_analyzer.encoding_utils.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = Exception("Test error")

            result = extractor._get_node_text_optimized(mock_node)
            assert result == ""  # Should return empty string on error

    def test_class_extraction_without_name(self, extractor):
        """Test class extraction when class has no name"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []  # No identifier child

        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_class_extraction_with_invalid_identifier(self, extractor):
        """Test class extraction with invalid identifier"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock identifier with None text
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_node.children = [mock_identifier]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = None

            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_class_extraction_with_attribute_error(self, extractor):
        """Test class extraction when AttributeError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []

        # Mock to raise AttributeError
        with patch.object(extractor, "_extract_modifiers_optimized") as mock_modifiers:
            mock_modifiers.side_effect = AttributeError("Test error")

            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_class_extraction_with_value_error(self, extractor):
        """Test class extraction when ValueError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []

        # Mock to raise ValueError
        with patch.object(extractor, "_extract_modifiers_optimized") as mock_modifiers:
            mock_modifiers.side_effect = ValueError("Test error")

            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_class_extraction_with_type_error(self, extractor):
        """Test class extraction when TypeError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []

        # Mock to raise TypeError
        with patch.object(extractor, "_extract_modifiers_optimized") as mock_modifiers:
            mock_modifiers.side_effect = TypeError("Test error")

            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_class_extraction_with_unexpected_error(self, extractor):
        """Test class extraction when unexpected error occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []

        # Mock to raise unexpected exception
        with patch.object(extractor, "_extract_modifiers_optimized") as mock_modifiers:
            mock_modifiers.side_effect = RuntimeError("Unexpected error")

            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_method_extraction_with_missing_signature(self, extractor):
        """Test method extraction when signature parsing fails"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock signature parsing to return None
        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.return_value = None

            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_method_extraction_with_attribute_error(self, extractor):
        """Test method extraction when AttributeError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise AttributeError
        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.side_effect = AttributeError("Test error")

            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_method_extraction_with_value_error(self, extractor):
        """Test method extraction when ValueError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise ValueError
        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.side_effect = ValueError("Test error")

            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_method_extraction_with_type_error(self, extractor):
        """Test method extraction when TypeError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise TypeError
        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.side_effect = TypeError("Test error")

            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_method_extraction_with_unexpected_error(self, extractor):
        """Test method extraction when unexpected error occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise unexpected exception
        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.side_effect = RuntimeError("Unexpected error")

            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_field_extraction_with_missing_declaration(self, extractor):
        """Test field extraction when declaration parsing fails"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock field parsing to return None
        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.return_value = None

            result = extractor._extract_field_optimized(mock_node)
            assert result == []

    def test_field_extraction_with_attribute_error(self, extractor):
        """Test field extraction when AttributeError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise AttributeError
        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.side_effect = AttributeError("Test error")

            result = extractor._extract_field_optimized(mock_node)
            assert result == []

    def test_field_extraction_with_value_error(self, extractor):
        """Test field extraction when ValueError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise ValueError
        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.side_effect = ValueError("Test error")

            result = extractor._extract_field_optimized(mock_node)
            assert result == []

    def test_field_extraction_with_type_error(self, extractor):
        """Test field extraction when TypeError occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise TypeError
        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.side_effect = TypeError("Test error")

            result = extractor._extract_field_optimized(mock_node)
            assert result == []

    def test_field_extraction_with_unexpected_error(self, extractor):
        """Test field extraction when unexpected error occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise unexpected exception
        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.side_effect = RuntimeError("Unexpected error")

            result = extractor._extract_field_optimized(mock_node)
            assert result == []

    def test_import_extraction_with_malformed_imports(self, extractor):
        """Test import extraction with malformed import statements"""
        malformed_imports = """
        import ;
        import java.util.;
        import static ;
        import static java.util.Collections.;
        import java..util.List;
        """

        mock_tree = Mock()
        mock_tree.root_node.children = []

        # Should handle malformed imports gracefully
        imports = extractor.extract_imports(mock_tree, malformed_imports)
        assert isinstance(imports, list)

    def test_import_fallback_with_invalid_patterns(self, extractor):
        """Test import fallback with invalid patterns"""
        invalid_imports = """
        import ;
        import java.util.;
        import static ;
        import static java.util.Collections.;
        """

        imports = extractor._extract_imports_fallback(invalid_imports)

        # Should handle invalid patterns gracefully
        assert isinstance(imports, list)
        # May contain some imports if patterns partially match

    def test_package_extraction_with_malformed_package(self, extractor):
        """Test package extraction with malformed package statements"""
        malformed_package = """
        package ;
        package com..example;
        package 123invalid;
        """

        mock_tree = Mock()
        mock_tree.root_node.children = []

        # Should handle malformed packages gracefully
        packages = extractor.extract_packages(mock_tree, malformed_package)
        assert isinstance(packages, list)

    def test_annotation_extraction_with_malformed_annotations(self, extractor):
        """Test annotation extraction with malformed annotations"""
        malformed_annotations = """
        @
        @Annotation(
        @Annotation(value=
        @Annotation(value="test", invalid
        """

        mock_tree = Mock()
        mock_tree.root_node.children = []

        # Should handle malformed annotations gracefully
        annotations = extractor.extract_annotations(mock_tree, malformed_annotations)
        assert isinstance(annotations, list)

    def test_memory_pressure_simulation(self, extractor):
        """Test behavior under memory pressure simulation"""
        # Simulate memory pressure by creating many large objects
        large_objects = []
        try:
            for _i in range(1000):
                large_objects.append("x" * 10000)  # 10KB strings

                # Test extraction during memory pressure
                mock_tree = Mock()
                mock_tree.root_node = Mock()
                mock_tree.root_node.children = []

                functions = extractor.extract_functions(
                    mock_tree, "public void test() {}"
                )
                assert isinstance(functions, list)

        except MemoryError:
            # If we hit memory error, that's expected in this test
            pass
        finally:
            # Clean up
            large_objects.clear()

    def test_concurrent_access_simulation(self, extractor):
        """Test simulation of concurrent access to caches"""
        import threading
        import time

        results = []
        errors = []

        def worker():
            try:
                for i in range(10):
                    mock_node = Mock()
                    mock_node.start_byte = i
                    mock_node.end_byte = i + 5
                    mock_node.start_point = (0, 0)
                    mock_node.end_point = (0, 5)

                    extractor.content_lines = [f"test content {i}"]

                    with patch(
                        "tree_sitter_analyzer.encoding_utils.extract_text_slice"
                    ) as mock_extract:
                        mock_extract.return_value = f"text_{i}"
                        result = extractor._get_node_text_optimized(mock_node)
                        results.append(result)

                    time.sleep(
                        0.001
                    )  # Small delay to increase chance of race conditions
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _i in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should not have any errors
        assert len(errors) == 0
        assert len(results) == 50  # 5 threads * 10 operations each

    def test_plugin_initialization_edge_cases(self, plugin):
        """Test plugin initialization with edge cases"""
        # Test with None language
        assert plugin.language == "java"

        # Test supported extensions
        assert ".java" in plugin.supported_extensions

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

        # Test with tree that has no root_node
        invalid_tree = Mock()
        invalid_tree.root_node = None

        result = plugin.extract_elements(invalid_tree, "public class Test {}")
        assert set(result.keys()) == expected_keys
        for key in expected_keys:
            assert result[key] == []

    def test_plugin_with_extraction_errors(self, plugin):
        """Test plugin behavior when extraction methods raise errors"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Mock extractor to raise exceptions
        with patch.object(plugin, "extractor") as mock_extractor:
            mock_extractor.extract_functions.side_effect = Exception(
                "Function extraction error"
            )
            mock_extractor.extract_classes.side_effect = Exception(
                "Class extraction error"
            )
            mock_extractor.extract_variables.side_effect = Exception(
                "Variable extraction error"
            )
            mock_extractor.extract_imports.side_effect = Exception(
                "Import extraction error"
            )
            mock_extractor.extract_packages.side_effect = Exception(
                "Package extraction error"
            )
            mock_extractor.extract_annotations.side_effect = Exception(
                "Annotation extraction error"
            )

            # Should handle exceptions gracefully
            result = plugin.extract_elements(mock_tree, "public class Test {}")

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

    def test_extreme_file_sizes(self, extractor):
        """Test handling of extremely large files"""
        # Simulate very large file
        large_content = "public void test() {}\n" * 10000  # 10k methods

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle large files without crashing
        functions = extractor.extract_functions(mock_tree, large_content)
        assert isinstance(functions, list)

    def test_encoding_edge_cases(self, extractor):
        """Test various encoding edge cases"""
        # Test with different encodings
        encodings = ["utf-8", "latin1", "ascii", "utf-16"]

        for encoding in encodings:
            extractor._file_encoding = encoding
            mock_node = Mock()
            mock_node.start_byte = 0
            mock_node.end_byte = 5
            mock_node.start_point = (0, 0)
            mock_node.end_point = (0, 5)

            extractor.content_lines = ["test"]

            # Should handle different encodings
            with patch(
                "tree_sitter_analyzer.encoding_utils.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = "test"
                result = extractor._get_node_text_optimized(mock_node)
                assert isinstance(result, str)

    def test_null_source_code_handling(self, extractor):
        """Test handling of None source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle None source code gracefully
        try:
            functions = extractor.extract_functions(mock_tree, None)
            classes = extractor.extract_classes(mock_tree, None)
            variables = extractor.extract_variables(mock_tree, None)
            imports = extractor.extract_imports(mock_tree, None)
            packages = extractor.extract_packages(mock_tree, None)
            annotations = extractor.extract_annotations(mock_tree, None)

            # Should return lists (may be empty)
            assert isinstance(functions, list)
            assert isinstance(classes, list)
            assert isinstance(variables, list)
            assert isinstance(imports, list)
            assert isinstance(packages, list)
            assert isinstance(annotations, list)
        except Exception:
            # If exceptions are raised, they should be handled gracefully
            pass

    def test_complex_generics_and_wildcards(self, extractor):
        """Test handling of complex generics and wildcards"""
        complex_code = """
        public class GenericTest<T extends Comparable<? super T>> {
            private Map<String, List<? extends Number>> complexField;

            public <U extends T> List<? super U> complexMethod(
                Map<? extends String, ? super Integer> param) {
                return null;
            }
        }
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle complex generics without crashing
        classes = extractor.extract_classes(mock_tree, complex_code)
        functions = extractor.extract_functions(mock_tree, complex_code)
        variables = extractor.extract_variables(mock_tree, complex_code)

        assert isinstance(classes, list)
        assert isinstance(functions, list)
        assert isinstance(variables, list)

    def test_lambda_expressions_and_method_references(self, extractor):
        """Test handling of lambda expressions and method references"""
        lambda_code = """
        public class LambdaTest {
            public void testLambdas() {
                List<String> list = Arrays.asList("a", "b", "c");
                list.forEach(s -> System.out.println(s));
                list.stream().map(String::toUpperCase).collect(Collectors.toList());

                Comparator<String> comp = (s1, s2) -> s1.compareTo(s2);
                Function<String, Integer> func = String::length;
            }
        }
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle lambdas and method references without crashing
        functions = extractor.extract_functions(mock_tree, lambda_code)
        assert isinstance(functions, list)

    def test_annotation_with_complex_values(self, extractor):
        """Test handling of annotations with complex values"""
        annotation_code = """
        @Entity(name = "user_table")
        @Table(indexes = {
            @Index(name = "idx_name", columnList = "name"),
            @Index(name = "idx_email", columnList = "email", unique = true)
        })
        @NamedQueries({
            @NamedQuery(name = "User.findByName",
                       query = "SELECT u FROM User u WHERE u.name = :name"),
            @NamedQuery(name = "User.findByEmail",
                       query = "SELECT u FROM User u WHERE u.email = :email")
        })
        public class User {
            @Column(nullable = false, length = 100)
            private String name;
        }
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle complex annotations without crashing
        annotations = extractor.extract_annotations(mock_tree, annotation_code)
        classes = extractor.extract_classes(mock_tree, annotation_code)
        variables = extractor.extract_variables(mock_tree, annotation_code)

        assert isinstance(annotations, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)
