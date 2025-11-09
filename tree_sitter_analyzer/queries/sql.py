#!/usr/bin/env python3
"""
SQL Language Queries

Tree-sitter queries specific to SQL language constructs.
Covers tables, views, procedures, functions, triggers, indexes, and other SQL-specific elements.
"""

# SQL-specific comprehensive query library
SQL_QUERIES: dict[str, str] = {
    # --- Basic DDL Statements ---
    "table": """
    (create_table_statement
        table_name: (identifier) @table_name) @table
    """,
    "create_table": """
    (create_table_statement
        table_name: (identifier) @table_name
        (column_definitions
            (column_definition
                column_name: (identifier) @column_name
                data_type: (_) @column_type)*) @columns) @create_table
    """,
    "view": """
    (create_view_statement
        view_name: (identifier) @view_name) @view
    """,
    "create_view": """
    (create_view_statement
        view_name: (identifier) @view_name
        (select_statement) @view_query) @create_view
    """,
    "index": """
    (create_index_statement
        index_name: (identifier) @index_name
        table_name: (identifier) @table_name) @index
    """,
    "create_index": """
    (create_index_statement
        index_name: (identifier) @index_name
        table_name: (identifier) @table_name
        (column_list
            (identifier) @index_column)*) @create_index
    """,
    # --- Stored Procedures and Functions ---
    "procedure": """
    (create_procedure_statement
        procedure_name: (identifier) @procedure_name) @procedure
    """,
    "create_procedure": """
    (create_procedure_statement
        procedure_name: (identifier) @procedure_name
        (parameter_list
            (parameter
                parameter_name: (identifier) @param_name
                data_type: (_) @param_type)*)?
        (compound_statement) @procedure_body) @create_procedure
    """,
    "function": """
    (create_function_statement
        function_name: (identifier) @function_name) @function
    """,
    "create_function": """
    (create_function_statement
        function_name: (identifier) @function_name
        (parameter_list
            (parameter
                parameter_name: (identifier) @param_name
                data_type: (_) @param_type)*)?
        return_type: (_) @return_type
        (compound_statement) @function_body) @create_function
    """,
    # --- Triggers ---
    "trigger": """
    (create_trigger_statement
        trigger_name: (identifier) @trigger_name) @trigger
    """,
    "create_trigger": """
    (create_trigger_statement
        trigger_name: (identifier) @trigger_name
        timing: (_) @trigger_timing
        event: (_) @trigger_event
        table_name: (identifier) @table_name
        (compound_statement) @trigger_body) @create_trigger
    """,
    # --- DML Statements ---
    "select": """
    (select_statement) @select
    """,
    "select_detailed": """
    (select_statement
        (select_clause
            (select_list
                (_) @select_item)*) @select_clause
        (from_clause
            (table_reference) @from_table)?
        (where_clause
            (_) @where_condition)?
        (group_by_clause
            (_) @group_by_item)*
        (having_clause
            (_) @having_condition)?
        (order_by_clause
            (order_by_item) @order_by_item)*) @select_detailed
    """,
    "insert": """
    (insert_statement
        table_name: (identifier) @table_name) @insert
    """,
    "update": """
    (update_statement
        table_name: (identifier) @table_name) @update
    """,
    "delete": """
    (delete_statement
        table_name: (identifier) @table_name) @delete
    """,
    # --- Constraints ---
    "primary_key": """
    (primary_key_constraint
        (column_list
            (identifier) @pk_column)*) @primary_key
    """,
    "foreign_key": """
    (foreign_key_constraint
        (column_list
            (identifier) @fk_column)*
        referenced_table: (identifier) @referenced_table
        (column_list
            (identifier) @referenced_column)*) @foreign_key
    """,
    "unique_constraint": """
    (unique_constraint
        (column_list
            (identifier) @unique_column)*) @unique_constraint
    """,
    "check_constraint": """
    (check_constraint
        (_) @check_condition) @check_constraint
    """,
    # --- Column Definitions ---
    "column": """
    (column_definition
        column_name: (identifier) @column_name
        data_type: (_) @data_type) @column
    """,
    "column_with_constraints": """
    (column_definition
        column_name: (identifier) @column_name
        data_type: (_) @data_type
        (column_constraint)* @constraints) @column_with_constraints
    """,
    # --- Joins ---
    "join": """
    (join_clause
        join_type: (_)? @join_type
        table_reference: (_) @joined_table
        join_condition: (_) @join_condition) @join
    """,
    "inner_join": """
    (join_clause
        join_type: (inner_join) @join_type
        table_reference: (_) @joined_table
        join_condition: (_) @join_condition) @inner_join
    """,
    "left_join": """
    (join_clause
        join_type: (left_join) @join_type
        table_reference: (_) @joined_table
        join_condition: (_) @join_condition) @left_join
    """,
    "right_join": """
    (join_clause
        join_type: (right_join) @join_type
        table_reference: (_) @joined_table
        join_condition: (_) @join_condition) @right_join
    """,
    # --- Aggregate Functions ---
    "aggregate_function": """
    (function_call
        function_name: (identifier) @function_name
        (#match? @function_name "COUNT|SUM|AVG|MIN|MAX|GROUP_CONCAT")
        arguments: (argument_list) @arguments) @aggregate_function
    """,
    "count_function": """
    (function_call
        function_name: (identifier) @function_name
        (#match? @function_name "COUNT")
        arguments: (argument_list) @arguments) @count_function
    """,
    "sum_function": """
    (function_call
        function_name: (identifier) @function_name
        (#match? @function_name "SUM")
        arguments: (argument_list) @arguments) @sum_function
    """,
    # --- Window Functions ---
    "window_function": """
    (window_function
        function_name: (identifier) @function_name
        arguments: (argument_list)? @arguments
        (over_clause
            (partition_by_clause)? @partition_by
            (order_by_clause)? @order_by)) @window_function
    """,
    # --- Common Table Expressions (CTE) ---
    "cte": """
    (with_clause
        (cte_definition
            cte_name: (identifier) @cte_name
            (select_statement) @cte_query)) @cte
    """,
    "with_statement": """
    (with_statement
        (with_clause
            (cte_definition
                cte_name: (identifier) @cte_name
                (select_statement) @cte_query)*) @with_clause
        (select_statement) @main_query) @with_statement
    """,
    # --- Subqueries ---
    "subquery": """
    (subquery
        (select_statement) @subquery_select) @subquery
    """,
    "exists_subquery": """
    (exists_expression
        (subquery
            (select_statement) @exists_query)) @exists_subquery
    """,
    "in_subquery": """
    (in_expression
        left: (_) @in_left
        right: (subquery
            (select_statement) @in_query)) @in_subquery
    """,
    # --- Data Types ---
    "varchar_type": """
    (varchar_type
        size: (integer) @varchar_size) @varchar_type
    """,
    "decimal_type": """
    (decimal_type
        precision: (integer) @decimal_precision
        scale: (integer)? @decimal_scale) @decimal_type
    """,
    "enum_type": """
    (enum_type
        (string_literal) @enum_value*) @enum_type
    """,
    # --- Comments ---
    "comment": """
    (comment) @comment
    """,
    "line_comment": """
    (line_comment) @line_comment
    """,
    "block_comment": """
    (block_comment) @block_comment
    """,
    # --- Name-only Extraction ---
    "table_name": """
    (create_table_statement
        table_name: (identifier) @table_name)
    """,
    "view_name": """
    (create_view_statement
        view_name: (identifier) @view_name)
    """,
    "procedure_name": """
    (create_procedure_statement
        procedure_name: (identifier) @procedure_name)
    """,
    "function_name": """
    (create_function_statement
        function_name: (identifier) @function_name)
    """,
    "trigger_name": """
    (create_trigger_statement
        trigger_name: (identifier) @trigger_name)
    """,
    "index_name": """
    (create_index_statement
        index_name: (identifier) @index_name)
    """,
    "column_name": """
    (column_definition
        column_name: (identifier) @column_name)
    """,
    # --- Advanced Patterns ---
    "stored_procedure_call": """
    (call_statement
        procedure_name: (identifier) @procedure_name
        arguments: (argument_list)? @arguments) @procedure_call
    """,
    "transaction": """
    (transaction_statement) @transaction
    """,
    "begin_transaction": """
    (begin_transaction_statement) @begin_transaction
    """,
    "commit_transaction": """
    (commit_transaction_statement) @commit_transaction
    """,
    "rollback_transaction": """
    (rollback_transaction_statement) @rollback_transaction
    """,
    # --- Database-specific Features ---
    "auto_increment": """
    (column_definition
        column_name: (identifier) @column_name
        data_type: (_) @data_type
        (auto_increment_constraint) @auto_increment) @auto_increment_column
    """,
    "default_value": """
    (column_definition
        column_name: (identifier) @column_name
        data_type: (_) @data_type
        (default_constraint
            value: (_) @default_value)) @column_with_default
    """,
    "not_null": """
    (column_definition
        column_name: (identifier) @column_name
        data_type: (_) @data_type
        (not_null_constraint) @not_null) @not_null_column
    """,
    # --- Error Handling (for tree-sitter-sql ERROR nodes) ---
    "error_node": """
    (ERROR) @error_node
    """,
    "procedure_in_error": """
    (ERROR
        "PROCEDURE" @procedure_keyword
        (identifier) @procedure_name) @procedure_error
    """,
    "function_in_error": """
    (ERROR
        "FUNCTION" @function_keyword
        (identifier) @function_name) @function_error
    """,
    "trigger_in_error": """
    (ERROR
        "TRIGGER" @trigger_keyword
        (identifier) @trigger_name) @trigger_error
    """,
}

