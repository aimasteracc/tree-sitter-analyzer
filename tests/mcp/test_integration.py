#!/usr/bin/env python3
"""
Integration tests for MCP Server (Fixed Version)

Tests the complete MCP server functionality including tools,
resources, and their interactions.

Fixes:
- Improved cleanup fixtures based on root cause analysis
- Explicit cleanup of singleton instances
- Resolved async processing issues in destructors
"""

import asyncio
import gc
import json
import tempfile
import warnings
from pathlib import Path

# Mock functionality now provided by pytest-mock
import pytest
import pytest_asyncio

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.utils import (
    get_cache_manager,
    get_error_handler,
    get_performance_monitor,
)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_event_loop():
    """Event loop cleanup fixture (root fix version)"""
    yield

    # Explicitly cleanup singleton instances
    try:
        # Performance monitor (UnifiedAnalysisEngine) cleanup
        monitor = get_performance_monitor()
        if monitor and hasattr(monitor, "cleanup"):
            monitor.cleanup()

        # Cache manager cleanup
        cache_manager = get_cache_manager()
        if cache_manager and hasattr(cache_manager, "clear_all_caches"):
            cache_manager.clear_all_caches()

    except Exception as e:
        print(f"Warning: Error during explicit cleanup: {e}")

    # Post-test cleanup
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and not loop.is_closed():
        # Investigate remaining tasks
        pending = asyncio.all_tasks(loop)
        current_task = asyncio.current_task(loop)

        # Exclude current task
        pending = {task for task in pending if task is not current_task}

        if pending:
            # Cancel tasks
            for task in pending:
                if not task.done():
                    task.cancel()

            # Wait briefly to process cancellations
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True), timeout=1.0
                )
            except asyncio.TimeoutError:
                print(f"Warning: {len(pending)} tasks did not complete within timeout")
                # Forcibly check task status
                for i, task in enumerate(pending):
                    if not task.done():
                        print(f"  Task {i} is still running: {task}")
                        # Attempt forced termination
                        try:
                            task.cancel()
                        except Exception:
                            pass

        # Explicit event loop cleanup
        try:
            # Process remaining callbacks
            if hasattr(loop, "_ready"):
                loop._ready.clear()
            if hasattr(loop, "_scheduled"):
                loop._scheduled.clear()

            # Socket and file descriptor cleanup
            if hasattr(loop, "_selector") and loop._selector:
                try:
                    # Cleanup registered file descriptors in selector
                    for key in list(loop._selector.get_map().values()):
                        try:
                            loop._selector.unregister(key.fileobj)
                        except (KeyError, ValueError, OSError):
                            pass
                except Exception:
                    pass

        except Exception as e:
            print(f"Warning: Error during loop cleanup: {e}")

    # Force garbage collection
    gc.collect()


class TestMCPServerIntegration:
    """Integration tests for the complete MCP server"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.server = TreeSitterAnalyzerMCPServer()

        # Create temporary test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_files = self._create_test_files()

        # Set project path for statistics
        self.server.set_project_path(self.temp_dir)

        # Clear caches and metrics
        get_cache_manager().clear_all_caches()
        get_error_handler().clear_history()
        get_performance_monitor().clear_metrics()

    def teardown_method(self) -> None:
        """Clean up test fixtures"""
        import shutil

        # Temporarily suppress ResourceWarning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)

            # Explicit cleanup
            try:
                monitor = get_performance_monitor()
                if monitor and hasattr(monitor, "cleanup"):
                    monitor.cleanup()
            except Exception:
                pass

            # Server instance cleanup
            if hasattr(self, "server"):
                try:
                    # Clear server references
                    if hasattr(self.server, "server") and self.server.server:
                        self.server.server = None

                    # Clear analyzer references
                    if hasattr(self.server, "universal_analyzers"):
                        self.server.universal_analyzers.clear()

                    self.server = None
                except Exception:
                    pass

            # Delete temporary directory
            shutil.rmtree(self.temp_dir, ignore_errors=True)

            # Force garbage collection
            gc.collect()

    def _create_test_files(self) -> dict[str, Path]:
        """Create test files for integration testing"""
        test_files = {}

        # Java file
        java_content = """package com.example.test;

import java.util.List;
import java.util.ArrayList;

/**
 * Test class for integration testing
 */
public class TestClass {
    private String name;
    private List<String> items;

    public TestClass(String name) {
        this.name = name;
        this.items = new ArrayList<>();
    }

    public void addItem(String item) {
        if (item != null && !item.isEmpty()) {
            items.add(item);
        }
    }

    public String getName() {
        return name;
    }

    public List<String> getItems() {
        return new ArrayList<>(items);
    }
}
"""
        java_file = Path(self.temp_dir) / "TestClass.java"
        java_file.write_text(java_content)
        test_files["java"] = java_file

        # Python file
        python_content = '''#!/usr/bin/env python3
"""
Test Python module for integration testing
"""

from typing import List, Optional


class DataProcessor:
    """Process data with various operations"""

    def __init__(self, name: str):
        self.name = name
        self.data: List[str] = []

    def add_data(self, item: str) -> None:
        """Add data item"""
        if item and isinstance(item, str):
            self.data.append(item)

    def process_data(self) -> List[str]:
        """Process all data items"""
        result = []
        for item in self.data:
            if len(item) > 3:
                result.append(item.upper())
        return result

    def get_stats(self) -> dict:
        """Get processing statistics"""
        return {
            "total_items": len(self.data),
            "processed_items": len(self.process_data()),
            "processor_name": self.name
        }


def main():
    """Main function"""
    processor = DataProcessor("test")
    processor.add_data("hello")
    processor.add_data("world")
    print(processor.get_stats())


if __name__ == "__main__":
    main()
'''
        python_file = Path(self.temp_dir) / "data_processor.py"
        python_file.write_text(python_content)
        test_files["python"] = python_file

        # JavaScript file
        js_content = """/**
 * Test JavaScript module for integration testing
 */

