"""Regression tests for Ruby/PHP extraction bugs #763 #765 #768 #769 #770.

#768 - Ruby keyword_parameter (bar: "default") silently dropped
#769 - Ruby/PHP code elements report line_count == 0 via getattr
#770 - Ruby @ivar assignments inside non-initialize methods extracted as fields
#763 - PHP enum methods have receiver_type=None instead of the enum name
#765 - PHP extract_functions does not call _extract_namespace, so namespace
       is '' when called standalone and the last-set namespace when called
       after extract_classes, making the result order-dependent.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_php
import tree_sitter_ruby

from tree_sitter_analyzer.languages.php_plugin import PHPElementExtractor
from tree_sitter_analyzer.languages.ruby_plugin import RubyElementExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ruby_parser() -> tree_sitter.Parser:
    lang = tree_sitter.Language(tree_sitter_ruby.language())
    return tree_sitter.Parser(lang)


def _php_parser() -> tree_sitter.Parser:
    lang = tree_sitter.Language(tree_sitter_php.language_php())
    return tree_sitter.Parser(lang)


# ---------------------------------------------------------------------------
# #768 — keyword_parameter missing from Ruby parameter types
# ---------------------------------------------------------------------------

RUBY_KEYWORD_PARAM_SRC = """\
class Config
  def setup(host: "localhost", port: 80, debug: false)
    @host = host
  end
end
"""


def test_ruby_keyword_param_extracted() -> None:
    """Keyword parameters (name: default) must appear in .parameters."""
    parser = _ruby_parser()
    tree = parser.parse(RUBY_KEYWORD_PARAM_SRC.encode())
    extractor = RubyElementExtractor()
    funcs = extractor.extract_functions(tree, RUBY_KEYWORD_PARAM_SRC)

    setup = next(f for f in funcs if f.name == "setup")
    # All three keyword params must be present
    assert setup.parameters == ['host: "localhost"', "port: 80", "debug: false"]


def test_ruby_mixed_params_all_extracted() -> None:
    """All Ruby parameter kinds (positional, optional, keyword, splat, block)
    must all appear; none silently dropped."""
    src = """\
class Foo
  def bar(pos, opt = 1, key: "v", *rest, **opts, &blk)
    nil
  end
end
"""
    parser = _ruby_parser()
    tree = parser.parse(src.encode())
    extractor = RubyElementExtractor()
    funcs = extractor.extract_functions(tree, src)

    bar = next(f for f in funcs if f.name == "bar")
    assert bar.parameters == ["pos", "opt = 1", 'key: "v"', "*rest", "**opts", "&blk"]


# ---------------------------------------------------------------------------
# #769 — CodeElement.line_count always 0 via getattr(elem, "line_count", 0)
# ---------------------------------------------------------------------------


def test_ruby_function_line_count_nonzero() -> None:
    """getattr(func, 'line_count', 0) must return end_line - start_line + 1."""
    src = """\
class Foo
  def multi
    x = 1
    y = 2
    x + y
  end
end
"""
    parser = _ruby_parser()
    tree = parser.parse(src.encode())
    extractor = RubyElementExtractor()
    funcs = extractor.extract_functions(tree, src)

    multi = next(f for f in funcs if f.name == "multi")
    assert multi.start_line == 2
    assert multi.end_line == 6
    assert getattr(multi, "line_count", 0) == 5


def test_php_method_line_count_nonzero() -> None:
    """PHP method line_count must equal end_line - start_line + 1."""
    src = b"""\
<?php
class Foo {
    public function multi(): void {
        $x = 1;
        $y = 2;
    }
}
"""
    parser = _php_parser()
    tree = parser.parse(src)
    extractor = PHPElementExtractor()
    funcs = extractor.extract_functions(tree, src.decode())

    multi = next(f for f in funcs if f.name == "multi")
    assert multi.start_line == 3
    assert multi.end_line == 6
    assert getattr(multi, "line_count", 0) == 4


def test_ruby_single_line_method_line_count_one() -> None:
    """A one-liner method must have line_count == 1."""
    src = "class Foo\n  def one; 1; end\nend\n"
    parser = _ruby_parser()
    tree = parser.parse(src.encode())
    extractor = RubyElementExtractor()
    funcs = extractor.extract_functions(tree, src)

    one = next(f for f in funcs if f.name == "one")
    assert getattr(one, "line_count", 0) == 1


# ---------------------------------------------------------------------------
# #770 — Ruby @ivar assignments inside non-initialize methods → phantom fields
# ---------------------------------------------------------------------------

RUBY_PHANTOM_FIELD_SRC = """\
class Order
  MAX_ITEMS = 99

  def initialize(buyer)
    @buyer = buyer
  end

  def update_total(price)
    @total = price * 2
  end

  def cache_result
    @cached = true
  end
