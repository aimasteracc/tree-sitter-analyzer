#!/usr/bin/env python3
"""Tests for AST-aware chunking service."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.core.ast_chunker import (
    AstChunk,
    chunk_analysis_result,
    chunks_summary,
)
from tree_sitter_analyzer.models import Class, Function, Import, Variable

# --- Helpers ---


def _cls(name: str, start: int, end: int) -> Class:
    return Class(name=name, start_line=start, end_line=end)


def _fn(name: str, start: int, end: int) -> Function:
    return Function(name=name, start_line=start, end_line=end)


def _imp(name: str, start: int, end: int) -> Import:
    return Import(name=name, start_line=start, end_line=end)


def _var(name: str, start: int, end: int) -> Variable:
    return Variable(name=name, start_line=start, end_line=end)


# --- AstChunk properties ---


class TestAstChunk:
    def test_line_span(self) -> None:
        chunk = AstChunk(
            name="foo", chunk_type="function",
            start_line=10, end_line=20, token_estimate=44,
        )
        assert chunk.line_span == 11

    def test_to_dict(self) -> None:
        child = AstChunk(
            name="bar", chunk_type="method",
            start_line=2, end_line=5, token_estimate=16,
        )
        parent = AstChunk(
            name="Foo", chunk_type="class",
            start_line=1, end_line=10, token_estimate=40,
            language="java", children=(child,),
        )
        d = parent.to_dict()
        assert d["name"] == "Foo"
        assert d["type"] == "class"
        assert d["line_span"] == 10
        assert len(d["children"]) == 1
        assert d["children"][0]["name"] == "bar"


# --- Empty / edge cases ---


class TestEdgeCases:
    def test_empty_elements_returns_empty(self) -> None:
        assert chunk_analysis_result([], 100, "java") == []

    def test_zero_lines_returns_empty(self) -> None:
        els = [_fn("f", 1, 5)]
        assert chunk_analysis_result(els, 0, "python") == []

    def test_unknown_language_uses_default_strategy(self) -> None:
        els = [_cls("A", 1, 20), _fn("main", 22, 30)]
        chunks = chunk_analysis_result(els, 30, "brainfuck")
        assert len(chunks) >= 2
        types = {c.chunk_type for c in chunks}
        assert "class" in types
        assert "function" in types


# --- OOP languages (Java, C#, Kotlin, Scala) ---


class TestOopChunking:
    @pytest.mark.parametrize("lang", ["java", "csharp", "kotlin", "scala"])
    def test_java_style_class_with_methods(self, lang: str) -> None:
        elements: list = [
            _imp("java.util.List", 1, 1),
            _cls("Service", 3, 40),
            _fn("process", 5, 15),
            _fn("validate", 17, 25),
            _fn("Service", 27, 30),  # constructor
            _var("MAX", 32, 32),
        ]
        chunks = chunk_analysis_result(elements, 40, lang)

        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1
        svc = class_chunks[0]
        assert svc.name == "Service"
        assert svc.start_line == 3
        assert svc.end_line == 40
        method_names = {c.name for c in svc.children}
        assert "process" in method_names
        assert "validate" in method_names
        assert "Service" in method_names

    def test_import_chunk(self) -> None:
        elements: list = [
            _imp("java.util.List", 1, 1),
            _imp("java.util.Map", 2, 2),
            _cls("App", 4, 10),
        ]
        chunks = chunk_analysis_result(elements, 10, "java")
        import_chunks = [c for c in chunks if c.chunk_type == "import_block"]
        assert len(import_chunks) == 1
        assert import_chunks[0].start_line == 1
        assert import_chunks[0].end_line == 2

    def test_multiple_classes(self) -> None:
        elements: list = [
            _cls("A", 1, 20),
            _fn("a_method", 3, 10),
            _cls("B", 22, 40),
            _fn("b_method", 24, 35),
        ]
        chunks = chunk_analysis_result(elements, 40, "java")
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 2
        assert class_chunks[0].name == "A"
        assert class_chunks[1].name == "B"

    def test_header_and_tail_chunks(self) -> None:
        elements: list = [
            _imp("java.util.List", 1, 1),
            _cls("Service", 5, 35),
        ]
        chunks = chunk_analysis_result(elements, 40, "java")
        types = [c.chunk_type for c in chunks]
        assert "header" in types
        assert "tail" in types


# --- Script languages (Python, JS, TS, Ruby, PHP) ---


class TestScriptChunking:
    @pytest.mark.parametrize("lang", ["python", "javascript", "typescript", "ruby", "php"])
    def test_class_plus_top_level_functions(self, lang: str) -> None:
        elements: list = [
            _imp("os", 1, 1),
            _cls("Calculator", 3, 20),
            _fn("add", 5, 10),
            _fn("subtract", 12, 18),
            _fn("helper", 22, 30),
        ]
        chunks = chunk_analysis_result(elements, 30, lang)

        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        fn_chunks = [c for c in chunks if c.chunk_type == "function"]

        assert len(class_chunks) == 1
        assert class_chunks[0].name == "Calculator"
        assert len(class_chunks[0].children) == 2  # add, subtract

        assert len(fn_chunks) == 1
        assert fn_chunks[0].name == "helper"

    def test_only_top_level_functions(self) -> None:
        elements: list = [
            _fn("main", 1, 10),
            _fn("helper", 12, 20),
        ]
        chunks = chunk_analysis_result(elements, 20, "python")
        fn_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(fn_chunks) == 2

    def test_no_imports(self) -> None:
        elements: list = [
            _cls("Foo", 1, 10),
            _fn("bar", 3, 8),
        ]
        chunks = chunk_analysis_result(elements, 10, "python")
        import_chunks = [c for c in chunks if c.chunk_type == "import_block"]
        assert len(import_chunks) == 0


# --- Go / Rust / C / C++ ---


class TestFunctionChunking:
    @pytest.mark.parametrize("lang", ["go", "rust", "c", "cpp"])
    def test_top_level_functions_only(self, lang: str) -> None:
        elements: list = [
            _imp("fmt", 1, 1),
            _fn("main", 3, 10),
            _fn("handler", 12, 25),
        ]
        chunks = chunk_analysis_result(elements, 25, lang)
        fn_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(fn_chunks) == 2
        assert fn_chunks[0].name == "main"
        assert fn_chunks[1].name == "handler"


# --- chunks_summary ---


class TestChunksSummary:
    def test_empty(self) -> None:
        s = chunks_summary([])
        assert s["chunk_count"] == 0
        assert s["total_tokens"] == 0

    def test_with_chunks(self) -> None:
        chunks = [
            AstChunk("A", "class", 1, 10, 40, language="java"),
            AstChunk("foo", "function", 12, 20, 36, language="java"),
        ]
        s = chunks_summary(chunks)
        assert s["chunk_count"] == 2
        assert s["total_tokens"] == 76
        assert len(s["chunks"]) == 2


# --- Token estimation ---


class TestTokenEstimation:
    def test_single_line_chunk(self) -> None:
        els = [_fn("f", 1, 1)]
        chunks = chunk_analysis_result(els, 1, "python")
        fn = [c for c in chunks if c.chunk_type == "function"]
        assert len(fn) == 1
        assert fn[0].token_estimate >= 1

    def test_large_chunk_has_more_tokens(self) -> None:
        small_els = [_fn("small", 1, 5)]
        big_els = [_fn("big", 1, 100)]
        small = chunk_analysis_result(small_els, 5, "python")
        big = chunk_analysis_result(big_els, 100, "python")
        assert big[0].token_estimate > small[0].token_estimate


# --- Coverage: fields inside class ---


class TestFieldsInClass:
    def test_class_with_fields_produces_chunk(self) -> None:
        elements: list = [
            _cls("Config", 1, 20),
            _var("host", 3, 3),
            _var("port", 4, 4),
            _fn("load", 6, 15),
        ]
        chunks = chunk_analysis_result(elements, 20, "java")
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1
        assert class_chunks[0].name == "Config"
        assert any(c.name == "load" for c in class_chunks[0].children)
