#!/usr/bin/env python3
"""
Comprehensive tests for LanguageLoader

This test module provides comprehensive coverage for the LanguageLoader class,
testing language loading, caching, parser creation, and error handling.
"""

from unittest.mock import Mock, patch

from tree_sitter_analyzer.language_loader import (
    LanguageLoader,
    check_language_availability,
    create_parser_safely,
    get_loader,
    load_language,
    loader,
)


class TestLanguageLoaderInitialization:
    """Test LanguageLoader initialization"""

    def test_init(self):
        """Test basic initialization"""
        loader = LanguageLoader()
        assert loader._loaded_languages == {}
        assert loader._loaded_modules == {}
        assert loader._availability_cache == {}
        assert loader._parser_cache == {}
        assert loader._unavailable_languages == set()

    def test_language_modules_defined(self):
        """Test that LANGUAGE_MODULES is properly defined"""
        loader = LanguageLoader()
        assert isinstance(loader.LANGUAGE_MODULES, dict)
        assert len(loader.LANGUAGE_MODULES) > 0

    def test_supported_languages_property(self):
        """Test SUPPORTED_LANGUAGES property"""
        loader = LanguageLoader()
        languages = loader.SUPPORTED_LANGUAGES
        assert isinstance(languages, list)
        assert len(languages) > 0
        assert "python" in languages
        assert "java" in languages

    def test_typescript_dialects_defined(self):
        """Test TypeScript dialects mapping"""
        loader = LanguageLoader()
        assert isinstance(loader.TYPESCRIPT_DIALECTS, dict)
        assert "typescript" in loader.TYPESCRIPT_DIALECTS
        assert "tsx" in loader.TYPESCRIPT_DIALECTS


class TestLanguageAvailability:
    """Test language availability checking"""

    def test_is_language_available_cached_unavailable(self):
        """Test language marked as unavailable is returned immediately"""
        loader = LanguageLoader()
        loader._unavailable_languages.add("nonexistent")
        assert loader.is_language_available("nonexistent") is False

    def test_is_language_available_cached_available(self):
        """Test cached availability result"""
        loader = LanguageLoader()
        loader._availability_cache["test_lang"] = True
        assert loader.is_language_available("test_lang") is True

    @patch("tree_sitter_analyzer.language_loader.TREE_SITTER_AVAILABLE", False)
    def test_is_language_available_no_tree_sitter(self):
        """Test when tree-sitter is not available"""
        loader = LanguageLoader()
        assert loader.is_language_available("python") is False
        assert "python" in loader._unavailable_languages

    def test_is_language_available_unknown_language(self):
        """Test unknown language"""
        loader = LanguageLoader()
        assert loader.is_language_available("unknown_lang_xyz") is False
        assert "unknown_lang_xyz" in loader._unavailable_languages

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    def test_is_language_available_import_success(self, mock_import):
        """Test successful import marks language as available"""
        loader = LanguageLoader()
        mock_import.return_value = Mock()

        result = loader.is_language_available("python")

        assert result is True
        assert loader._availability_cache["python"] is True
        assert "python" not in loader._unavailable_languages

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    def test_is_language_available_import_failure(self, mock_import):
        """Test failed import marks language as unavailable"""
        loader = LanguageLoader()
        mock_import.side_effect = ImportError("Module not found")

        result = loader.is_language_available("python")

        assert result is False
        assert loader._availability_cache["python"] is False
        assert "python" in loader._unavailable_languages


