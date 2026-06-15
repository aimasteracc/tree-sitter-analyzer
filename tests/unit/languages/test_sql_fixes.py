"""
Tests for SQL extraction bugs:
  #775 — FUNCTION with params: schema-qualified function produces 0 results
  #808 — CREATE TABLE ... AS SELECT: drops table (extracts schema name instead)

RED tests written before the fix; each asserts EXACT values (no >= bounds).
"""

from typing import Any

import pytest

try:
    import tree_sitter
    import tree_sitter_sql

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor
from tree_sitter_analyzer.languages.sql_plugin.table_extractor import (
    _is_in_sql_comment,
    fill_missing_sql_tables_from_regex,
)
from tree_sitter_analyzer.models import SQLFunction, SQLTable


def _parse(sql: str):
    """Return a tree-sitter Tree for the given SQL string."""
    if not TREE_SITTER_SQL_AVAILABLE:
        pytest.skip("tree-sitter-sql not installed — tracked #775/#808")
    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_sql.language()))
    return parser.parse(sql.encode("utf-8"))


def _extract(sql: str):
    """Parse SQL and run extract_sql_elements; return the element list."""
    tree = _parse(sql)
    ext = SQLElementExtractor()
    return ext.extract_sql_elements(tree, sql)


# ---------------------------------------------------------------------------
# Bug #775 — FUNCTION with params: schema-qualified function returns 0 results
# ---------------------------------------------------------------------------


class TestFunctionParamExtraction:
    """#775: CREATE FUNCTION with parameters must be extracted correctly."""

    def test_simple_function_with_two_params_extracted(self):
        """A simple (non-schema) function with params returns 1 SQLFunction."""
        sql = (
            "CREATE FUNCTION add_nums(a INT, b INT) RETURNS INT\n"
            "BEGIN\n"
            "  RETURN a + b;\n"
            "END;\n"
        )
        elements = _extract(sql)
        functions = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(functions) == 1
        assert functions[0].name == "add_nums"

    def test_simple_function_params_names(self):
        sql = (
            "CREATE FUNCTION add_nums(a INT, b INT) RETURNS INT\n"
            "BEGIN\n"
            "  RETURN a + b;\n"
            "END;\n"
        )
        elements = _extract(sql)
        functions = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(functions) == 1
        param_names = [p.name for p in functions[0].parameters]
        assert param_names == ["a", "b"]

    def test_simple_function_params_types(self):
        sql = (
            "CREATE FUNCTION add_nums(a INT, b INT) RETURNS INT\n"
            "BEGIN\n"
            "  RETURN a + b;\n"
            "END;\n"
        )
        elements = _extract(sql)
        functions = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(functions) == 1
        param_types = [p.data_type.upper() for p in functions[0].parameters]
        assert param_types == ["INT", "INT"]

    def test_schema_qualified_function_is_extracted(self):
        """#775: schema.function(params) must NOT silently return 0 results."""
        sql = (
            "CREATE FUNCTION myschema.get_count(user_id INT, status TEXT) RETURNS INT\n"
            "BEGIN\n"
            "  RETURN 1;\n"
            "END;\n"
        )
        elements = _extract(sql)
        functions = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(functions) == 1

    def test_schema_qualified_function_name_is_function_not_schema(self):
        """#775: extracted name must be 'get_count', not 'myschema'."""
        sql = (
            "CREATE FUNCTION myschema.get_count(user_id INT, status TEXT) RETURNS INT\n"
            "BEGIN\n"
            "  RETURN 1;\n"
            "END;\n"
        )
        elements = _extract(sql)
        functions = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(functions) == 1
        assert functions[0].name == "get_count"

    def test_schema_qualified_function_params_extracted(self):
        """#775: schema-qualified function must carry its parameters."""
        sql = (
            "CREATE FUNCTION myschema.get_count(user_id INT, status TEXT) RETURNS INT\n"
            "BEGIN\n"
            "  RETURN 1;\n"
            "END;\n"
        )
        elements = _extract(sql)
        functions = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(functions) == 1
        param_names = [p.name for p in functions[0].parameters]
        assert param_names == ["user_id", "status"]

    def test_function_with_mixed_param_types(self):
        """Function with INT and TEXT params — both captured."""
        sql = (
            "CREATE FUNCTION foo(param1 INT, param2 TEXT) RETURNS INT\n"
            "BEGIN\n"
            "  RETURN param1 + 1;\n"
            "END;\n"
        )
        elements = _extract(sql)
        functions = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(functions) == 1
        params = functions[0].parameters
        assert len(params) == 2
        assert params[0].name == "param1"
        assert params[0].data_type.upper() == "INT"
        assert params[1].name == "param2"
        assert params[1].data_type.upper() == "TEXT"


