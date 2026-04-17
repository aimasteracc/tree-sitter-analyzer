#!/usr/bin/env python3
"""Integration tests for AST chunking quality on real files.

Validates that chunk_analysis_result produces semantically correct chunks
for real-world code files in different language families.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    UnifiedAnalysisEngine,
)
from tree_sitter_analyzer.core.ast_chunker import (
    AstChunk,
    chunk_analysis_result,
    chunks_summary,
)

# --- Real file contents for testing ---

# Use the actual content from real files
BIG_SERVICE_JAVA = Path(__file__).parent.parent.parent / "examples/BigService.java"
SAMPLE_GO = Path(__file__).parent.parent.parent / "examples/sample.go"
AST_CHUNKER_PY = Path(__file__).parent.parent.parent / "tree_sitter_analyzer/core/ast_chunker.py"


def _create_temp_file_with_content(path: Path) -> str:
    """Create a temp file with the content from the given path."""
    if not path.exists():
        pytest.skip(f"Source file not found: {path}")
    content = path.read_text()
    f = tempfile.NamedTemporaryFile(mode="w", suffix=path.suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


def _analyze_directly(file_path: str, language: str):
    """Analyze a file using the engine directly (bypassing API security checks)."""
    engine = UnifiedAnalysisEngine()
    request = AnalysisRequest(
        file_path=file_path,
        language=language,
        queries=None,
        include_elements=True,
        include_queries=False,
    )
    return engine.analyze_sync(request)


# --- Quality validation helpers ---


def _count_overlapping_chunks(chunks: list[AstChunk]) -> int:
    """Count how many chunks overlap with each other.

    Note: header-import overlap is allowed by design (header includes import block).
    Only count overlaps between other chunk types.
    """
    overlap_count = 0
    for i, c1 in enumerate(chunks):
        for c2 in chunks[i + 1 :]:
            # Skip header-import overlap (allowed by design)
            if (
                c1.chunk_type == "header" and c2.chunk_type == "import_block"
            ) or (
                c2.chunk_type == "header" and c1.chunk_type == "import_block"
            ):
                continue
            if not (c1.end_line < c2.start_line or c2.end_line < c1.start_line):
                overlap_count += 1
    return overlap_count


def _count_gaps(chunks: list[AstChunk], total_lines: int) -> int:
    """Count lines not covered by any chunk (gaps in coverage)."""
    if not chunks:
        return total_lines

    covered_lines: set[int] = set()
    for c in chunks:
        covered_lines.update(range(c.start_line, c.end_line + 1))
    return total_lines - len(covered_lines)


def _validate_chunk_hierarchy(chunks: list[AstChunk]) -> bool:
    """Validate that children chunks are properly nested within parents."""
    for chunk in chunks:
        for child in chunk.children:
            if not (chunk.start_line <= child.start_line and child.end_line <= chunk.end_line):
                return False
    return True


def _validate_token_estimates(chunks: list[AstChunk]) -> bool:
    """Validate that token estimates are reasonable (line_count * 4)."""
    for chunk in chunks:
        expected = (chunk.end_line - chunk.start_line + 1) * 4
        if chunk.token_estimate != expected:
            return False
    return True


# --- Java chunking quality tests ---


class TestJavaChunkingQuality:
    """Test AST chunking on real Java files."""

    def test_java_file_chunks_without_overlaps(self) -> None:
        """Real Java files should produce non-overlapping chunks."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "java",
            )

            overlaps = _count_overlapping_chunks(chunks)
            assert overlaps == 0, f"Found {overlaps} overlapping chunks in BigService.java"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_java_chunks_cover_entire_file(self) -> None:
        """Chunks should cover all lines of the file (including header/tail)."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            total_lines = result.line_count
            chunks = chunk_analysis_result(result.elements, total_lines, "java")

            # Allow some gaps for empty lines, but not excessive
            gaps = _count_gaps(chunks, total_lines)
            gap_percentage = (gaps / total_lines) * 100 if total_lines > 0 else 0
            assert gap_percentage < 10, f"Too many gaps ({gap_percentage:.1f}%) in BigService.java"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_big_service_has_class_chunk(self) -> None:
        """BigService.java should have at least one class chunk."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "java",
            )

            class_chunks = [c for c in chunks if c.chunk_type == "class"]
            assert len(class_chunks) >= 1, "Should have at least one class chunk"
            assert any(c.name == "BigService" for c in class_chunks), "Should have BigService class"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_big_service_import_chunk(self) -> None:
        """BigService.java should have an import block chunk."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "java",
            )

            import_chunks = [c for c in chunks if c.chunk_type == "import_block"]
            assert len(import_chunks) == 1, "Should have exactly one import block"
        finally:
            Path(temp_file).unlink(missing_ok=True)


# --- Go chunking quality tests ---


class TestGoChunkingQuality:
    """Test AST chunking on real Go files."""

    def test_go_file_chunks_without_overlaps(self) -> None:
        """Real Go files should produce non-overlapping chunks."""
        temp_file = _create_temp_file_with_content(SAMPLE_GO)
        try:
            result = _analyze_directly(temp_file, "go")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "go",
            )

            overlaps = _count_overlapping_chunks(chunks)
            assert overlaps == 0, f"Found {overlaps} overlapping chunks in sample.go"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_sample_go_has_struct_chunks(self) -> None:
        """sample.go should have struct (class) chunks."""
        temp_file = _create_temp_file_with_content(SAMPLE_GO)
        try:
            result = _analyze_directly(temp_file, "go")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "go",
            )

            struct_chunks = [c for c in chunks if c.chunk_type == "class"]
            assert len(struct_chunks) >= 2, "Should have at least 2 struct chunks"

            # Check for specific structs
            struct_names = {c.name for c in struct_chunks}
            assert "Service" in struct_names
            assert "WorkerPool" in struct_names or "Config" in struct_names
        finally:
            Path(temp_file).unlink(missing_ok=True)


# --- Python chunking quality tests ---


class TestPythonChunkingQuality:
    """Test AST chunking on real Python files."""

    def test_python_file_chunks_without_overlaps(self) -> None:
        """Real Python files should produce non-overlapping chunks."""
        temp_file = _create_temp_file_with_content(AST_CHUNKER_PY)
        try:
            result = _analyze_directly(temp_file, "python")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "python",
            )

            overlaps = _count_overlapping_chunks(chunks)
            assert overlaps == 0, f"Found {overlaps} overlapping chunks in ast_chunker.py"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_ast_chunker_has_function_chunks(self) -> None:
        """ast_chunker.py should have function chunks for top-level functions."""
        temp_file = _create_temp_file_with_content(AST_CHUNKER_PY)
        try:
            result = _analyze_directly(temp_file, "python")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "python",
            )

            fn_chunks = [c for c in chunks if c.chunk_type == "function"]
            assert len(fn_chunks) >= 5, "Should have at least 5 function chunks"

            # Check for specific key functions
            fn_names = {c.name for c in fn_chunks}
            assert "chunk_analysis_result" in fn_names
            assert "chunks_summary" in fn_names
        finally:
            Path(temp_file).unlink(missing_ok=True)


# --- Cross-language quality invariants ---


class TestCrossLanguageQualityInvariants:
    """Tests that should pass for ALL languages."""

    def test_no_overlapping_chunks_java(self) -> None:
        """Invariant: chunks should never overlap (Java)."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(result.elements, result.line_count, "java")
            overlaps = _count_overlapping_chunks(chunks)
            assert overlaps == 0
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_no_overlapping_chunks_go(self) -> None:
        """Invariant: chunks should never overlap (Go)."""
        temp_file = _create_temp_file_with_content(SAMPLE_GO)
        try:
            result = _analyze_directly(temp_file, "go")
            chunks = chunk_analysis_result(result.elements, result.line_count, "go")
            overlaps = _count_overlapping_chunks(chunks)
            assert overlaps == 0
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_no_overlapping_chunks_python(self) -> None:
        """Invariant: chunks should never overlap (Python)."""
        temp_file = _create_temp_file_with_content(AST_CHUNKER_PY)
        try:
            result = _analyze_directly(temp_file, "python")
            chunks = chunk_analysis_result(result.elements, result.line_count, "python")
            overlaps = _count_overlapping_chunks(chunks)
            assert overlaps == 0
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_chunk_hierarchy_valid_java(self) -> None:
        """Invariant: children chunks must be within parent bounds (Java)."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(result.elements, result.line_count, "java")
            assert _validate_chunk_hierarchy(chunks), "Chunk hierarchy validation failed"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_chunk_hierarchy_valid_go(self) -> None:
        """Invariant: children chunks must be within parent bounds (Go)."""
        temp_file = _create_temp_file_with_content(SAMPLE_GO)
        try:
            result = _analyze_directly(temp_file, "go")
            chunks = chunk_analysis_result(result.elements, result.line_count, "go")
            assert _validate_chunk_hierarchy(chunks), "Chunk hierarchy validation failed"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_chunk_hierarchy_valid_python(self) -> None:
        """Invariant: children chunks must be within parent bounds (Python)."""
        temp_file = _create_temp_file_with_content(AST_CHUNKER_PY)
        try:
            result = _analyze_directly(temp_file, "python")
            chunks = chunk_analysis_result(result.elements, result.line_count, "python")
            assert _validate_chunk_hierarchy(chunks), "Chunk hierarchy validation failed"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_token_estimates_consistent_java(self) -> None:
        """Invariant: token estimates should be line_count * 4 (Java)."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(result.elements, result.line_count, "java")
            assert _validate_token_estimates(chunks), "Token estimate validation failed"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_token_estimates_consistent_go(self) -> None:
        """Invariant: token estimates should be line_count * 4 (Go)."""
        temp_file = _create_temp_file_with_content(SAMPLE_GO)
        try:
            result = _analyze_directly(temp_file, "go")
            chunks = chunk_analysis_result(result.elements, result.line_count, "go")
            assert _validate_token_estimates(chunks), "Token estimate validation failed"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_token_estimates_consistent_python(self) -> None:
        """Invariant: token estimates should be line_count * 4 (Python)."""
        temp_file = _create_temp_file_with_content(AST_CHUNKER_PY)
        try:
            result = _analyze_directly(temp_file, "python")
            chunks = chunk_analysis_result(result.elements, result.line_count, "python")
            assert _validate_token_estimates(chunks), "Token estimate validation failed"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_chunks_summary_matches_chunks_java(self) -> None:
        """Invariant: chunks_summary should accurately reflect chunks (Java)."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(result.elements, result.line_count, "java")
            summary = chunks_summary(chunks)
            assert summary["chunk_count"] == len(chunks)
            expected_tokens = sum(c.token_estimate for c in chunks)
            assert summary["total_tokens"] == expected_tokens
            assert len(summary["chunks"]) == len(chunks)
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_chunks_summary_matches_chunks_go(self) -> None:
        """Invariant: chunks_summary should accurately reflect chunks (Go)."""
        temp_file = _create_temp_file_with_content(SAMPLE_GO)
        try:
            result = _analyze_directly(temp_file, "go")
            chunks = chunk_analysis_result(result.elements, result.line_count, "go")
            summary = chunks_summary(chunks)
            assert summary["chunk_count"] == len(chunks)
            expected_tokens = sum(c.token_estimate for c in chunks)
            assert summary["total_tokens"] == expected_tokens
            assert len(summary["chunks"]) == len(chunks)
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_chunks_summary_matches_chunks_python(self) -> None:
        """Invariant: chunks_summary should accurately reflect chunks (Python)."""
        temp_file = _create_temp_file_with_content(AST_CHUNKER_PY)
        try:
            result = _analyze_directly(temp_file, "python")
            chunks = chunk_analysis_result(result.elements, result.line_count, "python")
            summary = chunks_summary(chunks)
            assert summary["chunk_count"] == len(chunks)
            expected_tokens = sum(c.token_estimate for c in chunks)
            assert summary["total_tokens"] == expected_tokens
            assert len(summary["chunks"]) == len(chunks)
        finally:
            Path(temp_file).unlink(missing_ok=True)


# --- Specific semantic validations ---


class TestSemanticChunkCorrectness:
    """Validate that chunks represent semantically meaningful units."""

    def test_java_class_chunk_contains_methods(self) -> None:
        """Java class chunks should have method children."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "java",
            )

            class_chunks = [c for c in chunks if c.chunk_type == "class"]
            big_service = next((c for c in class_chunks if c.name == "BigService"), None)

            assert big_service is not None
            # BigService has many methods, should have at least 10 method children
            assert len(big_service.children) >= 10, f"Expected many methods, got {len(big_service.children)}"

            # Verify all children are methods
            for child in big_service.children:
                assert child.chunk_type == "method"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_go_struct_contains_methods(self) -> None:
        """Go struct chunks should exist but methods are top-level in Go."""
        temp_file = _create_temp_file_with_content(SAMPLE_GO)
        try:
            result = _analyze_directly(temp_file, "go")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "go",
            )

            service_chunk = next((c for c in chunks if c.name == "Service"), None)
            assert service_chunk is not None, "Service struct not found"

            # In Go, methods are declared at top level with receiver, not inside struct
            # So Service struct won't have method children, but there should be
            # top-level functions that are methods (Name, IsRunning, Start, etc.)
            function_chunks = [c for c in chunks if c.chunk_type == "function"]
            method_names = {c.name for c in function_chunks}
            assert "Name" in method_names, "Expected Name method"
            assert "IsRunning" in method_names, "Expected IsRunning method"
            assert "Start" in method_names, "Expected Start method"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_python_mixed_class_and_function_chunks(self) -> None:
        """Python files should have both class chunks and top-level function chunks."""
        temp_file = _create_temp_file_with_content(AST_CHUNKER_PY)
        try:
            result = _analyze_directly(temp_file, "python")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "python",
            )

            chunk_types = {c.chunk_type for c in chunks}

            # Should have at least some of these chunk types
            assert len(chunk_types) >= 2, f"Expected multiple chunk types, got {chunk_types}"

            # If there are classes, they should be in class chunks
            class_chunks = [c for c in chunks if c.chunk_type == "class"]
            if class_chunks:
                # Class chunks may have method children
                for cls in class_chunks:
                    for child in cls.children:
                        assert child.chunk_type in ("method", "function"), f"Unexpected child type: {child.chunk_type}"
        finally:
            Path(temp_file).unlink(missing_ok=True)


