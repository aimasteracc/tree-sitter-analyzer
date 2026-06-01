"""Tests for codegraph_class_hierarchy MCP tool — type inheritance analysis."""

from __future__ import annotations

import json

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.class_hierarchy import ClassHierarchy
from tree_sitter_analyzer.graph import edge_store as edge_store_module
from tree_sitter_analyzer.graph.edge_store import (
    Edge,
    EdgeKind,
    EdgeStore,
    class_node,
    file_node,
    symbol_node,
)
from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool


@pytest.fixture
def tool():
    return ClassHierarchyTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "models.py").write_text(
        "class Animal:\n    pass\n\nclass Dog(Animal):\n    pass\n\nclass Poodle(Dog):\n    pass\n"
    )
    return ClassHierarchyTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_class_hierarchy"

    def test_description_mentions_no_other(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "No other tool" in desc

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {
            "subclasses",
            "superclasses",
            "tree",
            "impact",
            "all",
            "summary",
        }

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

    def test_annotations_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is True
        assert hints["destructiveHint"] is False


class TestValidation:
    def test_all_mode_no_class_required(self, tool):
        assert tool.validate_arguments({"mode": "all"}) is True

    def test_summary_mode_no_class_required(self, tool):
        assert tool.validate_arguments({"mode": "summary"}) is True

    def test_subclasses_requires_class_name(self, tool):
        with pytest.raises(ValueError, match="class_name is required"):
            tool.validate_arguments({"mode": "subclasses"})

    def test_superclasses_requires_class_name(self, tool):
        with pytest.raises(ValueError, match="class_name is required"):
            tool.validate_arguments({"mode": "superclasses"})

    def test_valid_subclasses_with_class_name(self, tool):
        assert (
            tool.validate_arguments({"mode": "subclasses", "class_name": "Animal"})
            is True
        )


@pytest.mark.asyncio
class TestExecute:
    async def test_no_project_root_raises_or_returns_error(self, tool):
        try:
            result = await tool.execute({"mode": "all", "output_format": "json"})
            assert result["success"] is False
        except ValueError:
            pass  # tool raises ValueError when project root is not set

    async def test_all_mode_on_project(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "all", "output_format": "json"})
        assert result["success"] is True

    async def test_summary_mode_on_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "summary", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "summary"})
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_subclasses_mode_reads_edge_store_when_symbol_parents_missing(
        self, tmp_path
    ):
        sample = tmp_path / "models.py"
        sample.write_text(
            "class Animal:\n    pass\n\nclass Dog(Animal):\n    pass\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            assert cache.index_file(str(sample))["status"] == "indexed"
            row = (
                cache.get_conn()
                .execute(
                    "SELECT symbols_json FROM ast_index WHERE file_path = ?",
                    ("models.py",),
                )
                .fetchone()
            )
            symbols = json.loads(row["symbols_json"])
            for symbol in symbols["symbols"]:
                symbol["parents"] = []
            cache.get_conn().execute(
                "UPDATE ast_index SET symbols_json = ? WHERE file_path = ?",
                (json.dumps(symbols), "models.py"),
            )
            cache.get_conn().commit()
        finally:
            cache.close()

        result = await ClassHierarchyTool(str(tmp_path)).execute(
            {
                "mode": "subclasses",
                "class_name": "Animal",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert [item["name"] for item in result["subclasses"]] == ["Dog"]


class TestClassHierarchyEdgeStore:
    def test_falls_back_to_symbol_parents_when_edge_store_unavailable(
        self, monkeypatch, tmp_path
    ):
        sample = tmp_path / "models.py"
        sample.write_text(
            "class Animal:\n    pass\n\nclass Dog(Animal):\n    pass\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))

        class BrokenEdgeStore:
            def __init__(self, *_args, **_kwargs):
                raise RuntimeError("edge store unavailable")

        try:
            assert cache.index_file(str(sample))["status"] == "indexed"
            monkeypatch.setattr(edge_store_module, "EdgeStore", BrokenEdgeStore)

            hierarchy = ClassHierarchy(cache)
            hierarchy.build()

            assert [item["name"] for item in hierarchy.subclasses_of("Animal")] == [
                "Dog"
            ]
        finally:
            cache.close()

    def test_edge_store_metadata_fallbacks_and_empty_parent_map(self, tmp_path):
        sample = tmp_path / "models.py"
        sample.write_text(
            "\n".join(
                [
                    "class Animal:",
                    "    pass",
                    "",
                    "class Dog(Animal):",
                    "    pass",
                    "",
                    "class Cat(Animal):",
                    "    pass",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            assert cache.index_file(str(sample))["status"] == "indexed"
            conn = cache.get_conn()
            conn.execute("DELETE FROM edges")
            store = EdgeStore(conn, ensure_schema=False)
            store.upsert_edges(
                [
                    Edge(
                        symbol_node("models.py", "Cat", 7),
                        symbol_node("models.py", "Animal", 1),
                        EdgeKind.EXTENDS,
                        metadata={},
                    ),
                    Edge(
                        file_node("models.py"),
                        class_node("Animal"),
                        EdgeKind.EXTENDS,
                        metadata={},
                    ),
                ]
            )
            conn.execute(
                """INSERT INTO edges
                   (source_node_id, target_node_id, kind, line, provenance, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    symbol_node("models.py", "Dog", 4),
                    symbol_node("models.py", "Animal", 1),
                    EdgeKind.EXTENDS.value,
                    4,
                    "tree-sitter",
                    "{broken",
                ),
            )
            conn.commit()

            hierarchy = ClassHierarchy(cache)
            hierarchy.build()
            assert [item["name"] for item in hierarchy.subclasses_of("Animal")] == [
                "Cat",
                "Dog",
            ]

            conn.execute("DELETE FROM edges")
            store.upsert_edges(
                [Edge(file_node("models.py"), class_node("Animal"), EdgeKind.EXTENDS)]
            )
            assert ClassHierarchy(cache)._build_edges_from_edge_store() is False
        finally:
            cache.close()