# Query descriptions
SQL_QUERY_DESCRIPTIONS: dict[str, str] = {
    "table": "Extract table creation statements",
    "create_table": "Extract detailed table creation with columns",
    "view": "Extract view creation statements",
    "create_view": "Extract detailed view creation with query",
    "index": "Extract index creation statements",
    "create_index": "Extract detailed index creation with columns",
    "procedure": "Extract stored procedure definitions",
    "create_procedure": "Extract detailed procedure creation with parameters",
    "function": "Extract function definitions",
    "create_function": "Extract detailed function creation with parameters and return type",
    "trigger": "Extract trigger definitions",
    "create_trigger": "Extract detailed trigger creation with timing and events",
    "select": "Extract SELECT statements",
    "select_detailed": "Extract detailed SELECT statements with clauses",
    "insert": "Extract INSERT statements",
    "update": "Extract UPDATE statements",
    "delete": "Extract DELETE statements",
    "primary_key": "Extract primary key constraints",
    "foreign_key": "Extract foreign key constraints",
    "unique_constraint": "Extract unique constraints",
    "check_constraint": "Extract check constraints",
    "column": "Extract column definitions",
    "column_with_constraints": "Extract columns with constraints",
    "join": "Extract JOIN clauses",
    "inner_join": "Extract INNER JOIN clauses",
    "left_join": "Extract LEFT JOIN clauses",
    "right_join": "Extract RIGHT JOIN clauses",
    "aggregate_function": "Extract aggregate functions (COUNT, SUM, AVG, etc.)",
    "count_function": "Extract COUNT functions",
    "sum_function": "Extract SUM functions",
    "window_function": "Extract window functions with OVER clause",
    "cte": "Extract Common Table Expressions (CTE)",
    "with_statement": "Extract WITH statements",
    "subquery": "Extract subqueries",
    "exists_subquery": "Extract EXISTS subqueries",
    "in_subquery": "Extract IN subqueries",
    "varchar_type": "Extract VARCHAR data types",
    "decimal_type": "Extract DECIMAL data types",
    "enum_type": "Extract ENUM data types",
    "comment": "Extract all comments",
    "line_comment": "Extract line comments (--)",
    "block_comment": "Extract block comments (/* */)",
    "table_name": "Extract table names only",
    "view_name": "Extract view names only",
    "procedure_name": "Extract procedure names only",
    "function_name": "Extract function names only",
    "trigger_name": "Extract trigger names only",
    "index_name": "Extract index names only",
    "column_name": "Extract column names only",
    "stored_procedure_call": "Extract stored procedure calls",
    "transaction": "Extract transaction statements",
    "begin_transaction": "Extract BEGIN TRANSACTION statements",
    "commit_transaction": "Extract COMMIT statements",
    "rollback_transaction": "Extract ROLLBACK statements",
    "auto_increment": "Extract AUTO_INCREMENT columns",
    "default_value": "Extract columns with DEFAULT values",
    "not_null": "Extract NOT NULL columns",
    "error_node": "Extract ERROR nodes (parsing issues)",
    "procedure_in_error": "Extract procedures that appear as ERROR nodes",
    "function_in_error": "Extract functions that appear as ERROR nodes",
    "trigger_in_error": "Extract triggers that appear as ERROR nodes",
}


