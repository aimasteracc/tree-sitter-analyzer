#!/usr/bin/env python3
"""
Java Language Queries

Tree-sitter queries specific to Java language constructs.
Covers classes, methods, annotations, imports, and other Java-specific elements.
"""

# Java-specific query library
JAVA_QUERIES: dict[str, str] = {
    # --- Basic Structure ---
    "class": """
    (class_declaration) @class
    """,
    "interface": """
    (interface_declaration) @interface
    """,
    "enum": """
    (enum_declaration) @enum
    """,
    "annotation_type": """
    (annotation_type_declaration) @annotation_type
    """,
    # --- Methods and Constructors ---
    "method": """
    (method_declaration) @method
    """,
    "constructor": """
    (constructor_declaration) @constructor
    """,
    "abstract_method": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "abstract")) @abstract_method
    """,
    # --- Fields and Variables ---
    "field": """
    (field_declaration) @field
    """,
    "static_field": """
    (field_declaration
      (modifiers) @mod
      (#match? @mod "static")) @static_field
    """,
    "final_field": """
    (field_declaration
      (modifiers) @mod
      (#match? @mod "final")) @final_field
    """,
    # --- Imports and Packages ---
    "import": """
    (import_declaration) @import
    """,
    "static_import": """
    (import_declaration
      "static") @static_import
    """,
    "package": """
    (package_declaration) @package
    """,
    # --- Annotations ---
    "annotation": """
    (annotation) @annotation
    """,
    "marker_annotation": """
    (marker_annotation) @marker_annotation
    """,
    "annotation_with_params": """
    (annotation
      (annotation_argument_list)) @annotation_with_params
    """,
    # --- Java-specific Constructs ---
    "lambda": """
    (lambda_expression) @lambda
    """,
    "try_catch": """
    (try_statement) @try_catch
    """,
    "synchronized_block": """
    (synchronized_statement) @synchronized_block
    """,
    "generic_type": """
    (generic_type) @generic_type
    """,
    # --- Name-only Extraction ---
    "class_name": """
    (class_declaration
      name: (identifier) @class_name)
    """,
    "method_name": """
    (method_declaration
      name: (identifier) @method_name)
    """,
    "field_name": """
    (field_declaration
      declarator: (variable_declarator
        name: (identifier) @field_name))
    """,
    # --- Detailed Queries ---
    "class_with_body": """
    (class_declaration
      name: (identifier) @name
      body: (class_body) @body) @class_with_body
    """,
    "method_with_body": """
    (method_declaration
      name: (identifier) @name
      body: (block) @body) @method_with_body
    """,
    # Fixed: Match methods WITH annotations (at least one required)
    # Uses alternation [(annotation) (marker_annotation)] to match both types:
    # - marker_annotation: Annotations without parameters (e.g., @Override)
    # - annotation: Annotations with parameters (e.g., @SuppressWarnings("unchecked"))
    # The + quantifier requires at least one annotation
    "method_with_annotations": """
    (method_declaration
      (modifiers
        [(annotation) (marker_annotation)]+ @annotation)
      name: (identifier) @name) @method
    """,
    # --- Inheritance Relations ---
    "extends_clause": """
    (class_declaration
      (superclass) @extends_clause)
    """,
    "implements_clause": """
    (class_declaration
      (super_interfaces) @implements_clause)
    """,
    # --- By Modifiers ---
    "public_methods": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "public")
      name: (identifier) @name) @public_methods
    """,
    "private_methods": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "private")
      name: (identifier) @name) @private_methods
    """,
    "static_methods": """
    (method_declaration
      (modifiers) @mod
      (#match? @mod "static")
      name: (identifier) @name) @static_methods
    """,
    # --- Spring Framework Annotations ---
    # NOTE: Java annotations with no arguments are "marker_annotation" nodes in
    # tree-sitter (e.g. @Controller, @Entity, @Bean). Annotations WITH arguments
    # are "annotation" nodes (e.g. @Table(name="x")).  We must match BOTH.
    # The (#match? ...) predicate is applied manually by _execute_newest_api()
    # because tree-sitter-python 0.25+ QueryCursor does not apply it automatically.
    "spring_controller": """
    ((class_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @controller_name) @spring_controller
     (#match? @annotation_name "^(Controller|RestController)$"))
    """,
    "spring_service": """
    ((class_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @service_name) @spring_service
     (#match? @annotation_name "^Service$"))
    """,
    "spring_repository": """
    ((class_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @repository_name) @spring_repository
     (#match? @annotation_name "^Repository$"))
    """,
    # --- JPA Annotations ---
    "jpa_entity": """
    ((class_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @entity_name) @jpa_entity
     (#match? @annotation_name "^Entity$"))
    """,
    "jpa_id_field": """
    ((field_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      declarator: (variable_declarator
        name: (identifier) @field_name)) @jpa_id_field
     (#match? @annotation_name "^Id$"))
    """,
    # --- Structural Information Extraction Queries ---
    "javadoc_comment": """
    (block_comment) @javadoc_comment
    (#match? @javadoc_comment "^/\\\\\\\\\\\\*\\\\\\\\\\\\*")
    """,
    "class_with_javadoc": """
    (class_declaration
      name: (identifier) @class_name
      body: (class_body) @class_body) @class_with_javadoc
    """,
    "method_with_javadoc": """
    (method_declaration
      name: (identifier) @method_name
      parameters: (formal_parameters) @parameters
      body: (block) @method_body) @method_with_javadoc
    """,
    "field_with_javadoc": """
    (field_declaration
      type: (_) @field_type
      declarator: (variable_declarator
        name: (identifier) @field_name)) @field_with_javadoc
    """,
    "method_parameters_detailed": """
    (method_declaration
      name: (identifier) @method_name
      parameters: (formal_parameters
        (formal_parameter
          type: (_) @param_type
          name: (identifier) @param_name)*) @parameters) @method_parameters_detailed
    """,
    "class_inheritance_detailed": """
    (class_declaration
      name: (identifier) @class_name
      (superclass
        (type_identifier) @extends_class)?
      (super_interfaces
        (interface_type_list
          (type_identifier) @implements_interface)*)?
      body: (class_body) @class_body) @class_inheritance_detailed
    """,
    "annotation_detailed": """
    (annotation
      name: (identifier) @annotation_name
      (annotation_argument_list
        (element_value_pair
          key: (identifier) @param_key
          value: (_) @param_value)*)?
      ) @annotation_detailed
    """,
    "import_detailed": """
    (import_declaration
      "static"? @static_modifier
      (scoped_identifier) @import_path) @import_detailed
    """,
    "package_detailed": """
    (package_declaration
      (scoped_identifier) @package_name) @package_detailed
    """,
    "constructor_detailed": """
    (constructor_declaration
      name: (identifier) @constructor_name
      parameters: (formal_parameters) @parameters
      body: (constructor_body) @constructor_body) @constructor_detailed
    """,
    "enum_constant": """
    (enum_declaration
      body: (enum_body
        (enum_constant
          name: (identifier) @constant_name)*)) @enum_constant
    """,
    "interface_method": """
    (interface_declaration
      body: (interface_body
        (method_declaration
          name: (identifier) @method_name
          parameters: (formal_parameters) @parameters)*)) @interface_method
    """,
    # --- Java 16+ Language Features ---
    "record_declaration": """
    (record_declaration
      name: (identifier) @record_name) @record_declaration
    """,
    "sealed_class": """
    (class_declaration
      name: (identifier) @class_name) @sealed_class
    """,
    # --- Spring Framework: Configuration & Beans ---
    "spring_bean": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @spring_bean
     (#match? @annotation_name "^Bean$"))
    """,
    "spring_configuration": """
    ((class_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @class_name) @spring_configuration
     (#match? @annotation_name "^Configuration$"))
    """,
    "spring_component": """
    ((class_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @class_name) @spring_component
     (#match? @annotation_name "^Component$"))
    """,
    "spring_transactional": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @spring_transactional
     (#match? @annotation_name "^Transactional$"))
    """,
    "spring_autowired": """
    ((field_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      declarator: (variable_declarator name: (identifier) @field_name)) @spring_autowired
     (#match? @annotation_name "^Autowired$"))
    """,
    "spring_request_mapping": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @spring_request_mapping
     (#match? @annotation_name "^(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)$"))
    """,
    "spring_event_listener": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @spring_event_listener
     (#match? @annotation_name "^EventListener$"))
    """,
    "spring_scheduled": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @spring_scheduled
     (#match? @annotation_name "^Scheduled$"))
    """,
    # --- Testing Queries ---
    "junit5_test": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @junit5_test
     (#match? @annotation_name "^Test$"))
    """,
    "junit5_lifecycle": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @junit5_lifecycle
     (#match? @annotation_name "^(BeforeEach|AfterEach|BeforeAll|AfterAll)$"))
    """,
    "parameterized_test": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @parameterized_test
     (#match? @annotation_name "^ParameterizedTest$"))
    """,
    # --- Concurrency Queries ---
    "volatile_field": """
    (field_declaration
      (modifiers "volatile") @modifier
      declarator: (variable_declarator
        name: (identifier) @field_name)) @volatile_field
    """,
    "spring_async": """
    ((method_declaration
      (modifiers
        [(marker_annotation name: (identifier) @annotation_name)
         (annotation name: (identifier) @annotation_name)])
      name: (identifier) @method_name) @spring_async
     (#match? @annotation_name "^Async$"))
    """,
    "synchronized_method": """
    (method_declaration
      (modifiers "synchronized") @modifier
      name: (identifier) @method_name) @synchronized_method
    """,
    # --- Exception Handling ---
    "throws_declaration": """
    (method_declaration
      (throws
        (type_identifier) @exception_type)
      name: (identifier) @method_name) @throws_declaration
    """,
}

# Query descriptions
JAVA_QUERY_DESCRIPTIONS: dict[str, str] = {
    "class": "Extract Java class declarations",
    "interface": "Extract Java interface declarations",
    "enum": "Extract Java enum declarations",
    "annotation_type": "Extract Java annotation type declarations",
    "method": "Extract Java method declarations",
    "constructor": "Extract Java constructor declarations",
    "field": "Extract Java field declarations",
    "import": "Extract Java import statements",
    "package": "Extract Java package declarations",
    "annotation": "Extract Java annotations",
    "lambda": "Extract Java lambda expressions",
    "try_catch": "Extract Java try-catch statements",
    "class_name": "Extract class names only",
    "method_name": "Extract method names only",
    "field_name": "Extract field names only",
    "class_with_body": "Extract class declarations with body",
    "method_with_body": "Extract method declarations with body",
    "extends_clause": "Extract class inheritance clauses",
    "implements_clause": "Extract class implementation clauses",
    "public_methods": "Extract public methods",
    "private_methods": "Extract private methods",
    "static_methods": "Extract static methods",
    # Structural information extraction query descriptions
    "javadoc_comment": "Extract JavaDoc comments",
    "class_with_javadoc": "Extract classes with JavaDoc",
    "method_with_javadoc": "Extract methods with JavaDoc",
    "field_with_javadoc": "Extract fields with JavaDoc",
    "method_parameters_detailed": "Extract detailed method parameter information",
    "class_inheritance_detailed": "Extract detailed class inheritance relationships",
    "annotation_detailed": "Extract detailed annotation information",
    "import_detailed": "Extract detailed import statement information",
    "package_detailed": "Extract detailed package declaration information",
    "constructor_detailed": "Extract detailed constructor information",
    "enum_constant": "Extract enum constants",
    "interface_method": "Extract interface methods",
    "spring_controller": "Extract Spring Controller classes",
    "spring_service": "Extract Spring Service classes",
    "spring_repository": "Extract Spring Repository classes",
    "jpa_entity": "Extract JPA Entity classes",
    "abstract_method": "Extract abstract methods",
    "static_field": "Extract static fields",
    "final_field": "Extract final fields",
    "static_import": "Extract static import statements",
    "marker_annotation": "Extract marker annotations",
    "annotation_with_params": "Extract annotations with parameters",
    "synchronized_block": "Extract synchronized statements",
    "generic_type": "Extract generic types",
    "method_with_annotations": "Extract methods with annotations",
    "jpa_id_field": "Extract JPA ID fields",
    "record_declaration": "Extract Java 16+ record declarations",
    "sealed_class": "Extract Java 17+ sealed class declarations",
    "spring_bean": "Extract @Bean annotated methods in @Configuration classes",
    "spring_configuration": "Extract @Configuration annotated classes",
    "spring_component": "Extract @Component annotated classes",
    "spring_transactional": "Extract @Transactional annotated methods",
    "spring_autowired": "Extract @Autowired injection points (fields)",
    "spring_request_mapping": "Extract HTTP mapping annotated methods (@GetMapping, @PostMapping, etc.)",
    "spring_event_listener": "Extract @EventListener annotated methods",
    "spring_scheduled": "Extract @Scheduled annotated methods",
    "junit5_test": "Extract @Test annotated JUnit 5 test methods",
    "junit5_lifecycle": "Extract JUnit 5 lifecycle methods (@BeforeEach, @AfterEach, etc.)",
    "parameterized_test": "Extract @ParameterizedTest annotated methods",
    "volatile_field": "Extract volatile field declarations",
    "spring_async": "Extract @Async annotated methods",
    "synchronized_method": "Extract synchronized method declarations",
    "throws_declaration": "Extract methods with throws clauses",
}


def get_java_query(name: str) -> str:
    """
    Get the specified Java query

    Args:
        name: Query name

    Returns:
        Query string

    Raises:
        ValueError: When query is not found
    """
    if name not in JAVA_QUERIES:
        available = list(JAVA_QUERIES.keys())
        raise ValueError(f"Java query '{name}' does not exist. Available: {available}")

    return JAVA_QUERIES[name]


def get_java_query_description(name: str) -> str:
    """
    Get the description of the specified Java query

    Args:
        name: Query name

    Returns:
        Query description
    """
    return JAVA_QUERY_DESCRIPTIONS.get(name, "No description")


# Convert to ALL_QUERIES format for dynamic loader compatibility
ALL_QUERIES = {}
for query_name, query_string in JAVA_QUERIES.items():
    description = JAVA_QUERY_DESCRIPTIONS.get(query_name, "No description")
    ALL_QUERIES[query_name] = {"query": query_string, "description": description}

# Add common query aliases for cross-language compatibility
ALL_QUERIES["functions"] = {
    "query": JAVA_QUERIES["method"],
    "description": "Search all function/method declarations (alias for method)",
}

ALL_QUERIES["methods"] = {
    "query": JAVA_QUERIES["method"],
    "description": "Search all method declarations (alias for method)",
}

ALL_QUERIES["classes"] = {
    "query": JAVA_QUERIES["class"],
    "description": "Search all class declarations (alias for class)",
}


def get_query(name: str) -> str:
    """Get a specific query by name."""
    if name in ALL_QUERIES:
        return ALL_QUERIES[name]["query"]
    raise ValueError(
        f"Query '{name}' not found. Available queries: {list(ALL_QUERIES.keys())}"
    )


def get_all_queries() -> dict[str, dict[str, str]]:
    """Get all available queries."""
    return ALL_QUERIES


def list_queries() -> list[str]:
    """List all available query names."""
    return list(ALL_QUERIES.keys())


def get_available_java_queries() -> list[str]:
    """
    Get list of available Java queries

    Returns:
        List of query names
    """
    return list(JAVA_QUERIES.keys())
