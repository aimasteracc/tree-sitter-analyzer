#!/usr/bin/env python3
"""
Java-specific code element models.

Contains: JavaAnnotation, JavaMethod, JavaClass, JavaField,
          JavaImport, JavaPackage
"""

from dataclasses import dataclass, field
from typing import Any


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


__all__ = [
    "JavaAnnotation",
    "JavaMethod",
    "JavaClass",
    "JavaField",
    "JavaImport",
    "JavaPackage",
]