end
"""


def test_ruby_class_level_constant_extracted() -> None:
    """Constants assigned at class body level must be extracted."""
    parser = _ruby_parser()
    tree = parser.parse(RUBY_PHANTOM_FIELD_SRC.encode())
    extractor = RubyElementExtractor()
    variables = extractor.extract_variables(tree, RUBY_PHANTOM_FIELD_SRC)

    names = [v.name for v in variables]
    assert "MAX_ITEMS" in names


def test_ruby_initialize_ivar_extracted() -> None:
    """@ivar assigned inside initialize IS a field and must be extracted."""
    parser = _ruby_parser()
    tree = parser.parse(RUBY_PHANTOM_FIELD_SRC.encode())
    extractor = RubyElementExtractor()
    variables = extractor.extract_variables(tree, RUBY_PHANTOM_FIELD_SRC)

    names = [v.name for v in variables]
    assert "buyer" in names  # @buyer from initialize


def test_ruby_non_initialize_ivar_not_extracted() -> None:
    """@ivar assigned inside non-initialize methods must NOT be extracted."""
    parser = _ruby_parser()
    tree = parser.parse(RUBY_PHANTOM_FIELD_SRC.encode())
    extractor = RubyElementExtractor()
    variables = extractor.extract_variables(tree, RUBY_PHANTOM_FIELD_SRC)

    names = [v.name for v in variables]
    assert "total" not in names  # from update_total
    assert "cached" not in names  # from cache_result


def test_ruby_exact_variable_count() -> None:
    """Exact count: 1 constant (MAX_ITEMS) + 1 ivar (@buyer) = 2."""
    parser = _ruby_parser()
    tree = parser.parse(RUBY_PHANTOM_FIELD_SRC.encode())
    extractor = RubyElementExtractor()
    variables = extractor.extract_variables(tree, RUBY_PHANTOM_FIELD_SRC)

    assert len(variables) == 2


# ---------------------------------------------------------------------------
# #763 — PHP enum methods have receiver_type=None
# ---------------------------------------------------------------------------

PHP_ENUM_SRC = b"""\
<?php
enum Suit {
    case Hearts;
    case Diamonds;

    public function label(): string {
        return match($this) {
            Suit::Hearts => "Hearts",
            Suit::Diamonds => "Diamonds",
        };
    }

    public static function fromSymbol(string $sym): self {
        return match($sym) {
            'H' => self::Hearts,
            'D' => self::Diamonds,
        };
    }
}
"""


def test_php_enum_method_has_receiver_type() -> None:
    """Methods declared inside a PHP enum must have receiver_type == enum name."""
    parser = _php_parser()
    tree = parser.parse(PHP_ENUM_SRC)
    extractor = PHPElementExtractor()
    funcs = extractor.extract_functions(tree, PHP_ENUM_SRC.decode())

    label = next(f for f in funcs if f.name == "label")
    assert label.receiver_type == "Suit"


def test_php_enum_static_method_has_receiver_type() -> None:
    """Static methods inside a PHP enum must also carry receiver_type."""
    parser = _php_parser()
    tree = parser.parse(PHP_ENUM_SRC)
    extractor = PHPElementExtractor()
    funcs = extractor.extract_functions(tree, PHP_ENUM_SRC.decode())

    from_sym = next(f for f in funcs if f.name == "fromSymbol")
    assert from_sym.receiver_type == "Suit"


def test_php_enum_method_count() -> None:
    """Exact count: 2 methods in the Suit enum."""
    parser = _php_parser()
    tree = parser.parse(PHP_ENUM_SRC)
    extractor = PHPElementExtractor()
    funcs = extractor.extract_functions(tree, PHP_ENUM_SRC.decode())

    assert len(funcs) == 2


# ---------------------------------------------------------------------------
# #765 — PHP extract_functions namespace is order-dependent
# ---------------------------------------------------------------------------

PHP_NS_FUNC_SRC = b"""\
<?php
namespace App\\Services;

class UserService {
    public function getUser(): string {
        return "user";
    }
}

function helper(): void {}
"""


def test_php_top_level_function_name_consistent_when_called_standalone() -> None:
    """extract_functions called standalone must include the file namespace in
    top-level function names (App\\Services\\helper), not bare 'helper'."""
    parser = _php_parser()
    tree = parser.parse(PHP_NS_FUNC_SRC)
    src = PHP_NS_FUNC_SRC.decode()

    extractor = PHPElementExtractor()
    # Call extract_functions WITHOUT calling extract_classes first
    funcs = extractor.extract_functions(tree, src)

    helper = next(f for f in funcs if "helper" in f.name)
    assert helper.name == "App\\Services\\helper"


def test_php_top_level_function_name_consistent_after_extract_classes() -> None:
    """extract_functions called AFTER extract_classes must yield the same name
    as when called standalone (order-independence)."""
    parser = _php_parser()
    tree = parser.parse(PHP_NS_FUNC_SRC)
    src = PHP_NS_FUNC_SRC.decode()

    extractor = PHPElementExtractor()
    extractor.extract_classes(tree, src)  # sets current_namespace
    funcs = extractor.extract_functions(tree, src)

    helper = next(f for f in funcs if "helper" in f.name)
    assert helper.name == "App\\Services\\helper"


def test_php_no_namespace_function_has_bare_name() -> None:
    """A function in a file with no namespace declaration must keep its bare name."""
    src = b"<?php\nfunction myFunc(): void {}\n"
    parser = _php_parser()
    tree = parser.parse(src)
    extractor = PHPElementExtractor()
    funcs = extractor.extract_functions(tree, src.decode())

    assert len(funcs) == 1
    assert funcs[0].name == "myFunc"
