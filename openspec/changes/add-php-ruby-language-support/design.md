# Design: Add PHP and Ruby Language Support

**Change ID:** `add-php-ruby-language-support`  
**Status:** Draft  
**Created:** 2025-11-10

---

## Overview

This design document outlines the architecture and implementation strategy for adding PHP and Ruby language support to Tree-sitter Analyzer. Both languages will follow the established plugin architecture pattern, maintaining consistency with existing language plugins (especially C#, Python, and JavaScript).

---

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Tree-sitter Analyzer                      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Language     │  │ Language     │  │ Language     │      │
│  │ Detector     │  │ Loader       │  │ Plugin       │      │
│  │              │  │              │  │ Manager      │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘              │
│                            │                                 │
│         ┌──────────────────┴──────────────────┐             │
│         │                                      │             │
│    ┌────▼────┐                          ┌─────▼────┐        │
│    │   PHP   │                          │  Ruby    │        │
│    │ Plugin  │                          │  Plugin  │        │
│    └────┬────┘                          └─────┬────┘        │
│         │                                      │             │
│    ┌────▼────────┐                      ┌─────▼──────────┐  │
│    │    PHP      │                      │     Ruby       │  │
│    │  Element    │                      │   Element      │  │
│    │  Extractor  │                      │   Extractor    │  │
│    └─────────────┘                      └────────────────┘  │
│         │                                      │             │
│         └──────────────────┬───────────────────┘             │
│                            │                                 │
│                     ┌──────▼──────┐                          │
│                     │   Unified   │                          │
│                     │   Element   │                          │
│                     │    Model    │                          │
│                     └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

#### 1. PHP Plugin (`PHPPlugin`)
- **Responsibility**: Provide PHP language support
- **Interface**: Implements `LanguagePlugin`
- **Dependencies**: `tree-sitter-php`
- **Lifecycle**: Managed by `PluginManager`

#### 2. Ruby Plugin (`RubyPlugin`)
- **Responsibility**: Provide Ruby language support
- **Interface**: Implements `LanguagePlugin`
- **Dependencies**: `tree-sitter-ruby`
- **Lifecycle**: Managed by `PluginManager`

#### 3. PHP Element Extractor (`PHPElementExtractor`)
- **Responsibility**: Extract PHP elements from AST
- **Interface**: Implements `ElementExtractor`
- **Output**: Unified element model (Class, Function, Variable, Import)

#### 4. Ruby Element Extractor (`RubyElementExtractor`)
- **Responsibility**: Extract Ruby elements from AST
- **Interface**: Implements `ElementExtractor`
- **Output**: Unified element model (Class, Function, Variable, Import)

---

## PHP Plugin Design

### PHP Element Mapping

| PHP Construct | Unified Element | Notes |
|---------------|-----------------|-------|
| `class` | `Class` | Full class support |
| `interface` | `Class` | `is_interface=True` |
| `trait` | `Class` | `is_trait=True` |
| `enum` (PHP 8.1+) | `Class` | `is_enum=True` |
| `function` | `Function` | Global and namespaced functions |
| `method` | `Function` | Class methods |
| `property` | `Variable` | Class properties |
| `constant` | `Variable` | `is_constant=True` |
| `use` statement | `Import` | Namespace imports |

### PHP-Specific Features

#### 1. Namespaces
```php
namespace App\Controllers;

use App\Models\User;
use function App\Helpers\helper_function;
use const App\Constants\MAX_SIZE;
```

**Handling:**
- Track current namespace context
- Generate fully qualified names
- Support multiple use statement types

#### 2. Traits
```php
trait Loggable {
    public function log($message) {
        // ...
    }
}

class User {
    use Loggable;
}
```

**Handling:**
- Extract traits as Class elements with `is_trait=True`
- Track trait usage in classes

#### 3. Attributes (PHP 8+)
```php
#[Route('/api/users')]
#[Authorize('admin')]
class UserController {
    #[HttpGet]
    public function index() {
        // ...
    }
}
```

**Handling:**
- Extract attributes as metadata
- Associate with parent element
- Store as `attributes` list

#### 4. Magic Methods
```php
class User {
    public function __construct() { }
    public function __get($name) { }
    public function __set($name, $value) { }
}
```

**Handling:**
- Detect magic methods by name pattern (`__*`)
- Mark as `is_magic_method=True`

#### 5. Typed Properties (PHP 7.4+)
```php
class User {
    public string $name;
    private ?int $age;
    public readonly DateTime $createdAt;
}
```

**Handling:**
- Extract type information
- Detect nullable types (`?`)
- Detect readonly modifier

---

## Ruby Plugin Design

### Ruby Element Mapping

| Ruby Construct | Unified Element | Notes |
|----------------|-----------------|-------|
| `class` | `Class` | Full class support |
| `module` | `Class` | `is_module=True` |
| `def` (instance method) | `Function` | Instance methods |
| `def self.` (class method) | `Function` | `is_class_method=True` |
| `attr_accessor` | `Function` | `is_property=True` |
| `attr_reader` | `Function` | `is_property=True, readonly=True` |
| `attr_writer` | `Function` | `is_property=True, writeonly=True` |
| `CONSTANT` | `Variable` | `is_constant=True` |
| `@instance_var` | `Variable` | `is_instance_variable=True` |
| `@@class_var` | `Variable` | `is_class_variable=True` |
| `$global_var` | `Variable` | `is_global=True` |
| `require` | `Import` | Module imports |

### Ruby-Specific Features

#### 1. Modules
```ruby
module Loggable
  def log(message)
    # ...
  end
end

class User
  include Loggable
  extend AnotherModule
  prepend YetAnotherModule
end
```

**Handling:**
- Extract modules as Class elements with `is_module=True`
- Track module inclusion (include, extend, prepend)

#### 2. Class Methods vs Instance Methods
```ruby
class User
  # Instance method
  def save
    # ...
  end
  
  # Class method (style 1)
  def self.find(id)
    # ...
  end
  
  # Class method (style 2)
  class << self
    def all
      # ...
    end
  end
end
```

**Handling:**
- Detect `self.` prefix for class methods
- Detect `class << self` blocks
- Mark with `is_class_method=True`

#### 3. Attribute Shortcuts
```ruby
class User
  attr_accessor :name, :email
  attr_reader :id
  attr_writer :password
end
```

**Handling:**
- Extract as Function elements with `is_property=True`
- Detect read/write permissions
- Generate getter/setter methods

#### 4. Blocks, Procs, and Lambdas
```ruby
users.each do |user|
  puts user.name
end

callback = Proc.new { |x| x * 2 }
multiply = ->(x) { x * 2 }
```

**Handling:**
- Detect block syntax (`do...end`, `{...}`)
- Detect proc and lambda declarations
- Mark as `is_block=True` or `is_lambda=True`

#### 5. Symbols and String Interpolation
```ruby
status = :active
message = "User #{user.name} is #{status}"
```

**Handling:**
- Handle symbols (`:symbol`) in AST
- Handle string interpolation (`#{}`)

---

## Shared Design Patterns

### 1. Plugin Structure

Both plugins follow the same structure:

```python
class PHPPlugin(LanguagePlugin):
    def get_language_name(self) -> str:
        return "php"
    
    def get_file_extensions(self) -> list[str]:
        return [".php"]
    
    def get_tree_sitter_language(self) -> Language:
        # Load and cache tree-sitter-php
        pass
    
    def create_extractor(self) -> ElementExtractor:
        return PHPElementExtractor()
    
    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        # Load file, parse, extract elements
        pass
```

### 2. Element Extractor Structure

Both extractors follow the same structure:

```python
class PHPElementExtractor(ElementExtractor):
    def __init__(self):
        self._reset_caches()
    
    def _reset_caches(self) -> None:
        self._text_cache: dict[int, str] = {}
        self._namespace_cache: dict[int, str] = {}
    
    def extract_classes(self, tree: Tree, source_code: str) -> list[Class]:
        # Extract classes, interfaces, traits, enums
        pass
    
    def extract_functions(self, tree: Tree, source_code: str) -> list[Function]:
        # Extract methods and functions
        pass
    
    def extract_variables(self, tree: Tree, source_code: str) -> list[Variable]:
        # Extract properties, constants, variables
        pass
    
    def extract_imports(self, tree: Tree, source_code: str) -> list[Import]:
        # Extract use/require statements
        pass
```

### 3. Caching Strategy

Both plugins use the same caching strategy:

```python
# Node text caching
def _get_node_text_optimized(self, node: Node, source_code: str) -> str:
    node_id = id(node)
    if node_id not in self._text_cache:
        self._text_cache[node_id] = source_code[node.start_byte:node.end_byte]
    return self._text_cache[node_id]

# Namespace caching
def _extract_namespace(self, node: Node, source_code: str) -> str:
    node_id = id(node)
    if node_id not in self._namespace_cache:
        # Extract namespace from parent nodes
        self._namespace_cache[node_id] = namespace
    return self._namespace_cache[node_id]
```

### 4. Error Handling

Both plugins use the same error handling pattern:

```python
async def analyze_file(
    self, file_path: str, request: AnalysisRequest
) -> AnalysisResult:
    try:
        # Load file with encoding detection
        content = await self._load_file_safe(file_path)
        
        # Parse with tree-sitter
        tree = parser.parse(content.encode('utf-8'))
        
        # Extract elements
        classes = self.extractor.extract_classes(tree, content)
        functions = self.extractor.extract_functions(tree, content)
        variables = self.extractor.extract_variables(tree, content)
        imports = self.extractor.extract_imports(tree, content)
        
        return AnalysisResult(
            language=self.get_language_name(),
            file_path=file_path,
            success=True,
            elements=classes + functions + variables + imports,
            node_count=self._count_nodes(tree.root_node)
        )
    except Exception as e:
        return AnalysisResult(
            language=self.get_language_name(),
            file_path=file_path,
            success=False,
            error=str(e)
        )
```

---

## Performance Considerations

### 1. Lazy Loading
- Tree-sitter languages are loaded on first use
- Cached for subsequent uses
- No performance impact on users who don't use PHP/Ruby

### 2. Iterative Traversal
- Use iterative tree traversal instead of recursive
- Avoid stack overflow on deeply nested code
- Better performance on large files

### 3. Caching
- Cache node text to avoid repeated string slicing
- Cache namespace context to avoid repeated traversal
- Clear caches after each file analysis

### 4. Parallel Processing
- PHP and Ruby plugins can be loaded in parallel
- File analysis is async-capable
- No blocking operations

---

## Testing Strategy

### 1. Unit Tests
- Test each extraction method independently
- Test edge cases (empty files, invalid syntax)
- Test language-specific features
- Mock tree-sitter for faster tests

### 2. Integration Tests
- Test full file analysis end-to-end
- Test CLI integration
- Test MCP integration
- Test format output

### 3. Golden Master Tests
- Create golden master files for sample code
- Test output consistency
- Test format correctness

### 4. Performance Tests
- Test large file handling
- Test memory usage
- Test parsing speed

---

## Migration Strategy

### Phase 1: Foundation (Day 1)
- Verify tree-sitter package availability
- Update dependencies
- No user impact

### Phase 2: PHP Implementation (Day 2-3)
- Implement PHP plugin
- PHP users can start using the feature
- No impact on existing users

### Phase 3: Ruby Implementation (Day 4-5)
- Implement Ruby plugin
- Ruby users can start using the feature
- No impact on existing users

### Phase 4: Testing (Day 6-7)
- Comprehensive testing
- Bug fixes
- Quality assurance

### Phase 5: Documentation (Day 8)
- Update documentation
- Release notes
- User guides

---

## Rollout Plan

### 1. Alpha Release (Internal Testing)
- Deploy to development environment
- Internal testing with real projects
- Gather feedback

### 2. Beta Release (Early Adopters)
- Deploy to beta users
- Monitor usage and errors
- Fix critical bugs

### 3. General Availability
- Deploy to all users
- Announce in release notes
- Update documentation

---

## Monitoring and Metrics

### Success Metrics
- Number of PHP files analyzed
- Number of Ruby files analyzed
- Average analysis time
- Error rate
- User adoption rate

### Monitoring
- Log plugin loading
- Log analysis errors
- Track performance metrics
- Monitor memory usage

---

## Risk Mitigation

### Risk 1: tree-sitter Package Incompatibility
**Mitigation:**
- Verify compatibility before implementation
- Test with multiple versions
- Document version requirements

### Risk 2: Complex Syntax Not Parsing
**Mitigation:**
- Create comprehensive test cases
- Test with real-world projects
- Iterative improvement

### Risk 3: Performance Issues
**Mitigation:**
- Optimize caching
- Use iterative traversal
- Profile and benchmark

### Risk 4: Breaking Existing Functionality
**Mitigation:**
- Complete isolation from other plugins
- Comprehensive regression testing
- Gradual rollout

---

## Future Enhancements

### PHP
- Laravel-specific pattern recognition
- WordPress hook/filter detection
- Composer dependency analysis
- PHPUnit test detection

### Ruby
- Rails-specific pattern recognition
- RSpec test pattern detection
- Gem dependency analysis
- Rake task detection

---

## References

- C# Plugin Implementation: `tree_sitter_analyzer/languages/csharp_plugin.py`
- Python Plugin Implementation: `tree_sitter_analyzer/languages/python_plugin.py`
- JavaScript Plugin Implementation: `tree_sitter_analyzer/languages/javascript_plugin.py`
- Plugin Architecture: `tree_sitter_analyzer/plugins/manager.py`
- Element Model: `tree_sitter_analyzer/models.py`

