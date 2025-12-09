# sample.c

## Imports
```c
#include <stdio.h>
#include <stdlib.h>
#include "local_header.h"
```

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| Color | enum | public | 24-24 | 0 | 0 |
| Status | enum | public | 27-31 | 0 | 0 |
| Point | struct | public | 34-37 | 0 | 2 |
| Rectangle | struct | public | 40-43 | 0 | 2 |
| Number | union | public | 46-50 | 0 | 3 |
| Person | struct | public | 53-56 | 0 | 2 |

## Color (24-24)
## Status (27-31)
## Point (34-37)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| x | int | + |  | 35 | - |
| y | int | + |  | 36 | - |

## Rectangle (40-43)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| top_left | struct Point | + |  | 41 | - |
| bottom_right | struct Point | + |  | 42 | - |

## Number (46-50)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| i | int | + |  | 47 | - |
| f | float | + |  | 48 | - |
| d | double | + |  | 49 | - |

## Person (53-56)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| name | char[] | + |  | 54 | - |
| age | int | + |  | 55 | - |

## Global Functions
| Method | Signature | Vis | Lines | Cols | Cx | Doc |
|--------|-----------|-----|-------|------|----|----|
| SQUARE | (param:x):macro | + | 12-13 | 5-6 | 1 | - |
| add | (a:int, b:int):int | + | 86-88 | 5-6 | 1 | - |
| multiply | (a:int, b:int):int [static] | + | 91-93 | 5-6 | 1 | - |
| process_array | (arr:int[], len:size_t):void | + | 96-100 | 5-6 | 2 | - |
| compare_ints | (a:const void*, b:const void*):int | + | 103-105 | 5-6 | 1 | - |
| find_max | (arr:int*, len:size_t):int* | + | 108-117 | 5-6 | 4 | - |
| calculate_distance | (p1:struct Point, p2:struct Point):double | + | 120-124 | 5-6 | 1 | - |
| sort_with_comparator | (arr:int[], len:size_t, cmp:Comparator):void | + | 127-129 | 5-6 | 1 | - |
| main | (param:void):int | + | 135-161 | 5-6 | 1 | - |

## Global Variables
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| MAX_SIZE | macro | + | const,macro | 11 | - |
| DEBUG | macro | + | const,macro | 13 | - |
| global_value | int | + |  | 63 | - |
| static_value | int | - | static | 64 | - |
| CONSTANT_VALUE | int | + | const | 65 | - |
| external_value | int | + | extern | 66 | - |