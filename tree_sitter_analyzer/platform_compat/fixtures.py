from dataclasses import dataclass


@dataclass
class SQLTestFixture:
    """A SQL code sample for testing platform compatibility."""

    id: str
    sql: str
    description: str
    expected_constructs: list[
        str
    ]  # List of construct types expected (e.g. "table", "view")
    is_edge_case: bool = False
    known_platform_issues: list[str] | None = None


# Standard SQL constructs

FIXTURE_SIMPLE_TABLE = SQLTestFixture(
    id="simple_table",
    sql="""
    CREATE TABLE users (
        id INT PRIMARY KEY,
        username VARCHAR(50) NOT NULL,
        email VARCHAR(100)
    );
    """,
    description="Basic table with columns",
    expected_constructs=["table"],
)

FIXTURE_COMPLEX_TABLE = SQLTestFixture(
    id="complex_table",
    sql="""
    CREATE TABLE orders (
        order_id INT PRIMARY KEY,
        user_id INT,
        order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_amount DECIMAL(10, 2),
        CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """,
    description="Table with constraints and foreign keys",
    expected_constructs=["table"],
)

FIXTURE_VIEW_WITH_JOIN = SQLTestFixture(
    id="view_with_join",
    sql="""
    CREATE VIEW user_orders AS
    SELECT u.username, o.order_date, o.total_amount
    FROM users u
    JOIN orders o ON u.id = o.user_id;
    """,
    description="View with JOIN operations",
    expected_constructs=["view"],
)

FIXTURE_STORED_PROCEDURE = SQLTestFixture(
    id="stored_procedure",
    sql="""
    CREATE PROCEDURE GetUserOrders(IN userId INT)
    BEGIN
        SELECT * FROM orders WHERE user_id = userId;
    END;
    """,
    description="Procedure with parameters",
    expected_constructs=["procedure"],
)

FIXTURE_FUNCTION_WITH_PARAMS = SQLTestFixture(
    id="function_with_params",
    sql="""
    CREATE FUNCTION CalculateTax(amount DECIMAL(10,2))
    RETURNS DECIMAL(10,2)
    BEGIN
        RETURN amount * 0.15;
    END;
    """,
    description="Function with parameters and return type",
    expected_constructs=["function"],
)

FIXTURE_TRIGGER_BEFORE_INSERT = SQLTestFixture(
    id="trigger_before_insert",
    sql="""
    CREATE TRIGGER before_order_insert
    BEFORE INSERT ON orders
    FOR EACH ROW
    BEGIN
        SET NEW.order_date = NOW();
    END;
    """,
    description="Trigger with timing and event",
    expected_constructs=["trigger"],
)

FIXTURE_INDEX_UNIQUE = SQLTestFixture(
    id="index_unique",
    sql="""
    CREATE UNIQUE INDEX idx_user_email ON users(email);
    """,
    description="Unique index on table",
    expected_constructs=["index"],
)

# Edge case fixtures for platform issues

FIXTURE_FUNCTION_WITH_SELECT = SQLTestFixture(
    id="function_with_select",
    sql="""
    CREATE FUNCTION GetTotalSales() RETURNS DECIMAL(10,2)
    BEGIN
        DECLARE total DECIMAL(10,2);
        SELECT SUM(total_amount) INTO total FROM orders;
        RETURN total;
    END;
    """,
    description="Function with SELECT in body (Ubuntu 3.12 issue)",
    expected_constructs=["function"],
    is_edge_case=True,
    known_platform_issues=["ubuntu-3.12"],
)

FIXTURE_TRIGGER_WITH_DESCRIPTION = SQLTestFixture(
    id="trigger_with_description",
    sql="""
    CREATE TRIGGER update_description
    BEFORE UPDATE ON products
    FOR EACH ROW
    BEGIN
        -- Trigger logic here
    END;
    """,
    description="Trigger name extraction (macOS issue where name might be confused with description keyword if present)",
    expected_constructs=["trigger"],
    is_edge_case=True,
    known_platform_issues=["macos"],
)

FIXTURE_FUNCTION_WITH_AUTO_INCREMENT = SQLTestFixture(
    id="function_with_auto_increment",
    sql="""
    CREATE TABLE items (
        id INT AUTO_INCREMENT PRIMARY KEY
    );

    CREATE FUNCTION GetNextId() RETURNS INT
    BEGIN
        RETURN 1;
    END;
    """,
    description="Function near AUTO_INCREMENT (Windows issue)",
    expected_constructs=["table", "function"],
    is_edge_case=True,
    known_platform_issues=["windows"],
)

FIXTURE_VIEW_IN_ERROR_NODE = SQLTestFixture(
    id="view_in_error_node",
    sql="""
    -- Some complex SQL that might confuse the parser
    CREATE VIEW complex_view AS
    WITH cte AS (SELECT 1)
    SELECT * FROM cte;
    """,
    description="View that appears in ERROR nodes on some platforms",
    expected_constructs=["view"],
    is_edge_case=True,
)

FIXTURE_PHANTOM_TRIGGER = SQLTestFixture(
    id="phantom_trigger",
    sql="""
    -- A comment that looks like a trigger
    -- CREATE TRIGGER phantom_trigger
    CREATE TABLE real_table (id INT);
    """,
    description="Trigger that creates phantom elements on some platforms",
    expected_constructs=["table"],  # Should NOT contain trigger
    is_edge_case=True,
    known_platform_issues=["ubuntu-3.12"],
)

FIXTURE_PROCEDURE_WITH_COMMENTS = SQLTestFixture(
    id="procedure_with_comments",
    sql="""
    CREATE PROCEDURE ComplexProc()
    BEGIN
        /*
           Multi-line comment
           that might confuse parser
        */
        SELECT 1;
    END;
    """,
    description="Procedure with complex comments",
    expected_constructs=["procedure"],
    is_edge_case=True,
)

FIXTURE_INDEX_ON_EXPRESSION = SQLTestFixture(
    id="index_on_expression",
    sql="""
    CREATE INDEX idx_lower_email ON users((lower(email)));
    """,
    description="Index on expression",
    expected_constructs=["index"],
    is_edge_case=True,
)

ALL_FIXTURES = [
    FIXTURE_SIMPLE_TABLE,
    FIXTURE_COMPLEX_TABLE,
    FIXTURE_VIEW_WITH_JOIN,
    FIXTURE_STORED_PROCEDURE,
    FIXTURE_FUNCTION_WITH_PARAMS,
    FIXTURE_TRIGGER_BEFORE_INSERT,
    FIXTURE_INDEX_UNIQUE,
    FIXTURE_FUNCTION_WITH_SELECT,
    FIXTURE_TRIGGER_WITH_DESCRIPTION,
    FIXTURE_FUNCTION_WITH_AUTO_INCREMENT,
    FIXTURE_VIEW_IN_ERROR_NODE,
    FIXTURE_PHANTOM_TRIGGER,
    FIXTURE_PROCEDURE_WITH_COMMENTS,
    FIXTURE_INDEX_ON_EXPRESSION,
]
