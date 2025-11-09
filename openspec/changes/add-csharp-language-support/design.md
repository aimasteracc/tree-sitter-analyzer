# Design: C# Language Support

## Architecture Overview

This design document describes the architecture for adding C# language support to tree-sitter-analyzer, following the established plugin pattern used by other language plugins, with special attention to C#-specific features like properties, attributes, and modern C# syntax.

## Design Principles

1. **Consistency**: Follow existing plugin architecture patterns (Java, TypeScript, SQL)
2. **Type Safety**: Full mypy compliance with proper type annotations
3. **Code Quality**: Ruff compliance, no linting errors
4. **Testability**: Comprehensive test coverage (>80%)
5. **Maintainability**: Clear code structure following project conventions
6. **Isolation**: No impact on existing language plugins
7. **Extensibility**: Support for future C# feature additions
8. **SOLID Principles**: Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion

## Architecture Alignment

### Current Plugin Pattern

All language plugins follow this structure:

```
tree_sitter_analyzer/languages/
├── {language}_plugin.py
    ├── {Language}ElementExtractor(ElementExtractor)
    │   ├── extract_functions()
    │   ├── extract_classes()
    │   ├── extract_variables()
    │   └── extract_imports()
    └── {Language}Plugin(LanguagePlugin)
        ├── get_language_name()
        ├── get_file_extensions()
        ├── create_extractor()
        ├── get_tree_sitter_language()
        └── analyze_file()
```

### C# Plugin Structure

C# plugin will follow the same pattern:

```
tree_sitter_analyzer/languages/
└── csharp_plugin.py
    ├── CSharpElementExtractor(ElementExtractor)
    │   ├── extract_functions() → methods, constructors, properties
    │   ├── extract_classes() → classes, interfaces, records, enums
    │   ├── extract_variables() → fields, constants
    │   └── extract_imports() → using directives, namespace references
    └── CSharpPlugin(LanguagePlugin)
        ├── get_language_name() → "csharp"
        ├── get_file_extensions() → [".cs"]
        ├── create_extractor() → CSharpElementExtractor()
        ├── get_tree_sitter_language() → tree-sitter-c-sharp
        └── analyze_file() → standard analysis flow
```

## C# Element Mapping

### C# → Unified Element Model

C# has unique concepts that need careful mapping to the unified element model:

| C# Element | Maps To | Rationale |
|-----------|---------|-----------|
| class | Class | Direct mapping |
| interface | Class | Structural definition (class_type="interface") |
| struct | Class | Value type structural definition (class_type="struct") |
| record | Class | Immutable data class (class_type="record") |
| enum | Class | Enumeration type (class_type="enum") |
| delegate | Class | Function pointer type (class_type="delegate") |
| method | Function | Direct mapping |
| constructor | Function | Special method (is_constructor=True) |
| property | Function | Accessor method (is_property=True) |
| indexer | Function | Special accessor (is_indexer=True) |
| operator | Function | Operator overload (is_operator=True) |
| field | Variable | Direct mapping |
| const | Variable | Constant (is_constant=True) |
| event | Variable | Event field (is_event=True) |
| using directive | Import | Namespace import |
| namespace | Package | Namespace grouping |
| attribute | Annotation | Metadata (similar to Java annotations) |

### Element Extraction Strategy

#### Classes (extract_classes)

```csharp
namespace MyApp.Models
{
    [Serializable]
    public class User : IUser, IEquatable<User>
    {
        public int Id { get; set; }
        public string Name { get; set; }
    }
}
```

