# Sample.rb

## Info
| Property | Value |
|----------|-------|
| Package |  |
| Methods | 33 |
| Fields | 25 |

## Methods
| Method | Sig | V | L | Cx | Doc |
|--------|-----|---|---|----|----|
| User#username | (): | + | 18-18 | 1 | - |
| User#email | (): | + | 18-18 | 1 | - |
| User#id | (): | + | 19-19 | 1 | - |
| User#created_at | (): | + | 19-19 | 1 | - |
| User#password_hash | (): | + | 20-20 | 1 | - |
| User#initialize | (Any, Any): | + | 26-33 | 1 | - |
| User#authenticate | (Any): | + | 36-40 | 1 | - |
| User#update_profile | (Any): | + | 43-47 | 1 | - |
| User#active? | (): | + | 50-52 | 1 | - |
| User#deactivate! | (): | + | 55-58 | 1 | - |
| User.instance_count | (): | + | 61-63 | 1 | - |
| User.find_by_email | (Any): | + | 66-69 | 1 | - |
| User.create_with_password | (Any, Any, Any): | + | 72-76 | 1 | - |
| User#validate_email | (): | + | 81-83 | 1 | - |
| User#generate_token | (): | + | 85-87 | 1 | - |
| AdminUser#permissions | (): | + | 92-92 | 1 | - |
| AdminUser#initialize | (Any, Any, permissions =): | + | 94-97 | 1 | - |
| AdminUser#has_permission? | (Any): | + | 99-101 | 1 | - |
| AdminUser#grant_permission | (Any): | + | 103-105 | 1 | - |
| AdminUser#revoke_permission | (Any): | + | 107-109 | 1 | - |
| AdminUser#update_profile | (Any): | + | 112-115 | 1 | - |
| Session.start | (Any): | + | 121-127 | 1 | - |
| Session.valid? | (Any): | + | 130-132 | 1 | - |
| Session.generate_session_token | (): | + | 135-137 | 1 | - |
| UserRepository#initialize | (Any): | + | 143-146 | 1 | - |
| UserRepository#find | (Any): | + | 148-154 | 1 | - |
| UserRepository#save | (Any): | + | 156-162 | 1 | - |
| UserRepository#delete | (Any): | + | 164-167 | 1 | - |
| UserRepository#insert | (Any): | + | 171-176 | 1 | - |
| UserRepository#update | (Any): | + | 178-183 | 1 | - |
| create_user | (Any, Any): | + | 187-189 | 1 | - |
| hash_password | (Any): | + | 191-193 | 1 | - |
| with_transaction | (Any): | + | 205-214 | 1 | - |
