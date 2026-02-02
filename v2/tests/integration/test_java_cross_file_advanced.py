"""
Integration tests for Java cross-file call resolution (T5.3).

Tests the enhanced CrossFileCallResolver with Java qualified method calls.
"""

from pathlib import Path

import networkx as nx
import pytest

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
from tree_sitter_analyzer_v2.graph.cross_file import CrossFileCallResolver
from tree_sitter_analyzer_v2.graph.symbols import SymbolEntry, SymbolTable


@pytest.fixture
def java_cross_file_dir() -> Path:
    """Return path to Java cross-file test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "java_project" / "src" / "main" / "java"


@pytest.fixture
def java_builder() -> CodeGraphBuilder:
    """Create CodeGraphBuilder for Java."""
    return CodeGraphBuilder(language="java")


# T5.3: Java Cross-File Call Resolver


def test_java_cross_file_resolver_qualified_lookup() -> None:
    """Test: Resolve Java qualified method calls (ClassName.methodName)."""
    # Create symbol table with Java methods
    table = SymbolTable()

    # Add UserService.createUser
    entry1 = SymbolEntry(
        node_id="module:UserService:class:UserService:method:createUser",
        file_path="UserService.java",
        name="createUser",
        type="FUNCTION",
        line_start=25,
        line_end=35,
    )
    table.add(entry1)

    # Add UserRepository.save
    entry2 = SymbolEntry(
        node_id="module:UserRepository:class:UserRepository:method:save",
        file_path="UserRepository.java",
        name="save",
        type="FUNCTION",
        line_start=20,
        line_end=28,
    )
    table.add(entry2)

    # Create import graph: UserService imports UserRepository
    import_graph = nx.DiGraph()
    import_graph.add_edge(
        "UserService.java", "UserRepository.java", type="IMPORTS", imported_names=["UserRepository"]
    )

    # Create resolver
    resolver = CrossFileCallResolver(import_graph, table)

    # Test resolving qualified call
    target = resolver._resolve_call(
        "save", "UserService.java", "module:UserService:class:UserService:method:createUser"
    )

    # Should resolve to UserRepository.save via import
    assert target is not None
    assert "save" in target
    assert "UserRepository" in target


def test_java_cross_file_resolver_same_file_priority() -> None:
    """Test: Same-file methods have higher priority than imports."""
    # Create symbol table
    table = SymbolTable()

    # Add validate() in UserService (same file)
    entry1 = SymbolEntry(
        node_id="module:UserService:class:UserService:method:validateEmail",
        file_path="UserService.java",
        name="validateEmail",
        type="FUNCTION",
        line_start=55,
        line_end=62,
    )
    table.add(entry1)

    # Add validate() in EmailService (different file)
    entry2 = SymbolEntry(
        node_id="module:EmailService:class:EmailService:method:validateEmail",
        file_path="EmailService.java",
        name="validateEmail",
        type="FUNCTION",
        line_start=30,
        line_end=35,
    )
    table.add(entry2)

    # Create import graph: UserService imports EmailService
    import_graph = nx.DiGraph()
    import_graph.add_edge(
        "UserService.java", "EmailService.java", type="IMPORTS", imported_names=["EmailService"]
    )

    # Create resolver
    resolver = CrossFileCallResolver(import_graph, table)

    # Test resolving validateEmail from UserService
    target = resolver._resolve_call(
        "validateEmail",
        "UserService.java",
        "module:UserService:class:UserService:method:createUser",
    )

    # Should resolve to same-file method (UserService.validateEmail)
    assert target is not None
    assert target == "module:UserService:class:UserService:method:validateEmail"
    assert "UserService" in target


def test_java_cross_file_resolver_filter_by_imports() -> None:
    """Test: Filter qualified lookups by imported files."""
    # Create symbol table
    table = SymbolTable()

    # Add save() in UserRepository
    entry1 = SymbolEntry(
        node_id="module:UserRepository:class:UserRepository:method:save",
        file_path="UserRepository.java",
        name="save",
        type="FUNCTION",
        line_start=20,
        line_end=28,
    )
    table.add(entry1)

    # Add save() in OrderRepository (not imported)
    entry2 = SymbolEntry(
        node_id="module:OrderRepository:class:OrderRepository:method:save",
        file_path="OrderRepository.java",
        name="save",
        type="FUNCTION",
        line_start=15,
        line_end=22,
    )
    table.add(entry2)

    # Create import graph: UserService only imports UserRepository
    import_graph = nx.DiGraph()
    import_graph.add_edge(
        "UserService.java", "UserRepository.java", type="IMPORTS", imported_names=["UserRepository"]
    )

    # Create resolver
    resolver = CrossFileCallResolver(import_graph, table)

    # Filter by imports
    all_saves = [entry1, entry2]
    filtered = resolver._filter_by_imports(all_saves, "UserService.java")

    # Should only include UserRepository.save (imported)
    assert len(filtered) == 1
    assert filtered[0].file_path == "UserRepository.java"


def test_java_cross_file_full_project_integration(java_builder: CodeGraphBuilder, java_cross_file_dir: Path) -> None:
    """Test: Full integration with Java project fixture."""
    # Build graph with cross-file resolution
    graph = java_builder.build_from_directory(
        str(java_cross_file_dir), pattern="**/*.java", cross_file=True
    )

    # Verify graph has nodes
    assert graph.number_of_nodes() > 0

    # Check if cross-file resolution created any CALLS edges
    # Note: May not work fully until JavaImportResolver is integrated in builder
    calls_edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d.get("type") == "CALLS"]

    print(f"\nTotal CALLS edges found: {len(calls_edges)}")
    for u, v, data in calls_edges:
        source_name = graph.nodes[u].get("name")
        target_name = graph.nodes.get(v, {}).get("name", "???")
        cross_file = data.get("cross_file", False)
        print(f"  {source_name} -> {target_name} (cross_file={cross_file})")

    # At minimum, should have intra-file calls
    assert len(calls_edges) >= 4


def test_java_cross_file_resolver_unresolved_tracking() -> None:
    """Test: Track unresolved calls for diagnostics."""
    # Create empty symbol table
    table = SymbolTable()

    # Create empty import graph
    import_graph = nx.DiGraph()

    # Create resolver
    resolver = CrossFileCallResolver(import_graph, table)

    # Try to resolve non-existent call
    target = resolver._resolve_call(
        "nonExistentMethod", "App.java", "module:App:class:App:method:main"
    )

    # Should return None for unresolved
    assert target is None

    # Try to resolve ambiguous call
    # Add two save() methods
    entry1 = SymbolEntry(
        node_id="module:UserRepository:class:UserRepository:method:save",
        file_path="UserRepository.java",
        name="save",
        type="FUNCTION",
        line_start=20,
        line_end=28,
    )
    table.add(entry1)

    entry2 = SymbolEntry(
        node_id="module:OrderRepository:class:OrderRepository:method:save",
        file_path="OrderRepository.java",
        name="save",
        type="FUNCTION",
        line_start=15,
        line_end=22,
    )
    table.add(entry2)

    # Add imports for both
    import_graph.add_edge(
        "App.java", "UserRepository.java", type="IMPORTS", imported_names=["UserRepository"]
    )
    import_graph.add_edge(
        "App.java", "OrderRepository.java", type="IMPORTS", imported_names=["OrderRepository"]
    )

    # Try to resolve ambiguous call
    target = resolver._resolve_call("save", "App.java", "module:App:class:App:method:main")

    # Should return None and log warning
    assert target is None
    assert len(resolver.get_unresolved_calls()) > 0
    assert "Ambiguous" in resolver.get_unresolved_calls()[0]
