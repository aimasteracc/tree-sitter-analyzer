"""Tests for AST chunker semantic boundaries and import context enrichment."""
from __future__ import annotations

from tree_sitter_analyzer.core.ast_chunker import (
    AstChunk,
    detect_semantic_boundaries,
    enrich_chunks_with_imports,
)

# ---------------------------------------------------------------------------
# Semantic boundary detection
# ---------------------------------------------------------------------------


class TestDetectSemanticBoundaries:
    """Detect natural code boundaries from source text."""

    def test_blank_line_gap(self) -> None:
        source = "class A { }\n\n\nclass B { }\n"
        boundaries = detect_semantic_boundaries(source, 5)
        # Blank run at lines 2-3 should produce boundary at line 2
        assert 2 in boundaries

    def test_no_boundaries_in_compact_code(self) -> None:
        source = "class A {\n  void f() {}\n  void g() {}\n}\n"
        boundaries = detect_semantic_boundaries(source, 4)
        assert boundaries == []

    def test_block_comment_boundary(self) -> None:
        source = (
            "/**\n"
            " * Service layer.\n"
            " */\n"
            "class Service {\n"
            "}\n"
        )
        boundaries = detect_semantic_boundaries(source, 5)
        # After */ ending at line 3, boundary should be near line 5
        assert len(boundaries) >= 1

    def test_annotation_group_boundary(self) -> None:
        source = (
            "@Singleton\n"
            "@Transactional\n"
            "public class Service {\n"
            "}\n"
        )
        boundaries = detect_semantic_boundaries(source, 4)
        # After annotations, boundary at line 3 (where class starts)
        assert 3 in boundaries

    def test_empty_source(self) -> None:
        boundaries = detect_semantic_boundaries("", 0)
        assert boundaries == []

    def test_single_blank_line_no_boundary(self) -> None:
        source = "class A { }\n\nclass B { }\n"
        boundaries = detect_semantic_boundaries(source, 4)
        assert boundaries == []  # Single blank line not enough

    def test_multiple_boundaries(self) -> None:
        source = (
            "import A;\n\n\n"
            "class X { }\n\n\n"
            "class Y { }\n"
        )
        boundaries = detect_semantic_boundaries(source, 8)
        assert len(boundaries) >= 2


# ---------------------------------------------------------------------------
# Import context enrichment
# ---------------------------------------------------------------------------


class TestEnrichChunksWithImports:
    """Import context preservation when chunking."""

    def test_no_import_chunk_returns_original(self) -> None:
        chunks = [
            AstChunk(
                name="MyClass",
                chunk_type="class",
                start_line=1,
                end_line=10,
                token_estimate=40,
            ),
        ]
        result = enrich_chunks_with_imports(chunks, None, "class MyClass { }")
        assert len(result) == 1
        assert result[0].name == "MyClass"
        assert len(result[0].children) == 0

    def test_import_context_attached_to_referencing_chunk(self) -> None:
        source = (
            "import UserService;\n"
            "import Logger;\n"
            "\n"
            "class MyController {\n"
            "  UserService service;\n"
            "}\n"
        )
        import_chunk = AstChunk(
            name="imports",
            chunk_type="import_block",
            start_line=1,
            end_line=2,
            token_estimate=8,
        )
        class_chunk = AstChunk(
            name="MyController",
            chunk_type="class",
            start_line=4,
            end_line=6,
            token_estimate=12,
        )

        result = enrich_chunks_with_imports([class_chunk], import_chunk, source)
        assert len(result) == 1
        # Should have import_context as child since UserService is referenced
        assert any(c.chunk_type == "import_context" for c in result[0].children)

    def test_import_context_skipped_for_unreferenced_chunk(self) -> None:
        source = (
            "import UserService;\n"
            "\n"
            "class Unrelated {\n"
            "  int x;\n"
            "}\n"
        )
        import_chunk = AstChunk(
            name="imports",
            chunk_type="import_block",
            start_line=1,
            end_line=1,
            token_estimate=4,
        )
        class_chunk = AstChunk(
            name="Unrelated",
            chunk_type="class",
            start_line=3,
            end_line=5,
            token_estimate=12,
        )

        result = enrich_chunks_with_imports([class_chunk], import_chunk, source)
        assert len(result) == 1
        # No import context since UserService is not referenced
        assert all(c.chunk_type != "import_context" for c in result[0].children)

    def test_header_and_tail_chunks_not_enriched(self) -> None:
        source = "import A;\n\nclass C { A a; }\n"
        import_chunk = AstChunk(
            name="imports",
            chunk_type="import_block",
            start_line=1,
            end_line=1,
            token_estimate=4,
        )
        header_chunk = AstChunk(
            name="header",
            chunk_type="header",
            start_line=1,
            end_line=1,
            token_estimate=4,
        )
        tail_chunk = AstChunk(
            name="tail",
            chunk_type="tail",
            start_line=4,
            end_line=4,
            token_estimate=4,
        )

        result = enrich_chunks_with_imports(
            [header_chunk, tail_chunk], import_chunk, source
        )
        for chunk in result:
            assert all(c.chunk_type != "import_context" for c in chunk.children)

    def test_empty_chunks_returns_empty(self) -> None:
        import_chunk = AstChunk(
            name="imports",
            chunk_type="import_block",
            start_line=1,
            end_line=1,
            token_estimate=4,
        )
        result = enrich_chunks_with_imports([], import_chunk, "import A;")
        assert result == []
