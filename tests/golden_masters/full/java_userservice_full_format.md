# com.example.service.UserService

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
| Name | UserService |
| Package | com.example.service |
| Type | class |
| Access | public |

## Methods
| Name | Return Type | Parameters | Access | Line |
|------|-------------|------------|--------|------|
| UserService | - | UserRepository userRepository | public | 10 |
| findUserById | User | Long id | public | 14 |
| createUser | User | String name, String email | public | 21 |
| validateUser | boolean | User user | private | 27 |

## Fields
| Name | Type | Access | Static | Final | Line |
|------|------|--------|--------|-------|------|
| userRepository | UserRepository | private | false | false | 7 |
| logger | Logger | private | true | true | 8 |
