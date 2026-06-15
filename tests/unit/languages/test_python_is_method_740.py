"""
Regression tests for Issue #740 — Python extraction: is_method always False.

Functions defined inside a class body must report is_method=True and have
parent_class set to the enclosing class name.  Module-level functions must
continue to report is_method=False.
"""

import pytest

try:
    import tree_sitter_python as _tspy
    from tree_sitter import Language, Parser

    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _TREE_SITTER_AVAILABLE = False

from tree_sitter_analyzer.languages.python_plugin.extractor import (
    PythonElementExtractor,
)

pytestmark = pytest.mark.skipif(
    not _TREE_SITTER_AVAILABLE, reason="tree-sitter-python not installed"
)

_SOURCE = """\
class Parser:
    def __init__(self, path):
        self.path = path

    def parse_file(self, path):
        pass

    @staticmethod
    def cache_info():
        pass

    @classmethod
    def from_string(cls, s):
        pass


def standalone_function():
    pass
"""


@pytest.fixture(scope="module")
def py_parser():
    lang = Language(_tspy.language())
    return Parser(lang)


@pytest.fixture
def extractor():
    return PythonElementExtractor()


class TestPythonIsMethod:
    """is_method must be True for class methods, False for module-level fns."""

    def _get_functions(self, extractor, py_parser):
        tree = py_parser.parse(_SOURCE.encode())
        return {f.name: f for f in extractor.extract_functions(tree, _SOURCE)}

    def test_parse_file_is_method(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert "parse_file" in funcs
        assert funcs["parse_file"].is_method is True, (
            "parse_file defined inside class Parser must have is_method=True"
        )

    def test_init_is_method(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert "__init__" in funcs
        assert funcs["__init__"].is_method is True

    def test_static_method_is_method(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert "cache_info" in funcs
        assert funcs["cache_info"].is_method is True, (
            "@staticmethod methods inside a class must still be is_method=True"
        )

    def test_classmethod_is_method(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert "from_string" in funcs
        assert funcs["from_string"].is_method is True

    def test_standalone_function_is_not_method(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert "standalone_function" in funcs
        assert funcs["standalone_function"].is_method is False, (
            "Module-level function must have is_method=False"
        )


class TestPythonParentClass:
    """parent_class must be set to the enclosing class name for methods."""

    def _get_functions(self, extractor, py_parser):
        tree = py_parser.parse(_SOURCE.encode())
        return {f.name: f for f in extractor.extract_functions(tree, _SOURCE)}

    def test_parse_file_parent_class(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert funcs["parse_file"].parent_class == "Parser", (
            f"parent_class must be 'Parser', got {funcs['parse_file'].parent_class!r}"
        )

    def test_init_parent_class(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert funcs["__init__"].parent_class == "Parser"

    def test_standalone_no_parent_class(self, extractor, py_parser):
        funcs = self._get_functions(extractor, py_parser)
        assert funcs["standalone_function"].parent_class is None, (
            "Module-level function must have parent_class=None"
        )
