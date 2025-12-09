# Sample.cs

## Imports
```csharp
using System;
using System.Collections.Generic;
using System.Linq;
```

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| User | class | public | 10-65 | 10 | 3 |
| IUserRepository | interface | public | 70-77 | 5 | 0 |
| UserRole | enum | public | 82-88 | 0 | 0 |
| UserSettings | struct | public | 93-105 | 4 | 0 |

## User (10-65)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| _id | int | - | private | 13 | - |
| _createdBy | string | - | private,readonly | 14 | - |
| MaxNameLength | int | + | public,const | 15 | - |

### Constructors
| Constructor | Signature | Vis | Lines | Cx | Doc |
|-------------|-----------|-----|-------|----|----|
| User | (name:string, email:string, createdBy:string):void | + | 35-41 | 1 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Id | ():int | + | 18-22 | 1 | - |
| Name | ():string | + | 24-24 | 1 | - |
| Email | ():string | + | 25-25 | 1 | - |
| CreatedAt | ():DateTime | + | 26-26 | 1 | - |
| PhoneNumber | ():string? | + | 29-29 | 1 | - |
| DisplayName | ():string | + | 32-32 | 1 | - |
| UpdateEmail | (newEmail:string):void | + | 44-52 | 2 | - |
| IsValid | ():void | + | 54-59 | 1 | - |
| ToString | ():void | + | 61-64 | 1 | - |

## IUserRepository (70-77)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| GetById | (id:int):void | + | 72-72 | 1 | - |
| GetAll | ():void | + | 73-73 | 1 | - |
| Add | (user:User):void | + | 74-74 | 1 | - |
| Update | (user:User):void | + | 75-75 | 1 | - |
| Delete | (id:int):void | + | 76-76 | 1 | - |

## UserRole (82-88)
## UserSettings (93-105)
### Constructors
| Constructor | Signature | Vis | Lines | Cx | Doc |
|-------------|-----------|-----|-------|----|----|
| UserSettings | (emailNotifications:bool, smsNotifications:bool, theme:string):void | + | 99-104 | 1 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| EmailNotifications | ():bool | + | 95-95 | 1 | - |
| SmsNotifications | ():bool | + | 96-96 | 1 | - |
| Theme | ():string | + | 97-97 | 1 | - |