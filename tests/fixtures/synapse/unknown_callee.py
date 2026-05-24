# Fixture: fallback to 'unknown'.
# `mystery_func` is neither defined locally, nor imported, nor in the
# stdlib allowlist. Expected resolution: callee_resolution='unknown',
# callee_symbol_id IS NULL, callee_resolved_file=''.


def caller():
    mystery_func()  # noqa: F821 -- intentionally undefined for resolver test
