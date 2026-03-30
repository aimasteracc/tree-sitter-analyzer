-- ============================================================================
-- SQL Golden Corpus - Grammar Coverage MECE Test
-- ============================================================================
--
-- This file provides comprehensive coverage of SQL (PostgreSQL) syntax
-- features to verify tree-sitter-sql parser completeness.
--
-- Coverage includes:
-- - CREATE statements (TABLE, INDEX, VIEW, FUNCTION, TRIGGER)
-- - SELECT queries (simple, joins, subqueries, CTEs, window functions)
-- - INSERT, UPDATE, DELETE statements
-- - WHERE, GROUP BY, ORDER BY, HAVING clauses
-- - Aggregate functions, scalar functions, window functions
-- - CASE expressions, CAST operations
-- - Constraints (PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK)
-- - Data types (INTEGER, VARCHAR, TEXT, TIMESTAMP, JSON, etc.)
-- - Transactions (BEGIN, COMMIT, ROLLBACK)
-- - Complex real-world queries
-- ============================================================================

-- ============================================================================
-- CREATE TABLE Statements
-- ============================================================================

-- Simple table creation
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table with various data types
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL CHECK (price > 0),
    quantity INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    category_id INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table with foreign keys
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_number VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_amount DECIMAL(10, 2) NOT NULL,
    shipping_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled'))
);

-- Table with composite primary key
CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

-- Table with complex constraints
CREATE TABLE user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    bio TEXT,
    birth_date DATE,
    phone VARCHAR(20),
    country VARCHAR(50),
    city VARCHAR(50),
    postal_code VARCHAR(10),
    avatar_url TEXT,
    CONSTRAINT age_check CHECK (birth_date IS NULL OR birth_date < CURRENT_DATE - INTERVAL '13 years')
);

-- ============================================================================
-- CREATE INDEX Statements
-- ============================================================================

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);

-- Composite index
CREATE INDEX idx_order_items_lookup ON order_items(order_id, product_id);

-- Partial index
CREATE INDEX idx_active_products ON products(name) WHERE is_active = TRUE;

-- JSONB index
CREATE INDEX idx_products_metadata ON products USING GIN (metadata);

-- ============================================================================
-- CREATE VIEW Statements
-- ============================================================================

CREATE VIEW active_products AS
SELECT id, sku, name, price, quantity
FROM products
WHERE is_active = TRUE;

CREATE VIEW user_order_summary AS
SELECT
    u.id AS user_id,
    u.username,
    COUNT(o.id) AS total_orders,
    SUM(o.total_amount) AS total_spent,
    MAX(o.created_at) AS last_order_date
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username;

CREATE VIEW order_details AS
SELECT
    o.id AS order_id,
    o.order_number,
    u.username,
    u.email,
    o.status,
    o.total_amount,
    o.created_at,
    COUNT(oi.product_id) AS item_count
FROM orders o
JOIN users u ON o.user_id = u.id
LEFT JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id, o.order_number, u.username, u.email, o.status, o.total_amount, o.created_at;

-- ============================================================================
-- INSERT Statements
-- ============================================================================

-- Simple insert
INSERT INTO users (username, email, password_hash)
VALUES ('alice', 'alice@example.com', 'hashed_password_1');

-- Multiple row insert
INSERT INTO users (username, email, password_hash)
VALUES
    ('bob', 'bob@example.com', 'hashed_password_2'),
    ('charlie', 'charlie@example.com', 'hashed_password_3'),
    ('david', 'david@example.com', 'hashed_password_4');

-- Insert with explicit columns
INSERT INTO products (sku, name, description, price, quantity, category_id)
VALUES
    ('LAPTOP-001', 'Professional Laptop 15"', 'High-performance laptop for professionals', 1299.99, 50, 1),
    ('MONITOR-001', '4K Monitor 27"', 'Ultra HD 4K monitor', 599.99, 30, 1),
    ('KEYBOARD-001', 'Mechanical Keyboard', 'RGB mechanical keyboard', 149.99, 100, 2);

