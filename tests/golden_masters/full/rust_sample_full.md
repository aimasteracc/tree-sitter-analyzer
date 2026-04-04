# sample.rs

## Structs
| Name | Type | Visibility | Lines | Fields | Traits |
|------|------|------------|-------|--------|--------|
| sample_module | module | pub | 2-88 | 6 | - |
| User | struct | pub | 7-12 | 4 | - |
| UserRole | enum | pub | 16-21 | 0 | - |
| Displayable | trait | pub | 24-30 | 0 | - |
| User impl | impl | private | 32-52 | 0 | - |
| User impl Displayable | impl | private | 54-58 | 0 | - |
| Container | struct | pub | 67-69 | 1 | - |
| Container<T> impl | impl | private | 71-80 | 1 | - |
| BorrowedItem | struct | pub | 77-79 | 1 | - |

## Functions
| Function | Signature | Vis | Async | Lines | Doc |
|----------|-----------|-----|-------|-------|-----|
| display | fn({'name': 'self', 'type': 'Any'}) -> String | public | - | 25-25 | - |
| summary | fn({'name': 'self', 'type': 'Any'}) -> String | public | - | 27-29 | - |
| new | fn({'name': 'id', 'type': 'u64'}, {'name': 'username', 'type': 'String'}, {'name': 'email', 'type': 'String'}) -> Self | public | - | 34-41 | - |
| deactivate | fn({'name': 'self', 'type': 'Any'}) | public | - | 44-46 | - |
| is_active | fn({'name': 'self', 'type': 'Any'}) -> bool | public | - | 49-51 | - |
| display | fn({'name': 'self', 'type': 'Any'}) -> String | public | - | 55-57 | - |
| fetch_user_data | fn({'name': 'user_id', 'type': 'u64'}) -> Result<User, String> | public | - | 61-64 | - |
| new | fn({'name': 'item', 'type': 'T'}) -> Self | public | - | 72-74 | - |
| main | fn() | public | - | 91-93 | - |
