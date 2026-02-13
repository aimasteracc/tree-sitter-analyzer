#!/usr/bin/env python3
"""Tests for SymbolIndex (Code Intelligence Graph)."""

import pytest
from tree_sitter_analyzer.intelligence.symbol_index import SymbolIndex
from tree_sitter_analyzer.intelligence.models import SymbolDefinition, SymbolReference


@pytest.fixture
def index():
    return SymbolIndex()


class TestSymbolIndexInit:
    def test_init(self, index):
        assert index is not None
        assert index._definitions == {}
        assert index._references == {}

    def test_empty_lookup(self, index):
        assert index.lookup_definition("unknown") == []
        assert index.lookup_references("unknown") == []


class TestSymbolIndexAddDefinition:
    def test_add_function_definition(self, index):
        sd = SymbolDefinition(
            name="login",
            file_path="auth.py",
            line=10,
            end_line=30,
            symbol_type="function",
            parameters=["user", "password"],
        )
        index.add_definition(sd)
        results = index.lookup_definition("login")
        assert len(results) == 1
        assert results[0].file_path == "auth.py"

    def test_add_multiple_definitions_same_name(self, index):
        sd1 = SymbolDefinition(
            name="validate", file_path="a.py", line=1, end_line=5, symbol_type="function"
        )
        sd2 = SymbolDefinition(
            name="validate", file_path="b.py", line=1, end_line=5, symbol_type="function"
        )
        index.add_definition(sd1)
        index.add_definition(sd2)
        results = index.lookup_definition("validate")
        assert len(results) == 2

    def test_add_class_definition(self, index):
        sd = SymbolDefinition(
            name="AuthService",
            file_path="auth.py",
            line=5,
            end_line=100,
            symbol_type="class",
        )
        index.add_definition(sd)
        results = index.lookup_definition("AuthService")
        assert len(results) == 1
        assert results[0].symbol_type == "class"


class TestSymbolIndexAddReference:
    def test_add_call_reference(self, index):
        ref = SymbolReference(
            symbol_name="login",
            file_path="api.py",
            line=30,
            ref_type="call",
            context_function="handle_request",
        )
        index.add_reference(ref)
        results = index.lookup_references("login")
        assert len(results) == 1
        assert results[0].ref_type == "call"

    def test_add_import_reference(self, index):
        ref = SymbolReference(
            symbol_name="AuthService",
            file_path="api.py",
            line=1,
            ref_type="import",
        )
        index.add_reference(ref)
        results = index.lookup_references("AuthService")
        assert len(results) == 1

    def test_add_multiple_references(self, index):
        ref1 = SymbolReference(
            symbol_name="foo", file_path="a.py", line=1, ref_type="call"
        )
        ref2 = SymbolReference(
            symbol_name="foo", file_path="b.py", line=5, ref_type="call"
        )
        ref3 = SymbolReference(
            symbol_name="foo", file_path="c.py", line=1, ref_type="import"
        )
        index.add_reference(ref1)
        index.add_reference(ref2)
        index.add_reference(ref3)
        results = index.lookup_references("foo")
        assert len(results) == 3


class TestSymbolIndexLookup:
    def test_lookup_definition_with_file_hint(self, index):
        sd1 = SymbolDefinition(
            name="validate", file_path="a.py", line=1, end_line=5, symbol_type="function"
        )
        sd2 = SymbolDefinition(
            name="validate", file_path="b.py", line=1, end_line=5, symbol_type="function"
        )
        index.add_definition(sd1)
        index.add_definition(sd2)
        results = index.lookup_definition("validate", file_hint="a.py")
        assert len(results) == 1
        assert results[0].file_path == "a.py"

    def test_lookup_references_by_type(self, index):
        ref1 = SymbolReference(
            symbol_name="X", file_path="a.py", line=1, ref_type="call"
        )
        ref2 = SymbolReference(
            symbol_name="X", file_path="b.py", line=1, ref_type="import"
        )
        index.add_reference(ref1)
        index.add_reference(ref2)
        results = index.lookup_references("X", ref_type="call")
        assert len(results) == 1
        assert results[0].ref_type == "call"


class TestSymbolIndexInheritance:
    def test_get_inheritance_chain_empty(self, index):
        chain = index.get_inheritance_chain("Unknown")
        assert chain == []

    def test_get_inheritance_chain_single(self, index):
        sd = SymbolDefinition(
            name="AuthService",
            file_path="auth.py",
            line=5,
            end_line=100,
            symbol_type="class",
        )
        index.add_definition(sd)
        ref = SymbolReference(
            symbol_name="BaseService",
            file_path="auth.py",
            line=5,
            ref_type="inheritance",
        )
        index.add_reference(ref)
        # Store parent info
        index.set_class_parent("AuthService", "BaseService")
        chain = index.get_inheritance_chain("AuthService")
        assert "BaseService" in chain

    def test_get_subclasses(self, index):
        index.set_class_parent("AuthService", "BaseService")
        index.set_class_parent("MockAuth", "AuthService")
        children = index.get_subclasses("AuthService")
        assert "MockAuth" in children


class TestSymbolIndexClear:
    def test_clear(self, index):
        sd = SymbolDefinition(
            name="foo", file_path="a.py", line=1, end_line=5, symbol_type="function"
        )
        index.add_definition(sd)
        index.clear()
        assert index.lookup_definition("foo") == []
