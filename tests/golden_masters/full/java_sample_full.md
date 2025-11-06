# Sample

## Package
`com.example`

## Imports
```java
java.util.List
java.util.ArrayList
```

## Classes Overview
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| AbstractParentClass | class | package | 7-15 | 2 | 0 |
| ParentClass | class | package | 18-45 | 4 | 2 |
| TestInterface | interface | package | 48-64 | 3 | 0 |
| AnotherInterface | interface | package | 67-69 | 1 | 0 |
| Test | class | public | 72-159 | 12 | 3 |
| InnerClass | class | public | 83-87 | 1 | 0 |
| StaticNestedClass | class | public | 90-94 | 1 | 0 |
| TestEnum | enum | package | 162-178 | 2 | 1 |

## AbstractParentClass (7-15)
### Package Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| abstractMethod | ():void | ~ | 9-9 | 1 | - |
| concreteMethod | ():void | ~ | 12-14 | 1 | - |

## ParentClass (18-45)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| CONSTANT | String | ~ | static,final | 20 | - |
| parentField | String | # | protected | 23 | - |

### Constructors
| Constructor | Signature | Vis | Lines | Cx | Doc |
|-------------|-----------|-----|-------|----|----|
| ParentClass | ():void | + | 26-28 | 1 | - |

### Package Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| staticParentMethod | ():void [static] | ~ | 31-33 | 1 | - |
| abstractMethod | ():void | ~ | 36-39 | 1 | - |
| parentMethod | ():void | ~ | 42-44 | 1 | - |

## TestInterface (48-64)
### Package Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| doSomething | ():void | ~ | 53-53 | 1 | - |
| defaultMethod | ():void | ~ | 56-58 | 1 | - |
| staticInterfaceMethod | ():void [static] | ~ | 61-63 | 1 | - |

## AnotherInterface (67-69)
### Package Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| anotherMethod | ():void | ~ | 68-68 | 1 | - |

## Test (72-159)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| value | int | - | private | 74 | - |
| staticValue | int | + | public,static | 77 | - |
| finalField | String | - | private,final | 80 | - |

### Constructors
| Constructor | Signature | Vis | Lines | Cx | Doc |
|-------------|-----------|-----|-------|----|----|
| Test | (value:int):void | + | 97-100 | 1 | - |
| Test | ():void | + | 103-105 | 1 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| getValue | ():String | + | 108-110 | 1 | - |
| staticMethod | ():void [static] | + | 128-130 | 1 | - |
| finalMethod | ():void | + | 133-135 | 1 | - |
| doSomething | ():void | + | 138-141 | 1 | - |
| anotherMethod | ():void | + | 143-146 | 1 | - |
| genericMethod | (input:T):void | + | 149-151 | 1 | - |
| createList | (item:T):List<T> | + | 154-158 | 1 | - |

### Protected Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| setValue | (value:int):void | # | 113-115 | 1 | - |

### Package Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| packageMethod | ():void | ~ | 118-120 | 1 | - |

### Private Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| privateMethod | ():void | - | 123-125 | 1 | - |

## InnerClass (83-87)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| innerMethod | ():void | + | 84-86 | 1 | - |

## StaticNestedClass (90-94)
### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| nestedMethod | ():void | + | 91-93 | 1 | - |

## TestEnum (162-178)
### Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| description | String | - | private,final | 167 | - |

### Constructors
| Constructor | Signature | Vis | Lines | Cx | Doc |
|-------------|-----------|-----|-------|----|----|
| TestEnum | (description:String):void | ~ | 170-172 | 1 | - |

### Public Methods
| Method | Signature | Vis | Lines | Cx | Doc |
|--------|-----------|-----|-------|----|----|
| getDescription | ():String | + | 175-177 | 1 | - |
