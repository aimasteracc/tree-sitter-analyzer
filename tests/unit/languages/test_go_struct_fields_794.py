"""Tests for Go struct field extraction — issue #794.

Struct fields (field_declaration nodes inside struct_type) were not extracted
at all: field_count was always 0, and no Variable elements with receiver_type
set were produced for Go structs.
"""

from __future__ import annotations

import pytest

# Skip the whole module if tree-sitter-go is unavailable
pytest.importorskip("tree_sitter_go")
pytest.importorskip("tree_sitter")


def _make_tree(src: str):
    import tree_sitter_go as tsg
    from tree_sitter import Language, Parser

    lang = Language(tsg.language())
    parser = Parser(lang)
    return parser.parse(src.encode("utf-8"))


def _extractor():
    from tree_sitter_analyzer.languages.go_plugin import GoElementExtractor

    return GoElementExtractor()


# ---------------------------------------------------------------------------
# Repro fixture from the issue
# ---------------------------------------------------------------------------

_WORKER_SRC = """\
package main

import "sync"

type Worker struct {
    wg    sync.WaitGroup
    mu    sync.Mutex
    count int
    name  string
}
"""


def test_go_struct_fields_count() -> None:
    """Four struct fields must be returned as Variable elements."""
    tree = _make_tree(_WORKER_SRC)
    ext = _extractor()
    variables = ext.extract_variables(tree, _WORKER_SRC)

    field_vars = [v for v in variables if getattr(v, "receiver_type", None) == "Worker"]
    assert len(field_vars) == 4


def test_go_struct_field_names() -> None:
    """Field names must match the struct declaration order."""
    tree = _make_tree(_WORKER_SRC)
    ext = _extractor()
    variables = ext.extract_variables(tree, _WORKER_SRC)

    field_vars = [v for v in variables if getattr(v, "receiver_type", None) == "Worker"]
    names = [v.name for v in field_vars]
    assert names == ["wg", "mu", "count", "name"]


def test_go_struct_field_types() -> None:
    """Field types must capture both qualified (sync.WaitGroup) and simple types."""
    tree = _make_tree(_WORKER_SRC)
    ext = _extractor()
    variables = ext.extract_variables(tree, _WORKER_SRC)

    field_vars = [v for v in variables if getattr(v, "receiver_type", None) == "Worker"]
    type_map = {v.name: (v.variable_type or v.field_type) for v in field_vars}
    assert type_map["wg"] == "sync.WaitGroup"
    assert type_map["mu"] == "sync.Mutex"
    assert type_map["count"] == "int"
    assert type_map["name"] == "string"


def test_go_struct_field_element_type() -> None:
    """Fields must carry element_type='variable' so the formatter routes them correctly."""
    tree = _make_tree(_WORKER_SRC)
    ext = _extractor()
    variables = ext.extract_variables(tree, _WORKER_SRC)

    field_vars = [v for v in variables if getattr(v, "receiver_type", None) == "Worker"]
    for v in field_vars:
        assert v.element_type == "variable"


def test_go_plain_var_still_extracted() -> None:
    """Package-level var declarations must still be extracted (no regression)."""
    src = """\
package main

var timeout = 30
const maxRetries = 3

type Config struct {
    host string
    port int
}
"""
    tree = _make_tree(src)
    ext = _extractor()
    variables = ext.extract_variables(tree, src)

    # package-level var
    pkg_vars = [v for v in variables if getattr(v, "receiver_type", None) is None]
    pkg_names = [v.name for v in pkg_vars]
    assert "timeout" in pkg_names

    # struct fields
    config_fields = [
        v for v in variables if getattr(v, "receiver_type", None) == "Config"
    ]
    assert len(config_fields) == 2
    assert [v.name for v in config_fields] == ["host", "port"]


def test_go_multiple_structs_fields_isolated() -> None:
    """Fields from multiple structs are correctly attributed to their owners."""
    src = """\
package main

type A struct {
    x int
    y int
}

type B struct {
    label string
}
"""
    tree = _make_tree(src)
    ext = _extractor()
    variables = ext.extract_variables(tree, src)

    a_fields = [v for v in variables if getattr(v, "receiver_type", None) == "A"]
    b_fields = [v for v in variables if getattr(v, "receiver_type", None) == "B"]

    assert len(a_fields) == 2
    assert [v.name for v in a_fields] == ["x", "y"]

    assert len(b_fields) == 1
    assert b_fields[0].name == "label"
