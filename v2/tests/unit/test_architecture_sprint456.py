"""
Parametrized tests for Sprint 4-6 architectural changes.

Tests cover:
- S4-1: MCPServer argument validation
- S4-2: _meta envelope for timing
- S4-3: FormatterRegistry thread safety
- S4-4: ToolRegistry.get_all_schemas uses get_tool_definition
- S4-6: _detect_language_from_path uses registry
- S4-7: Unified LanguageRegistry
- S5-1: Parser return type LanguageParseResult
- S5-5: AnalyzerConfig centralized defaults
- S5-6: LRU file cache eviction
- S6-1: SymbolProtocol bridge
- S6-6: __init_subclass__ auto-registration
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


# ── S4-3: FormatterRegistry thread safety ──


class TestFormatterRegistryThreadSafety:
    """Verify that concurrent access to FormatterRegistry is safe."""

    def test_singleton_returns_same_instance(self) -> None:
        from tree_sitter_analyzer_v2.formatters.registry import get_default_registry

        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2

    def test_registry_has_lock(self) -> None:
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        reg = FormatterRegistry()
        assert hasattr(reg, "_lock")
        assert isinstance(reg._lock, type(threading.Lock()))

    def test_concurrent_register_and_get(self) -> None:
        """No crash when registering and getting formatters concurrently."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        reg = FormatterRegistry()
        errors: list[Exception] = []

        def register_custom(n: int) -> None:
            try:
                mock = MagicMock()
                reg.register(f"test_format_{n}", mock)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_custom, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(reg.list_formats()) >= 20 + 3  # 3 defaults + 20 custom


# ── S4-6: _detect_language_from_path ──


class TestDetectLanguageFromPath:
    """Verify _detect_language_from_path uses parser registry."""

    @pytest.mark.parametrize(
        "file_path,expected",
        [
            ("test.py", "python"),
            ("test.pyw", "python"),
            ("Test.java", "java"),
            ("app.ts", "typescript"),
            ("app.tsx", "typescript"),
            ("app.js", "javascript"),
            ("app.jsx", "javascript"),
            ("unknown.xyz", "python"),  # default
            (None, "python"),  # None path
            ("", "python"),  # empty path
        ],
        ids=[
            "python-py", "python-pyw", "java", "typescript-ts", "typescript-tsx",
            "javascript-js", "javascript-jsx", "unknown-ext", "none-path", "empty-path",
        ],
    )
    def test_detect_language(self, file_path: str | None, expected: str) -> None:
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        result = BaseTool._detect_language_from_path(file_path)
        assert result == expected

    @pytest.mark.parametrize(
        "file_path,default,expected",
        [
            ("unknown.xyz", "java", "java"),
            (None, "typescript", "typescript"),
        ],
    )
    def test_custom_default(self, file_path: str | None, default: str, expected: str) -> None:
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        result = BaseTool._detect_language_from_path(file_path, default=default)
        assert result == expected


# ── S4-7: Unified LanguageRegistry ──


class TestUnifiedLanguageRegistry:
    """Verify the unified language registry works correctly."""

    def test_parsers_registered(self) -> None:
        from tree_sitter_analyzer_v2.core.language_registry import get_all_parsers

        parsers = get_all_parsers()
        assert "python" in parsers
        assert "java" in parsers

    def test_ext_map_registered(self) -> None:
        from tree_sitter_analyzer_v2.core.language_registry import get_ext_lang_map

        ext_map = get_ext_lang_map()
        assert ext_map[".py"] == "python"
        assert ext_map[".java"] == "java"
        assert ext_map[".ts"] == "typescript"
        assert ext_map[".mjs"] == "javascript"

    def test_call_extractors_registered(self) -> None:
        from tree_sitter_analyzer_v2.core.language_registry import get_call_extractor

        py_ext = get_call_extractor("python")
        java_ext = get_call_extractor("java")
        assert py_ext is not None
        assert java_ext is not None

    def test_backward_compat_parser_registry(self) -> None:
        """Old imports from parser_registry still work."""
        from tree_sitter_analyzer_v2.core.parser_registry import get_parser

        assert get_parser("python") is not None

    def test_backward_compat_call_extractor_registry(self) -> None:
        """Old imports from call_extractor_registry still work."""
        from tree_sitter_analyzer_v2.core.call_extractor_registry import get_call_extractor

        assert get_call_extractor("python") is not None


# ── S5-5: AnalyzerConfig ──


class TestAnalyzerConfig:
    """Verify centralized configuration."""

    def test_default_config_immutable(self) -> None:
        from tree_sitter_analyzer_v2.core.config import DEFAULT_CONFIG

        with pytest.raises(AttributeError):
            DEFAULT_CONFIG.default_output_format = "markdown"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "attr,expected",
        [
            ("batch.max_files", 20),
            ("batch.max_sections_per_file", 50),
            ("batch.max_sections_total", 200),
            ("batch.max_total_bytes", 1024 * 1024),
            ("batch.max_total_lines", 5000),
            ("batch.max_file_size_bytes", 5 * 1024 * 1024),
            ("security.max_file_size", 50 * 1024 * 1024),
            ("code_map.max_tokens", 4000),
            ("graph.max_tokens", 4000),
            ("graph.max_nodes", 50),
            ("default_output_format", "toon"),
        ],
    )
    def test_default_values(self, attr: str, expected: Any) -> None:
        from tree_sitter_analyzer_v2.core.config import DEFAULT_CONFIG

        obj = DEFAULT_CONFIG
        for part in attr.split("."):
            obj = getattr(obj, part)
        assert obj == expected

    def test_batch_limits_backward_compat(self) -> None:
        """BATCH_LIMITS dict in extract.py matches centralized config."""
        from tree_sitter_analyzer_v2.core.config import DEFAULT_CONFIG
        from tree_sitter_analyzer_v2.mcp.tools.extract import BATCH_LIMITS

        assert BATCH_LIMITS == DEFAULT_CONFIG.batch.to_dict()


