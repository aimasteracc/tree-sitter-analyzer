"""Tests for codegraph_class_hierarchy MCP tool — type inheritance analysis."""

from __future__ import annotations

import json

import pytest

from tree_sitter_analyzer import _ast_cache_build_state as build_state
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


def _stub_hierarchy(names_with_parents: dict[str, list[str]]) -> ClassHierarchy:
    """Build a pre-populated ClassHierarchy without touching an AST cache.

    The tmp-path fixtures in this module build no index (``_classes`` stays
    empty), so existence-dependent behavior is tested against an injected
    hierarchy instead.
    """
    from tree_sitter_analyzer.class_hierarchy import ClassInfo

    hierarchy = ClassHierarchy(cache=None)
    for name, parents in names_with_parents.items():
        hierarchy._classes[name].append(
            ClassInfo(
                name=name,
                file="models.py",
                line=1,
                end_line=2,
                language="python",
                parents=parents,
            )
        )
        for parent in parents:
            hierarchy._parent_map[name].append(parent)
            hierarchy._children[parent].append(name)
    hierarchy._built = True  # bypass build(); data is already populated
    return hierarchy


def test_has_class_distinguishes_existence_from_emptiness() -> None:
    """has_class is True for a defined leaf class (no subclasses) and False for
    an unknown name — the distinction the tree verdict relies on."""
    h = _stub_hierarchy({"Poodle": ["Dog"]})
    assert h.has_class("Poodle") is True
    assert h.has_class("NoSuchClassZZZ") is False


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
        # 'supers' is a documented alias for 'superclasses' (#802).
        assert set(mode["enum"]) == {
            "subclasses",
            "superclasses",
            "supers",
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

    def test_mode_not_required(self, tool):
        """Wave 1b (review issue 2): mode is resolved at runtime, so it must NOT
        be advertised as required — else a strict MCP client rejects a valid
        {class_name: X} call before dispatch."""
        assert "mode" not in tool.get_tool_schema().get("required", [])


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

    async def test_tree_leaf_class_is_found_not_notfound(self, tool, monkeypatch):
        """Wave 1b (audit structure-01): a real leaf class (exists but has no
        subclasses) must report INFO, not NOT_FOUND — existence, not subclass
        count, drives the verdict. Injects a populated hierarchy so the test is
        deterministic (the tmp fixture builds no index)."""
        monkeypatch.setattr(
            tool, "_get_hierarchy", lambda: _stub_hierarchy({"Poodle": ["Dog"]})
        )
        result = await tool.execute(
            {"mode": "tree", "class_name": "Poodle", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["subclass_count"] == 0
        assert result["verdict"] == "INFO"

    async def test_tree_unknown_class_is_notfound(self, tool, monkeypatch):
        monkeypatch.setattr(
            tool, "_get_hierarchy", lambda: _stub_hierarchy({"Poodle": ["Dog"]})
        )
        result = await tool.execute(
            {"mode": "tree", "class_name": "NoSuchClassZZZ", "output_format": "json"}
        )
        assert result["verdict"] == "NOT_FOUND"

    async def test_default_mode_named_class_is_class_scoped_not_global(
        self, tool, monkeypatch
    ):
        """No explicit mode + a class_name → class-scoped 'tree', NOT the global
        'summary' (which would ignore the class and return project-wide stats)."""
        monkeypatch.setattr(
            tool, "_get_hierarchy", lambda: _stub_hierarchy({"Poodle": ["Dog"]})
        )
        result = await tool.execute({"class_name": "Poodle", "output_format": "json"})
        assert result["mode"] == "tree"
        assert result["class_name"] == "Poodle"
        assert result["verdict"] == "INFO"
        assert "total_classes" not in result  # not the global summary

    async def test_subclasses_existing_class_no_children_is_info(
        self, tool, monkeypatch
    ):
        """Review issue 1: an existing class with zero subclasses is a valid
        INFO result, not NOT_FOUND (NOT_FOUND is reserved for unknown classes)."""
        # Dog exists (inherits Animal) but nothing inherits from Dog.
        monkeypatch.setattr(
            tool, "_get_hierarchy", lambda: _stub_hierarchy({"Dog": ["Animal"]})
        )
        result = await tool.execute(
            {"mode": "subclasses", "class_name": "Dog", "output_format": "json"}
        )
        assert result["subclass_count"] == 0
        assert result["verdict"] == "INFO"

    async def test_subclasses_unknown_class_is_notfound(self, tool, monkeypatch):
        monkeypatch.setattr(
            tool, "_get_hierarchy", lambda: _stub_hierarchy({"Dog": ["Animal"]})
        )
        result = await tool.execute(
            {
                "mode": "subclasses",
                "class_name": "NoSuchClassZZZ",
                "output_format": "json",
            }
        )
        assert result["verdict"] == "NOT_FOUND"

    async def test_rebuild_marker_warns_without_phantom_subclass_count(self, tmp_path):
        sample = tmp_path / "models.py"
        sample.write_text(
            "class Animal:\n    pass\n\nclass Dog(Animal):\n    pass\n",
            encoding="utf-8",
        )
        cache = ASTCache(str(tmp_path))
        try:
            cache.index_project(workers=0)
            build_state.mark_build_in_progress(cache.get_conn())

            tool = ClassHierarchyTool(str(tmp_path))
            result = await tool.execute(
                {
                    "mode": "subclasses",
                    "class_name": "Animal",
                    "output_format": "json",
                }
            )
        finally:
            build_state.clear_build_in_progress(cache.get_conn())
            cache.close()

        assert result["verdict"] == "WARN"
        assert result["index_rebuilding"] is True
        assert "subclass_count" not in result
        assert "subclasses" not in result
        assert "--full-index" not in result["next_step"]
        assert result["agent_summary"]["verdict"] == "WARN"

    async def test_superclasses_root_class_is_info(self, tool, monkeypatch):
        """Review issue 1: a root class with no parents exists → INFO, not
        NOT_FOUND."""
        monkeypatch.setattr(
            tool, "_get_hierarchy", lambda: _stub_hierarchy({"Animal": []})
        )
        result = await tool.execute(
            {"mode": "superclasses", "class_name": "Animal", "output_format": "json"}
        )
        assert result["superclass_count"] == 0
        assert result["verdict"] == "INFO"

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

    def test_same_name_class_without_parents_not_listed_as_subclass(
        self, tmp_path
    ) -> None:
        """Regression: #659 — same-name collision must not create false subclass.

        Two files both define a class named 'Worker':
        - real_worker.py: class Worker(Base) — genuinely inherits Base
        - fake_worker.py: class Worker:       — no inheritance whatsoever

        subclasses_of('Base') must return exactly one entry (real_worker.py),
        NOT two.  Before the fix the bare-name lookup in _classes['Worker']
        returned both ClassInfo entries, emitting the parentless one as a ghost.
        """
        real = tmp_path / "real_worker.py"
        real.write_text(
            "class Base:\n    pass\n\nclass Worker(Base):\n    pass\n",
            encoding="utf-8",
        )
        fake = tmp_path / "fake_worker.py"
        fake.write_text(
            "class Worker:\n    pass\n",
            encoding="utf-8",
        )

        cache = ASTCache(str(tmp_path))
        try:
            assert cache.index_file(str(real))["status"] == "indexed"
            assert cache.index_file(str(fake))["status"] == "indexed"

            hierarchy = ClassHierarchy(cache)
            hierarchy.build()

            subs = hierarchy.subclasses_of("Base")
            sub_entries = [(s["name"], s["file"]) for s in subs]

            # Only the real inheriting Worker must appear
            assert ("Worker", "real_worker.py") in sub_entries, (
                f"Real Worker missing from subclasses: {sub_entries}"
            )
            # The parentless Worker from fake_worker.py must NOT appear
            assert ("Worker", "fake_worker.py") not in sub_entries, (
                f"Ghost Worker from fake_worker.py incorrectly listed: {sub_entries}"
            )
            # Exactly one Worker entry total
            worker_entries = [e for e in sub_entries if e[0] == "Worker"]
            assert len(worker_entries) == 1, (
                f"Expected exactly 1 Worker subclass, got {len(worker_entries)}: {worker_entries}"
            )
        finally:
            cache.close()


class TestSameNameDifferentBaseCollision:
    """Codex P2 on #659: two same-named children inheriting DIFFERENT bases
    must each only appear under their actual base."""

    def test_same_name_children_different_bases_isolated(self, tmp_path):
        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy, ClassInfo

        h = ClassHierarchy.__new__(ClassHierarchy)
        # Minimal hand-built state (bypass index): two Worker classes, one
        # inherits Base, the other inherits Other.
        from collections import defaultdict

        h._built = True
        h._parent_map = defaultdict(list)
        h._children = defaultdict(list, {"Base": ["Worker"], "Other": ["Worker"]})
        h._confirmed_child_files = defaultdict(
            set,
            {
                "Base": {("a.py", "Worker")},
                "Other": {("b.py", "Worker")},
            },
        )
        h._classes = defaultdict(
            list,
            {
                "Worker": [
                    ClassInfo(
                        name="Worker",
                        file="a.py",
                        line=1,
                        end_line=2,
                        parents=["Base"],
                        language="python",
                    ),
                    ClassInfo(
                        name="Worker",
                        file="b.py",
                        line=1,
                        end_line=2,
                        parents=["Other"],
                        language="python",
                    ),
                ]
            },
        )
        h.build = lambda: None  # already "built"

        base_subs = h.subclasses_of("Base")
        assert [(s["file"]) for s in base_subs] == ["a.py"]
        other_subs = h.subclasses_of("Other")
        assert [(s["file"]) for s in other_subs] == ["b.py"]


@pytest.mark.asyncio
class TestAgentSummaryPresence:
    """#733: class_hierarchy must include agent_summary in every mode's response."""

    @pytest.fixture
    def tool_with_monkeypatched_hierarchy(self, tool, monkeypatch):
        from tree_sitter_analyzer.class_hierarchy import ClassHierarchy

        h = ClassHierarchy.__new__(ClassHierarchy)
        h._class_map = {
            "Animal": type(
                "CI",
                (),
                {
                    "name": "Animal",
                    "file": "a.py",
                    "line": 1,
                    "end_line": 5,
                    "parents": [],
                    "language": "python",
                },
            )(),
            "Dog": type(
                "CI",
                (),
                {
                    "name": "Dog",
                    "file": "b.py",
                    "line": 1,
                    "end_line": 5,
                    "parents": ["Animal"],
                    "language": "python",
                },
            )(),
        }
        h._built = True
        h.build = lambda: None

        def _has_class(name):
            return name in h._class_map

        def _subclasses_of(name, max_depth=10):
            return (
                [
                    {"name": "Dog", "file": "b.py", "line": 1}
                    for n in h._class_map
                    if name == "Animal"
                ]
                if name == "Animal"
                else []
            )

        def _superclasses_of(name):
            return (
                [{"name": "Animal", "file": "a.py", "line": 1}] if name == "Dog" else []
            )

        def _hierarchy_tree(name):
            return {"name": name, "children": []}

        def _all_classes(self=None):
            return ["Animal", "Dog"]

        def _summary(self=None):
            return {"total_classes": 2, "total_relationships": 1}

        h.has_class = _has_class
        h.subclasses_of = _subclasses_of
        h.superclasses_of = _superclasses_of
        h.hierarchy_tree = _hierarchy_tree
        h.all_classes = _all_classes
        h.summary = _summary
        monkeypatch.setattr(tool, "_hierarchy", h)
        monkeypatch.setattr(tool, "_get_hierarchy", lambda: h)
        return tool

    async def test_subclasses_has_agent_summary(
        self, tool_with_monkeypatched_hierarchy
    ):
        result = await tool_with_monkeypatched_hierarchy.execute(
            {"mode": "subclasses", "class_name": "Animal", "output_format": "json"}
        )
        assert "agent_summary" in result
        assert "summary_line" in result["agent_summary"]
        assert "next_step" in result["agent_summary"]
        assert "verdict" in result["agent_summary"]

    async def test_superclasses_has_agent_summary(
        self, tool_with_monkeypatched_hierarchy
    ):
        result = await tool_with_monkeypatched_hierarchy.execute(
            {"mode": "superclasses", "class_name": "Dog", "output_format": "json"}
        )
        assert "agent_summary" in result

    async def test_tree_has_agent_summary(self, tool_with_monkeypatched_hierarchy):
        result = await tool_with_monkeypatched_hierarchy.execute(
            {"mode": "tree", "class_name": "Animal", "output_format": "json"}
        )
        assert "agent_summary" in result

    async def test_all_has_agent_summary(self, tool_with_monkeypatched_hierarchy):
        result = await tool_with_monkeypatched_hierarchy.execute(
            {"mode": "all", "output_format": "json"}
        )
        assert "agent_summary" in result

    async def test_summary_has_agent_summary(self, tool_with_monkeypatched_hierarchy):
        result = await tool_with_monkeypatched_hierarchy.execute(
            {"mode": "summary", "output_format": "json"}
        )
        assert "agent_summary" in result

    async def test_unknown_mode_has_agent_summary(
        self, tool_with_monkeypatched_hierarchy
    ):
        result = await tool_with_monkeypatched_hierarchy.execute(
            {"mode": "nonexistent_mode", "output_format": "json"}
        )
        assert "agent_summary" in result
        assert result["agent_summary"]["verdict"] == "ERROR"