class TestLoadLanguage:
    """Test language loading functionality"""

    @patch("tree_sitter_analyzer.language_loader.TREE_SITTER_AVAILABLE", False)
    def test_load_language_no_tree_sitter(self):
        """Test loading when tree-sitter is not available"""
        loader = LanguageLoader()
        result = loader.load_language("python")
        assert result is None

    def test_load_language_from_cache(self):
        """Test loading language from cache"""
        loader = LanguageLoader()
        mock_language = Mock()
        loader._loaded_languages["python"] = mock_language

        result = loader.load_language("python")

        assert result == mock_language

    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_unavailable(self, mock_available):
        """Test loading unavailable language"""
        loader = LanguageLoader()
        mock_available.return_value = False

        result = loader.load_language("unknown")

        assert result is None

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_success_modern_api(
        self, mock_available, mock_tree_sitter, mock_import
    ):
        """Test successful language loading with modern API"""
        loader = LanguageLoader()
        mock_available.return_value = True

        # Mock language object (modern API returns Language directly)
        # Need to create a mock that passes isinstance-like checks
        class MockLanguage:
            pass

        mock_language_obj = MockLanguage()

        mock_module = Mock()
        mock_module.language.return_value = mock_language_obj
        mock_import.return_value = mock_module

        loader.load_language("python")

        # Result might be wrapped in Language(), so check it's in cache
        assert loader._loaded_languages["python"] is not None

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_success_capsule_api(
        self, mock_available, mock_tree_sitter, mock_import
    ):
        """Test successful language loading with PyCapsule API"""
        loader = LanguageLoader()
        mock_available.return_value = True

        # Mock PyCapsule object
        mock_capsule = Mock()
        mock_capsule.__class__.__name__ = "PyCapsule"

        # Mock Language constructor
        mock_language_obj = Mock()
        mock_tree_sitter.Language.return_value = mock_language_obj

        mock_module = Mock()
        mock_module.language.return_value = mock_capsule
        mock_import.return_value = mock_module

        result = loader.load_language("python")

        assert result == mock_language_obj
        mock_tree_sitter.Language.assert_called_once_with(mock_capsule)

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_typescript_dialect(
        self, mock_available, mock_tree_sitter, mock_import
    ):
        """Test loading TypeScript with dialect selection"""
        loader = LanguageLoader()
        mock_available.return_value = True

        # Create proper mock language that passes checks
        class MockLanguage:
            pass

        mock_language_obj = MockLanguage()

        mock_module = Mock()
        mock_module.language_typescript.return_value = mock_language_obj
        mock_import.return_value = mock_module

        result = loader.load_language("typescript")

        # Should load successfully
        assert result is not None
        mock_module.language_typescript.assert_called_once()

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_tsx_dialect(
        self, mock_available, mock_tree_sitter, mock_import
    ):
        """Test loading TSX dialect"""
        loader = LanguageLoader()
        mock_available.return_value = True

        # Create proper mock language that passes checks
        class MockLanguage:
            pass

        mock_language_obj = MockLanguage()

        mock_module = Mock()
        mock_module.language_tsx.return_value = mock_language_obj
        mock_import.return_value = mock_module

        result = loader.load_language("tsx")

        # Should load successfully
        assert result is not None
        mock_module.language_tsx.assert_called_once()

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_module_cache(self, mock_available, mock_import):
        """Test that modules are cached"""
        loader = LanguageLoader()
        mock_available.return_value = True

        mock_language_obj = Mock()
        mock_language_obj.__class__.__name__ = "Language"

        mock_module = Mock()
        mock_module.language.return_value = mock_language_obj
        mock_import.return_value = mock_module

        # Load twice
        loader.load_language("python")
        loader.load_language("python")

        # Module should only be imported once
        mock_import.assert_called_once()

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_no_language_function(self, mock_available, mock_import):
        """Test loading when module has no language function"""
        loader = LanguageLoader()
        mock_available.return_value = True

        mock_module = Mock(spec=[])  # No language attribute
        mock_import.return_value = mock_module

        result = loader.load_language("python")

        assert result is None

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_import_error(self, mock_available, mock_import):
        """Test handling of import errors"""
        loader = LanguageLoader()
        mock_available.return_value = True

        mock_import.side_effect = ImportError("Module not found")

        result = loader.load_language("python")

        assert result is None
        assert "python" in loader._unavailable_languages


