"""
Tests for SQL extraction bugs:
  #775 — FUNCTION with params: schema-qualified function produces 0 results
  #808 — CREATE TABLE ... AS SELECT: drops table (extracts schema name instead)

RED tests written before the fix; each asserts EXACT values (no >= bounds).
"""

import pytest

try:
    import tree_sitter
    import tree_sitter_sql

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor
from tree_sitter_analyzer.models import SQLFunction, SQLTable


def _parse(sql: str):
    """Return a tree-sitter Tree for the given SQL string."""
    if not TREE_SITTER_SQL_AVAILABLE:
        pytest.skip("tree-sitter-sql not installed")
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