-- Insert with RETURNING clause
INSERT INTO orders (user_id, order_number, total_amount)
VALUES (1, 'ORD-001', 1899.98)
RETURNING id, order_number, created_at;

-- ============================================================================
-- SELECT Statements (Simple)
-- ============================================================================

-- Simple select all
SELECT * FROM users;

-- Select specific columns
SELECT id, username, email FROM users;

-- Select with WHERE clause
SELECT * FROM products WHERE price > 500;

-- Select with multiple conditions
SELECT * FROM products
WHERE is_active = TRUE
  AND quantity > 0
  AND price BETWEEN 100 AND 1000;

-- Select with LIKE
SELECT * FROM users WHERE username LIKE 'a%';

-- Select with IN
SELECT * FROM orders WHERE status IN ('pending', 'processing');

-- Select with IS NULL
SELECT * FROM user_profiles WHERE bio IS NULL;

-- Select with ORDER BY
SELECT * FROM products ORDER BY price DESC, name ASC;

-- Select with LIMIT and OFFSET
SELECT * FROM products ORDER BY created_at DESC LIMIT 10 OFFSET 20;

-- ============================================================================
-- SELECT Statements (Aggregate Functions)
-- ============================================================================

-- COUNT
SELECT COUNT(*) AS total_users FROM users;

-- SUM
SELECT SUM(total_amount) AS total_revenue FROM orders;

-- AVG
SELECT AVG(price) AS average_price FROM products;

-- MIN and MAX
SELECT MIN(price) AS min_price, MAX(price) AS max_price FROM products;

-- GROUP BY with HAVING
SELECT category_id, COUNT(*) AS product_count, AVG(price) AS avg_price
FROM products
WHERE is_active = TRUE
GROUP BY category_id
HAVING COUNT(*) > 5;

-- Multiple aggregates
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount,
    AVG(total_amount) AS avg_amount,
    MIN(total_amount) AS min_amount,
    MAX(total_amount) AS max_amount
FROM orders
GROUP BY status
ORDER BY total_amount DESC;

-- ============================================================================
-- SELECT Statements (JOIN)
-- ============================================================================

-- INNER JOIN
SELECT u.username, o.order_number, o.total_amount, o.status
FROM users u
INNER JOIN orders o ON u.id = o.user_id;

-- LEFT JOIN
SELECT u.username, u.email, COUNT(o.id) AS order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username, u.email;

-- RIGHT JOIN
SELECT p.name, oi.quantity, oi.unit_price
FROM order_items oi
RIGHT JOIN products p ON oi.product_id = p.id;

-- Multiple joins
SELECT
    o.order_number,
    u.username,
    p.name AS product_name,
    oi.quantity,
    oi.unit_price,
    oi.subtotal
FROM orders o
JOIN users u ON o.user_id = u.id
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
WHERE o.status = 'delivered';

-- Self join
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    manager_id INTEGER REFERENCES employees(id)
);

SELECT e.name AS employee, m.name AS manager
FROM employees e
LEFT JOIN employees m ON e.manager_id = m.id;

-- ============================================================================
-- SELECT Statements (Subqueries)
-- ============================================================================

-- Subquery in WHERE clause
SELECT *
FROM products
WHERE category_id IN (
    SELECT id FROM categories WHERE is_active = TRUE
);

-- Subquery in SELECT clause
SELECT
    username,
    email,
    (SELECT COUNT(*) FROM orders WHERE user_id = users.id) AS order_count
FROM users;

-- Subquery in FROM clause
SELECT avg_price_by_category.category_id, avg_price_by_category.avg_price
FROM (
    SELECT category_id, AVG(price) AS avg_price
    FROM products
    GROUP BY category_id
) AS avg_price_by_category
WHERE avg_price_by_category.avg_price > 500;

-- Correlated subquery
SELECT p.name, p.price
FROM products p
WHERE p.price > (
    SELECT AVG(price)
    FROM products
    WHERE category_id = p.category_id
);

-- EXISTS
SELECT u.username
FROM users u
WHERE EXISTS (
    SELECT 1 FROM orders o WHERE o.user_id = u.id AND o.status = 'delivered'
);

