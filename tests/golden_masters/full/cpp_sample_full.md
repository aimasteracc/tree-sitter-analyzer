# sample.cpp

## Namespaces
- `math` (18-47)

## Imports
```cpp
#include <iostream>
#include <string>
#include <vector>
#include <memory>
#include <functional>
using namespace std;
using std::vector;
using StringList = vector<string>;
```

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| Container | class | public | 31-45 | 5 | 0 |
| Point | struct | public | 62-70 | 1 | 2 |
| Shape | class | public | 73-83 | 4 | 0 |
| Rectangle | class | public | 86-128 | 11 | 3 |
| Printable | class | public | 134-138 | 2 | 0 |
| Circle | class | public | 140-157 | 5 | 1 |

## Container (31-45)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Container | ():void | + | 33-33 | 5-6 | 1 | - |
| Container | (value:T):void | + | 34-34 | 5-6 | 1 | - |
| ~Container | ():void | + | 35-35 | 5-6 | 1 | - |
| get | ():T | + | 37-37 | 5-6 | 2 | - |
| set | (value:T):void | + | 38-41 | 5-6 | 1 | - |

## Point (62-70)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| x | int | + |  | 63 | - |
| y | int | + |  | 64 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| distance | ():double | + | 67-69 | 5-6 | 1 | - |

## Shape (73-83)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| ~Shape | ():void | + | 75-75 | 5-6 | 1 | - |
| area | ():double | + | 78-78 | 5-6 | 1 | - |
| perimeter | ():double | + | 79-79 | 5-6 | 1 | - |
| name | ():string | + | 82-82 | 5-6 | 1 | - |

## Rectangle (86-128)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| width_ | double | - |  | 123 | - |
| height_ | double | - |  | 124 | - |
| instance_count_ | int | - | static | 127 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Rectangle | (w:double, h:double):void | + | 89-89 | 5-6 | 1 | - |
| Rectangle | (other:const Rectangle&):void | + | 92-92 | 5-6 | 1 | - |
| Rectangle | (other:Rectangle&&):void | + | 95-98 | 5-6 | 1 | - |
| ~Rectangle | ():void | + | 101-101 | 5-6 | 1 | - |
| area | ():double | + | 104-104 | 5-6 | 1 | - |
| perimeter | ():double | + | 105-105 | 5-6 | 1 | - |
| name | ():string | + | 106-106 | 5-6 | 1 | - |
| width | ():double | + | 109-109 | 5-6 | 1 | - |
| height | ():double | + | 110-110 | 5-6 | 1 | - |
| operator== | (other:const Rectangle&):bool | + | 113-115 | 5-6 | 1 | - |
| square | (side:double):Rectangle [static] | + | 118-120 | 5-6 | 1 | - |

## Printable (134-138)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| print | ():void | + | 136-136 | 5-6 | 1 | - |
| ~Printable | ():void | + | 137-137 | 5-6 | 1 | - |

## Circle (140-157)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| radius_ | double | - |  | 156 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Circle | (r:double):void | + | 142-142 | 5-6 | 1 | - |
| area | ():double | + | 144-144 | 5-6 | 1 | - |
| perimeter | ():double | + | 145-145 | 5-6 | 1 | - |
| name | ():string | + | 146-146 | 5-6 | 1 | - |
| print | ():void | + | 148-150 | 5-6 | 1 | - |

## Global Functions
| Method | Signature | Vis | Lines | Cols | Cx | Doc |
|--------|-----------|-----|-------|------|----|----|
| max | (a:T, b:T):T | + | 25-27 | 5-6 | 2 | - |
| operator<< | (os:ostream&, c:const Circle&):ostream& | + | 160-163 | 5-6 | 1 | - |
| swap_values | (a:T&, b:T&):void | + | 176-180 | 5-6 | 1 | - |
| add | (a:int, 0:int b =):int | + | 185-187 | 5-6 | 1 | - |
| add | (a:double, b:double):double | + | 190-192 | 5-6 | 1 | - |
| process | (vec:vector<int>&, transformer:function<int(int)>):void | + | 195-199 | 5-6 | 2 | - |
| create_shape | (type:const string&, size:double):unique_ptr<Shape> | + | 202-208 | 5-6 | 2 | - |
| main | ():int | + | 211-256 | 5-6 | 3 | - |

## Global Variables
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| PI | double | + | constexpr | 21 | - |
| static_value | int | - | static | 170 | - |
| APP_NAME | string | + | const | 171 | - |
| MAX_SIZE | int | + | constexpr | 172 | - |