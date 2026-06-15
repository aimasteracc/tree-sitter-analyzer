"""Regression tests for Ruby phantom-field bug #770.

_extract_assignment_variable emitted Variable for ANY assignment LHS:
  - local identifiers (user = new(...))
  - qualified targets (user.password_hash = ...)
  - index/element-reference targets (@cache[id] = value)
  - top-level lambdas/procs (validate_email = lambda { ... })

Only genuine @ivar, @@cvar, and CONSTANT assignments should be emitted.
"""

from __future__ import annotations

import pytest

try:
    import tree_sitter
    import tree_sitter_ruby

    RUBY_AVAILABLE = True
except ImportError:
    RUBY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not RUBY_AVAILABLE,
    reason="tree-sitter-ruby not installed (tracked: #770 environment dependency)",
)


def _parse(code: str):
    lang = tree_sitter.Language(tree_sitter_ruby.language())
    parser = tree_sitter.Parser(lang)
    return parser.parse(code.encode())


def _extract_vars(code: str):
    from tree_sitter_analyzer.languages.ruby_plugin import RubyElementExtractor

    tree = _parse(code)
    ext = RubyElementExtractor()
    return ext.extract_variables(tree, code)


# ---------------------------------------------------------------------------
# Phantom cases that must NOT be emitted
# ---------------------------------------------------------------------------


def test_local_variable_in_initialize_is_not_a_field():
    """Local variable assignment inside initialize must NOT become a field (#770).

    Uses a name (``temp_record``) that has no @ivar counterpart in the same
    code, so there is no naming collision after the ``@``-strip.
    """
    code = """\
class UserService
  def initialize(user_id)
    temp_record = find_by_id(user_id)
    @user_id = user_id
  end
end
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    assert "temp_record" not in names


def test_instance_variable_in_initialize_is_a_field():
    """@ivar assignment inside initialize MUST be emitted (#770 complement)."""
    code = """\
class UserService
  def initialize(user_id)
    temp_record = find_by_id(user_id)
    @user_id = user_id
  end
end
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    assert "user_id" in names


def test_qualified_assignment_is_not_a_field():
    """recv.attr = value (call target) must NOT become a field (#770)."""
    code = """\
class UserService
  def update(user_id)
    user = find_by_id(user_id)
    user.password_hash = "hash"  # pragma: allowlist secret
  end
end
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    assert "user.password_hash" not in names
    assert "password_hash" not in names


def test_index_assignment_is_not_a_field():
    """recv[key] = value (element_reference target) must NOT become a field (#770)."""
    code = """\
class UserService
  def initialize
    @cache = {}
  end

  def cache_user(id, user)
    @cache[id] = user
  end
end
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    # @cache itself is valid; @cache[id] must not appear
    assert "cache[id]" not in names
    assert "cache" in names


def test_toplevel_lambda_is_not_a_field():
    """Top-level lambda/proc assignments must NOT appear as fields (#770)."""
    code = """\
class Validator
  RULE = "strict"
end

validate_email = lambda { |e| e.include?("@") }
format_username = proc { |u| u.downcase }
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    assert "validate_email" not in names
    assert "format_username" not in names


# ---------------------------------------------------------------------------
# Real fields that MUST still be emitted
# ---------------------------------------------------------------------------


def test_real_ivar_still_extracted():
    """@ivar inside initialize must still be a field after the fix."""
    code = """\
class Order
  def initialize(total)
    @total = total
    @status = "pending"
  end
end
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    assert "total" in names
    assert "status" in names


def test_real_classvar_still_extracted():
    """@@cvar at class body level must still be a field after the fix."""
    code = """\
class Counter
  @@count = 0

  def initialize
    @@count += 1
  end
end
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    assert "count" in names


def test_real_constant_still_extracted():
    """CONSTANT assignment at class body level must still be a field after the fix."""
    code = """\
class Config
  MAX = 100
  TIMEOUT = 30
end
"""
    vars_ = _extract_vars(code)
    names = [v.name for v in vars_]
    assert "MAX" in names
    assert "TIMEOUT" in names


def test_exact_field_count_in_clean_class():
    """A class with exactly 2 @ivars and 1 @@cvar yields exactly 3 fields (#770)."""
    code = """\
class Account
  @@count = 0

  def initialize(name, balance)
    @name = name
    @balance = balance
    local_temp = 0
  end
end
"""
    vars_ = _extract_vars(code)
    assert len(vars_) == 3