-- NOT EXISTS
SELECT u.username
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM orders o WHERE o.user_id = u.id
);

-- ============================================================================
-- SELECT Statements (Common Table Expressions - CTE)
-- ============================================================================

-- Simple CTE
WITH active_users AS (
    SELECT id, username, email
    FROM users
    WHERE created_at > CURRENT_DATE - INTERVAL '30 days'
)
SELECT * FROM active_users;

-- Multiple CTEs
WITH
    recent_orders AS (
        SELECT * FROM orders WHERE created_at > CURRENT_DATE - INTERVAL '7 days'
    ),
    order_stats AS (
        SELECT
            user_id,
            COUNT(*) AS order_count,
            SUM(total_amount) AS total_spent
        FROM recent_orders
        GROUP BY user_id
    )
SELECT u.username, os.order_count, os.total_spent
FROM users u
JOIN order_stats os ON u.id = os.user_id
ORDER BY os.total_spent DESC;

-- Recursive CTE (organizational hierarchy)
WITH RECURSIVE employee_hierarchy AS (
    -- Base case: top-level employees
    SELECT id, name, manager_id, 0 AS level
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive case: employees with managers
    SELECT e.id, e.name, e.manager_id, eh.level + 1
    FROM employees e
    JOIN employee_hierarchy eh ON e.manager_id = eh.id
)
SELECT * FROM employee_hierarchy ORDER BY level, name;

-- ============================================================================
-- SELECT Statements (Window Functions)
-- ============================================================================

-- ROW_NUMBER
SELECT
    name,
    price,
    ROW_NUMBER() OVER (ORDER BY price DESC) AS price_rank
FROM products;

-- RANK and DENSE_RANK
SELECT
    name,
    category_id,
    price,
    RANK() OVER (PARTITION BY category_id ORDER BY price DESC) AS rank,
    DENSE_RANK() OVER (PARTITION BY category_id ORDER BY price DESC) AS dense_rank
FROM products;

-- LAG and LEAD
SELECT
    order_number,
    created_at,
    total_amount,
    LAG(total_amount) OVER (ORDER BY created_at) AS previous_amount,
    LEAD(total_amount) OVER (ORDER BY created_at) AS next_amount
FROM orders;

