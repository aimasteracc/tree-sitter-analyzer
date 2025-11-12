"""
Tests for Utils Module Initialization (utils/__init__.py)

Tests for all exported functions/classes, module imports, and re-exports.
"""

import pytest

from tree_sitter_analyzer.utils import (
    LoggingContext,
    QuietMode,
    SafeStreamHandler,
    TreeSitterQueryCompat,
    create_performance_logger,
    get_node_text_safe,
    log_api_info,
    log_debug,
    log_error,
    log_info,
    log_performance,
    log_warning,
    logger,
    perf_logger,
    safe_print,
    setup_logger,
    setup_performance_logger,
    setup_safe_logging_shutdown,
    suppress_output,
)


class TestModuleExports:
    """Test that all expected exports are available."""

    def test_tree_sitter_compat_exports(self) -> None:
        """Test tree-sitter compatibility exports are available."""
        assert TreeSitterQueryCompat is not None
        assert get_node_text_safe is not None
        assert log_api_info is not None

    def test_logging_function_exports(self) -> None:
        """Test logging function exports are available."""
        assert setup_logger is not None
        assert log_debug is not None
        assert log_error is not None
        assert log_warning is not None
        assert log_info is not None
        assert log_performance is not None

    def test_logging_class_exports(self) -> None:
        """Test logging class exports are available."""
        assert QuietMode is not None
        assert LoggingContext is not None
        assert SafeStreamHandler is not None

    def test_logging_utility_exports(self) -> None:
        """Test logging utility exports are available."""
        assert safe_print is not None
        assert setup_performance_logger is not None
        assert create_performance_logger is not None
        assert setup_safe_logging_shutdown is not None
        assert suppress_output is not None

    def test_logger_instance_exports(self) -> None:
        """Test logger instance exports are available."""
        assert logger is not None
        assert perf_logger is not None


class TestImportability:
    """Test that all exports can be imported."""

    def test_all_exports_importable(self) -> None:
        """Test that all items in __all__ can be imported."""
        from tree_sitter_analyzer import utils
        
        # Get __all__ list
        all_exports = getattr(utils, "__all__", [])
        
        # Verify all items are present
        for item in all_exports:
            assert hasattr(utils, item), f"{item} not found in utils module"

    def test_direct_import_from_utils(self) -> None:
        """Test direct import from utils works."""
        # This import should not raise
        from tree_sitter_analyzer.utils import (
            TreeSitterQueryCompat,
            log_info,
            logger,
        )
        
        assert TreeSitterQueryCompat is not None
        assert log_info is not None
        assert logger is not None


class TestFunctionTypes:
    """Test that exported functions are callable."""

    def test_tree_sitter_compat_callables(self) -> None:
        """Test tree-sitter compatibility functions are callable."""
        assert callable(get_node_text_safe)
        assert callable(log_api_info)

    def test_logging_functions_callable(self) -> None:
        """Test logging functions are callable."""
        assert callable(setup_logger)
        assert callable(log_debug)
        assert callable(log_error)
        assert callable(log_warning)
        assert callable(log_info)
        assert callable(log_performance)
        assert callable(safe_print)
        assert callable(setup_performance_logger)
        assert callable(create_performance_logger)
        assert callable(setup_safe_logging_shutdown)
        assert callable(suppress_output)


class TestClassTypes:
    """Test that exported classes are proper classes."""

    def test_tree_sitter_query_compat_is_class(self) -> None:
        """Test TreeSitterQueryCompat is a class."""
        assert isinstance(TreeSitterQueryCompat, type)

    def test_quiet_mode_is_class(self) -> None:
        """Test QuietMode is a class."""
        assert isinstance(QuietMode, type)

    def test_logging_context_is_class(self) -> None:
        """Test LoggingContext is a class."""
        assert isinstance(LoggingContext, type)

    def test_safe_stream_handler_is_class(self) -> None:
        """Test SafeStreamHandler is a class."""
        assert isinstance(SafeStreamHandler, type)


class TestLoggerInstances:
    """Test logger instance properties."""

    def test_logger_is_logger_instance(self) -> None:
        """Test logger is a Logger instance."""
        import logging
        
        assert isinstance(logger, logging.Logger)

    def test_perf_logger_is_logger_instance(self) -> None:
        """Test perf_logger is a Logger instance."""
        import logging
        
        assert isinstance(perf_logger, logging.Logger)

    def test_logger_has_name(self) -> None:
        """Test logger has a name."""
        assert logger.name is not None
        assert len(logger.name) > 0

    def test_perf_logger_has_name(self) -> None:
        """Test perf_logger has a name."""
        assert perf_logger.name is not None
        assert len(perf_logger.name) > 0


