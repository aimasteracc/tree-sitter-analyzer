-- Sample SQL Database Schema
-- This file demonstrates various SQL elements for testing tree-sitter-analyzer

-- Create users table
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    status ENUM('active', 'inactive', 'suspended') DEFAULT 'active'
);

-- Create orders table
CREATE TABLE orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create products table
CREATE TABLE products (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INT DEFAULT 0,
    category_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create view for active users
CREATE VIEW active_users AS
SELECT
    id,
    username,
    email,
    created_at
FROM users
WHERE status = 'active';

-- Create view for order summary
CREATE VIEW order_summary AS
SELECT
    o.id AS order_id,
    u.username,
    o.order_date,
    o.total_amount,
    o.status
FROM orders o
INNER JOIN users u ON o.user_id = u.id;

-- Create stored procedure to get user orders
CREATE PROCEDURE get_user_orders(IN user_id_param INT)
BEGIN
    SELECT
        o.id,
        o.order_date,
        o.total_amount,
        o.status
    FROM orders o
    WHERE o.user_id = user_id_param
    ORDER BY o.order_date DESC;
END;

-- Create stored procedure to update product stock
CREATE PROCEDURE update_product_stock(
    IN product_id_param INT,
    IN quantity_change INT
)
BEGIN
    UPDATE products
    SET stock_quantity = stock_quantity + quantity_change
    WHERE id = product_id_param;

    SELECT
        id,
        name,
        stock_quantity
    FROM products
    WHERE id = product_id_param;
END;

-- Create function to calculate order total
CREATE FUNCTION calculate_order_total(order_id_param INT)
RETURNS DECIMAL(10, 2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE total DECIMAL(10, 2);

    SELECT COALESCE(SUM(price * quantity), 0) INTO total
    FROM order_items
    WHERE order_id = order_id_param;

    RETURN total;
END;

-- Create function to check user status
CREATE FUNCTION is_user_active(user_id_param INT)
RETURNS BOOLEAN
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE user_status VARCHAR(50);

    SELECT status INTO user_status
    FROM users
    WHERE id = user_id_param;

    RETURN user_status = 'active';
END;

-- Create trigger to update order total
CREATE TRIGGER update_order_total
AFTER INSERT ON order_items
FOR EACH ROW
BEGIN
    UPDATE orders
    SET total_amount = (
        SELECT COALESCE(SUM(price * quantity), 0)
        FROM order_items
        WHERE order_id = NEW.order_id
    )
    WHERE id = NEW.order_id;
END;

-- Create trigger to log user changes
CREATE TRIGGER log_user_changes
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    INSERT INTO user_audit_log (
        user_id,
        old_status,
        new_status,
        changed_at
    ) VALUES (
        NEW.id,
        OLD.status,
        NEW.status,
        NOW()
    );
END;

-- Create indexes for performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_name ON products(name);

-- Create composite index
CREATE INDEX idx_orders_user_date ON orders(user_id, order_date);
