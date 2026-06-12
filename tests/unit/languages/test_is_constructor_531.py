"""Issue #531 — is_constructor for Python/__init__, Ruby/initialize,
PHP/__construct, Scala/def-this, and C++ keyword constructors.

Each test class:
  - uses a live tree-sitter parse (real grammar, real AST nodes)
  - pins is_constructor is True for the known constructor
  - pins is_constructor is False for a regular method
  - for C++: also pins the destructor as False

No mocks are used for the node tree — test_kw4b_rules require live node
parent chains to actually exercise the parent-walk logic.
"""

from __future__ import annotations

import pytest
import tree_sitter

from tree_sitter_analyzer.languages._cpp_plugin_analysis_helpers import (
    create_cpp_parser,
)
from tree_sitter_analyzer.languages.cpp_plugin import CppPlugin
from tree_sitter_analyzer.languages.php_plugin import PHPPlugin
from tree_sitter_analyzer.languages.python_plugin.plugin import (
    PythonElementExtractor,
    PythonPlugin,
)
from tree_sitter_analyzer.languages.ruby_plugin import RubyPlugin
from tree_sitter_analyzer.languages.scala_plugin import (
    ScalaPlugin,
)

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

_PYTHON_SRC = """\
class Animal:
    def __init__(self, name: str) -> None:
        self.name = name

    def make_sound(self) -> str:
        return ""


def __init__() -> None:
    # module-level __init__ — NOT a constructor
    pass
"""


class TestPythonIsConstructor:
    """__init__ inside a class → True; outside → False."""

    @pytest.fixture
    def extractor(self) -> PythonElementExtractor:
        return PythonElementExtractor()

    @pytest.fixture
    def functions(self, extractor: PythonElementExtractor):
        plugin = PythonPlugin()
        lang = plugin.get_tree_sitter_language()
        assert lang is not None, "tree-sitter Python grammar unavailable"
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(_PYTHON_SRC.encode())
        return extractor.extract_functions(tree, _PYTHON_SRC)

    def test_init_in_class_is_constructor_true(self, functions) -> None:
        init_in_class = [
            f for f in functions if f.name == "__init__" and f.is_constructor
        ]
        assert len(init_in_class) == 1

    def test_regular_method_is_constructor_false(self, functions) -> None:
        make_sound = next(f for f in functions if f.name == "make_sound")
        assert make_sound.is_constructor is False

    def test_module_level_init_is_constructor_false(self, functions) -> None:
        # There are 2 __init__ functions; the module-level one must be False
        module_inits = [
            f for f in functions if f.name == "__init__" and not f.is_constructor
        ]
        assert len(module_inits) == 1


# ---------------------------------------------------------------------------
# Ruby
# ---------------------------------------------------------------------------

_RUBY_SRC = """\
class User
  def initialize(username, email)
    @username = username
    @email = email
  end

  def authenticate(password)
    true
  end
end
"""


class TestRubyIsConstructor:
    """initialize → True; regular method → False."""

    @pytest.fixture
    def functions(self):
        plugin = RubyPlugin()
        lang = plugin.get_tree_sitter_language()
        assert lang is not None, "tree-sitter Ruby grammar unavailable"
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(_RUBY_SRC.encode())
        extractor = plugin.create_extractor()
        return extractor.extract_functions(tree, _RUBY_SRC)

    def test_initialize_is_constructor_true(self, functions) -> None:
        init = next(f for f in functions if f.name == "initialize")
        assert init.is_constructor is True

    def test_regular_method_is_constructor_false(self, functions) -> None:
        auth = next(f for f in functions if f.name == "authenticate")
        assert auth.is_constructor is False


# ---------------------------------------------------------------------------
# PHP
# ---------------------------------------------------------------------------

_PHP_SRC = """\
<?php
class User {
    public function __construct(string $username, string $email) {
        $this->username = $username;
    }

    public function authenticate(string $password): bool {
        return true;
    }
}

function standaloneFunc(string $x): void {}
?>"""


class TestPhpIsConstructor:
    """__construct → True; regular method → False; standalone function → None/False."""

    @pytest.fixture
    def functions(self):
        plugin = PHPPlugin()
        lang = plugin.get_tree_sitter_language()
        assert lang is not None, "tree-sitter PHP grammar unavailable"
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(_PHP_SRC.encode())
        extractor = plugin.create_extractor()
        return extractor.extract_functions(tree, _PHP_SRC)

    def test_construct_is_constructor_true(self, functions) -> None:
        ctor = next(f for f in functions if f.name == "__construct")
        assert ctor.is_constructor is True

    def test_regular_method_is_constructor_false(self, functions) -> None:
        auth = next(f for f in functions if f.name == "authenticate")
        assert auth.is_constructor is False


# ---------------------------------------------------------------------------
# Scala
# ---------------------------------------------------------------------------

_SCALA_SRC = """\
class Point(x: Double, y: Double) {
  def this(x: Double) = this(x, 0.0)
  def distance(other: Point): Double = 0.0
}
"""


class TestScalaIsConstructor:
    """def this(...) → True; regular method → False."""

    @pytest.fixture
    def functions(self):
        plugin = ScalaPlugin()
        lang = plugin.get_tree_sitter_language()
        assert lang is not None, "tree-sitter Scala grammar unavailable"
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(_SCALA_SRC.encode())
        extractor = plugin.create_extractor()
        return extractor.extract_functions(tree, _SCALA_SRC)

    def test_def_this_is_constructor_true(self, functions) -> None:
        ctor = next(f for f in functions if f.name == "this")
        assert ctor.is_constructor is True

    def test_regular_method_is_constructor_false(self, functions) -> None:
        dist = next(f for f in functions if f.name == "distance")
        assert dist.is_constructor is False


# ---------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------

_CPP_SRC = """\
class Rectangle {
public:
    Rectangle(double w, double h) {}
    ~Rectangle() {}
    void foo() {}
};

void global_func() {}
"""


class TestCppIsConstructor:
    """Constructor (name == class name) → True; destructor → False; regular → False."""

    @pytest.fixture
    def functions(self):
        plugin = CppPlugin()
        lang = plugin.get_tree_sitter_language()
        assert lang is not None, "tree-sitter C++ grammar unavailable"
        parser, failure = create_cpp_parser(lang, "test.cpp", _CPP_SRC)
        assert failure is None, f"C++ parser creation failed: {failure}"
        tree = parser.parse(_CPP_SRC.encode())
        extractor = plugin.create_extractor()
        return extractor.extract_functions(tree, _CPP_SRC)

    def test_constructor_is_constructor_true(self, functions) -> None:
        ctor = next(f for f in functions if f.name == "Rectangle" and f.is_constructor)
        assert ctor.is_constructor is True

    def test_destructor_is_constructor_false(self, functions) -> None:
        dtor = next(f for f in functions if f.name == "~Rectangle")
        assert dtor.is_constructor is False

    def test_regular_method_is_constructor_false(self, functions) -> None:
        foo = next(f for f in functions if f.name == "foo")
        assert foo.is_constructor is False

    def test_global_function_is_constructor_false(self, functions) -> None:
        gfunc = next(f for f in functions if f.name == "global_func")
        assert gfunc.is_constructor is False
