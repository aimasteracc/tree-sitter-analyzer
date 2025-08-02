#!/usr/bin/env python3
"""
Tests for Query Library Coverage Enhancement

Additional tests to improve coverage for query_library.py
"""

import sys

import pytest

# Add project root to path
sys.path.insert(0, ".")

from tree_sitter_analyzer.query_loader import get_query, get_query_loader, list_queries

# Use a fixed language for testing
TEST_LANGUAGE = "java"


def test_get_query_valid_key():
    """Test getting query with valid key"""
    query = get_query(TEST_LANGUAGE, "class")
    assert isinstance(query, str)
    assert "class_declaration" in query


def test_get_query_invalid_key():
    """Test getting query with invalid key"""
    query = get_query(TEST_LANGUAGE, "nonexistent_key")
    assert query is None


def test_get_available_queries():
    """Test getting available queries"""
    queries = list_queries(TEST_LANGUAGE)

    assert isinstance(queries, list)
    assert len(queries) > 0
    assert "class" in queries
    assert "method" in queries
    assert "interface" in queries


def test_get_query_description_valid_key():
    """Test getting query description with valid key"""
    loader = get_query_loader()
    description = loader.get_query_description(TEST_LANGUAGE, "class")
    assert description == "クラス宣言を抽出"

    description = loader.get_query_description(TEST_LANGUAGE, "method")
    assert description == "メソッド宣言を抽出"

    description = loader.get_query_description(TEST_LANGUAGE, "interface")
    assert description == "インターフェース宣言を抽出"


def test_get_query_description_invalid_key():
    """Test getting query description with invalid key"""
    loader = get_query_loader()
    description = loader.get_query_description(TEST_LANGUAGE, "nonexistent_key")
    assert description is None


def test_get_query_description_all_keys():
    """Test getting descriptions for all available keys"""
    loader = get_query_loader()
    for key in list_queries(TEST_LANGUAGE):
        description = loader.get_query_description(TEST_LANGUAGE, key)
        assert isinstance(description, str)
        assert len(description) > 0


def test_queries_dict_structure():
    """Test QUERIES dictionary structure"""
    loader = get_query_loader()
    queries = loader.load_language_queries(TEST_LANGUAGE)
    assert isinstance(queries, dict)
    assert len(queries) > 0

    # Test some expected keys
    expected_keys = [
        "class",
        "interface",
        "method",
        "constructor",
        "field",
        "import",
        "package",
        "annotation",
        "method_name",
        "class_name",
    ]

    for key in expected_keys:
        assert key in queries
        query_info = queries[key]
        assert isinstance(query_info, str | dict)


def test_query_content_validity():
    """Test that query content contains expected patterns"""
    # Test class query
    class_query = get_query(TEST_LANGUAGE, "class")
    assert "class_declaration" in class_query
    assert "@class" in class_query

    # Test method query
    method_query = get_query(TEST_LANGUAGE, "method")
    assert "method_declaration" in method_query
    assert "@method" in method_query

    # Test interface query
    interface_query = get_query(TEST_LANGUAGE, "interface")
    assert "interface_declaration" in interface_query
    assert "@interface" in interface_query


def test_structured_queries():
    """Test structured queries with multiple captures"""
    # Test class_with_body query
    class_with_body = get_query(TEST_LANGUAGE, "class_with_body")
    assert "class_declaration" in class_with_body
    assert "@name" in class_with_body  # 新しいクエリ構造では@nameを使用
    assert "@body" in class_with_body

    # Test method_with_body query
    method_with_body = get_query(TEST_LANGUAGE, "method_with_body")
    if method_with_body:  # クエリが存在する場合のみテスト
        assert "method_declaration" in method_with_body
        assert "@name" in method_with_body  # 新しいクエリ構造では@nameを使用
        assert "@body" in method_with_body


def test_query_descriptions_completeness():
    """Test that all queries have descriptions"""
    available_queries = list_queries(TEST_LANGUAGE)

    for query_key in available_queries:
        loader = get_query_loader()
        description = loader.get_query_description(TEST_LANGUAGE, query_key)
        # Should not be empty or default "説明なし"
        assert description is not None
        assert len(description) > 0


if __name__ == "__main__":
    pytest.main([__file__])