def get_sql_query(name: str) -> str:
    """
    Get the specified SQL query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in SQL_QUERIES:
        available = list(SQL_QUERIES.keys())
        raise ValueError(f"SQL query '{name}' does not exist. Available: {available}")

    return SQL_QUERIES[name]


def get_sql_query_description(name: str) -> str:
    """
    Get the description of the specified SQL query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return SQL_QUERY_DESCRIPTIONS.get(name, "No description")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in SQL_QUERIES.items():
    description = SQL_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": SQL_QUERIES["function"],
    "description": "Search all function definitions (alias for function)",
}

ALL_QUERIES["procedures"] = {
    "query": SQL_QUERIES["procedure"],
    "description": "Search all procedure definitions (alias for procedure)",
}

ALL_QUERIES["tables"] = {
    "query": SQL_QUERIES["table"],
    "description": "Search all table definitions (alias for table)",
}

ALL_QUERIES["views"] = {
    "query": SQL_QUERIES["view"],
    "description": "Search all view definitions (alias for view)",
}

ALL_QUERIES["indexes"] = {
    "query": SQL_QUERIES["index"],
    "description": "Search all index definitions (alias for index)",
}

ALL_QUERIES["triggers"] = {
    "query": SQL_QUERIES["trigger"],
    "description": "Search all trigger definitions (alias for trigger)",
}