**Extraction**:
- Element Type: `Class`
- Name: `User`
- Full Qualified Name: `MyApp.Models.User`
- Start/End Line: From class declaration
- Raw Text: Full class definition
- Superclass: None (C# doesn't show base class in this example)
- Interfaces: `["IUser", "IEquatable<User>"]`
- Modifiers: `["public"]`
- Visibility: `"public"`
- Attributes: `[{"name": "Serializable", "line": X, "text": "[Serializable]"}]`
- Class Type: `"class"`

#### Methods (extract_functions)

```csharp
[HttpGet]
public async Task<ActionResult<User>> GetUser(int id)
{
    var user = await _context.Users.FindAsync(id);
    return user;
}
```

**Extraction**:
- Element Type: `Function`
- Name: `GetUser`
- Start/End Line: From method declaration
- Raw Text: Full method definition
- Parameters: `["int id"]`
- Return Type: `"Task<ActionResult<User>>"`
- Modifiers: `["public", "async"]`
- Visibility: `"public"`
- Is Async: `True`
- Attributes: `[{"name": "HttpGet", "line": X, "text": "[HttpGet]"}]`
- Complexity Score: Calculated based on control flow

#### Properties (extract_functions)

```csharp
public string Name { get; set; }

public int Age 
{ 
    get => _age; 
    set => _age = value > 0 ? value : 0; 
}
```

**Extraction**:
- Element Type: `Function`
- Name: `Name` or `Age`
- Start/End Line: From property declaration
- Raw Text: Full property definition
- Return Type: `"string"` or `"int"`
- Modifiers: `["public"]`
- Visibility: `"public"`
- Is Property: `True`
- Has Getter: `True`
- Has Setter: `True`

#### Fields (extract_variables)

```csharp
private readonly ILogger<UserController> _logger;
public const int MaxUsers = 1000;
```

**Extraction**:
- Element Type: `Variable`
- Name: `_logger` or `MaxUsers`
- Start/End Line: From field declaration
- Raw Text: Full field definition
- Variable Type: `"ILogger<UserController>"` or `"int"`
- Modifiers: `["private", "readonly"]` or `["public", "const"]`
- Visibility: `"private"` or `"public"`
- Is Constant: `False` or `True`
- Is Readonly: `True` or `False`

#### Using Directives (extract_imports)

```csharp
using System;
using System.Collections.Generic;
using Microsoft.AspNetCore.Mvc;
```

**Extraction**:
- Element Type: `Import`
- Name: `System`, `System.Collections.Generic`, `Microsoft.AspNetCore.Mvc`
- Start/End Line: From using directive
- Raw Text: Full using statement
- Module Name: Same as name
- Import Type: `"using"`

#### Records (extract_classes)

```csharp
public record Person(string FirstName, string LastName);
```

**Extraction**:
- Element Type: `Class`
- Name: `Person`
- Start/End Line: From record declaration
- Raw Text: Full record definition
- Class Type: `"record"`
- Modifiers: `["public"]`
- Visibility: `"public"`
- Properties: Extracted as separate Function elements

## Tree-sitter C# Grammar

### Node Types (Expected)

Based on tree-sitter-c-sharp grammar, we expect these node types:

- `compilation_unit` - Root node
- `namespace_declaration` - Namespace definitions
- `using_directive` - Using statements
- `class_declaration` - Class definitions
- `interface_declaration` - Interface definitions
- `struct_declaration` - Struct definitions
- `record_declaration` - Record definitions (C# 9+)
- `enum_declaration` - Enum definitions
- `delegate_declaration` - Delegate definitions
- `method_declaration` - Method definitions
- `constructor_declaration` - Constructor definitions
- `property_declaration` - Property definitions
- `field_declaration` - Field definitions
- `event_declaration` - Event definitions
- `indexer_declaration` - Indexer definitions
- `operator_declaration` - Operator overloads
- `attribute_list` - Attributes (C# annotations)
- `parameter_list` - Method parameters
- `type_parameter_list` - Generic type parameters

### Query Patterns

C#-specific queries for common patterns:

```python
# Find all classes
"classes": """
(class_declaration
  name: (identifier) @name) @class
"""

# Find all methods
"methods": """
(method_declaration
  name: (identifier) @name) @method
"""

# Find all properties
"properties": """
(property_declaration
  name: (identifier) @name) @property
"""

# Find all interfaces
"interfaces": """
(interface_declaration
  name: (identifier) @name) @interface
"""

# Find all attributes
"attributes": """
(attribute_list) @attribute
"""
```

## Implementation Details

### C# Plugin Class

```python
class CSharpPlugin(LanguagePlugin):
    """C# language plugin implementation"""
    
    def __init__(self) -> None:
        super().__init__()
        self.extractor = CSharpElementExtractor()
        self.language = "csharp"
        self.supported_extensions = [".cs"]
        self._cached_language: Any | None = None
    
    def get_language_name(self) -> str:
        return "csharp"
    
    def get_file_extensions(self) -> list[str]:
        return [".cs"]
    
    def create_extractor(self) -> ElementExtractor:
        return CSharpElementExtractor()
    
    def get_tree_sitter_language(self) -> Any | None:
        """Load tree-sitter-c-sharp language"""
        if self._cached_language is not None:
            return self._cached_language
        
        try:
            import tree_sitter
            import tree_sitter_c_sharp
            
            lang = tree_sitter_c_sharp.language()
            if hasattr(lang, "__class__") and "Language" in str(type(lang)):
                self._cached_language = lang
            else:
                self._cached_language = tree_sitter.Language(lang)
            
            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-c-sharp not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for C#: {e}")
            return None
```

### C# Element Extractor

```python
class CSharpElementExtractor(ElementExtractor):
    """C#-specific element extractor"""
    
    def __init__(self) -> None:
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.current_namespace: str = ""
        
        # Performance optimization caches
        self._node_text_cache: dict[int, str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        self._file_encoding: str | None = None
        self._attribute_cache: dict[int, list[dict[str, Any]]] = {}
    
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """Extract methods, constructors, and properties"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        
        functions: list[Function] = []
        
        if tree is not None and tree.root_node is not None:
            # Extract methods
            self._extract_methods(tree.root_node, functions)
            # Extract constructors
            self._extract_constructors(tree.root_node, functions)
            # Extract properties
            self._extract_properties(tree.root_node, functions)
        
        return functions
    
    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """Extract classes, interfaces, records, enums, structs"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        
        classes: list[Class] = []
        
        if tree is not None and tree.root_node is not None:
            # Extract namespace first
            self._extract_namespace(tree.root_node)
            # Extract classes
            self._extract_csharp_classes(tree.root_node, classes)
            # Extract interfaces
            self._extract_interfaces(tree.root_node, classes)
            # Extract records
            self._extract_records(tree.root_node, classes)
            # Extract enums
            self._extract_enums(tree.root_node, classes)
            # Extract structs
            self._extract_structs(tree.root_node, classes)
        
        return classes
    
    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """Extract fields, constants, events"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._reset_caches()
        
        variables: list[Variable] = []
        
        if tree is not None and tree.root_node is not None:
            # Extract fields
            self._extract_fields(tree.root_node, variables)
        
        return variables
    
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """Extract using directives"""
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        
        imports: list[Import] = []
        
        if tree is not None and tree.root_node is not None:
            # Extract using directives
            self._extract_using_directives(tree.root_node, imports)
        
        return imports
```

## C#-Specific Features

### Attributes (Annotations)

C# attributes are similar to Java annotations and should be extracted and associated with their target elements:

```csharp
[HttpGet]
[Authorize(Roles = "Admin")]
public async Task<IActionResult> GetUsers()
{
    // ...
}
```

**Extraction Strategy**:
- Parse `attribute_list` nodes
- Extract attribute name and arguments
- Associate with following class/method/property
- Store in `annotations` field (consistent with Java)

### Properties

C# properties are first-class language features (not just getter/setter methods):

```csharp
// Auto-property
public string Name { get; set; }

// Computed property
public string FullName => $"{FirstName} {LastName}";

// Property with backing field
private int _age;
public int Age 
{ 
    get => _age; 
    set => _age = value > 0 ? value : 0; 
}
```

**Extraction Strategy**:
- Treat properties as special functions (`is_property=True`)
- Extract getter/setter presence
- Distinguish auto-properties from computed properties
- Include property type as return type

### Async/Await

C# has first-class async/await support:

```csharp
public async Task<User> GetUserAsync(int id)
{
    return await _context.Users.FindAsync(id);
}
```

**Extraction Strategy**:
- Detect `async` modifier
- Set `is_async=True`
- Extract return type (including `Task<T>`)

### Records (C# 9+)

Records are immutable data classes:

```csharp
public record Person(string FirstName, string LastName);

public record Employee : Person
{
    public int EmployeeId { get; init; }
}
```

**Extraction Strategy**:
- Treat as special class type (`class_type="record"`)
- Extract primary constructor parameters as properties
- Support record inheritance

### Nullable Reference Types (C# 8+)

C# 8+ supports nullable reference types:

```csharp
public string? NullableName { get; set; }
public string NonNullableName { get; set; }
```

**Extraction Strategy**:
- Preserve `?` in type annotations
- Include in type information

## Error Handling

### Missing tree-sitter-c-sharp

If `tree-sitter-c-sharp` is not installed:
- Plugin should load but return `None` from `get_tree_sitter_language()`
- Analysis should fail gracefully with clear error message
- Tests should handle optional dependency

### Unsupported C# Version

- Focus on modern C# (C# 8+)
- Older syntax should still parse correctly
- Log warnings for unrecognized syntax
- Don't fail entire analysis for partial failures

### Partial Classes

C# supports partial classes across multiple files:
- Extract each partial class separately
- Mark as partial in metadata
- Don't attempt to merge across files (out of scope)

## Testing Strategy

### Unit Tests

1. **Plugin Loading**
   - Test plugin instantiation
   - Test language name and extensions
   - Test tree-sitter language loading

2. **Element Extraction**
   - Test class extraction
   - Test method extraction
   - Test property extraction
   - Test field extraction
   - Test interface extraction
   - Test record extraction
   - Test enum extraction
   - Test using directive extraction

3. **C#-Specific Features**
   - Test attribute extraction
   - Test async method detection
   - Test property types (auto, computed, backing field)
   - Test generic types
   - Test nullable reference types

4. **Edge Cases**
   - Empty C# files
   - Invalid C# syntax
   - Large C# files
   - Nested classes
   - Partial classes

### Integration Tests

1. **CLI Integration**
   - Test `analyze` command with C# file
   - Test format output (Full, Compact, CSV)

2. **API Integration**
   - Test `analyze_file()` with C#
   - Test element extraction results

3. **MCP Integration**
   - Test MCP tools with C# files
   - Test query execution

### Sample Files

Create comprehensive sample C# files:

1. **Sample.cs** - Basic C# features
   - Classes, methods, properties, fields
   - Using directives, namespaces

2. **SampleAdvanced.cs** - Advanced features
   - Async/await, LINQ
   - Attributes, generics
   - Records, nullable reference types

3. **SampleASPNET.cs** - ASP.NET Core patterns
   - Controllers, actions
   - Dependency injection
   - HTTP attributes

## Performance Considerations

- C# files can be large (enterprise applications)
- Use streaming file reading (already implemented in analysis engine)
- Cache parsed AST for repeated analysis
- Optimize element extraction for large files
- Use iterative traversal (not recursive) to avoid stack overflow

## Future Enhancements

1. **LINQ Query Analysis**
   - Extract LINQ queries
   - Analyze query complexity
   - Identify query patterns

2. **Dependency Injection Analysis**
   - Detect DI patterns
   - Extract service registrations
   - Analyze dependency graphs

3. **ASP.NET Core-Specific Features**
   - Controller analysis
   - Middleware detection
   - Route analysis

4. **Unity-Specific Features**
   - MonoBehaviour detection
   - Unity attributes
   - Coroutine analysis

5. **Pattern Matching Analysis**
   - Extract pattern matching expressions
   - Analyze pattern complexity

## Dependencies

### Required

- `tree-sitter-c-sharp`: C# grammar for tree-sitter
- `tree-sitter>=0.25.0`: Core tree-sitter library (already required)

### Optional

- Add C# to optional dependencies group in `pyproject.toml`
- Allow installation with: `pip install tree-sitter-analyzer[csharp]`

## Migration Path

No migration needed - this is a new feature addition with no breaking changes.

## SOLID Principles Application

### Single Responsibility Principle (SRP)
- `CSharpPlugin` handles only C# language integration
- `CSharpElementExtractor` handles only C# element extraction
- Each extraction method handles one element type

### Open/Closed Principle (OCP)
- Plugin is open for extension (can add new extraction methods)
- Plugin is closed for modification (doesn't change existing plugins)

### Liskov Substitution Principle (LSP)
- `CSharpPlugin` can substitute `LanguagePlugin` without breaking behavior
- `CSharpElementExtractor` can substitute `ElementExtractor` without breaking behavior

### Interface Segregation Principle (ISP)
- Plugin implements only required `LanguagePlugin` interface methods
- No unnecessary dependencies on other plugins

### Dependency Inversion Principle (DIP)
- Plugin depends on abstract `LanguagePlugin` interface
- Plugin doesn't depend on concrete implementations
- Uses dependency injection for tree-sitter language loading

## Isolation Guarantee

To ensure C# support doesn't affect other languages:

1. **No Shared State**: C# plugin has its own state, no global variables
2. **No Cross-Plugin Dependencies**: C# plugin doesn't import other language plugins
3. **Independent Testing**: C# tests don't depend on other language tests
4. **Optional Dependency**: tree-sitter-c-sharp is optional, doesn't affect other languages
5. **Plugin Manager Isolation**: Plugin manager loads plugins independently
6. **No API Changes**: No changes to existing interfaces or base classes

## Quality Assurance

- ✅ 100% mypy compliance
- ✅ 100% ruff compliance
- ✅ >80% test coverage
- ✅ All tests pass
- ✅ No regression in existing tests
- ✅ Documentation complete
- ✅ Sample files provided

