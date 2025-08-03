#!/usr/bin/env python3
"""
Global test configuration for tree-sitter-analyzer

Controls warnings and logs during test execution to ensure clean output.
"""

import asyncio
import gc
import logging
import os
import warnings

import pytest


@pytest.fixture(autouse=True)
def configure_logging():
    """
    Automatic application of test logging configuration

    Adjusts log levels before all test execution and
    suppresses unnecessary log output.
    """
    # Main logger configuration
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.ERROR)

    # Application-specific logger configuration
    app_logger = logging.getLogger("tree_sitter_analyzer")
    app_original_level = app_logger.level
    app_logger.setLevel(logging.ERROR)

    # Performance logger configuration
    perf_logger = logging.getLogger("tree_sitter_analyzer.performance")
    perf_original_level = perf_logger.level
    perf_logger.setLevel(logging.ERROR)

    yield

    # Restore levels after test
    root_logger.setLevel(original_level)
    app_logger.setLevel(app_original_level)
    perf_logger.setLevel(perf_original_level)


@pytest.fixture(autouse=True)
def cleanup_event_loops():
    """
    Root solution for Event loop ResourceWarning

    Properly cleanup unclosed event loops after tests
    """
    yield

    # Explicit event loop cleanup
    try:
        # Get current event loop and close it
        try:
            loop = asyncio.get_running_loop()
            if loop and not loop.is_closed():
                # Cancel running tasks
                pending_tasks = [
                    task for task in asyncio.all_tasks(loop) if not task.done()
                ]
                for task in pending_tasks:
                    task.cancel()

                # Wait for task completion
                if pending_tasks:
                    loop.run_until_complete(
                        asyncio.gather(*pending_tasks, return_exceptions=True)
                    )
        except RuntimeError:
            # Ignore if event loop is not running
            pass

        # Get and close all event loops
        try:
            # Get existing loop (don't create new one)
            try:
                # Python 3.12+ support: suppress warnings to avoid DeprecationWarning
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    try:
                        loop = asyncio.get_event_loop_policy().get_event_loop()
                    except RuntimeError:
                        # If event loop doesn't exist
                        loop = None
                if loop and not loop.is_closed():
                    # Cancel all incomplete tasks
                    pending = [
                        task for task in asyncio.all_tasks(loop) if not task.done()
                    ]
                    for task in pending:
                        task.cancel()

                    # Cleanup tasks
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )

                    # Explicitly close loop
                    loop.close()
            except (RuntimeError, AttributeError):
                pass

            # Reset event loop policy
            try:
                if (
                    hasattr(asyncio, "WindowsProactorEventLoopPolicy")
                    and os.name == "nt"
                ):
                    asyncio.set_event_loop_policy(
                        asyncio.WindowsProactorEventLoopPolicy()
                    )
                else:
                    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
                asyncio.set_event_loop(None)
            except Exception:
                pass

        except Exception:
            # Continue even if error occurs
            pass

        # Force garbage collection
        gc.collect()

    except Exception:
        # Ignore cleanup errors (prioritize test continuation)
        pass


# Disabled warning suppression - let's fix the root causes instead
# @pytest.fixture(autouse=True)
# def suppress_warnings():
#     """
#     Warning suppression configuration
#
#     Suppresses unnecessary warnings during test execution.
#     """
#     # Suppress various warnings
#     warnings.filterwarnings("ignore", category=DeprecationWarning)
#     warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
#     warnings.filterwarnings("ignore", category=FutureWarning)
#     warnings.filterwarnings("ignore", category=UserWarning)
#     warnings.filterwarnings("ignore", category=ResourceWarning)
#
#     # pytest-specific warnings
#     try:
#         import pytest
#         warnings.filterwarnings("ignore", category=pytest.PytestMockWarning)
#         warnings.filterwarnings("ignore", category=pytest.PytestRemovedIn9Warning)
#     except (ImportError, AttributeError):
#         pass
#
#     # asyncio-specific warnings
#     warnings.filterwarnings("ignore", message=".*unclosed event loop.*", category=ResourceWarning)
#     warnings.filterwarnings("ignore", message=".*Enable tracemalloc.*", category=ResourceWarning)
#
#     yield


# pytest-asyncio configuration
pytest_plugins = ["pytest_asyncio"]
