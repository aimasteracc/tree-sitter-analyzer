# Sample.rb

## Imports
```ruby
import date
import json
import concerns/timestampable
```

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| Authentication | module | public | 5-139 | 0 | 0 |
| User | class | public | 9-88 | 15 | 15 |
| AdminUser | class | public | 91-116 | 6 | 2 |
| Session | module | public | 119-138 | 3 | 0 |
| UserRepository | class | public | 142-184 | 6 | 4 |

## Authentication (5-139)
## User (9-88)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| User::STATUS_ACTIVE | None | + |  | 13 | - |
| User::STATUS_INACTIVE | None | + |  | 14 | - |
| User::MAX_LOGIN_ATTEMPTS | None | + |  | 15 | - |
| instance_count | None | - |  | 23 | - |
| username | None | - |  | 27 | - |
| email | None | - |  | 28 | - |
| created_at | None | - |  | 29 | - |
| password_hash | None | - |  | 30 | - |
| last_login_at | None | - |  | 31 | - |
| email | None | - |  | 44 | - |
| username | None | - |  | 45 | - |
| status | None | - |  | 56 | - |
| deactivated_at | None | - |  | 57 | - |
| user | None | - |  | 73 | - |
| user.password_hash | None | - |  | 74 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| User#username | (): | + | 18-18 | 1 | - |
| User#email | (): | + | 18-18 | 1 | - |
| User#id | (): | + | 19-19 | 1 | - |
| User#created_at | (): | + | 19-19 | 1 | - |
| User#password_hash | (): | + | 20-20 | 1 | - |
| User#initialize | (username:Any, email:Any): | + | 26-33 | 1 | - |
| User#authenticate | (password:Any): | + | 36-40 | 1 | - |
| User#update_profile | (data:Any): | + | 43-47 | 1 | - |
| User#active? | (): | + | 50-52 | 1 | - |
| User#deactivate! | (): | + | 55-58 | 1 | - |
| User.instance_count | (): [static] | + | 61-63 | 1 | - |
| User.find_by_email | (email:Any): [static] | + | 66-69 | 1 | - |
| User.create_with_password | (username:Any, email:Any, password:Any): [static] | + | 72-76 | 1 | - |
| User#validate_email | (): | + | 81-83 | 1 | - |
| User#generate_token | (): | + | 85-87 | 1 | - |

## AdminUser (91-116)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| permissions | None | - |  | 96 | - |
| permissions | None | - |  | 114 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| AdminUser#permissions | (): | + | 92-92 | 1 | - |
| AdminUser#initialize | (username:Any, email:Any, []:permissions =): | + | 94-97 | 1 | - |
| AdminUser#has_permission? | (permission:Any): | + | 99-101 | 1 | - |
| AdminUser#grant_permission | (permission:Any): | + | 103-105 | 1 | - |
| AdminUser#revoke_permission | (permission:Any): | + | 107-109 | 1 | - |
| AdminUser#update_profile | (data:Any): | + | 112-115 | 1 | - |

## Session (119-138)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Session.start | (user:Any): [static] | + | 121-127 | 1 | - |
| Session.valid? | (session:Any): [static] | + | 130-132 | 1 | - |
| Session.generate_session_token | (): [static] | + | 135-137 | 1 | - |

## UserRepository (142-184)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| database | None | - |  | 144 | - |
| cache | None | - |  | 145 | - |
| user | None | - |  | 151 | - |
| cache[id] | None | - |  | 152 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| UserRepository#initialize | (database:Any): | + | 143-146 | 1 | - |
| UserRepository#find | (id:Any): | + | 148-154 | 1 | - |
| UserRepository#save | (user:Any): | + | 156-162 | 1 | - |
| UserRepository#delete | (user:Any): | + | 164-167 | 1 | - |
| UserRepository#insert | (user:Any): | + | 171-176 | 1 | - |
| UserRepository#update | (user:Any): | + | 178-183 | 1 | - |

## Module Functions
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| create_user | (username:Any, email:Any): | + | 187-189 | 1 | - |
| hash_password | (password:Any): | + | 191-193 | 1 | - |
| with_transaction | (&block:Any): | + | 205-214 | 1 | - |
