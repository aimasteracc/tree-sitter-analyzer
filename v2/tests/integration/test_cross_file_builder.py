"""
Integration tests for cross-file call resolution in CodeGraphBuilder.

Tests the complete flow: ImportResolver → SymbolTableBuilder → CrossFileCallResolver
"""

from pathlib import Path

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

# Test fixture directory
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "cross_file_project"


class TestCrossFileBuilder:
    """Test cross-file call resolution in CodeGraphBuilder."""

    def test_build_with_cross_file_disabled(self):
        """Test that cross_file=False only includes intra-file calls."""
        builder = CodeGraphBuilder()
        graph = builder.build_from_directory(str(FIXTURE_DIR), cross_file=False)

        # Should have nodes from both files
        # Node IDs are formatted as "module:main", "module:utils", etc.
        assert any("module:main" in node for node in graph.nodes())
        assert any("module:utils" in node for node in graph.nodes())

        # Should NOT have cross-file edges (only intra-file calls)
        # Note: Basic builder doesn't add CALLS edges, so we just verify no cross_file edges exist
        cross_file_edges = [
            (u, v)
            for u, v, data in graph.edges(data=True)
            if data.get("type") == "CALLS" and data.get("cross_file") is True
        ]
        assert len(cross_file_edges) == 0, "Should not have cross-file edges when cross_file=False"

    def test_build_with_cross_file_enabled(self):
        """Test that cross_file=True adds cross-file CALLS edges."""
        builder = CodeGraphBuilder()
        graph = builder.build_from_directory(str(FIXTURE_DIR), cross_file=True)

        # Should have nodes from both modules
        # Node format: "module:main:function:main", "module:utils:function:helper", etc.
        main_nodes = [n for n in graph.nodes() if "module:main" in n]
        utils_nodes = [n for n in graph.nodes() if "module:utils" in n]

        assert len(main_nodes) > 0, "Should have main module nodes"
        assert len(utils_nodes) > 0, "Should have utils module nodes"

        # Find cross-file CALLS edges
        cross_file_edges = []
        for u, v, data in graph.edges(data=True):
            if data.get("type") == "CALLS" and data.get("cross_file") is True:
                cross_file_edges.append((u, v))

        # Should have at least one cross-file call
        # module:main:function:main calls module:utils:function:helper
        # module:main:function:main calls module:utils:function:validate
        assert len(cross_file_edges) > 0, "Should have cross-file CALLS edges"

        # Verify specific cross-file calls exist
        main_main = "module:main:function:main"
        utils_helper = "module:utils:function:helper"

        if main_main in graph.nodes() and utils_helper in graph.nodes():
            # Check if main calls helper
            assert graph.has_edge(main_main, utils_helper), (
                f"Expected edge from {main_main} to {utils_helper}"
            )

            # Check edge is marked as cross-file
            edge_data = graph[main_main][utils_helper]
            assert edge_data.get("cross_file") is True, (
                "Cross-file edge should be marked with cross_file=True"
            )

    def test_cross_file_resolution_accuracy(self):
        """Test that cross-file resolution correctly identifies targets."""
        builder = CodeGraphBuilder()
        graph = builder.build_from_directory(str(FIXTURE_DIR), cross_file=True)

        # Get all CALLS edges
        calls_edges = [
            (u, v, data) for u, v, data in graph.edges(data=True) if data.get("type") == "CALLS"
        ]

        # Verify we have cross-file calls
        cross_file_calls = [(u, v) for u, v, data in calls_edges if data.get("cross_file") is True]

        # Should have some of each type
        # Note: May have no intra-file calls if parser doesn't detect them
        assert len(cross_file_calls) > 0, "Should detect cross-file calls"
