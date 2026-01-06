#!/usr/bin/env python3
"""
Data Models for Multi-Language Code Analysis

Data classes for representing code structures extracted through
Tree-sitter analysis across multiple programming languages.
"""

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from .constants import (
    ELEMENT_TYPE_ANNOTATION,
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)

if TYPE_CHECKING:
    pass


# Use dataclass with slots for Python 3.10+
def dataclass_with_slots(*args: Any, **kwargs: Any) -> Any:
    return dataclass(*args, slots=True, **kwargs)


# ========================================
# Base Generic Models (Language Agnostic)
# ========================================


@dataclass(frozen=False)
class CodeElement(ABC):
    """Base class for all code elements"""

    name: str
    start_line: int
    end_line: int
    raw_text: str = ""
    language: str = "unknown"
    docstring: str | None = None  # JavaDoc/docstring for this element
    element_type: str = "unknown"

    def to_summary_item(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.element_type,
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class Function(CodeElement):
    """Generic function/method representation"""

    parameters: list[str] = field(default_factory=list)
    return_type: str | None = None
    modifiers: list[str] = field(default_factory=list)
    is_async: bool = False
    is_static: bool = False
    is_private: bool = False
    is_public: bool = True
    is_constant: bool = False
    visibility: str = "public"
    is_suspend: bool | None = None  # Kotlin
    receiver: str | None = None  # Go
    receiver_type: str | None = None  # Go
    is_constructor: bool | None = None  # Java
    element_type: str = "function"
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    throws: list[str] = field(default_factory=list)
    complexity_score: int = 1
    is_abstract: bool = False
    is_final: bool = False
    # JavaScript-specific fields
    is_generator: bool = False
    is_arrow: bool = False
    is_method: bool = False
    framework_type: str | None = None
    # Python-specific fields
    is_property: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False


@dataclass(frozen=False)
class Class(CodeElement):
    """Generic class representation"""

    class_type: str = "class"
    full_qualified_name: str | None = None
    package_name: str | None = None
    superclass: str | None = None
    interfaces: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    visibility: str = "public"
    element_type: str = "class"
    methods: list[Function] = field(default_factory=list)
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    is_nested: bool = False
    parent_class: str | None = None
    extends_class: str | None = None  # Alias for superclass
    implements_interfaces: list[str] = field(
        default_factory=list
    )  # Alias for interfaces
    # JavaScript-specific fields
    is_react_component: bool = False
    framework_type: str | None = None
    is_exported: bool = False
    # Python-specific fields
    is_dataclass: bool = False
    is_abstract: bool = False
    is_exception: bool = False


@dataclass(frozen=False)
class Variable(CodeElement):
    """Generic variable representation"""

    variable_type: str | None = None
    modifiers: list[str] = field(default_factory=list)
    is_constant: bool = False
    is_static: bool = False
    visibility: str = "private"
    element_type: str = "variable"
    is_val: bool | None = None  # Kotlin
    is_var: bool | None = None  # Kotlin
    initializer: str | None = None
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    is_final: bool = False
    is_readonly: bool = False  # PHP 8.1+ readonly property
    field_type: str | None = None  # Alias for variable_type


@dataclass(frozen=False)
class Import(CodeElement):
    """Generic import statement representation"""

    module_name: str = ""
    module_path: str = ""  # Add module_path for compatibility with plugins
    imported_names: list[str] = field(default_factory=list)
    is_wildcard: bool = False
    is_static: bool = False
    element_type: str = "import"
    alias: str | None = None
    # Java-specific fields for detailed analysis
    imported_name: str = ""  # Alias for name
    import_statement: str = ""  # Full import statement
    line_number: int = 0  # Line number for compatibility


@dataclass(frozen=False)
class Package(CodeElement):
    """Generic package declaration representation"""

    element_type: str = "package"


# ========================================
# HTML/CSS-Specific Models
# ========================================


@dataclass(frozen=False)
class MarkupElement(CodeElement):
    """
    HTML要素を表現するデータモデル。
    CodeElementを継承し、マークアップ固有の属性を追加する。
    """

    tag_name: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    parent: "MarkupElement | None" = None
    children: list["MarkupElement"] = field(default_factory=list)
    element_class: str = ""  # 分類システムのカテゴリ (例: 'structure', 'media', 'form')
    element_type: str = "html_element"

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "tag_name": self.tag_name,
            "type": "html_element",
            "element_class": self.element_class,
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class StyleElement(CodeElement):
    """
    CSSルールを表現するデータモデル。
    CodeElementを継承する。
    """

    selector: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    element_class: str = (
        ""  # 分類システムのカテゴリ (例: 'layout', 'typography', 'color')
    )
    element_type: str = "css_rule"

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "selector": self.selector,
            "type": "css_rule",
            "element_class": self.element_class,
            "lines": {"start": self.start_line, "end": self.end_line},
        }