-- FIRST_VALUE and LAST_VALUE
SELECT
    name,
    price,
    FIRST_VALUE(price) OVER (ORDER BY price) AS min_price,
    LAST_VALUE(price) OVER (ORDER BY price ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS max_price
FROM products;

-- Running total
SELECT
    order_number,
    created_at,
    total_amount,
    SUM(total_amount) OVER (ORDER BY created_at) AS running_total
FROM orders;

-- ============================================================================
-- CASE Expressions
-- ============================================================================

-- Simple CASE
SELECT
    name,
    price,
    CASE
        WHEN price < 100 THEN 'Budget'
        WHEN price < 500 THEN 'Mid-range'
        WHEN price < 1000 THEN 'Premium'
        ELSE 'Luxury'
    END AS price_category
FROM products;

-- CASE in aggregation
SELECT
    COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending_orders,
    COUNT(CASE WHEN status = 'processing' THEN 1 END) AS processing_orders,
    COUNT(CASE WHEN status = 'shipped' THEN 1 END) AS shipped_orders,
    COUNT(CASE WHEN status = 'delivered' THEN 1 END) AS delivered_orders
FROM orders;

-- Searched CASE
SELECT
    username,
    CASE
        WHEN created_at > CURRENT_DATE - INTERVAL '7 days' THEN 'New'
        WHEN created_at > CURRENT_DATE - INTERVAL '30 days' THEN 'Recent'
        ELSE 'Established'
    END AS user_status
FROM users;

-- ============================================================================
-- UPDATE Statements
-- ============================================================================

-- Simple update
UPDATE products SET quantity = 45 WHERE sku = 'LAPTOP-001';

-- Update with multiple columns
UPDATE users
SET email = 'newemail@example.com', updated_at = CURRENT_TIMESTAMP
WHERE username = 'alice';

-- Update with arithmetic
UPDATE products SET price = price * 1.1 WHERE category_id = 1;

-- Update with subquery
UPDATE products
SET quantity = quantity - (
    SELECT SUM(oi.quantity)
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.id
    WHERE oi.product_id = products.id AND o.created_at > CURRENT_DATE - INTERVAL '1 day'
)
WHERE id IN (SELECT DISTINCT product_id FROM order_items);

-- Update with JOIN (PostgreSQL syntax)
UPDATE orders o
SET status = 'cancelled'
FROM users u
WHERE o.user_id = u.id AND u.username = 'deleted_user';

-- Update with RETURNING
UPDATE products
SET is_active = FALSE
WHERE quantity = 0
RETURNING id, sku, name;

-- ============================================================================
-- DELETE Statements
-- ============================================================================

-- Simple delete
DELETE FROM products WHERE sku = 'OLD-PRODUCT-001';

-- Delete with condition
DELETE FROM orders WHERE status = 'cancelled' AND created_at < CURRENT_DATE - INTERVAL '90 days';

-- Delete with subquery
DELETE FROM user_profiles
WHERE user_id IN (
    SELECT id FROM users WHERE created_at < CURRENT_DATE - INTERVAL '2 years'
);

-- Delete with subquery (simpler alternative to USING)
DELETE FROM order_items
WHERE order_id IN (
    SELECT id FROM orders WHERE status = 'cancelled'
);

-- Delete with RETURNING
DELETE FROM products
WHERE is_active = FALSE AND quantity = 0
RETURNING id, sku, name;

-- ============================================================================
-- Functions and CAST
-- ============================================================================

-- String functions
SELECT
    username,
    UPPER(username) AS upper_name,
    LOWER(username) AS lower_name,
    LENGTH(username) AS name_length,
    SUBSTRING(username, 1, 3) AS name_prefix,
    CONCAT(username, '@example.com') AS email_suggestion
FROM users;

-- Date functions
SELECT
    created_at,
    DATE(created_at) AS date_only,
    EXTRACT(YEAR FROM created_at) AS year,
    EXTRACT(MONTH FROM created_at) AS month,
    EXTRACT(DAY FROM created_at) AS day,
    AGE(CURRENT_DATE, DATE(created_at)) AS age
FROM orders;

-- Mathematical functions
SELECT
    price,
    ROUND(price, 0) AS rounded,
    CEIL(price) AS ceiling,
    FLOOR(price) AS floor,
    ABS(price - 500) AS distance_from_500
FROM products;

-- CAST operations
SELECT
    id,
    CAST(id AS VARCHAR) AS id_string,
    CAST(price AS INTEGER) AS price_int,
    CAST(created_at AS DATE) AS created_date
FROM products;

-- Type conversion with ::
SELECT
    id::VARCHAR AS id_text,
    price::INTEGER AS price_int,
    created_at::DATE AS created_date
FROM products;

-- ============================================================================
-- UNION, INTERSECT, EXCEPT
-- ============================================================================

-- UNION
SELECT username AS identifier FROM users
UNION
SELECT sku AS identifier FROM products;

-- UNION ALL
SELECT 'user' AS type, COUNT(*) AS count FROM users
UNION ALL
SELECT 'product' AS type, COUNT(*) AS count FROM products
UNION ALL
SELECT 'order' AS type, COUNT(*) AS count FROM orders;

-- INTERSECT
SELECT user_id FROM orders WHERE status = 'delivered'
INTERSECT
SELECT user_id FROM orders WHERE total_amount > 1000;

-- EXCEPT
SELECT id FROM users
EXCEPT
SELECT user_id FROM orders;

-- ============================================================================
-- Transactions
-- ============================================================================

-- Simple transaction
BEGIN;
UPDATE products SET quantity = quantity - 1 WHERE id = 1;
INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal)
VALUES (1, 1, 1, 1299.99, 1299.99);
COMMIT;

-- Transaction with rollback
BEGIN;
DELETE FROM orders WHERE id = 999;
ROLLBACK;

