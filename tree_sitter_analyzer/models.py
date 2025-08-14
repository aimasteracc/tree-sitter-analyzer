#!/usr/bin/env python3
"""
Data Models for Multi-Language Code Analysis

Data classes for representing code structures extracted through
Tree-sitter analysis across multiple programming languages.
"""

from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# Use dataclass with slots for Python 3.10+
def dataclass_with_slots(*args: Any, **kwargs: Any) -> Callable[..., Any]:
    return dataclass(*args, slots=True, **kwargs)  # type: ignore[no-any-return]


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
    is_constructor: bool = False
    visibility: str = "public"
    element_type: str = "function"
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    throws: list[str] = field(default_factory=list)
    complexity_score: int = 1
    is_abstract: bool = False
    is_final: bool = False


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


@dataclass(frozen=False)
class Variable(CodeElement):
    """Generic variable representation"""

    variable_type: str | None = None
    modifiers: list[str] = field(default_factory=list)
    is_constant: bool = False
    is_static: bool = False
    visibility: str = "private"
    element_type: str = "variable"
    initializer: str | None = None
    # Java-specific fields for detailed analysis
    annotations: list[dict[str, Any]] = field(default_factory=list)
    is_final: bool = False
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


@dataclass(frozen=False)
class AnalysisResult:
    """Comprehensive analysis result container"""

    file_path: str
    language: str = "unknown"  # Add language field for new architecture compatibility
    line_count: int = 0  # Add line_count for compatibility
    elements: list[CodeElement] = field(
        default_factory=list
    )  # Generic elements for new architecture
    node_count: int = 0  # Node count for new architecture
    query_results: dict[str, Any] = field(
        default_factory=dict
    )  # Query results for new architecture
    source_code: str = ""  # Source code for new architecture
    package: JavaPackage | None = None
    imports: list[JavaImport] = field(default_factory=list)
    classes: list[JavaClass] = field(default_factory=list)
    methods: list[JavaMethod] = field(default_factory=list)
    fields: list[JavaField] = field(default_factory=list)
    annotations: list[JavaAnnotation] = field(default_factory=list)
    analysis_time: float = 0.0
    success: bool = True
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert analysis result to dictionary for serialization"""
        return {
            "file_path": self.file_path,
            "line_count": self.line_count,
            "package": {"name": self.package.name} if self.package else None,
            "imports": [
                {
                    "name": imp.name,
                    "is_static": imp.is_static,
                    "is_wildcard": imp.is_wildcard,
                }
                for imp in self.imports
            ],
            "classes": [
                {"name": cls.name, "type": cls.class_type, "package": cls.package_name}
                for cls in self.classes
            ],
            "methods": [
                {
                    "name": method.name,
                    "return_type": method.return_type,
                    "parameters": method.parameters,
                }
                for method in self.methods
            ],
            "fields": [
                {"name": field.name, "type": field.field_type} for field in self.fields
            ],
            "annotations": [{"name": ann.name} for ann in self.annotations],
            "analysis_time": self.analysis_time,
            "success": self.success,
            "error_message": self.error_message,
        }

    def to_summary_dict(self, types: list[str] | None = None) -> dict[str, Any]:
        """
        Return analysis summary as a dictionary.
        Only include specified element types (e.g., 'classes', 'methods', 'fields').
        """
        if types is None:
            types = ["classes", "methods"]  # default

        summary: dict[str, Any] = {"file_path": self.file_path, "summary_elements": []}

        all_elements: dict[str, list[Any]] = {
            "imports": self.imports,
            "classes": self.classes,
            "methods": self.methods,
            "fields": self.fields,
            "annotations": self.annotations,
        }

        for type_name, elements in all_elements.items():
            if "all" in types or type_name in types:
                for element in elements:
                    # Call each element model's to_summary_item()
                    summary["summary_elements"].append(element.to_summary_item())

        return summary

    def get_summary(self) -> dict[str, Any]:
        """Get analysis summary statistics"""
        return {
            "file_path": self.file_path,
            "line_count": self.line_count,
            "class_count": len(self.classes),
            "method_count": len(self.methods),
            "field_count": len(self.fields),
            "import_count": len(self.imports),
            "annotation_count": len(self.annotations),
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
                    for imp in self.imports
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
                    for cls in self.classes
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
                    for method in self.methods
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
                    for field in self.fields
                ],
                "annotations": [
                    {
                        "name": safe_get_attr(ann, "name"),
                        "line_range": {
                            "start": safe_get_attr(ann, "start_line", 0),
                            "end": safe_get_attr(ann, "end_line", 0),
                        },
                    }
                    for ann in self.annotations
                ],
            },
            "metadata": {
                "line_count": self.line_count,
                "class_count": len(self.classes),
                "method_count": len(self.methods),
                "field_count": len(self.fields),
                "import_count": len(self.imports),
                "annotation_count": len(self.annotations),
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
