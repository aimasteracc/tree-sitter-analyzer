#!/usr/bin/env python3
"""
Analyze specific SQL constructs to understand AST structure
"""

import sys

try:
    import tree_sitter_sql
    from tree_sitter import Language, Parser
except ImportError:
    print("Error: tree-sitter or tree-sitter-sql not available")
    sys.exit(1)


def print_ast_node(node, indent=0, max_depth=5):
    """Print AST node information with limited depth"""
    if indent > max_depth:
        return

    node_text = node.text.decode("utf-8") if node.text else ""
    if len(node_text) > 80:
        node_text = node_text[:77] + "..."

    node_text = node_text.replace("\n", "\\n").replace("\r", "\\r")

    print(
        f"{'  ' * indent}{node.type} [{node.start_point[0]}:{node.start_point[1]}-{node.end_point[0]}:{node.end_point[1]}]"
    )
    if node_text.strip():
        print(f"{'  ' * indent}  Text: '{node_text}'")

    for child in node.children:
        print_ast_node(child, indent + 1, max_depth)


def analyze_specific_constructs():
    """Analyze specific SQL constructs"""

    # Test cases for different SQL constructs
    test_cases = {
        "CREATE PROCEDURE": """
CREATE PROCEDURE get_user_orders(IN user_id_param INT)
BEGIN
    SELECT id, order_date FROM orders WHERE user_id = user_id_param;
END;
""",
        "CREATE FUNCTION": """
CREATE FUNCTION calculate_total(order_id_param INT)
RETURNS DECIMAL(10, 2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE total DECIMAL(10, 2);
    SELECT SUM(price) INTO total FROM order_items WHERE order_id = order_id_param;
    RETURN total;
END;
""",
        "CREATE TRIGGER": """
CREATE TRIGGER update_order_total
AFTER INSERT ON order_items
FOR EACH ROW
BEGIN
    UPDATE orders SET total_amount = 100 WHERE id = NEW.order_id;
END;
""",
        "CREATE INDEX": """
CREATE INDEX idx_users_email ON users(email);
""",
        "CREATE TABLE": """
CREATE TABLE test_table (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);
""",
        "CREATE VIEW": """
CREATE VIEW test_view AS
SELECT id, name FROM test_table WHERE id > 0;
""",
    }

    # Set up parser
    try:
        language = Language(tree_sitter_sql.language())
        parser = Parser()

        if hasattr(parser, "set_language"):
            parser.set_language(language)
        elif hasattr(parser, "language"):
            parser.language = language
        else:
            parser = Parser(language)

    except Exception as e:
        print(f"Error setting up parser: {e}")
        return

    for construct_name, sql_code in test_cases.items():
        print(f"\n{'=' * 60}")
        print(f"Analyzing: {construct_name}")
        print(f"{'=' * 60}")
        print(f"SQL Code:\n{sql_code.strip()}")
        print("\nAST Structure:")
        print("-" * 40)

        try:
            tree = parser.parse(sql_code.encode("utf-8"))
            if tree and tree.root_node:
                print_ast_node(tree.root_node)
            else:
                print("Failed to parse")
        except Exception as e:
            print(f"Error parsing: {e}")


if __name__ == "__main__":
    analyze_specific_constructs()
