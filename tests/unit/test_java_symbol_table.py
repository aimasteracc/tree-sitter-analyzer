"""
Unit tests for Java symbol table support.

Tests T5.2: Java Symbol Table functionality.
"""

import networkx as nx

from tree_sitter_analyzer_v2.graph.symbols import SymbolEntry, SymbolTable, SymbolTableBuilder

# T5.2: Java Symbol Table


def test_symbol_table_add_java_method() -> None:
    """Test: Add Java method to symbol table."""
    table = SymbolTable()

    entry = SymbolEntry(
        node_id="module:UserService:class:UserService:method:createUser",
        file_path="UserService.java",
        name="createUser",
        type="FUNCTION",
        line_start=25,
        line_end=35,
    )

    table.add(entry)

    # Lookup by simple name
    results = table.lookup("createUser")
    assert len(results) == 1
    assert results[0].name == "createUser"
    assert results[0].file_path == "UserService.java"


def test_symbol_table_lookup_qualified_java_method() -> None:
    """Test: Lookup Java method by qualified name (ClassName.methodName)."""
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

    # Lookup by qualified name
    results = table.lookup_qualified("UserService.createUser")
    assert len(results) >= 1
    assert any(e.name == "createUser" and "UserService" in e.node_id for e in results)

    results = table.lookup_qualified("UserRepository.save")
    assert len(results) >= 1
    assert any(e.name == "save" and "UserRepository" in e.node_id for e in results)


def test_symbol_table_prioritize_same_file_java() -> None:
    """Test: Prioritize same-file Java methods when context provided."""
    table = SymbolTable()

    # Add save() method in UserRepository.java
    entry1 = SymbolEntry(
        node_id="module:UserRepository:class:UserRepository:method:save",
        file_path="UserRepository.java",
        name="save",
        type="FUNCTION",
        line_start=20,
        line_end=28,
    )
    table.add(entry1)

    # Add save() method in OrderRepository.java (different file)
    entry2 = SymbolEntry(
        node_id="module:OrderRepository:class:OrderRepository:method:save",
        file_path="OrderRepository.java",
        name="save",
        type="FUNCTION",
        line_start=15,
        line_end=22,
    )
    table.add(entry2)

    # Lookup without context: should return both
    results = table.lookup("save")
    assert len(results) == 2

    # Lookup with context: should prioritize same file
    results = table.lookup("save", context_file="UserRepository.java")
    assert len(results) == 1
    assert results[0].file_path == "UserRepository.java"

    results = table.lookup("save", context_file="OrderRepository.java")
    assert len(results) == 1
    assert results[0].file_path == "OrderRepository.java"


def test_symbol_table_builder_java_methods() -> None:
    """Test: SymbolTableBuilder extracts Java methods from graphs."""
    builder = SymbolTableBuilder()

    # Create graph for UserService.java
    graph1 = nx.DiGraph()
    graph1.add_node(
        "module:UserService:class:UserService:method:createUser",
        type="FUNCTION",
        name="createUser",
        line_start=25,
        line_end=35,
    )
    graph1.add_node(
        "module:UserService:class:UserService:method:deleteUser",
        type="FUNCTION",
        name="deleteUser",
        line_start=40,
        line_end=50,
    )

    # Create graph for UserRepository.java
    graph2 = nx.DiGraph()
    graph2.add_node(
        "module:UserRepository:class:UserRepository:method:save",
        type="FUNCTION",
        name="save",
        line_start=20,
        line_end=28,
    )

    # Build symbol table
    file_graphs = {"UserService.java": graph1, "UserRepository.java": graph2}
    table = builder.build(file_graphs)

    # Verify all methods are in the table
    assert len(table.lookup("createUser")) == 1
    assert len(table.lookup("deleteUser")) == 1
    assert len(table.lookup("save")) == 1


def test_symbol_table_lookup_qualified_simple_name() -> None:
    """Test: lookup_qualified() works with simple names (no dot)."""
    table = SymbolTable()

    entry = SymbolEntry(
        node_id="module:UserService:class:UserService:method:createUser",
        file_path="UserService.java",
        name="createUser",
        type="FUNCTION",
        line_start=25,
        line_end=35,
    )
    table.add(entry)

    # Lookup by simple name (no dot)
    results = table.lookup_qualified("createUser")
    assert len(results) == 1
    assert results[0].name == "createUser"


def test_symbol_table_lookup_qualified_with_context() -> None:
    """Test: lookup_qualified() respects context_file."""
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

    # Add save() in OrderRepository
    entry2 = SymbolEntry(
        node_id="module:OrderRepository:class:OrderRepository:method:save",
        file_path="OrderRepository.java",
        name="save",
        type="FUNCTION",
        line_start=15,
        line_end=22,
    )
    table.add(entry2)

    # Lookup qualified name with context
    results = table.lookup_qualified("UserRepository.save")
    assert len(results) >= 1
    # Should find the UserRepository version
    assert any("UserRepository" in e.node_id for e in results)

    # Lookup qualified name with context file
    results = table.lookup_qualified("save", context_file="UserRepository.java")
    assert len(results) == 1
    assert results[0].file_path == "UserRepository.java"


def test_symbol_table_handle_multiple_java_classes() -> None:
    """Test: Symbol table handles multiple Java classes correctly."""
    table = SymbolTable()

    # Add methods from different classes
    classes_methods = [
        ("App", "main", 10, 15),
        ("App", "run", 17, 25),
        ("UserService", "createUser", 30, 40),
        ("UserService", "deleteUser", 42, 52),
        ("UserRepository", "save", 20, 28),
        ("UserRepository", "delete", 30, 38),
    ]

    for class_name, method_name, start, end in classes_methods:
        entry = SymbolEntry(
            node_id=f"module:{class_name}:class:{class_name}:method:{method_name}",
            file_path=f"{class_name}.java",
            name=method_name,
            type="FUNCTION",
            line_start=start,
            line_end=end,
        )
        table.add(entry)

    # Verify all methods are findable
    assert len(table.lookup("main")) == 1
    assert len(table.lookup("run")) == 1
    assert len(table.lookup("createUser")) == 1
    assert len(table.lookup("deleteUser")) == 1
    assert len(table.lookup("save")) == 1
    assert len(table.lookup("delete")) == 1

    # Verify qualified lookups work
    results = table.lookup_qualified("UserService.createUser")
    assert len(results) >= 1
    assert any("UserService" in e.node_id for e in results)

    results = table.lookup_qualified("UserRepository.save")
    assert len(results) >= 1
    assert any("UserRepository" in e.node_id for e in results)
