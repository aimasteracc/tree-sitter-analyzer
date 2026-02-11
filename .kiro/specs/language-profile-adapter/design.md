# S6: LanguageProfile Unified Adapter — Design

## Architecture

```
LanguageProfile (data)     GenericLanguageParser (engine)
┌─────────────────────┐    ┌──────────────────────────┐
│ name: "go"          │───>│ parse(source, profile)   │
│ extensions: [".go"] │    │   _extract_functions()   │
│ function_types: ... │    │   _extract_classes()     │
│ class_types: ...    │    │   _extract_imports()     │
│ import_types: ...   │    │   _extract_metadata()    │
└─────────────────────┘    └──────────────────────────┘
```

## LanguageProfile Dataclass

```python
@dataclass(frozen=True)
class LanguageProfile:
    """Data-driven language configuration for the generic parser."""

    # Identity
    name: str                          # "go", "rust", "c"
    extensions: tuple[str, ...]        # (".go",), (".rs",), (".c", ".h")
    tree_sitter_name: str              # tree-sitter language name

    # AST Node Type Mappings
    function_node_types: tuple[str, ...] = ()    # ("function_declaration",)
    class_node_types: tuple[str, ...] = ()       # ("type_declaration",) for Go
    method_node_types: tuple[str, ...] = ()      # ("method_declaration",)
    import_node_types: tuple[str, ...] = ()      # ("import_declaration",)
    
    # Field names in AST (how to find name, params, body, etc.)
    name_field: str = "name"           # child field for identifier
    params_field: str = "parameters"   # child field for parameters
    body_field: str = "body"           # child field for function body
    return_type_field: str = "result"  # child field for return type
    
    # Visibility/modifier detection
    visibility_node_type: str = ""             # e.g., "visibility_modifier"
    public_keywords: tuple[str, ...] = ()      # ("public", "pub", "export")
    default_visibility: str = "public"         # default when not specified
    
    # Import extraction helpers
    import_path_field: str = "path"            # how to find import path
    
    # Comment/docstring
    comment_node_types: tuple[str, ...] = ("comment",)
    docstring_position: str = "before"         # "before" or "first_child"
    
    # Language-specific features
    has_interfaces: bool = False
    has_packages: bool = False
    has_decorators: bool = False
    has_async: bool = False
    async_keyword: str = "async"
```

## GenericLanguageParser

A single parser class that uses `LanguageProfile` to extract code elements:

```python
class GenericLanguageParser:
    def __init__(self, profile: LanguageProfile) -> None:
        self._profile = profile
        self._parser = TreeSitterParser(profile.tree_sitter_name)
    
    def parse(self, source_code: str, file_path: str = "") -> LanguageParseResult:
        parse_result = self._parser.parse(source_code, file_path)
        return {
            "ast": parse_result.tree,
            "functions": self._extract_functions(parse_result.tree),
            "classes": self._extract_classes(parse_result.tree),
            "imports": self._extract_imports(parse_result.tree),
            "metadata": self._extract_metadata(parse_result.tree, source_code),
            "errors": parse_result.has_errors,
        }
```

## Pre-defined Profiles

### Go Profile
```python
GO_PROFILE = LanguageProfile(
    name="go",
    extensions=(".go",),
    tree_sitter_name="go",
    function_node_types=("function_declaration",),
    method_node_types=("method_declaration",),
    class_node_types=("type_declaration",),    # struct types
    import_node_types=("import_declaration",),
    name_field="name",
    params_field="parameters",
    body_field="body",
    return_type_field="result",
    has_packages=True,
    has_interfaces=True,
    default_visibility="public",  # Go: capitalized = public
)
```

### Rust Profile
```python
RUST_PROFILE = LanguageProfile(
    name="rust",
    extensions=(".rs",),
    tree_sitter_name="rust",
    function_node_types=("function_item",),
    method_node_types=("function_item",),  # inside impl block
    class_node_types=("struct_item", "enum_item"),
    import_node_types=("use_declaration",),
    name_field="name",
    params_field="parameters",
    body_field="body",
    return_type_field="return_type",
    public_keywords=("pub",),
    default_visibility="private",
    has_interfaces=True,   # traits
)
```

### C Profile
```python
C_PROFILE = LanguageProfile(
    name="c",
    extensions=(".c", ".h"),
    tree_sitter_name="c",
    function_node_types=("function_definition",),
    class_node_types=("struct_specifier", "enum_specifier"),
    import_node_types=("preproc_include",),
    name_field="declarator",
    params_field="parameters",
    body_field="body",
    default_visibility="public",
)
```

## Registration & Integration

1. `LanguageProfile` instances registered in `LanguageRegistry`
2. `SupportedLanguage` enum extended dynamically (or replaced)
3. `TreeSitterParser._load_language()` extended to load new languages
4. Backward compatibility: Python/Java/TypeScript parsers kept as-is (they have extra features)

## File Layout

```
v2/tree_sitter_analyzer_v2/
├── core/
│   └── types.py         # Add LanguageProfile dataclass
├── languages/
│   ├── profiles.py      # All LanguageProfile instances
│   ├── generic_parser.py # GenericLanguageParser
│   ├── python_parser.py  # (keep, backward compat)
│   ├── java_parser.py    # (keep, backward compat)
│   └── typescript_parser.py # (keep, backward compat)
```

## Migration Path

Phase 1: Create LanguageProfile + GenericLanguageParser
Phase 2: Add Go/Rust/C using profiles
Phase 3: (Future) Optionally migrate Py/Java/TS to profiles