# --- Chunk summary quality tests ---


class TestChunksSummaryQuality:
    """Test that chunks_summary produces useful metadata."""

    def test_summary_includes_all_chunk_metadata(self) -> None:
        """Summary should include name, type, line_span, and tokens for each chunk."""
        temp_file = _create_temp_file_with_content(BIG_SERVICE_JAVA)
        try:
            result = _analyze_directly(temp_file, "java")
            chunks = chunk_analysis_result(
                result.elements,
                result.line_count,
                "java",
            )

            summary = chunks_summary(chunks)

            for chunk_dict in summary["chunks"]:
                assert "name" in chunk_dict
                assert "type" in chunk_dict
                assert "start_line" in chunk_dict
                assert "end_line" in chunk_dict
                assert "line_span" in chunk_dict
                assert "tokens" in chunk_dict
                assert "children" in chunk_dict

                # Validate line_span calculation
                expected_span = chunk_dict["end_line"] - chunk_dict["start_line"] + 1
                assert chunk_dict["line_span"] == expected_span
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_summary_empty_chunks(self) -> None:
        """Summary should handle empty chunk list gracefully."""
        summary = chunks_summary([])

        assert summary["chunk_count"] == 0
        assert summary["total_tokens"] == 0
        assert summary["chunks"] == []