# ---------------------------------------------------------------------------
# Bug #808 — CREATE TABLE ... AS SELECT drops the table
# ---------------------------------------------------------------------------


class TestCreateTableAsSelect:
    """#808: CREATE TABLE schema.name AS SELECT must extract the table."""

    def test_create_table_as_select_produces_one_table(self):
        """#808: 'CREATE TABLE reporting.daily_stats AS SELECT ...' must yield 1 table."""
        sql = (
            "CREATE TABLE reporting.daily_stats AS\n"
            "SELECT user_id, COUNT(*) AS cnt FROM users GROUP BY user_id;\n"
        )
        elements = _extract(sql)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1

    def test_create_table_as_select_name_is_table_not_schema(self):
        """#808: extracted name must be 'daily_stats', not 'reporting'."""
        sql = (
            "CREATE TABLE reporting.daily_stats AS\n"
            "SELECT user_id, COUNT(*) AS cnt FROM users GROUP BY user_id;\n"
        )
        elements = _extract(sql)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "daily_stats"

    def test_create_table_as_select_schema_captured(self):
        """#808: schema_name field must contain 'reporting'."""
        sql = (
            "CREATE TABLE reporting.daily_stats AS\n"
            "SELECT user_id, COUNT(*) AS cnt FROM users GROUP BY user_id;\n"
        )
        elements = _extract(sql)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].schema_name == "reporting"

    def test_create_table_no_schema_still_works(self):
        """Plain CREATE TABLE (no schema) is unaffected by the fix."""
        sql = "CREATE TABLE users (\n  id INT NOT NULL,\n  email TEXT\n);\n"
        elements = _extract(sql)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "users"

    def test_create_table_with_schema_no_as_select(self):
        """Schema-qualified CREATE TABLE with column list (no AS SELECT)."""
        sql = (
            "CREATE TABLE myschema.orders (\n"
            "  id INT NOT NULL,\n"
            "  total DECIMAL(10,2)\n"
            ");\n"
        )
        elements = _extract(sql)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "orders"
        assert tables[0].schema_name == "myschema"

    def test_create_table_as_select_single_schema(self):
        """Non-schema-qualified CREATE TABLE AS SELECT works too."""
        sql = "CREATE TABLE archive_users AS SELECT * FROM users WHERE deleted = 1;\n"
        elements = _extract(sql)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "archive_users"


# ---------------------------------------------------------------------------
# Bug #808 — CREATE TABLE silently dropped when FOREIGN KEY + ON DELETE/UPDATE
#            triggers tree-sitter parse-recovery ERROR node cascade
# ---------------------------------------------------------------------------

# Minimal Chinook-style DDL that reproduces the cascade:
# Artist → Album (FK with ON DELETE RESTRICT) → Customer
# tree-sitter SQL grammar creates an ERROR node that absorbs Customer when
# it encounters the multi-line ON DELETE/ON UPDATE clause.  The regex
# fallback in fill_missing_sql_tables_from_regex must recover it.
_SQL_FOREIGN_KEY_CASCADE = """
CREATE TABLE Artist (
    ArtistId INT NOT NULL,
    Name VARCHAR(120),
    CONSTRAINT PK_Artist PRIMARY KEY (ArtistId)
);

CREATE TABLE Album (
    AlbumId INT NOT NULL,
    Title VARCHAR(160) NOT NULL,
    ArtistId INT NOT NULL,
    CONSTRAINT PK_Album PRIMARY KEY (AlbumId),
    FOREIGN KEY (ArtistId) REFERENCES Artist (ArtistId)
        ON DELETE NO ACTION
        ON UPDATE NO ACTION
);

CREATE TABLE Customer (
    CustomerId INT NOT NULL,
    FirstName VARCHAR(40) NOT NULL,
    LastName VARCHAR(20) NOT NULL,
    CONSTRAINT PK_Customer PRIMARY KEY (CustomerId)
);
"""


