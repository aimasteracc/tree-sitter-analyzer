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
    not _TREE_SITTER_AVAILABLE,
    reason="tree-sitter-python not installed — tracked: #740",
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


_CONDITIONAL_SOURCE = """\
import sys

class Platform:
    if sys.platform == "win32":
        def win_method(self):
            pass
    else:
        def posix_method(self):
            pass

    try:
        def try_method(self):
            pass
    except Exception:
        pass
"""


class TestPythonControlFlowMethods:
    """Codex P2 on #740: methods inside if/try inside a class must be detected."""

    def _get_functions(self, extractor, py_parser):
        tree = py_parser.parse(_CONDITIONAL_SOURCE.encode())
        return {
            f.name: f for f in extractor.extract_functions(tree, _CONDITIONAL_SOURCE)
        }

    def test_if_branch_method_is_method(self, extractor, py_parser):
        """win_method inside 'if sys.platform' must be is_method=True."""
        funcs = self._get_functions(extractor, py_parser)
        assert "win_method" in funcs, "'win_method' not extracted"
        assert funcs["win_method"].is_method is True, (
            "Method inside 'if' block in class body must have is_method=True"
        )

    def test_if_branch_method_parent_class(self, extractor, py_parser):
        """win_method must know its parent is Platform."""
        funcs = self._get_functions(extractor, py_parser)
        assert funcs.get("win_method") is not None
        assert funcs["win_method"].parent_class == "Platform", (
            f"Expected parent_class='Platform', got {funcs['win_method'].parent_class!r}"
        )

    def test_else_branch_method_is_method(self, extractor, py_parser):
        """posix_method inside 'else' must be is_method=True."""
        funcs = self._get_functions(extractor, py_parser)
        assert "posix_method" in funcs, "'posix_method' not extracted"
        assert funcs["posix_method"].is_method is True

    def test_try_block_method_is_method(self, extractor, py_parser):
        """try_method inside 'try' block in class body must be is_method=True."""
        funcs = self._get_functions(extractor, py_parser)
        assert "try_method" in funcs, "'try_method' not extracted"
        assert funcs["try_method"].is_method is True
