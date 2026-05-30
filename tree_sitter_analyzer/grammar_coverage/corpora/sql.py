"""Built-in SQL corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
-- Create tables
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) UNIQUE NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status      VARCHAR(50) DEFAULT "active"
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total       DECIMAL(10, 2) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_orders_user_id ON orders(user_id);

-- Insert data
INSERT INTO users (name, email) VALUES
    ("Alice", "alice@example.com"),
    ("Bob", "bob@example.com");

-- Queries
SELECT
    u.id,
    u.name,
    COUNT(o.id) AS order_count,
    SUM(o.total) AS total_spent
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.status = "active"
GROUP BY u.id, u.name
HAVING COUNT(o.id) > 0
ORDER BY total_spent DESC
LIMIT 10;

-- Subquery
SELECT name FROM users
WHERE id IN (
    SELECT DISTINCT user_id FROM orders
    WHERE total > 100
);

-- CTE
WITH active_users AS (
    SELECT id, name FROM users WHERE status = "active"
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY name) AS rn
    FROM active_users
)
SELECT * FROM ranked WHERE rn <= 5;

-- Update & Delete
UPDATE users SET status = "inactive" WHERE created_at < NOW() - INTERVAL "1 year";
DELETE FROM orders WHERE user_id NOT IN (SELECT id FROM users);

-- View
CREATE VIEW user_summary AS
SELECT u.name, COUNT(o.id) AS orders FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.name;
"""
