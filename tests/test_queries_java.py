#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Java queries module
"""

import pytest
from tree_sitter_analyzer.queries.java import (
    get_java_query,
    get_java_query_description,
    get_query,
    get_all_queries,
    list_queries,
    get_available_java_queries,
    JAVA_QUERIES,
    JAVA_QUERY_DESCRIPTIONS,
    ALL_QUERIES,
)


class TestJavaQueries:
    """Test Java queries functionality"""

    def test_get_java_query_valid(self) -> None:
        """Test getting a valid Java query"""
        query = get_java_query("class")
        assert query is not None
        assert "class_declaration" in query
        assert "@class" in query

    def test_get_java_query_invalid(self) -> None:
        """Test getting an invalid Java query raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            get_java_query("nonexistent_query")
        
        assert "Javaクエリ 'nonexistent_query' は存在しません" in str(exc_info.value)
        assert "利用可能:" in str(exc_info.value)

    def test_get_java_query_description_valid(self) -> None:
        """Test getting description for valid query"""
        description = get_java_query_description("class")
        assert description == "Javaクラス宣言を抽出"

    def test_get_java_query_description_invalid(self) -> None:
        """Test getting description for invalid query returns default"""
        description = get_java_query_description("nonexistent_query")
        assert description == "説明なし"

    def test_get_query_valid(self) -> None:
        """Test getting query through ALL_QUERIES interface"""
        query = get_query("class")
        assert query is not None
        assert "class_declaration" in query

    def test_get_query_invalid(self) -> None:
        """Test getting invalid query through ALL_QUERIES interface"""
        with pytest.raises(ValueError) as exc_info:
            get_query("nonexistent_query")
        
        assert "Query 'nonexistent_query' not found" in str(exc_info.value)
        assert "Available queries:" in str(exc_info.value)

    def test_get_all_queries(self) -> None:
        """Test getting all queries"""
        all_queries = get_all_queries()
        assert isinstance(all_queries, dict)
        assert len(all_queries) > 0
        assert "class" in all_queries
        assert "query" in all_queries["class"]
        assert "description" in all_queries["class"]

    def test_list_queries(self) -> None:
        """Test listing all query names"""
        query_names = list_queries()
        assert isinstance(query_names, list)
        assert len(query_names) > 0
        assert "class" in query_names
        assert "method" in query_names

    def test_get_available_java_queries(self) -> None:
        """Test getting available Java queries"""
        available_queries = get_available_java_queries()
        assert isinstance(available_queries, list)
        assert len(available_queries) > 0
        assert "class" in available_queries
        assert "method" in available_queries

    def test_java_queries_structure(self) -> None:
        """Test JAVA_QUERIES dictionary structure"""
        assert isinstance(JAVA_QUERIES, dict)
        assert len(JAVA_QUERIES) > 0
        
        # Test some essential queries exist
        essential_queries = ["class", "method", "field", "import", "package"]
        for query_name in essential_queries:
            assert query_name in JAVA_QUERIES
            assert isinstance(JAVA_QUERIES[query_name], str)
            assert len(JAVA_QUERIES[query_name].strip()) > 0

    def test_java_query_descriptions_structure(self) -> None:
        """Test JAVA_QUERY_DESCRIPTIONS dictionary structure"""
        assert isinstance(JAVA_QUERY_DESCRIPTIONS, dict)
        assert len(JAVA_QUERY_DESCRIPTIONS) > 0
        
        # Test some essential descriptions exist
        essential_queries = ["class", "method", "field", "import", "package"]
        for query_name in essential_queries:
            assert query_name in JAVA_QUERY_DESCRIPTIONS
            assert isinstance(JAVA_QUERY_DESCRIPTIONS[query_name], str)
            assert len(JAVA_QUERY_DESCRIPTIONS[query_name].strip()) > 0

    def test_all_queries_structure(self) -> None:
        """Test ALL_QUERIES dictionary structure"""
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 0
        
        # Test structure of each query entry
        for query_name, query_data in ALL_QUERIES.items():
            assert isinstance(query_data, dict)
            assert "query" in query_data
            assert "description" in query_data
            assert isinstance(query_data["query"], str)
            assert isinstance(query_data["description"], str)

    def test_query_aliases(self) -> None:
        """Test that query aliases work correctly"""
        # Test functions alias
        assert "functions" in ALL_QUERIES
        functions_query = ALL_QUERIES["functions"]["query"]
        method_query = JAVA_QUERIES["method"]
        assert functions_query == method_query
        
        # Test classes alias
        assert "classes" in ALL_QUERIES
        classes_query = ALL_QUERIES["classes"]["query"]
        class_query = JAVA_QUERIES["class"]
        assert classes_query == class_query

    def test_spring_framework_queries(self) -> None:
        """Test Spring Framework specific queries"""
        spring_queries = ["spring_controller", "spring_service", "spring_repository"]
        for query_name in spring_queries:
            assert query_name in JAVA_QUERIES
            query = JAVA_QUERIES[query_name]
            assert "annotation" in query
            assert "class_declaration" in query

    def test_jpa_queries(self) -> None:
        """Test JPA specific queries"""
        jpa_queries = ["jpa_entity", "jpa_id_field"]
        for query_name in jpa_queries:
            assert query_name in JAVA_QUERIES
            query = JAVA_QUERIES[query_name]
            assert "annotation" in query

    def test_detailed_queries(self) -> None:
        """Test detailed information extraction queries"""
        detailed_queries = [
            "method_parameters_detailed",
            "class_inheritance_detailed", 
            "annotation_detailed",
            "import_detailed",
            "package_detailed",
            "constructor_detailed"
        ]
        for query_name in detailed_queries:
            assert query_name in JAVA_QUERIES
            query = JAVA_QUERIES[query_name]
            assert len(query.strip()) > 0

    def test_modifier_specific_queries(self) -> None:
        """Test modifier-specific queries"""
        modifier_queries = ["public_methods", "private_methods", "static_methods"]
        for query_name in modifier_queries:
            assert query_name in JAVA_QUERIES
            query = JAVA_QUERIES[query_name]
            assert "modifiers" in query
            assert "#match?" in query

    def test_query_consistency(self) -> None:
        """Test consistency between JAVA_QUERIES and ALL_QUERIES"""
        # All JAVA_QUERIES should be in ALL_QUERIES
        for query_name in JAVA_QUERIES:
            assert query_name in ALL_QUERIES
            assert ALL_QUERIES[query_name]["query"] == JAVA_QUERIES[query_name]
        
        # All queries in JAVA_QUERY_DESCRIPTIONS should have corresponding queries
        for query_name in JAVA_QUERY_DESCRIPTIONS:
            assert query_name in JAVA_QUERIES