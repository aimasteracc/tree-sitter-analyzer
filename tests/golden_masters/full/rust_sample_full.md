# sample.rs

## Structs
| Name | Type | Visibility | Lines | Fields | Traits |
|------|------|------------|-------|--------|--------|
| User | struct | pub | 7-12 | 4 | - |
| UserRole | enum | pub | 16-21 | 4 | - |
| Displayable | trait | pub | 24-30 | 0 | - |
| Container | struct | pub | 67-69 | 1 | - |
| BorrowedItem | struct | pub | 77-79 | 1 | - |

## Functions
| Function | Signature | Vis | Async | Lines | Doc |
|----------|-----------|-----|-------|-------|-----|
| display | fn(self) -> String | public | - | 25-25 | - |
| summary | fn(self) -> String | public | - | 27-29 | - |
| new | fn(id: u64, username: String, email: String) -> Self | public | - | 34-41 | - |
| deactivate | fn(self) | public | - | 44-46 | - |
| is_active | fn(self) -> bool | public | - | 49-51 | - |
| display | fn(self) -> String | public | - | 55-57 | - |
| fetch_user_data | fn(user_id: u64) -> Result<User, String> | public | Yes | 61-64 | - |
| new | fn(item: T) -> Self | public | - | 72-74 | - |
| main | fn() | public | - | 91-93 | - |
