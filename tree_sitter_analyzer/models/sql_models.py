#!/usr/bin/env python3
"""
SQL-specific code element models.

Contains: SQLElementType, SQLColumn, SQLParameter, SQLConstraint,
          SQLElement, SQLTable, SQLView, SQLProcedure, SQLFunction,
          SQLTrigger, SQLIndex
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import CodeElement


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


__all__ = [
    "SQLElementType",
    "SQLColumn",
    "SQLParameter",
    "SQLConstraint",
    "SQLElement",
    "SQLTable",
    "SQLView",
    "SQLProcedure",
    "SQLFunction",
    "SQLTrigger",
    "SQLIndex",
]
