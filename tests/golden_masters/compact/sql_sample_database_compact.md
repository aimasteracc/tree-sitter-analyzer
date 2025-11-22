# sample_database.sql

| Element | Type | Lines | Details |
|---------|------|-------|---------|
| users | table | 5-13 | 7 cols, PK: id |
| orders | table | 16-23 | 5 cols, PK: id |
| products | table | 26-34 | 7 cols, PK: id |
| active_users | view | 37-44 | view |
| order_summary | view | 47-55 | view |
| get_user_orders | procedure | 58-68 | 1 params |
| update_product_stock | procedure | 71-86 | 2 params |
| calculate_order_total | function | 89-101 | 1 params, -> DECIMAL(10, 2) |
| is_user_active | function | 104-116 | 1 params, -> BOOLEAN |
| update_order_total | trigger | 119-156 | AFTER UPDATE, on order_items |
| log_user_changes | trigger | 133-156 | AFTER UPDATE, on users |
| idx_users_email | index | 151-151 | on users, (email) |
| idx_users_status | index | 152-152 | on users, (status) |
| idx_orders_user_id | index | 153-153 | on orders, (user_id) |
| idx_orders_date | index | 154-154 | on orders, (order_date) |
| idx_products_category | index | 155-155 | on products, (category_id) |
| idx_products_name | index | 156-156 | on products, (name) |
| idx_orders_user_date | index | 159-159 | on orders, (user_id, order_date) |
