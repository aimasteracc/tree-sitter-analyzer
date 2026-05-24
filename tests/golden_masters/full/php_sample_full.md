# Sample.php

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| App\Models\User | class | public | 13-120 | 10 | 7 |
| App\Models\AdminUser | class | public | 125-146 | 3 | 1 |
| App\Models\UserRepositoryInterface | interface | public | 151-156 | 3 | 0 |
| App\Models\Loggable | trait | public | 161-177 | 2 | 1 |
| App\Models\UserStatus | enum | public | 182-198 | 1 | 0 |

## App\Models\User (13-120)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| User::id | int | - | private | 25 | - |
| User::username | string | + | public | 26 | - |
| User::email | string | + | public | 27 | - |
| User::passwordHash | string | - | private | 28 | - |
| User::createdAt | \DateTime | + | public,readonly | 29 | - |
| User::lastLoginAt | ?string | # | protected | 30 | - |
| User::instanceCount | int | - | private,static | 31 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| User::__construct | ($username:string, $email:string):void | + | 36-42 | 1 | - |
| User::getId | ():int | + | 47-50 | 1 | - |
| User::setId | ($id:int):void | + | 55-58 | 1 | - |
| User::getUsername | ():string | + | 63-66 | 1 | - |
| User::authenticate | ($password:string):bool | + | 71-75 | 1 | - |
| User::updateProfile | ($data:array):void | + | 80-86 | 1 | - |
| User::__get | ($name:string):mixed | + | 91-94 | 1 | - |
| User::__set | ($name:string, $value:mixed):void | + | 99-102 | 1 | - |
| User::getInstanceCount | ():int [static] | + | 107-110 | 1 | - |
| User::findByEmail | ($email:string):?self [static] | + | 115-119 | 1 | - |

## App\Models\AdminUser (125-146)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| AdminUser::permissions | array | - | private | 127 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| AdminUser::__construct | ($username:string, $email:string, $permissions:array):void | + | 129-133 | 1 | - |
| AdminUser::hasPermission | ($permission:string):bool | + | 135-138 | 1 | - |
| AdminUser::grantPermission | ($permission:string):void | + | 140-145 | 1 | - |

## App\Models\UserRepositoryInterface (151-156)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| UserRepositoryInterface::find | ($id:int):?User | + | 153-153 | 1 | - |
| UserRepositoryInterface::save | ($user:User):void | + | 154-154 | 1 | - |
| UserRepositoryInterface::delete | ($user:User):void | + | 155-155 | 1 | - |

## App\Models\Loggable (161-177)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| Loggable::logs | array | # | protected | 163 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Loggable::log | ($message:string):void | + | 165-171 | 1 | - |
| Loggable::getLogs | ():array | + | 173-176 | 1 | - |

## App\Models\UserStatus (182-198)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| UserStatus::label | ():string | + | 189-197 | 1 | - |

## Functions
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| App\Models\createUser | ($username:string, $email:string):User | + | 203-206 | 1 | - |
| App\Models\hashPassword | ($password:string):string | + | 211-214 | 1 | - |