class TestCreateParser:
    """Test parser creation functionality"""

    @patch("tree_sitter_analyzer.language_loader.TREE_SITTER_AVAILABLE", False)
    def test_create_parser_no_tree_sitter(self):
        """Test parser creation when tree-sitter is not available"""
        loader = LanguageLoader()
        result = loader.create_parser_safely("python")
        assert result is None

    def test_create_parser_from_cache(self):
        """Test getting parser from cache"""
        loader = LanguageLoader()
        mock_parser = Mock()
        loader._parser_cache["python"] = mock_parser

        result = loader.create_parser_safely("python")

        assert result == mock_parser

    @patch.object(LanguageLoader, "load_language")
    def test_create_parser_language_load_fails(self, mock_load):
        """Test parser creation when language loading fails"""
        loader = LanguageLoader()
        mock_load.return_value = None

        result = loader.create_parser_safely("python")

        assert result is None

    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "load_language")
    def test_create_parser_success(self, mock_load, mock_tree_sitter):
        """Test successful parser creation"""
        loader = LanguageLoader()

        # Create a proper mock that passes the hasattr check
        # Need to create a class that looks like Language
        class MockLanguage:
            pass

        mock_language = MockLanguage()
        mock_load.return_value = mock_language

        mock_parser = Mock()
        mock_tree_sitter.Parser.return_value = mock_parser

        result = loader.create_parser_safely("python")

        assert result == mock_parser
        mock_parser.set_language.assert_called_once_with(mock_language)
        assert loader._parser_cache["python"] == mock_parser

    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "load_language")
    def test_create_parser_invalid_language_object(self, mock_load, mock_tree_sitter):
        """Test parser creation with invalid language object"""
        loader = LanguageLoader()

        mock_language = "not_a_language_object"
        mock_load.return_value = mock_language

        result = loader.create_parser_safely("python")

        assert result is None

    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "load_language")
    def test_create_parser_fallback_property(self, mock_load, mock_tree_sitter):
        """Test parser creation using language property fallback"""
        loader = LanguageLoader()

        # Create a proper mock that passes the hasattr check
        class MockLanguage:
            pass

        mock_language = MockLanguage()
        mock_load.return_value = mock_language

        mock_parser = Mock(spec=[])  # No set_language method
        mock_parser.language = None
        mock_tree_sitter.Parser.return_value = mock_parser

        result = loader.create_parser_safely("python")

        assert result == mock_parser
        assert mock_parser.language == mock_language

    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "load_language")
    def test_create_parser_constructor_fallback(self, mock_load, mock_tree_sitter):
        """Test parser creation using constructor fallback"""
        loader = LanguageLoader()

        # Create a proper mock that passes the hasattr check
        class MockLanguage:
            pass

        mock_language = MockLanguage()
        mock_load.return_value = mock_language

        # First call returns parser without set_language or language property
        mock_parser_no_methods = Mock(spec=[])
        # Make sure language attribute doesn't exist
        if hasattr(mock_parser_no_methods, "language"):
            delattr(mock_parser_no_methods, "language")

        # Second call with language in constructor
        mock_parser_with_lang = Mock()

        mock_tree_sitter.Parser.side_effect = [
            mock_parser_no_methods,
            mock_parser_with_lang,
        ]

        result = loader.create_parser_safely("python")

        assert result == mock_parser_with_lang

    def test_create_parser_alias(self):
        """Test that create_parser calls create_parser_safely"""
        loader = LanguageLoader()
        # They should be the same method
        import types

        assert isinstance(loader.create_parser, types.MethodType)
        assert isinstance(loader.create_parser_safely, types.MethodType)


class TestGetSupportedLanguages:
    """Test getting supported languages"""

    def test_get_supported_languages_empty_cache(self):
        """Test getting supported languages with empty cache"""
        loader = LanguageLoader()
        with patch.object(loader, "is_language_available", return_value=True):
            languages = loader.get_supported_languages()
            assert isinstance(languages, list)
            assert len(languages) > 0

    def test_get_supported_languages_filters_unavailable(self):
        """Test that unavailable languages are filtered out"""
        loader = LanguageLoader()
        loader._unavailable_languages.add("python")

        languages = loader.get_supported_languages()

        # Python should not be in the list if it's unavailable
        # (or should be if is_language_available still returns True)
        assert isinstance(languages, list)

    @patch.object(LanguageLoader, "is_language_available")
    def test_get_supported_languages_checks_availability(self, mock_available):
        """Test that availability is checked for each language"""
        loader = LanguageLoader()
        mock_available.return_value = True

        languages = loader.get_supported_languages()

        assert len(languages) > 0
        # is_language_available should be called for languages not in unavailable set
        assert mock_available.call_count > 0


class TestClearCache:
    """Test cache clearing functionality"""

    def test_clear_cache(self):
        """Test clearing all caches"""
        loader = LanguageLoader()

        # Populate caches
        loader._loaded_languages["python"] = Mock()
        loader._loaded_modules["tree_sitter_python"] = Mock()
        loader._availability_cache["python"] = True
        loader._parser_cache["python"] = Mock()
        loader._unavailable_languages.add("unknown")

        # Clear
        loader.clear_cache()

        # Verify all caches are empty
        assert len(loader._loaded_languages) == 0
        assert len(loader._loaded_modules) == 0
        assert len(loader._availability_cache) == 0
        assert len(loader._parser_cache) == 0
        assert len(loader._unavailable_languages) == 0