-- Nested transaction example (using BEGIN/COMMIT)
BEGIN;
INSERT INTO users (username, email, password_hash) VALUES ('temp1', 'temp1@example.com', 'hash');
INSERT INTO users (username, email, password_hash) VALUES ('temp2', 'temp2@example.com', 'hash');
COMMIT;

-- ============================================================================
-- CREATE FUNCTION
-- ============================================================================

CREATE FUNCTION calculate_order_total(order_id_param INTEGER)
RETURNS DECIMAL(10, 2) AS $$
BEGIN
    RETURN (
        SELECT SUM(subtotal)
        FROM order_items
        WHERE order_id = order_id_param
    );
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION get_user_order_count(user_id_param INTEGER)
RETURNS INTEGER AS $$
BEGIN
    RETURN (
        SELECT COUNT(*)
        FROM orders
        WHERE user_id = user_id_param
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Complex Real-World Queries
-- ============================================================================

-- E-commerce analytics query
SELECT
    p.category_id,
    p.name,
    COUNT(DISTINCT o.id) AS times_ordered,
    SUM(oi.quantity) AS total_units_sold,
    SUM(oi.subtotal) AS total_revenue,
    AVG(oi.unit_price) AS avg_selling_price,
    p.price AS current_price,
    RANK() OVER (PARTITION BY p.category_id ORDER BY SUM(oi.subtotal) DESC) AS revenue_rank_in_category
FROM products p
LEFT JOIN order_items oi ON p.id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.id AND o.status IN ('delivered', 'shipped')
WHERE p.is_active = TRUE
GROUP BY p.id, p.category_id, p.name, p.price
HAVING SUM(oi.quantity) > 0
ORDER BY total_revenue DESC;

-- Customer segmentation query
WITH customer_metrics AS (
    SELECT
        u.id,
        u.username,
        COUNT(o.id) AS order_count,
        SUM(o.total_amount) AS lifetime_value,
        AVG(o.total_amount) AS avg_order_value,
        MAX(o.created_at) AS last_order_date,
        MIN(o.created_at) AS first_order_date
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    GROUP BY u.id, u.username
)
SELECT
    username,
    order_count,
    lifetime_value,
    avg_order_value,
    CASE
        WHEN order_count >= 10 AND lifetime_value >= 5000 THEN 'VIP'
        WHEN order_count >= 5 AND lifetime_value >= 2000 THEN 'Loyal'
        WHEN order_count >= 2 THEN 'Regular'
        WHEN order_count = 1 THEN 'One-time'
        ELSE 'Prospect'
    END AS customer_segment,
    CASE
        WHEN last_order_date > CURRENT_DATE - INTERVAL '30 days' THEN 'Active'
        WHEN last_order_date > CURRENT_DATE - INTERVAL '90 days' THEN 'At Risk'
        ELSE 'Inactive'
    END AS activity_status
FROM customer_metrics
ORDER BY lifetime_value DESC NULLS LAST;

-- Inventory and sales correlation
SELECT
    p.name,
    p.quantity AS current_stock,
    COALESCE(SUM(oi.quantity), 0) AS total_sold_last_30_days,
    COALESCE(SUM(oi.quantity) / 30.0, 0) AS avg_daily_sales,
    CASE
        WHEN COALESCE(SUM(oi.quantity) / 30.0, 0) > 0
        THEN p.quantity / (SUM(oi.quantity) / 30.0)
        ELSE NULL
    END AS days_of_inventory,
    CASE
        WHEN p.quantity < (COALESCE(SUM(oi.quantity) / 30.0, 0) * 7) THEN 'Low Stock'
        WHEN p.quantity > (COALESCE(SUM(oi.quantity) / 30.0, 0) * 60) THEN 'Overstocked'
        ELSE 'Normal'
    END AS stock_status
FROM products p
LEFT JOIN order_items oi ON p.id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.id
    AND o.created_at > CURRENT_DATE - INTERVAL '30 days'
    AND o.status IN ('delivered', 'shipped', 'processing')
WHERE p.is_active = TRUE
GROUP BY p.id, p.name, p.quantity
ORDER BY days_of_inventory ASC NULLS LAST;