class TestModuleAttributes:
    """Test module-level attributes."""

    def test_module_has_all_attribute(self) -> None:
        """Test module has __all__ attribute."""
        from tree_sitter_analyzer import utils
        
        assert hasattr(utils, "__all__")
        assert isinstance(utils.__all__, list)
        assert len(utils.__all__) > 0

    def test_all_attribute_completeness(self) -> None:
        """Test __all__ contains expected items."""
        from tree_sitter_analyzer import utils
        
        expected_items = [
            "TreeSitterQueryCompat",
            "get_node_text_safe",
            "log_api_info",
            "setup_logger",
            "log_debug",
            "log_error",
            "log_warning",
            "log_info",
            "log_performance",
            "QuietMode",
            "safe_print",
            "LoggingContext",
            "setup_performance_logger",
            "create_performance_logger",
            "SafeStreamHandler",
            "setup_safe_logging_shutdown",
            "suppress_output",
            "logger",
            "perf_logger",
        ]
        
        for item in expected_items:
            assert item in utils.__all__, f"{item} not in __all__"


class TestImportSources:
    """Test that imports come from correct sources."""

    def test_logging_imports_from_logging_module(self) -> None:
        """Test logging functions come from logging module."""
        from tree_sitter_analyzer.utils import logging as utils_logging
        
        # Verify logging module is accessible
        assert hasattr(utils_logging, "log_info")
        assert hasattr(utils_logging, "log_error")

    def test_compat_imports_from_compat_module(self) -> None:
        """Test compat functions come from tree_sitter_compat module."""
        from tree_sitter_analyzer.utils import tree_sitter_compat
        
        # Verify compat module is accessible
        assert hasattr(tree_sitter_compat, "TreeSitterQueryCompat")
        assert hasattr(tree_sitter_compat, "get_node_text_safe")


class TestModuleDocstring:
    """Test module documentation."""

    def test_module_has_docstring(self) -> None:
        """Test module has a docstring."""
        from tree_sitter_analyzer import utils
        
        assert utils.__doc__ is not None
        assert len(utils.__doc__) > 0

    def test_docstring_describes_purpose(self) -> None:
        """Test docstring describes module purpose."""
        from tree_sitter_analyzer import utils
        
        docstring = utils.__doc__.lower()
        assert "util" in docstring or "package" in docstring


class TestNoExtraExports:
    """Test that no unexpected items are exported."""

    def test_all_public_items_in_all(self) -> None:
        """Test that public items (not starting with _) are in __all__."""
        from tree_sitter_analyzer import utils
        
        public_items = [
            name for name in dir(utils)
            if not name.startswith("_")
        ]
        
        # These are submodules, not items to export
        submodules = ["logging", "tree_sitter_compat"]
        
        for item in public_items:
            if item in submodules:
                continue
            assert item in utils.__all__, f"Public item {item} not in __all__"


class TestImportPerformance:
    """Test that imports don't have side effects."""

    def test_import_does_not_raise(self) -> None:
        """Test that importing the module doesn't raise exceptions."""
        # This test passes if the import at the top of the file succeeds
        from tree_sitter_analyzer import utils
        
        assert utils is not None

    def test_reimport_is_safe(self) -> None:
        """Test that reimporting the module is safe."""
        import importlib
        from tree_sitter_analyzer import utils
        
        # Should not raise
        importlib.reload(utils)
        
        # Should still be importable
        assert hasattr(utils, "log_info")


class TestFunctionalityAvailability:
    """Test that exported functionality works."""

    def test_log_info_works(self) -> None:
        """Test that log_info can be called."""
        # Should not raise
        log_info("Test message")

    def test_log_error_works(self) -> None:
        """Test that log_error can be called."""
        # Should not raise
        log_error("Test error")

    def test_log_warning_works(self) -> None:
        """Test that log_warning can be called."""
        # Should not raise
        log_warning("Test warning")

    def test_log_debug_works(self) -> None:
        """Test that log_debug can be called."""
        # Should not raise
        log_debug("Test debug")

    def test_safe_print_works(self) -> None:
        """Test that safe_print can be called."""
        # Should not raise
        safe_print("Test print")


class TestClassInstantiation:
    """Test that exported classes can be instantiated."""

    def test_quiet_mode_instantiation(self) -> None:
        """Test QuietMode can be instantiated."""
        # Should not raise
        with QuietMode():
            pass

    def test_logging_context_instantiation(self) -> None:
        """Test LoggingContext can be instantiated."""
        # Should not raise (though may require specific args)
        # We just test it's a class
        assert isinstance(LoggingContext, type)

    def test_tree_sitter_query_compat_instantiation(self) -> None:
        """Test TreeSitterQueryCompat can be instantiated."""
        # Requires specific arguments, so just verify it's a class
        assert isinstance(TreeSitterQueryCompat, type)
