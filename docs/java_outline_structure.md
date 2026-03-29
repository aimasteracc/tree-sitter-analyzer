# Java 文件代码大纲 - 完整结构示例

## 测试文件: Sample.java

这是一个包含多种 Java 特性的示例文件：
- 抽象类和继承
- 接口和实现
- 内部类和静态嵌套类
- 枚举类型
- 字段（private/public/protected）
- 方法（构造函数/静态方法/默认方法）

---

## 📦 完整返回结构 (JSON)

```json
{
  "success": true,
  "outline": {
    "file_path": "C:\\git-private\\tree-sitter-analyzer\\examples\\Sample.java",
    "language": "java",
    "total_lines": 179,
    "package": "com.example",
    "classes": [
      {
        "name": "AbstractParentClass",
        "type": "class",
        "line_start": 7,
        "line_end": 15,
        "extends": null,
        "implements": [],
        "methods": [
          {
            "name": "abstractMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 9,
            "line_end": 9
          },
          {
            "name": "concreteMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 12,
            "line_end": 14
          }
        ],
        "fields": []
      },
      {
        "name": "ParentClass",
        "type": "class",
        "line_start": 18,
        "line_end": 45,
        "extends": "AbstractParentClass",
        "implements": [],
        "methods": [
          {
            "name": "ParentClass",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": true,
            "is_static": false,
            "line_start": 26,
            "line_end": 28
          },
          {
            "name": "staticParentMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": true,
            "line_start": 31,
            "line_end": 33
          },
          {
            "name": "abstractMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 36,
            "line_end": 39
          },
          {
            "name": "parentMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 42,
            "line_end": 44
          }
        ],
        "fields": [
          {
            "name": "CONSTANT",
            "type": "String",
            "visibility": "package",
            "is_static": true,
            "line_start": 20,
            "line_end": 20
          },
          {
            "name": "parentField",
            "type": "String",
            "visibility": "protected",
            "is_static": false,
            "line_start": 23,
            "line_end": 23
          }
        ]
      },
      {
        "name": "TestInterface",
        "type": "interface",
        "line_start": 48,
        "line_end": 64,
        "extends": null,
        "implements": [],
        "methods": [
          {
            "name": "doSomething",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 53,
            "line_end": 53
          },
          {
            "name": "defaultMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 56,
            "line_end": 58
          },
          {
            "name": "staticInterfaceMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": true,
            "line_start": 61,
            "line_end": 63
          }
        ],
        "fields": []
      },
      {
        "name": "AnotherInterface",
        "type": "interface",
        "line_start": 67,
        "line_end": 69,
        "extends": null,
        "implements": [],
        "methods": [
          {
            "name": "anotherMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 68,
            "line_end": 68
          }
        ],
        "fields": []
      },
      {
        "name": "Test",
        "type": "class",
        "line_start": 72,
        "line_end": 159,
        "extends": "ParentClass",
        "implements": [
          "TestInterface",
          "AnotherInterface"
        ],
        "methods": [
          {
            "name": "innerMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 84,
            "line_end": 86
          },
          {
            "name": "nestedMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 91,
            "line_end": 93
          },
          {
            "name": "Test",
            "return_type": "void",
            "parameters": [
              "int value"
            ],
            "visibility": "public",
            "is_constructor": true,
            "is_static": false,
            "line_start": 97,
            "line_end": 100
          },
          {
            "name": "Test",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": true,
            "is_static": false,
            "line_start": 103,
            "line_end": 105
          },
          {
            "name": "getValue",
            "return_type": "String",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 108,
            "line_end": 110
          },
          {
            "name": "setValue",
            "return_type": "void",
            "parameters": [
              "int value"
            ],
            "visibility": "protected",
            "is_constructor": false,
            "is_static": false,
            "line_start": 113,
            "line_end": 115
          },
          {
            "name": "packageMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "package",
            "is_constructor": false,
            "is_static": false,
            "line_start": 118,
            "line_end": 120
          },
          {
            "name": "privateMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "private",
            "is_constructor": false,
            "is_static": false,
            "line_start": 123,
            "line_end": 125
          },
          {
            "name": "staticMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": true,
            "line_start": 128,
            "line_end": 130
          },
          {
            "name": "finalMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 133,
            "line_end": 135
          },
          {
            "name": "doSomething",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 138,
            "line_end": 141
          },
          {
            "name": "anotherMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 143,
            "line_end": 146
          },
          {
            "name": "genericMethod",
            "return_type": "void",
            "parameters": [
              "T input"
            ],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 149,
            "line_end": 151
          },
          {
            "name": "createList",
            "return_type": "List<T>",
            "parameters": [
              "T item"
            ],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 154,
            "line_end": 158
          }
        ],
        "fields": [
          {
            "name": "value",
            "type": "int",
            "visibility": "private",
            "is_static": false,
            "line_start": 74,
            "line_end": 74
          },
          {
            "name": "staticValue",
            "type": "int",
            "visibility": "public",
            "is_static": true,
            "line_start": 77,
            "line_end": 77
          },
          {
            "name": "finalField",
            "type": "String",
            "visibility": "private",
            "is_static": false,
            "line_start": 80,
            "line_end": 80
          }
        ]
      },
      {
        "name": "InnerClass",
        "type": "class",
        "line_start": 83,
        "line_end": 87,
        "extends": null,
        "implements": [],
        "methods": [
          {
            "name": "innerMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 84,
            "line_end": 86
          }
        ],
        "fields": []
      },
      {
        "name": "StaticNestedClass",
        "type": "class",
        "line_start": 90,
        "line_end": 94,
        "extends": null,
        "implements": [],
        "methods": [
          {
            "name": "nestedMethod",
            "return_type": "void",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 91,
            "line_end": 93
          }
        ],
        "fields": []
      },
      {
        "name": "TestEnum",
        "type": "enum",
        "line_start": 162,
        "line_end": 178,
        "extends": null,
        "implements": [],
        "methods": [
          {
            "name": "TestEnum",
            "return_type": "void",
            "parameters": [
              "String description"
            ],
            "visibility": "package",
            "is_constructor": true,
            "is_static": false,
            "line_start": 170,
            "line_end": 172
          },
          {
            "name": "getDescription",
            "return_type": "String",
            "parameters": [],
            "visibility": "public",
            "is_constructor": false,
            "is_static": false,
            "line_start": 175,
            "line_end": 177
          }
        ],
        "fields": [
          {
            "name": "description",
            "type": "String",
            "visibility": "private",
            "is_static": false,
            "line_start": 167,
            "line_end": 167
          }
        ]
      }
    ],
    "top_level_functions": [],
    "statistics": {
      "class_count": 8,
      "method_count": 26,
      "field_count": 6,
      "import_count": 2
    },
    "imports": [
      "import java.util.List;",
      "import java.util.ArrayList;"
    ]
  }
}
```

