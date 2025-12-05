# sample.cpp

## Imports
```cpp
#include <iostream>

#include <string>

#include <vector>

#include <memory>

#include <functional>

using namespace std;
using std::vector;
using namespace math;
```

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| Container | class | public | 31-45 | 5 | 0 |
| Point | struct | public | 62-70 | 1 | 0 |
| Shape | class | public | 73-83 | 2 | 0 |
| Rectangle | class | public | 86-128 | 11 | 0 |
| Printable | class | public | 134-138 | 1 | 0 |
| Circle | class | public | 140-157 | 5 | 0 |

## Container (31-45)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Container | ((:Any, ):Any): | + | 33-33 | 1 | - |
| Container | ((:Any, value:T, ):Any): | + | 34-34 | 1 | - |
| Container | ((:Any, ):Any): | + | 35-35 | 1 | - |
| get | ((:Any, ):Any):T | + | 37-37 | 1 | - |
| set | ((:Any, value:T, ):Any):void | + | 38-41 | 1 | - |

## Point (62-70)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| distance | ((:Any, ):Any):double | + | 67-69 | 1 | - |

## Shape (73-83)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Shape | ((:Any, ):Any): | + | 75-75 | 1 | - |
| name | ((:Any, ):Any):string | + | 82-82 | 1 | - |

## Rectangle (86-128)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Rectangle | ((:Any, w:double, ,:Any, h:double, ):Any): | + | 89-89 | 1 | - |
| Rectangle | ((:Any, other:const Rectangle&, ):Any): | + | 92-92 | 1 | - |
| Rectangle | ((:Any, other:Rectangle&&, ):Any): | + | 95-98 | 1 | - |
| Rectangle | ((:Any, ):Any): | + | 101-101 | 1 | - |
| area | ((:Any, ):Any):double | + | 104-104 | 1 | - |
| perimeter | ((:Any, ):Any):double | + | 105-105 | 1 | - |
| name | ((:Any, ):Any):string | + | 106-106 | 1 | - |
| width | ((:Any, ):Any):double | + | 109-109 | 1 | - |
| height | ((:Any, ):Any):double | + | 110-110 | 1 | - |
| Rectangle | ((:Any, other:const Rectangle&, ):Any):bool | + | 113-115 | 1 | - |
| square | ((:Any, side:double, ):Any):Rectangle | + | 118-120 | 1 | - |

## Printable (134-138)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Printable | ((:Any, ):Any): | + | 137-137 | 1 | - |

## Circle (140-157)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| Circle | ((:Any, r:double, ):Any): | + | 142-142 | 1 | - |
| area | ((:Any, ):Any):double | + | 144-144 | 1 | - |
| perimeter | ((:Any, ):Any):double | + | 145-145 | 1 | - |
| name | ((:Any, ):Any):string | + | 146-146 | 1 | - |
| print | ((:Any, ):Any):void | + | 148-150 | 1 | - |
