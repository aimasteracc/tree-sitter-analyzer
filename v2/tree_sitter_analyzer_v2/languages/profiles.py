"""
Pre-defined LanguageProfile instances for data-driven parsing.

Each profile configures GenericLanguageParser to extract functions, classes,
and imports from a specific language without writing a dedicated parser class.
"""

from tree_sitter_analyzer_v2.core.types import LanguageProfile


# ── Go ──

GO_PROFILE = LanguageProfile(
    name="go",
    extensions=(".go",),
    tree_sitter_name="go",
    function_node_types=("function_declaration",),
    method_node_types=("method_declaration",),
    class_node_types=("type_declaration",),
    import_node_types=("import_declaration", "import_spec"),
    name_field="name",
    params_field="parameters",
    body_field="body",
    return_type_field="result",
    has_packages=True,
    has_interfaces=True,
    interface_node_types=(),  # Go interfaces are inside type_declaration
    package_node_type="package_clause",
    default_visibility="public",  # Go: capitalized = public
)


# ── Rust ──

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
    has_interfaces=True,
    interface_node_types=("trait_item",),
    has_async=True,
    async_keyword="async",
)


# ── C ──

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
    comment_node_types=("comment",),
)


# ── C++ ──

CPP_PROFILE = LanguageProfile(
    name="cpp",
    extensions=(".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"),
    tree_sitter_name="cpp",
    function_node_types=("function_definition",),
    method_node_types=("function_definition",),  # inside class body
    class_node_types=("class_specifier", "struct_specifier"),
    import_node_types=("preproc_include",),
    name_field="declarator",
    params_field="parameters",
    body_field="body",
    public_keywords=("public",),
    default_visibility="private",  # C++ default is private
    has_interfaces=False,
    comment_node_types=("comment",),
)


# ── Kotlin ──

KOTLIN_PROFILE = LanguageProfile(
    name="kotlin",
    extensions=(".kt", ".kts"),
    tree_sitter_name="kotlin",
    function_node_types=("function_declaration",),
    method_node_types=("function_declaration",),  # inside class_body
    class_node_types=("class_declaration",),
    import_node_types=("import",),  # import_header node type is 'import'
    name_field="identifier",
    params_field="function_value_parameters",
    body_field="function_body",
    return_type_field="user_type",
    has_packages=True,
    package_node_type="package_header",
    has_interfaces=True,
    interface_node_types=("class_declaration",),  # Kotlin uses class_declaration for interfaces too
    default_visibility="public",
)


# ── PHP ──

PHP_PROFILE = LanguageProfile(
    name="php",
    extensions=(".php",),
    tree_sitter_name="php",
    function_node_types=("function_definition",),
    method_node_types=("method_declaration",),
    class_node_types=("class_declaration",),
    import_node_types=("namespace_use_declaration",),
    name_field="name",
    params_field="formal_parameters",
    body_field="compound_statement",
    public_keywords=("public",),
    default_visibility="public",
    has_interfaces=True,
    interface_node_types=("interface_declaration",),
)


# ── Ruby ──

RUBY_PROFILE = LanguageProfile(
    name="ruby",
    extensions=(".rb",),
    tree_sitter_name="ruby",
    function_node_types=("method",),
    method_node_types=("method",),
    class_node_types=("class",),
    import_node_types=(),  # Ruby uses require/require_relative (call nodes)
    name_field="identifier",
    params_field="method_parameters",
    body_field="body_statement",
    default_visibility="public",
    has_interfaces=False,  # Ruby uses modules/mixins instead
)


# ── Registry of all profile-driven languages ──

ALL_PROFILES: dict[str, LanguageProfile] = {
    "go": GO_PROFILE,
    "rust": RUST_PROFILE,
    "c": C_PROFILE,
    "cpp": CPP_PROFILE,
    "kotlin": KOTLIN_PROFILE,
    "php": PHP_PROFILE,
    "ruby": RUBY_PROFILE,
}


def get_profile(language: str) -> LanguageProfile | None:
    """Get a language profile by name."""
    return ALL_PROFILES.get(language.lower())


def get_profile_by_extension(ext: str) -> LanguageProfile | None:
    """Get a language profile by file extension."""
    ext_lower = ext.lower()
    for profile in ALL_PROFILES.values():
        if ext_lower in profile.extensions:
            return profile
    return None