class Calculator {
    constructor(name) {
        this.name = name;
        this.history = [];
    }

    add(a, b) {
        const result = a + b;
        this.history.push(`${a} + ${b} = ${result}`);
        return result;
    }

    multiply(a, b) {
        const result = a * b;
        this.history.push(`${a} * ${b} = ${result}`);
        return result;
    }

    getHistory() {
        return [...this.history];
    }

    clear() {
        this.history = [];
    }
}

function createCalculator(name) {
    return new Calculator(name);
}

module.exports = { Calculator, createCalculator };
"""
        js_file = Path(self.temp_dir) / "calculator.js"
        js_file.write_text(js_content)
        test_files["javascript"] = js_file

        return test_files

    @pytest.mark.asyncio
    async def test_complete_analysis_workflow(self) -> None:
        """Test complete analysis workflow with multiple tools"""
        # Test Java file analysis
        java_file = str(self.test_files["java"])

        # Test analyze_code_scale
        scale_result = await self.server._analyze_code_scale(
            {
                "file_path": java_file,
                "include_complexity": True,
                "include_details": True,
            }
        )

        assert "metrics" in scale_result
        assert "elements" in scale_result["metrics"]

        # Check that we got a valid response structure
        elements = scale_result["metrics"]["elements"]
        assert isinstance(elements["classes"], int)
        assert isinstance(elements["methods"], int)
        assert isinstance(elements["total"], int)
        assert elements["total"] >= 0

        # Test structure analysis (Step 2)
        structure_result = await self.server.table_format_tool.execute(
            {"file_path": java_file, "format_type": "full"}
        )

        assert "table_output" in structure_result
        assert structure_result["language"] == "java"
        assert "metadata" in structure_result

        # Test partial reading (Step 3)
        partial_result = await self.server.read_partial_tool.execute(
            {"file_path": java_file, "start_line": 1, "end_line": 10}
        )

        assert "partial_content_result" in partial_result
        assert "package com.example.test" in partial_result["partial_content_result"]

        # Position detection functionality has been removed
        # Test continues with other tools

    @pytest.mark.asyncio
    async def test_multi_language_support(self) -> None:
        """Test multi-language analysis support"""
        languages_tested = []
        languages_skipped = []

        for lang, file_path in self.test_files.items():
            try:
                # Use check_code_scale for multi-language testing
                result = await self.server._analyze_code_scale(
                    {"file_path": str(file_path), "include_complexity": False}
                )

                assert result["language"] == lang
                assert "metrics" in result
                languages_tested.append(lang)

            except Exception as e:
                # Check if this is a language support issue
                error_msg = str(e).lower()
                if any(
                    keyword in error_msg
                    for keyword in [
                        "language not supported",
                        "no module named 'tree_sitter_",
                        "language plugin not found",
                        "unsupported language",
                        "could not load",
                        "language for parsing",
                    ]
                ):
                    # Skip languages that aren't supported in this environment
                    languages_skipped.append(lang)
                    print(f"Skipping {lang} analysis: {e}")
                else:
                    pytest.fail(f"Failed to analyze {lang} file: {e}")

        # Verify we tested at least one language successfully
        assert len(languages_tested) >= 1, (
            f"No languages tested successfully. Tested: {languages_tested}, Skipped: {languages_skipped}"
        )

        # Log results for debugging
        print(f"Languages tested: {languages_tested}")
        print(f"Languages skipped: {languages_skipped}")

    @pytest.mark.asyncio
    async def test_resource_functionality(self) -> None:
        """Test MCP resource functionality"""
        # Test code file resource
        java_file = str(self.test_files["java"])
        file_uri = f"code://file/{java_file}"

        assert self.server.code_file_resource.matches_uri(file_uri)

        file_content = await self.server.code_file_resource.read_resource(file_uri)
        assert "package com.example.test" in file_content

        # Test project statistics resource
        stats_uri = "code://stats/overview"
        assert self.server.project_stats_resource.matches_uri(stats_uri)

        overview_content = await self.server.project_stats_resource.read_resource(
            stats_uri
        )
        overview_data = json.loads(overview_content)

        assert "total_files" in overview_data
        assert "languages" in overview_data
        assert overview_data["total_files"] >= 0

    def test_server_initialization(self) -> None:
        """Test server initialization and configuration"""
        # Test server components are initialized (updated for unified tools)
        assert self.server.analysis_engine is not None
        assert self.server.read_partial_tool is not None  # extract_code_section
        assert self.server.table_format_tool is not None  # analyze_code_structure
        assert self.server.code_file_resource is not None
        assert self.server.project_stats_resource is not None

        # Test server metadata
        assert self.server.name is not None
        assert self.server.version is not None


if __name__ == "__main__":
    pytest.main([__file__])
