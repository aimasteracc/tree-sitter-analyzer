# com.example.kotlin.Sample.kt

## Imports
```kotlin
import java.util.Collections
```

## Classes & Objects
| Name | Type | Visibility | Lines | Props | Methods |
|------|------|------------|-------|-------|---------|
| User | data | public | 8-13 | 0 | 1 |
| Displayable | interface | public | 15-21 | 0 | 2 |
| Result | sealed | public | 23-26 | 0 | 2 |
| Success | data | public | 24-24 | 0 | 1 |
| Error | data | public | 25-25 | 0 | 1 |
| UserManager | class | public | 28-45 | 1 | 4 |
| Config | object | public | 47-50 | 2 | 0 |
| LegacyUserManager | class | public | 57-60 | 0 | 1 |

## Functions
| Function | Signature | Vis | Lines | Cx | Suspend | Doc |
|----------|-----------|-----|-------|----|---------|-----|
| User | fun(id: Long, username: String, email: String, active: Boolean) | pub | 8-13 | 1 | - | - |
| display | fun(): String | pub | 16-16 | 1 | - | - |
| summary | fun(): String | pub | 18-20 | 1 | - | - |
| Success | fun(data: T) | pub | 24-24 | 1 | - | - |
| Error | fun(message: String) | pub | 25-25 | 1 | - | - |
| UserManager | fun(db: Any?) | pub | 28-28 | 1 | - | - |
| getUser | fun(id: Long): User? | pub | 33-35 | 2 | - | - |
| fetchUserAsync | fun(id: Long): Result<User> | pub | 37-40 | 1 | - | - |
| display | fun(): String | pub | 42-44 | 1 | - | - |
| toTitleCase | fun(): String | pub | 52-54 | 2 | - | - |
| get | fun(): String | pub | 59-59 | 1 | - | - |
| main | fun(args: Array<String>) | pub | 62-65 | 1 | - | - |

## Properties
| Name | Type | Vis | Kind | Line | Doc |
|------|------|-----|------|------|-----|
| userCount | Int | pub | - | 30 | - |
| MAX_USERS | Inferred | pub | - | 48 | - |
| version | Inferred | pub | - | 49 | - |
