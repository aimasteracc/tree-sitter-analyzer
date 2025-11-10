# Sample.php

## Info
| Property | Value |
|----------|-------|
| Package |  |
| Methods | 21 |
| Fields | 9 |

## Methods
| Method | Sig | V | L | Cx | Doc |
|--------|-----|---|---|----|----|
| User::__construct | (string,string):void | + | 36-42 | 1 | - |
| User::getId | ():i | + | 47-50 | 1 | - |
| User::setId | (i):void | + | 55-58 | 1 | - |
| User::getUsername | ():string | + | 63-66 | 1 | - |
| User::authenticate | (string):bool | + | 71-75 | 1 | - |
| User::updateProfile | (array):void | + | 80-86 | 1 | - |
| User::__get | (string):mixed | + | 91-94 | 1 | - |
| User::__set | (string,mixed):void | + | 99-102 | 1 | - |
| User::getInstanceCount | ():i | + | 107-110 | 1 | - |
| User::findByEmail | (string):?self | + | 115-119 | 1 | - |
| AdminUser::__construct | (string,string,array):void | + | 129-133 | 1 | - |
| AdminUser::hasPermission | (string):bool | + | 135-138 | 1 | - |
| AdminUser::grantPermission | (string):void | + | 140-145 | 1 | - |
| UserRepositoryInterface::find | (i):?User | + | 153-153 | 1 | - |
| UserRepositoryInterface::save | (User):void | + | 154-154 | 1 | - |
| UserRepositoryInterface::delete | (User):void | + | 155-155 | 1 | - |
| Loggable::log | (string):void | + | 165-171 | 1 | - |
| Loggable::getLogs | ():array | + | 173-176 | 1 | - |
| label | ():string | + | 189-197 | 1 | - |
| App\Models\createUser | (string,string):User | + | 203-206 | 1 | - |
| App\Models\hashPassword | (string):string | + | 211-214 | 1 | - |
