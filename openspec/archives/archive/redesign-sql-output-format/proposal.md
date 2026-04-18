# Proposal: Redesign SQL Output Format

**Change ID**: `redesign-sql-output-format`  
**Type**: Enhancement  
**Priority**: High  
**Status**: Draft

---

## Problem Statement

The current SQL output format is inappropriate and confusing for SQL database elements:

### Current Issues
1. **Inappropriate terminology**: SQL tables/views are displayed as "class" with "public" visibility
2. **Empty content sections**: Table headers like `## users` appear with no meaningful content
3. **Missing SQL-specific elements**: Procedures, functions, triggers, and indexes are not displayed
4. **Generic formatting**: Uses Java/Python-oriented terminology instead of SQL-specific terms

### Current Output Example
```markdown
# sample_database.sql

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| users | class | public | 5-13 | 0 | 0 |

## users (5-13)
```

---

## Proposed Solution

Design a SQL-specific output format that properly represents database elements with appropriate terminology and comprehensive information.

### Proposed Output Format

#### Full Format
```markdown
# sample_database.sql

## Database Schema Overview
| Element | Type | Lines | Columns/Parameters | Dependencies |
|---------|------|-------|-------------------|--------------|
| users | table | 5-13 | 7 columns | - |
| orders | table | 16-23 | 5 columns | users(id) |
| active_users | view | 37-44 | 4 columns | users |
| get_user_orders | procedure | 58-68 | 1 parameter | orders, users |
| calculate_order_total | function | 89-101 | 1 parameter | order_items |
| update_order_total | trigger | 119-130 | - | orders, order_items |
| idx_users_email | index | 151 | users(email) | users |

## Tables
### users (5-13)
**Columns**: id, username, email, password_hash, created_at, updated_at, status  
**Primary Key**: id  
**Constraints**: UNIQUE(username), UNIQUE(email)

### orders (16-23)
**Columns**: id, user_id, order_date, total_amount, status  
**Primary Key**: id  
**Foreign Keys**: user_id → users(id)

## Views
### active_users (37-44)
**Source**: users  
**Columns**: id, username, email, created_at  
**Filter**: status = 'active'

## Procedures
### get_user_orders (58-68)
**Parameters**: user_id_param INT  
**Returns**: Result set (id, order_date, total_amount, status)  
**Dependencies**: orders

## Functions
### calculate_order_total (89-101)
**Parameters**: order_id_param INT  
**Returns**: DECIMAL(10, 2)  
**Dependencies**: order_items

## Triggers
### update_order_total (119-130)
**Event**: AFTER INSERT ON order_items  
**Action**: Update orders.total_amount  
**Dependencies**: orders, order_items

## Indexes
### idx_users_email (151)
**Table**: users  
**Columns**: email  
**Type**: Standard index
```

#### Compact Format
```markdown
# sample_database.sql

| Element | Type | Lines | Details |
|---------|------|-------|---------|
| users | table | 5-13 | 7 cols, PK: id |
| orders | table | 16-23 | 5 cols, FK: user_id→users |
| active_users | view | 37-44 | users filtered |
| get_user_orders | procedure | 58-68 | 1 param |
| calculate_order_total | function | 89-101 | INT→DECIMAL |
| update_order_total | trigger | 119-130 | INSERT→orders |
| idx_users_email | index | 151 | users(email) |
```

#### CSV Format
```csv
Element,Type,Lines,Columns_Parameters,Dependencies
users,table,5-13,7 columns,
orders,table,16-23,5 columns,users(id)
active_users,view,37-44,4 columns,users
get_user_orders,procedure,58-68,1 parameter,orders;users
calculate_order_total,function,89-101,1 parameter,order_items
update_order_total,trigger,119-130,,orders;order_items
idx_users_email,index,151,users(email),users
```

---

## Benefits

1. **SQL-appropriate terminology**: Uses database-specific terms (table, view, procedure, function, trigger, index)
2. **Comprehensive information**: Shows all SQL elements, not just tables/views
3. **Meaningful details**: Displays columns, parameters, dependencies, constraints
4. **Professional appearance**: Suitable for database documentation and analysis
5. **Consistent with SQL standards**: Aligns with database industry terminology

---

## Implementation Scope

### Core Changes
1. Create SQL-specific formatter classes
2. Modify output generation logic for SQL files
3. Update element extraction to include all SQL constructs
4. Add SQL-specific metadata extraction (columns, constraints, dependencies)

### Files to Modify
- `tree_sitter_analyzer/languages/sql_plugin.py` - Enhanced element extraction
- `tree_sitter_analyzer/formatters/` - New SQL-specific formatters
- `tree_sitter_analyzer/models.py` - SQL-specific element models
- Output generation logic in CLI and MCP tools

---

## Success Criteria

1. SQL files display appropriate database terminology
2. All SQL elements (tables, views, procedures, functions, triggers, indexes) are shown
3. Meaningful metadata is extracted and displayed
4. Output is professional and suitable for database documentation
5. All existing tests pass with updated golden masters
6. New tests validate SQL-specific formatting

---

## Dependencies

- Requires completion of `add-sql-language-support` change
- May impact existing golden master files
- Requires updates to format testing strategy

---

## Risk Assessment

**Risk Level**: 🟡 MEDIUM

### Risks
1. **Breaking changes**: Existing SQL output format will change completely
2. **Golden master updates**: All SQL-related golden masters need regeneration
3. **Test updates**: Format-related tests may need updates

### Mitigation
1. Comprehensive testing with updated golden masters
2. Clear documentation of format changes
3. Backward compatibility considerations for API consumers
