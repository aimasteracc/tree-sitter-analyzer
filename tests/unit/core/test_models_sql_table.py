#!/usr/bin/env python3
"""Unit tests for SQLTable model methods - get_primary_key_columns and get_foreign_key_columns."""

import pytest

from tree_sitter_analyzer.models import (
    SQLColumn,
    SQLTable,
)


class TestSQLTablePrimaryKeyColumns:
    """Tests for SQLTable.get_primary_key_columns."""

    def test_get_primary_key_columns_empty(self) -> None:
        """Returns empty list when no primary key columns."""
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=10,
            raw_text="CREATE TABLE users...",
            columns=[
                SQLColumn(name="id", data_type="INT", is_primary_key=False),
                SQLColumn(name="username", data_type="VARCHAR(100)", is_primary_key=False),
            ],
        )
        assert table.get_primary_key_columns() == []

    def test_get_primary_key_columns_single(self) -> None:
        """Returns single primary key column name."""
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=10,
            raw_text="CREATE TABLE users...",
            columns=[
                SQLColumn(name="id", data_type="INT", is_primary_key=True),
                SQLColumn(name="username", data_type="VARCHAR(100)", is_primary_key=False),
            ],
        )
        assert table.get_primary_key_columns() == ["id"]

    def test_get_primary_key_columns_composite(self) -> None:
        """Returns multiple primary key columns in order."""
        table = SQLTable(
            name="order_items",
            start_line=1,
            end_line=15,
            raw_text="CREATE TABLE order_items...",
            columns=[
                SQLColumn(name="order_id", data_type="INT", is_primary_key=True),
                SQLColumn(name="item_id", data_type="INT", is_primary_key=True),
                SQLColumn(name="quantity", data_type="INT", is_primary_key=False),
            ],
        )
        assert table.get_primary_key_columns() == ["order_id", "item_id"]


class TestSQLTableForeignKeyColumns:
    """Tests for SQLTable.get_foreign_key_columns."""

    def test_get_foreign_key_columns_empty(self) -> None:
        """Returns empty list when no foreign key columns."""
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=10,
            raw_text="CREATE TABLE users...",
            columns=[
                SQLColumn(name="id", data_type="INT", is_foreign_key=False),
                SQLColumn(name="username", data_type="VARCHAR(100)", is_foreign_key=False),
            ],
        )
        assert table.get_foreign_key_columns() == []

    def test_get_foreign_key_columns_single(self) -> None:
        """Returns single foreign key column name."""
        table = SQLTable(
            name="orders",
            start_line=1,
            end_line=10,
            raw_text="CREATE TABLE orders...",
            columns=[
                SQLColumn(name="id", data_type="INT", is_primary_key=True, is_foreign_key=False),
                SQLColumn(
                    name="user_id",
                    data_type="INT",
                    is_foreign_key=True,
                    foreign_key_reference="users(id)",
                ),
            ],
        )
        assert table.get_foreign_key_columns() == ["user_id"]

    def test_get_foreign_key_columns_multiple(self) -> None:
        """Returns multiple foreign key columns in order."""
        table = SQLTable(
            name="order_items",
            start_line=1,
            end_line=15,
            raw_text="CREATE TABLE order_items...",
            columns=[
                SQLColumn(name="order_id", data_type="INT", is_foreign_key=True),
                SQLColumn(name="product_id", data_type="INT", is_foreign_key=True),
                SQLColumn(name="quantity", data_type="INT", is_foreign_key=False),
            ],
        )
        assert table.get_foreign_key_columns() == ["order_id", "product_id"]