# ========================================
# Java-Specific Models
# ========================================


@dataclass(frozen=False)
class JavaAnnotation:
    """Java annotation representation"""

    name: str
    parameters: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    raw_text: str = ""

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "type": "annotation",
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class JavaMethod:
    """Java method representation with comprehensive details"""

    name: str
    return_type: str | None = None
    parameters: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    visibility: str = "package"
    annotations: list[JavaAnnotation] = field(default_factory=list)
    throws: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    is_constructor: bool = False
    is_abstract: bool = False
    is_static: bool = False
    is_final: bool = False
    complexity_score: int = 1
    file_path: str = ""

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "type": "method",
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class JavaClass:
    """Java class representation with comprehensive details"""

    name: str
    full_qualified_name: str = ""
    package_name: str = ""
    class_type: str = "class"
    modifiers: list[str] = field(default_factory=list)
    visibility: str = "package"
    extends_class: str | None = None
    implements_interfaces: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    annotations: list[JavaAnnotation] = field(default_factory=list)
    is_nested: bool = False
    parent_class: str | None = None
    file_path: str = ""

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "type": "class",
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class JavaField:
    """Java field representation"""

    name: str
    field_type: str = ""
    modifiers: list[str] = field(default_factory=list)
    visibility: str = "package"
    annotations: list[JavaAnnotation] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    is_static: bool = False
    is_final: bool = False
    file_path: str = ""

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "type": "field",
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class JavaImport:
    """Java import statement representation"""

    name: str
    module_name: str = ""  # Add module_name for compatibility
    imported_name: str = ""  # Add imported_name for compatibility
    import_statement: str = ""  # Add import_statement for compatibility
    line_number: int = 0  # Add line_number for compatibility
    is_static: bool = False
    is_wildcard: bool = False
    start_line: int = 0
    end_line: int = 0

    def to_summary_item(self) -> dict[str, Any]:
        """要約アイテムとして辞書を返す"""
        return {
            "name": self.name,
            "type": "import",
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class JavaPackage:
    """Java package declaration representation"""

    name: str
    start_line: int = 0
    end_line: int = 0

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item"""
        return {
            "name": self.name,
            "type": "package",
            "lines": {"start": self.start_line, "end": self.end_line},
        }


@dataclass(frozen=False)
class AnalysisResult:
    """Comprehensive analysis result container"""

    file_path: str
    language: str = "unknown"  # Add language field for new architecture compatibility
    line_count: int = 0  # Add line_count for compatibility
    elements: Sequence[CodeElement] = field(
        default_factory=list
    )  # Generic elements for new architecture
    node_count: int = 0  # Node count for new architecture
    query_results: dict[str, Any] = field(
        default_factory=dict
    )  # Query results for new architecture
    source_code: str = ""  # Source code for new architecture
    package: JavaPackage | None = None
    # Legacy fields removed - use elements list instead
    # imports: list[JavaImport] = field(default_factory=list)
    # classes: list[JavaClass] = field(default_factory=list)
    # methods: list[JavaMethod] = field(default_factory=list)
    # fields: list[JavaField] = field(default_factory=list)
    # annotations: list[JavaAnnotation] = field(default_factory=list)
    analysis_time: float = 0.0
    success: bool = True
    error_message: str | None = None

    # Additional language-specific data
    throws: list[str] | None = None
    complexity_score: int | None = None

    # Language-specific attributes
    is_suspend: bool | None = None  # Kotlin
    receiver: str | None = None  # Go
    receiver_type: str | None = None  # Go
    is_constructor: bool | None = None  # Java
    modules: list[Any] | None = None
    impls: list[Any] | None = None
    goroutines: list[Any] | None = None
    channels: list[Any] | None = None
    defers: list[Any] | None = None

    def __post_init__(self) -> None:
        pass

    def to_dict(self) -> dict[str, Any]:
        """Convert analysis result to dictionary for serialization using unified elements"""
        # Use unified elements list for consistent data structure
        elements = self.elements or []

        # Single pass grouping for better performance
        from .constants import (
            ELEMENT_TYPE_ANNOTATION,
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
            ELEMENT_TYPE_IMPORT,
            ELEMENT_TYPE_VARIABLE,
            get_element_type,
        )

        grouped: dict[str, list[CodeElement]] = {
            ELEMENT_TYPE_CLASS: [],
            ELEMENT_TYPE_FUNCTION: [],
            ELEMENT_TYPE_VARIABLE: [],
            ELEMENT_TYPE_IMPORT: [],
            ELEMENT_TYPE_PACKAGE: [],
            ELEMENT_TYPE_ANNOTATION: [],
        }

        for e in elements:
            etype = get_element_type(e)
            if etype in grouped:
                grouped[etype].append(e)

        classes = grouped[ELEMENT_TYPE_CLASS]
        methods = grouped[ELEMENT_TYPE_FUNCTION]
        fields = grouped[ELEMENT_TYPE_VARIABLE]
        imports = grouped[ELEMENT_TYPE_IMPORT]
        packages = grouped[ELEMENT_TYPE_PACKAGE]

        return {
            "file_path": self.file_path,
            "line_count": self.line_count,
            "package": {"name": packages[0].name} if packages else None,
            "imports": [
                {
                    "name": imp.name,
                    "is_static": getattr(imp, "is_static", False),
                    "is_wildcard": getattr(imp, "is_wildcard", False),
                }
                for imp in imports
            ],
            "classes": [
                {
                    "name": cls.name,
                    "type": getattr(cls, "class_type", "class"),
                    "package": getattr(cls, "package_name", None),
                }
                for cls in classes
            ],
            "methods": [
                {
                    "name": method.name,
                    "return_type": getattr(method, "return_type", None),
                    "parameters": getattr(method, "parameters", []),
                }
                for method in methods
            ],
            "fields": [
                {"name": field.name, "type": getattr(field, "field_type", None)}
                for field in fields
            ],
            "annotations": [
                {"name": getattr(ann, "name", str(ann))}
                for ann in (
                    grouped[ELEMENT_TYPE_ANNOTATION] or getattr(self, "annotations", [])
                )
            ],
            "analysis_time": self.analysis_time,
            "success": self.success,
            "error_message": self.error_message,
        }

    def to_summary_dict(self, types: list[str] | None = None) -> dict[str, Any]:
        """
        Return analysis summary as a dictionary using unified elements.
        Only include specified element types (e.g., 'classes', 'methods', 'fields').
        """
        if types is None:
            types = ["classes", "methods"]  # default

        summary: dict[str, Any] = {"file_path": self.file_path, "summary_elements": []}
        elements = self.elements or []

        # Map type names to element_type constants
        type_mapping = {
            "imports": ELEMENT_TYPE_IMPORT,
            "classes": ELEMENT_TYPE_CLASS,
            "methods": ELEMENT_TYPE_FUNCTION,
            "fields": ELEMENT_TYPE_VARIABLE,
            "annotations": ELEMENT_TYPE_ANNOTATION,
        }

        # Select relevant types based on input
        target_types = set()
        if "all" in types:
            target_types = set(type_mapping.values())
        else:
            for t in types:
                if t in type_mapping:
                    target_types.add(type_mapping[t])

        # Single pass filtering
        from .constants import get_element_type

        for element in elements:
            if get_element_type(element) in target_types:
                summary["summary_elements"].append(element.to_summary_item())

        return summary

    def get_summary(self) -> dict[str, Any]:
        """Get analysis summary statistics using unified elements"""
        elements = self.elements or []

        # Count elements by type from unified list using constants
        classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
        methods = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)]
        fields = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
        imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
        annotations = [
            e for e in elements if is_element_of_type(e, ELEMENT_TYPE_ANNOTATION)
        ]

        return {
            "file_path": self.file_path,
            "line_count": self.line_count,
            "class_count": len(classes),
            "method_count": len(methods),
            "field_count": len(fields),
            "import_count": len(imports),
            "annotation_count": len(annotations),
            "success": self.success,
            "analysis_time": self.analysis_time,
        }

    def to_mcp_format(self) -> dict[str, Any]:
        """
        Produce output in MCP-compatible format

        Returns:
            MCP-style result dictionary
        """
        # packageの安全な処理
        package_info = None
        if self.package:
            if hasattr(self.package, "name"):
                package_info = {"name": self.package.name}
            elif isinstance(self.package, dict):
                package_info = self.package
            else:
                package_info = {"name": str(self.package)}

        # 安全なアイテム処理ヘルパー関数
        def safe_get_attr(obj: Any, attr: str, default: Any = "") -> Any:
            if hasattr(obj, attr):
                return getattr(obj, attr)
            elif isinstance(obj, dict):
                return obj.get(attr, default)
            else:
                return default

        return {
            "file_path": self.file_path,
            "structure": {
                "package": package_info,
                "imports": [
                    {
                        "name": safe_get_attr(imp, "name"),
                        "is_static": safe_get_attr(imp, "is_static", False),
                        "is_wildcard": safe_get_attr(imp, "is_wildcard", False),
                        "line_range": {
                            "start": safe_get_attr(imp, "start_line", 0),
                            "end": safe_get_attr(imp, "end_line", 0),
                        },
                    }
                    for imp in [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
                    ]
                ],
                "classes": [
                    {
                        "name": safe_get_attr(cls, "name"),
                        "type": safe_get_attr(cls, "class_type"),
                        "package": safe_get_attr(cls, "package_name"),
                        "line_range": {
                            "start": safe_get_attr(cls, "start_line", 0),
                            "end": safe_get_attr(cls, "end_line", 0),
                        },
                    }
                    for cls in [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_CLASS)
                    ]
                ],
                "methods": [
                    {
                        "name": safe_get_attr(method, "name"),
                        "return_type": safe_get_attr(method, "return_type"),
                        "parameters": safe_get_attr(method, "parameters", []),
                        "line_range": {
                            "start": safe_get_attr(method, "start_line", 0),
                            "end": safe_get_attr(method, "end_line", 0),
                        },
                    }
                    for method in [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
                    ]
                ],
                "fields": [
                    {
                        "name": safe_get_attr(field, "name"),
                        "type": safe_get_attr(field, "field_type"),
                        "line_range": {
                            "start": safe_get_attr(field, "start_line", 0),
                            "end": safe_get_attr(field, "end_line", 0),
                        },
                    }
                    for field in [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
                    ]
                ],
                "annotations": [
                    {
                        "name": safe_get_attr(ann, "name"),
                        "line_range": {
                            "start": safe_get_attr(ann, "start_line", 0),
                            "end": safe_get_attr(ann, "end_line", 0),
                        },
                    }
                    for ann in [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_ANNOTATION)
                    ]
                ],
            },
            "metadata": {
                "line_count": self.line_count,
                "class_count": len(
                    [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_CLASS)
                    ]
                ),
                "method_count": len(
                    [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
                    ]
                ),
                "field_count": len(
                    [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
                    ]
                ),
                "import_count": len(
                    [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
                    ]
                ),
                "annotation_count": len(
                    [
                        e
                        for e in (self.elements or [])
                        if is_element_of_type(e, ELEMENT_TYPE_ANNOTATION)
                    ]
                ),
                "analysis_time": self.analysis_time,
                "success": self.success,
                "error_message": self.error_message,
            },
        }

    def get_statistics(self) -> dict[str, Any]:
        """Get detailed statistics (alias for get_summary)"""
        return self.get_summary()

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable format (alias for to_dict)"""
        return self.to_dict()


# ========================================
# SQL-Specific Models
# ========================================


class SQLElementType(Enum):
    """SQL element types for database objects"""

    TABLE = "table"
    VIEW = "view"
    PROCEDURE = "procedure"
    FUNCTION = "function"
    TRIGGER = "trigger"
    INDEX = "index"


@dataclass(frozen=False)
class SQLColumn:
    """SQL column definition"""

    name: str
    data_type: str
    nullable: bool = True
    default_value: str | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_reference: str | None = None


@dataclass(frozen=False)
class SQLParameter:
    """SQL procedure/function parameter"""

    name: str
    data_type: str
    direction: str = "IN"  # IN, OUT, INOUT


@dataclass(frozen=False)
class SQLConstraint:
    """SQL constraint definition"""

    name: str | None
    constraint_type: str  # PRIMARY_KEY, FOREIGN_KEY, UNIQUE, CHECK
    columns: list[str] = field(default_factory=list)
    reference_table: str | None = None
    reference_columns: list[str] | None = None


@dataclass(frozen=False)
class SQLElement(CodeElement):
    """Base SQL element with database-specific metadata"""

    sql_element_type: SQLElementType = SQLElementType.TABLE
    columns: list[SQLColumn] = field(default_factory=list)
    parameters: list[SQLParameter] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    constraints: list[SQLConstraint] = field(default_factory=list)
    element_type: str = "sql_element"

    # SQL-specific metadata
    schema_name: str | None = None
    table_name: str | None = None  # For indexes, triggers
    return_type: str | None = None  # For functions
    trigger_timing: str | None = None  # BEFORE, AFTER
    trigger_event: str | None = None  # INSERT, UPDATE, DELETE
    index_type: str | None = None  # UNIQUE, CLUSTERED, etc.

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item with SQL-specific information"""
        return {
            "name": self.name,
            "type": self.sql_element_type.value,
            "lines": {"start": self.start_line, "end": self.end_line},
            "columns_count": len(self.columns),
            "parameters_count": len(self.parameters),
            "dependencies": self.dependencies,
        }


@dataclass(frozen=False)
class SQLTable(SQLElement):
    """SQL table representation"""

    sql_element_type: SQLElementType = SQLElementType.TABLE
    element_type: str = "table"

    def get_primary_key_columns(self) -> list[str]:
        """Get primary key column names"""
        return [col.name for col in self.columns if col.is_primary_key]

    def get_foreign_key_columns(self) -> list[str]:
        """Get foreign key column names"""
        return [col.name for col in self.columns if col.is_foreign_key]


@dataclass(frozen=False)
class SQLView(SQLElement):
    """SQL view representation"""

    sql_element_type: SQLElementType = SQLElementType.VIEW
    element_type: str = "view"
    source_tables: list[str] = field(default_factory=list)
    view_definition: str = ""


@dataclass(frozen=False)
class SQLProcedure(SQLElement):
    """SQL stored procedure representation"""

    sql_element_type: SQLElementType = SQLElementType.PROCEDURE
    element_type: str = "procedure"


@dataclass(frozen=False)
class SQLFunction(SQLElement):
    """SQL function representation"""

    sql_element_type: SQLElementType = SQLElementType.FUNCTION
    element_type: str = "function"
    is_deterministic: bool = False
    reads_sql_data: bool = False


@dataclass(frozen=False)
class SQLTrigger(SQLElement):
    """SQL trigger representation"""

    sql_element_type: SQLElementType = SQLElementType.TRIGGER
    element_type: str = "trigger"
    table_name: str | None = None
    trigger_timing: str | None = None
    trigger_event: str | None = None


@dataclass(frozen=False)
class SQLIndex(SQLElement):
    """SQL index representation"""

    sql_element_type: SQLElementType = SQLElementType.INDEX
    element_type: str = "index"
    indexed_columns: list[str] = field(default_factory=list)
    is_unique: bool = False


@dataclass(frozen=False)
class YAMLElement(CodeElement):
    """
    YAML要素を表現するデータモデル。

    Attributes:
        element_type: 要素タイプ (mapping, sequence, scalar, anchor, alias, comment, document)
        key: マッピングのキー
        value: スカラー値（複合構造の場合はNone）
        value_type: 値の型 (string, number, boolean, null, mapping, sequence)
        anchor_name: アンカー名 (&name)
        alias_target: エイリアスの参照先名（展開しない）
        nesting_level: AST上の論理的な深さ
        document_index: マルチドキュメントYAMLでのドキュメントインデックス
        child_count: 複合構造の子要素数
    """

    language: str = "yaml"
    element_type: str = "yaml"
    key: str | None = None
    value: str | None = None
    value_type: str | None = None
    anchor_name: str | None = None
    alias_target: str | None = None
    nesting_level: int = 0
    document_index: int = 0
    child_count: int | None = None

    def to_summary_item(self) -> dict[str, Any]:
        """Return dictionary for summary item with YAML-specific information."""
        return {
            "name": self.name,
            "type": self.element_type,
            "lines": {"start": self.start_line, "end": self.end_line},
            "key": self.key,
            "value_type": self.value_type,
            "nesting_level": self.nesting_level,
            "document_index": self.document_index,
        }
