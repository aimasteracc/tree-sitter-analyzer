"""Tests for Go/Rust-specific AST chunking (struct + method grouping)."""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.core.ast_chunker import chunk_analysis_result
from tree_sitter_analyzer.models import Class, Function, Import


def _cls(name: str, start: int, end: int) -> Class:
    return Class(name=name, start_line=start, end_line=end)


def _fn(name: str, start: int, end: int) -> Function:
    return Function(name=name, start_line=start, end_line=end)


def _imp(name: str, start: int, end: int) -> Import:
    return Import(name=name, start_line=start, end_line=end)


class TestGoStructMethodGrouping:
    """Go-specific: struct (class) with receiver methods grouped together."""

    @pytest.mark.parametrize("lang", ["go", "rust"])
    def test_struct_with_methods_grouped(self, lang: str) -> None:
        elements = [
            _imp("fmt", 1, 1),
            _cls("Server", 3, 8),
            _fn("Start", 10, 20),
            _fn("Stop", 22, 30),
        ]
        chunks = chunk_analysis_result(elements, 30, lang)

        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        fn_chunks = [c for c in chunks if c.chunk_type == "function"]

        assert len(class_chunks) == 1
        assert class_chunks[0].name == "Server"
        # Start and Stop are top-level functions (no nesting info from class range)
        assert len(fn_chunks) == 2

    @pytest.mark.parametrize("lang", ["go", "rust"])
    def test_import_chunk_present(self, lang: str) -> None:
        elements = [
            _imp("fmt", 1, 1),
            _imp("net/http", 2, 2),
            _fn("main", 4, 10),
        ]
        chunks = chunk_analysis_result(elements, 10, lang)
        import_chunks = [c for c in chunks if c.chunk_type == "import_block"]
        assert len(import_chunks) == 1
        assert import_chunks[0].start_line == 1
        assert import_chunks[0].end_line == 2

    @pytest.mark.parametrize("lang", ["go", "rust"])
    def test_struct_with_inline_methods(self, lang: str) -> None:
        """When methods are within the struct range, they become children."""
        elements = [
            _cls("Handler", 1, 30),
            _fn("ServeHTTP", 3, 15),
            _fn("Handle", 17, 28),
        ]
        chunks = chunk_analysis_result(elements, 30, lang)
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1
        assert len(class_chunks[0].children) == 2

    @pytest.mark.parametrize("lang", ["go", "rust"])
    def test_multiple_structs_and_functions(self, lang: str) -> None:
        elements = [
            _cls("Server", 1, 10),
            _fn("NewServer", 12, 20),
            _cls("Client", 22, 35),
            _fn("NewClient", 37, 45),
        ]
        chunks = chunk_analysis_result(elements, 45, lang)
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        fn_chunks = [c for c in chunks if c.chunk_type == "function"]

        assert len(class_chunks) == 2
        assert len(fn_chunks) == 2

    @pytest.mark.parametrize("lang", ["go", "rust"])
    def test_header_and_tail_for_function_lang(self, lang: str) -> None:
        elements = [
            _imp("fmt", 1, 1),
            _cls("Config", 5, 15),
            _fn("Load", 17, 30),
        ]
        chunks = chunk_analysis_result(elements, 35, lang)
        types = [c.chunk_type for c in chunks]
        assert "tail" in types

    @pytest.mark.parametrize("lang", ["go", "rust", "c", "cpp"])
    def test_only_functions_no_classes(self, lang: str) -> None:
        elements = [
            _fn("process", 1, 10),
            _fn("cleanup", 12, 20),
            _fn("init", 22, 25),
        ]
        chunks = chunk_analysis_result(elements, 25, lang)
        fn_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(fn_chunks) == 3