# Add comprehensive aliases
ALL_QUERIES["ddl_statements"] = {
    "query": SQL_QUERIES["table"]
    + "\n\n"
    + SQL_QUERIES["view"]
    + "\n\n"
    + SQL_QUERIES["index"],
    "description": "Search all DDL statements (tables, views, indexes)",
}

ALL_QUERIES["dml_statements"] = {
    "query": SQL_QUERIES["select"]
    + "\n\n"
    + SQL_QUERIES["insert"]
    + "\n\n"
    + SQL_QUERIES["update"]
    + "\n\n"
    + SQL_QUERIES["delete"],
    "description": "Search all DML statements (SELECT, INSERT, UPDATE, DELETE)",
}

ALL_QUERIES["constraints"] = {
    "query": SQL_QUERIES["primary_key"]
    + "\n\n"
    + SQL_QUERIES["foreign_key"]
    + "\n\n"
    + SQL_QUERIES["unique_constraint"]
    + "\n\n"
    + SQL_QUERIES["check_constraint"],
    "description": "Search all constraint definitions",
}

ALL_QUERIES["joins"] = {
    "query": SQL_QUERIES["join"]
    + "\n\n"
    + SQL_QUERIES["inner_join"]
    + "\n\n"
    + SQL_QUERIES["left_join"]
    + "\n\n"
    + SQL_QUERIES["right_join"],
    "description": "Search all JOIN clauses",
}


def get_query(name: str) -> str:
    """Get a specific query by name."""
    if name in ALL_QUERIES:
        return ALL_QUERIES[name]["query"]
    raise ValueError(
        f"Query '{name}' not found. Available queries: {list(ALL_QUERIES.keys())}"
    )


def get_all_queries() -> dict:
    """Get all available queries."""
    return ALL_QUERIES


def list_queries() -> list:
    """List all available query names."""
    return list(ALL_QUERIES.keys())


def get_available_sql_queries() -> list[str]:
    """
    Get list of available SQL queries

    Returns:
        List of query names
    """
    return list(SQL_QUERIES.keys())