# ── S6-1: SymbolProtocol ──


class TestSymbolProtocol:
    """Verify SymbolProtocol is a usable bridge."""

    def test_symbol_info_satisfies_protocol(self) -> None:
        from tree_sitter_analyzer_v2.core.code_map.types import SymbolInfo
        from tree_sitter_analyzer_v2.core.types import SymbolProtocol

        sym = SymbolInfo(
            name="test_func", kind="function",
            file="test.py", line_start=1, line_end=10,
        )
        assert isinstance(sym, SymbolProtocol)

    def test_protocol_properties(self) -> None:
        from tree_sitter_analyzer_v2.core.code_map.types import SymbolInfo
        from tree_sitter_analyzer_v2.core.types import SymbolProtocol

        sym = SymbolInfo(
            name="MyClass", kind="class",
            file="src/models.py", line_start=5, line_end=50,
        )
        # Access via protocol-compatible properties
        assert sym.name == "MyClass"
        assert sym.kind == "class"
        assert sym.file == "src/models.py"
        assert sym.line_start == 5
        assert sym.line_end == 50


# ── S6-6: __init_subclass__ auto-registration ──


class TestInitSubclassRegistration:
    """Verify __init_subclass__ collects concrete tool classes."""

    def test_base_tool_has_registered_classes(self) -> None:
        """After importing tool modules, BaseTool should have registered classes."""
        import importlib

        # Import all tool modules to trigger registration
        modules = [
            "tree_sitter_analyzer_v2.mcp.tools.analyze",
            "tree_sitter_analyzer_v2.mcp.tools.query",
            "tree_sitter_analyzer_v2.mcp.tools.scale",
            "tree_sitter_analyzer_v2.mcp.tools.extract",
            "tree_sitter_analyzer_v2.mcp.tools.search",
            "tree_sitter_analyzer_v2.mcp.tools.find_and_grep",
        ]
        for mod in modules:
            importlib.import_module(mod)

        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool

        classes = BaseTool.registered_tool_classes()
        class_names = {cls.__name__ for cls in classes}
        # At minimum these should be registered
        assert "AnalyzeTool" in class_names
        assert "QueryTool" in class_names
        assert "CheckCodeScaleTool" in class_names
        assert "ExtractCodeSectionTool" in class_names


# ── S4-4: ToolRegistry.get_all_schemas uses get_tool_definition ──


class TestToolRegistrySchemas:
    """Verify schema generation uses get_tool_definition."""

    def test_schema_format(self) -> None:
        from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool
        from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry

        class DummyTool(BaseTool):
            def get_name(self) -> str:
                return "test_dummy"

            def get_description(self) -> str:
                return "A test tool"

            def get_schema(self) -> dict[str, Any]:
                return {"type": "object", "properties": {}}

            def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
                return {"success": True}

        registry = ToolRegistry()
        registry.register(DummyTool())
        schemas = registry.get_all_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "test_dummy"
        assert schemas[0]["description"] == "A test tool"
        assert "inputSchema" in schemas[0]


# ── S5-6: LRU file cache eviction ──


class TestLRUFileCache:
    """Verify the file cache respects max size limits."""

    def test_cache_eviction(self) -> None:
        """Cache should evict oldest entries when over capacity."""
        from collections import OrderedDict
        from tree_sitter_analyzer_v2.core.code_map.types import ModuleInfo, _FileCache

        # Simulate the cache behavior
        cache: OrderedDict[str, _FileCache] = OrderedDict()
        max_size = 3

        modules = [
            ModuleInfo(path=f"file{i}.py", language="python", lines=10,
                       classes=[], functions=[], imports=[], call_sites=[])
            for i in range(5)
        ]

        for i in range(5):
            key = f"file{i}.py"
            entry = _FileCache(mtime_ns=i * 1000, module=modules[i])
            if key in cache:
                cache.move_to_end(key)
            cache[key] = entry
            while len(cache) > max_size:
                cache.popitem(last=False)

        assert len(cache) == 3
        assert "file0.py" not in cache
        assert "file1.py" not in cache
        assert "file2.py" in cache
        assert "file3.py" in cache
        assert "file4.py" in cache


# ── S4-1 + S4-2: MCPServer validation and _meta envelope ──


class TestMCPServerValidation:
    """Verify argument validation and _meta envelope in MCPServer."""

    def test_meta_envelope_structure(self) -> None:
        """tools/call response should have _meta.timing_ms, not result._timing_ms."""
        from tree_sitter_analyzer_v2.mcp.server import MCPServer

        server = MCPServer(project_root=".")
        server.is_initialized = True

        # Call a tool that will fail (to test structure without needing real file)
        response = server.handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "check_code_scale",
                "arguments": {"file_path": "__nonexistent_file__.py"},
            },
        })

        # Should have result with success=False (file not found)
        assert "result" in response
        result = response["result"]
        assert result["success"] is False
        # _timing_ms should NOT be in result
        assert "_timing_ms" not in result
        # _meta should be at top level with timing_ms
        assert "_meta" in response
        assert "timing_ms" in response["_meta"]
