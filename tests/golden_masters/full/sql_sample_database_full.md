# sample_database.sql

## Database Schema Overview
| Element | Type | Lines | Columns/Parameters | Dependencies |
|---------|------|-------|-------------------|--------------|
| users | table | 5-13 | 7 columns | - |
| orders | table | 16-23 | 5 columns | - |
| products | table | 26-34 | 7 columns | - |
| active_users | view | 37-44 | - | - |
| order_summary | view | 47-55 | - | - |
| get_user_orders | procedure | 58-68 | (CREATE, user_id_param, BEGIN, status, orders, WHERE, user_id_param, BY, order_date) | - |
| update_product_stock | procedure | 71-86 | (CREATE, IN, _id_param, IN, _change, BEGIN, products, quantity_change, SELECT, stock_quantity, products) | - |
| calculate_order_total | function | 89-101 | (CREATE, order_id_param, RETURNS, READS, DATA, BEGIN, total, SELECT, INTO, FROM, _items, RETURN) | - |
| is_user_active | function | 104-116 | (CREATE, user_id_param, RETURNS, READS, DATA, BEGIN, user_status, SELECT, INTO, _status, users, RETURN) | - |
| update_order_total | trigger | 119-156 | - | - |
| idx_users_email | index | 151-151 | users(email) | users |
| idx_users_status | index | 152-152 | users(status) | users |
| idx_orders_user_id | index | 153-153 | orders(user_id) | orders |
| idx_orders_date | index | 154-154 | orders(order_date) | orders |
| idx_products_category | index | 155-155 | products(category_id) | products |
| idx_products_name | index | 156-156 | products(name) | products |
| idx_orders_user_date | index | 159-159 | - | - |

## Tables
### users (5-13)
**Columns**: id, username, email, password_hash, created_at, updated_at, status
**Primary Key**: id

### orders (16-23)
**Columns**: id, user_id, order_date, total_amount, status
**Primary Key**: id

### products (26-34)
**Columns**: id, name, description, price, stock_quantity, category_id, created_at
**Primary Key**: id

## Views
### active_users (37-44)

### order_summary (47-55)

## Procedures
### get_user_orders (58-68)
**Parameters**: CREATE PROCEDURE, user_id_param INT, BEGIN SELECT, status FROM, orders o, WHERE o, user_id_param ORDER, BY o, order_date DESC

### update_product_stock (71-86)
**Parameters**: CREATE PROCEDURE, IN product, _id_param INT, IN quantity, _change INT, BEGIN UPDATE, products SET, quantity_change WHERE, SELECT id, stock_quantity FROM, products WHERE

## Functions
### calculate_order_total (89-101)
**Parameters**: CREATE FUNCTION, order_id_param INT, RETURNS DECIMAL(10, 2), READS SQL, DATA DETERMINISTIC, BEGIN DECLARE, total DECIMAL(10, 2), SELECT COALESCE(SUM(price * quantity), INTO total, FROM order, _items WHERE, RETURN total
**Returns**: DECIMAL(10, 2)

### is_user_active (104-116)
**Parameters**: CREATE FUNCTION, user_id_param INT, RETURNS BOOLEAN, READS SQL, DATA DETERMINISTIC, BEGIN DECLARE, user_status VARCHAR(50), SELECT status, INTO user, _status FROM, users WHERE, RETURN user
**Returns**: BOOLEAN

## Triggers
### update_order_total (119-156)

## Indexes
### idx_users_email (151-151)
**Table**: users
**Columns**: email
**Type**: Standard index

### idx_users_status (152-152)
**Table**: users
**Columns**: status
**Type**: Standard index

### idx_orders_user_id (153-153)
**Table**: orders
**Columns**: user_id
**Type**: Standard index

### idx_orders_date (154-154)
**Table**: orders
**Columns**: order_date
**Type**: Standard index

### idx_products_category (155-155)
**Table**: products
**Columns**: category_id
**Type**: Standard index

### idx_products_name (156-156)
**Table**: products
**Columns**: name
**Type**: Standard index

### idx_orders_user_date (159-159)
**Type**: Standard index