class TestCreateTableErrorNodeCascade:
    """#808: CREATE TABLE absorbed into ERROR node must be recovered via regex fallback."""

    def test_all_three_tables_extracted(self):
        """Artist + Album + Customer must all appear — Customer is the cascade victim."""
        elements = _extract(_SQL_FOREIGN_KEY_CASCADE)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        names = {t.name for t in tables}
        assert names == {"Artist", "Album", "Customer"}

    def test_table_count_is_exactly_three(self):
        """Exact count — ensures no duplicates from regex + AST overlap."""
        elements = _extract(_SQL_FOREIGN_KEY_CASCADE)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 3

    def test_customer_table_name_correct(self):
        """Customer table must have name='Customer', not 'CustomerId' or similar."""
        elements = _extract(_SQL_FOREIGN_KEY_CASCADE)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        customer = next((t for t in tables if t.name == "Customer"), None)
        assert customer is not None
        assert customer.name == "Customer"

    def test_no_schema_name_on_simple_tables(self):
        """None of the three tables use schema-qualified names — schema_name must be None."""
        elements = _extract(_SQL_FOREIGN_KEY_CASCADE)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        for table in tables:
            assert table.schema_name is None, (
                f"{table.name} has unexpected schema_name={table.schema_name!r}"
            )


# ---------------------------------------------------------------------------
# Codex P2 fixes — comment detection and schema-aware deduplication
# ---------------------------------------------------------------------------


class TestIsInSqlComment:
    """Unit tests for _is_in_sql_comment helper."""

    def test_not_in_comment_plain_text(self):
        src = "CREATE TABLE foo (id INT);"
        assert _is_in_sql_comment(src, 0) is False

    def test_inside_line_comment(self):
        src = "-- CREATE TABLE foo (id INT);"
        assert _is_in_sql_comment(src, 3) is True

    def test_after_line_comment_on_same_line(self):
        src = "-- removed\nCREATE TABLE foo (id INT);"
        pos = src.index("CREATE")
        assert _is_in_sql_comment(src, pos) is False

    def test_inside_block_comment(self):
        src = "/* CREATE TABLE foo (id INT); */"
        assert _is_in_sql_comment(src, 3) is True

    def test_after_closed_block_comment(self):
        src = "/* removed */\nCREATE TABLE foo (id INT);"
        pos = src.index("CREATE")
        assert _is_in_sql_comment(src, pos) is False