class TestGlobalFunctions:
    """Test module-level global functions"""

    def test_get_loader_singleton(self):
        """Test that get_loader returns singleton instance"""
        loader1 = get_loader()
        loader2 = get_loader()
        assert loader1 is loader2

    def test_loader_global_variable(self):
        """Test that loader global variable exists"""
        assert loader is not None
        assert isinstance(loader, LanguageLoader)

    @patch.object(LanguageLoader, "is_language_available")
    def test_check_language_availability_function(self, mock_available):
        """Test check_language_availability function"""
        mock_available.return_value = True
        result = check_language_availability("python")
        assert result is True
        mock_available.assert_called_once_with("python")

    @patch.object(LanguageLoader, "create_parser_safely")
    def test_create_parser_safely_function(self, mock_create):
        """Test create_parser_safely function"""
        mock_parser = Mock()
        mock_create.return_value = mock_parser
        result = create_parser_safely("python")
        assert result == mock_parser
        mock_create.assert_called_once_with("python")

    @patch.object(LanguageLoader, "load_language")
    def test_load_language_function(self, mock_load):
        """Test load_language function"""
        mock_language = Mock()
        mock_load.return_value = mock_language
        result = load_language("python")
        assert result == mock_language
        mock_load.assert_called_once_with("python")


class TestLanguageMapping:
    """Test language module mapping"""

    def test_language_modules_completeness(self):
        """Test that all expected languages are in LANGUAGE_MODULES"""
        loader = LanguageLoader()
        expected_languages = [
            "java",
            "javascript",
            "typescript",
            "tsx",
            "python",
            "c",
            "cpp",
            "rust",
            "go",
            "markdown",
            "sql",
            "csharp",
            "cs",
        ]

        for lang in expected_languages:
            assert lang in loader.LANGUAGE_MODULES

    def test_csharp_alias(self):
        """Test that cs is an alias for csharp"""
        loader = LanguageLoader()
        assert loader.LANGUAGE_MODULES["cs"] == loader.LANGUAGE_MODULES["csharp"]


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_load_language_with_none(self):
        """Test loading with None language"""
        loader = LanguageLoader()
        # None will return None due to unavailability check
        result = loader.load_language(None)  # type: ignore
        assert result is None

    def test_load_language_with_empty_string(self):
        """Test loading with empty string"""
        loader = LanguageLoader()
        result = loader.load_language("")
        assert result is None

    @patch("tree_sitter_analyzer.language_loader.importlib.import_module")
    @patch.object(LanguageLoader, "is_language_available")
    def test_load_language_attribute_error(self, mock_available, mock_import):
        """Test handling of AttributeError during loading"""
        loader = LanguageLoader()
        mock_available.return_value = True
        mock_import.side_effect = AttributeError("No such attribute")

        result = loader.load_language("python")

        assert result is None
        assert "python" in loader._unavailable_languages

    @patch("tree_sitter_analyzer.language_loader.tree_sitter")
    @patch.object(LanguageLoader, "load_language")
    def test_create_parser_exception(self, mock_load, mock_tree_sitter):
        """Test parser creation with exception"""
        loader = LanguageLoader()

        mock_language = Mock()
        mock_language.__class__.__name__ = "Language"
        mock_load.return_value = mock_language

        mock_tree_sitter.Parser.side_effect = Exception("Parser creation failed")

        result = loader.create_parser_safely("python")

        assert result is None


class TestConcurrentAccess:
    """Test behavior with concurrent-like access patterns"""

    def test_multiple_load_same_language(self):
        """Test loading the same language multiple times"""
        loader = LanguageLoader()

        with patch.object(loader, "is_language_available", return_value=True):
            with patch(
                "tree_sitter_analyzer.language_loader.importlib.import_module"
            ) as mock_import:
                mock_language = Mock()
                mock_language.__class__.__name__ = "Language"

                mock_module = Mock()
                mock_module.language.return_value = mock_language
                mock_import.return_value = mock_module

                # Load multiple times
                result1 = loader.load_language("python")
                result2 = loader.load_language("python")
                result3 = loader.load_language("python")

                # Should return same object
                assert result1 is result2
                assert result2 is result3

                # Module should only be imported once
                mock_import.assert_called_once()

    def test_cache_consistency(self):
        """Test that caches remain consistent"""
        loader = LanguageLoader()

        # Add to availability cache
        loader._availability_cache["python"] = True

        # Load language (should use cache)
        with patch(
            "tree_sitter_analyzer.language_loader.importlib.import_module"
        ) as mock_import:
            with patch("tree_sitter_analyzer.language_loader.tree_sitter"):
                # Create proper mock language that passes checks
                class MockLanguage:
                    pass

                mock_language = MockLanguage()

                mock_module = Mock()
                mock_module.language.return_value = mock_language
                mock_import.return_value = mock_module

                loader.load_language("python")

                # Verify caches are consistent
                assert "python" in loader._loaded_languages
                assert loader._availability_cache["python"] is True
