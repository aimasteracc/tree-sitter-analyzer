# com.example.service.TestClass

## Package
`com.example.service`

## Imports
```java
import java.util.List;
import java.sql.SQLException;
```

## Class Info
| Property | Value |
|----------|-------|
| Package | com.example.service |
| Type | class |
| Visibility | public |
| Lines | 6-36 |
| Total Methods | 4 |
| Total Fields | 2 |

## UserService (6-36)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| userRepository | UserRepository | - | private | 7 | - |
| logger | Logger | - | private,static,final | 8 | - |

### Constructors
| Constructor | Signature | Vis | Lines | Cx | Doc |
|-------------|-----------|-----|-------|----|----|
| UserService | (userRepository:UserRepository):void | + | 10-12 | 1 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| findUserById | (id:Long):User | + | 14-19 | 2 | - |
| createUser | (name:String, email:String):User | + | 21-25 | 1 | - |

### Private Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| validateUser | (user:User):boolean | - | 27-35 | 3 | - |