---

## 📋 结构说明

### 顶层字段

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `success` | boolean | 是否成功 | `True` |
| `outline.file_path` | string | 文件完整路径 | `C:\git-private\tree-sitter-analyzer\examples\Sample.java` |
| `outline.language` | string | 编程语言 | `java` |
| `outline.total_lines` | int | 总行数 | `179` |
| `outline.package` | string/null | Java 包名 | `com.example` |

### 统计信息 (statistics)

| 指标 | 值 |
|------|-----|
| 类数量 | 8 |
| 方法数量 | 26 |
| 字段数量 | 6 |
| 导入数量 | 2 |

### 类结构 (classes)

每个类包含以下字段：

**示例：`ParentClass` 类**

```json
{
  "name": "ParentClass",
  "type": "class",
  "line_start": 18,
  "line_end": 45,
  "extends": "AbstractParentClass",
  "implements": [],
  "methods": [
    {
      "name": "ParentClass",
      "return_type": "void",
      "parameters": [],
      "visibility": "public",
      "is_constructor": true,
      "is_static": false,
      "line_start": 26,
      "line_end": 28
    },
    {
      "name": "staticParentMethod",
      "return_type": "void",
      "parameters": [],
      "visibility": "package",
      "is_constructor": false,
      "is_static": true,
      "line_start": 31,
      "line_end": 33
    },
    {
      "name": "abstractMethod",
      "return_type": "void",
      "parameters": [],
      "visibility": "package",
      "is_constructor": false,
      "is_static": false,
      "line_start": 36,
      "line_end": 39
    },
    {
      "name": "parentMethod",
      "return_type": "void",
      "parameters": [],
      "visibility": "package",
      "is_constructor": false,
      "is_static": false,
      "line_start": 42,
      "line_end": 44
    }
  ],
  "fields": [
    {
      "name": "CONSTANT",
      "type": "String",
      "visibility": "package",
      "is_static": true,
      "line_start": 20,
      "line_end": 20
    },
    {
      "name": "parentField",
      "type": "String",
      "visibility": "protected",
      "is_static": false,
      "line_start": 23,
      "line_end": 23
    }
  ]
}
```

**类级别字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 类名 |
| `type` | string | 固定值 "class" |
| `line_start` | int | 起始行号 |
| `line_end` | int | 结束行号 |
| `extends` | string/null | 父类名称 |
| `implements` | array | 实现的接口列表 |
| `fields` | array | 字段列表 |
| `methods` | array | 方法列表 |

**字段 (Field) 结构：**

```json
{
  "name": "CONSTANT",
  "type": "String",
  "visibility": "package",
  "is_static": true,
  "line_start": 20,
  "line_end": 20
}
```

| 字段 | 类型 | 说明 | 可能值 |
|------|------|------|--------|
| `name` | string | 字段名 | - |
| `type` | string | 字段类型 | `String`, `int`, `List<T>` 等 |
| `visibility` | string | 可见性 | `private`, `public`, `protected`, `package` |
| `line_start` | int | 字段声明行号 | - |

**方法 (Method) 结构：**

```json
{
  "name": "ParentClass",
  "return_type": "void",
  "parameters": [],
  "visibility": "public",
  "is_constructor": true,
  "is_static": false,
  "line_start": 26,
  "line_end": 28
}
```

| 字段 | 类型 | 说明 | 可能值 |
|------|------|------|--------|
| `name` | string | 方法名 | - |
| `return_type` | string | 返回类型 | `void`, `String`, `int` 等 |
| `parameters` | array | 参数列表 | `["int value", "String name"]` |
| `visibility` | string | 可见性 | `private`, `public`, `protected`, `package` |
| `is_static` | boolean | 是否静态 | `true`/`false` |
| `is_constructor` | boolean/null | 是否构造函数 | `true`/`false`/`null` |
| `line_start` | int | 方法起始行 | - |
| `line_end` | int | 方法结束行 | - |

---

## 🎯 关键特性

### 1. Package 识别
自动提取 Java package 声明：`com.example`

### 2. 导入语句
提取所有 import 语句（可选）：
- `import java.util.List;`
- `import java.util.ArrayList;`

### 3. 继承和接口
识别 extends 和 implements 关系：
- `ParentClass` extends `AbstractParentClass` implements ``
- `Test` extends `ParentClass` implements `TestInterface, AnotherInterface`

### 4. 可见性修饰符
准确识别 private/public/protected/package（默认）：
发现的修饰符：`package, private, protected, public`

### 5. 静态成员
识别 static 方法和字段

### 6. 内部类和嵌套类
检测到内部/嵌套类：`InnerClass, StaticNestedClass`