class TestFillMissingTablesCommentSkip:
    """Regex fallback must not add tables found only inside SQL comments."""

    def test_commented_create_table_is_ignored(self):
        sql = (
            "-- CREATE TABLE dropped_users (id INT);\n"
            "CREATE TABLE real_users (id INT);\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        names = {t.name for t in tables}
        assert "dropped_users" not in names
        assert "real_users" in names

    def test_block_commented_create_table_is_ignored(self):
        sql = (
            "/* CREATE TABLE old_schema (id INT); */\n"
            "CREATE TABLE new_schema (id INT);\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        names = {t.name for t in tables}
        assert "old_schema" not in names
        assert "new_schema" in names


class TestFillMissingTablesSchemaDeduplciation:
    """Regex fallback must distinguish same table name in different schemas."""

    def test_same_name_different_schemas_both_recovered(self):
        sql = (
            "CREATE TABLE tenant_a.users (id INT);\n"
            "CREATE TABLE tenant_b.users (id INT);\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 2
        schemas = {t.schema_name for t in tables}
        assert schemas == {"tenant_a", "tenant_b"}

    def test_duplicate_same_schema_not_added_twice(self):
        sql = (
            "CREATE TABLE myschema.orders (id INT);\n"
            "CREATE TABLE myschema.orders (id INT);\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1


# ---------------------------------------------------------------------------
# Bug #881 — _CREATE_TABLE_RE misses quoted identifiers
# ---------------------------------------------------------------------------


class TestQuotedTableNameRegex:
    """#881: regex fallback must match ANSI, MySQL, and SQL Server quoted table names."""

    def test_ansi_double_quoted_name_extracted(self):
        """ANSI SQL: CREATE TABLE "Order Details" (...) must be recovered."""
        sql = 'CREATE TABLE "Order Details" (id INT, name TEXT);\n'
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "Order Details"

    def test_mysql_backtick_quoted_name_extracted(self):
        """MySQL style: CREATE TABLE `order details` (...) must be recovered."""
        sql = "CREATE TABLE `order details` (id INT, qty INT);\n"
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "order details"

    def test_sql_server_bracket_quoted_name_extracted(self):
        """SQL Server: CREATE TABLE [Order Details] (...) must be recovered."""
        sql = "CREATE TABLE [Order Details] (id INT);\n"
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "Order Details"

    def test_quoted_schema_plus_quoted_table(self):
        """ANSI: CREATE TABLE "my schema"."my table" (...) — both stripped."""
        sql = 'CREATE TABLE "dbo"."Order Details" (id INT);\n'
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "Order Details"
        assert tables[0].schema_name == "dbo"

    def test_bare_identifier_still_works_after_regex_change(self):
        """Regression: bare CREATE TABLE orders (...) still extracted."""
        sql = "CREATE TABLE orders (id INT, total DECIMAL(10,2));\n"
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert tables[0].name == "orders"

    def test_case_sensitive_quoted_names_not_deduped(self):
        """Quoted table names differing only in case must both be recovered (Codex P2)."""
        sql = 'CREATE TABLE "Foo" (id INT);\nCREATE TABLE "foo" (id INT);\n'
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 2
        names = {t.name for t in tables}
        assert names == {"Foo", "foo"}


# ---------------------------------------------------------------------------
# Bug #880 — fill_missing_sql_tables_from_regex creates SQLTable without columns
# ---------------------------------------------------------------------------


class TestRegexFallbackColumnsPopulated:
    """#880: regex-recovered tables must have their columns populated, not empty."""

    def test_recovered_table_has_correct_column_count(self):
        """A 3-column table recovered via regex fallback must yield 3 columns."""
        sql = (
            "CREATE TABLE products (id INT NOT NULL, name TEXT, price DECIMAL(10,2));\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert len(tables[0].columns) == 3

    def test_recovered_table_column_names(self):
        """Column names must match the original DDL."""
        sql = (
            "CREATE TABLE products (id INT NOT NULL, name TEXT, price DECIMAL(10,2));\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        col_names = [c.name for c in tables[0].columns]
        assert col_names == ["id", "name", "price"]

    def test_recovered_table_column_types(self):
        """Column data types must be captured."""
        sql = (
            "CREATE TABLE products (id INT NOT NULL, name TEXT, price DECIMAL(10,2));\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        col_types = [c.data_type.upper() for c in tables[0].columns]
        assert col_types[0] == "INT"
        assert col_types[1] == "TEXT"

    def test_not_null_constraint_captured(self):
        """NOT NULL constraint on a recovered column must set nullable=False."""
        sql = "CREATE TABLE users (id INT NOT NULL, email TEXT);\n"
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        id_col = next((c for c in tables[0].columns if c.name == "id"), None)
        assert id_col is not None
        assert id_col.nullable is False

    def test_table_without_column_list_has_empty_columns(self):
        """AS SELECT form produces 0 columns (no column-list body)."""
        sql = "CREATE TABLE archive AS SELECT * FROM users;\n"
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert len(tables[0].columns) == 0

    def test_ctas_with_parenthesized_select_expression_produces_no_columns(self):
        """CTAS with CAST(...) in SELECT must not produce bogus columns (Codex P2)."""
        sql = "CREATE TABLE archive AS SELECT CAST(id AS INT) FROM users;\n"
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        assert len(tables[0].columns) == 0

    def test_primary_key_constraint_line_excluded_from_columns(self):
        """PRIMARY KEY constraint lines must not produce spurious columns."""
        sql = (
            "CREATE TABLE orders (\n"
            "  id INT NOT NULL,\n"
            "  total DECIMAL(10,2),\n"
            "  PRIMARY KEY (id)\n"
            ");\n"
        )
        elements: list[Any] = []
        fill_missing_sql_tables_from_regex(sql, elements)
        tables = [e for e in elements if isinstance(e, SQLTable)]
        assert len(tables) == 1
        col_names = [c.name for c in tables[0].columns]
        assert col_names == ["id", "total"]
