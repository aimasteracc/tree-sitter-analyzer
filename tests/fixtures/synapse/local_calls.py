# Fixture: file-local callee resolution.
# `foo` calls `bar`; both are defined in this single file.
# Expected resolution: callee_resolution='local', callee_symbol_id == bar's id,
# callee_resolved_file ends with 'local_calls.py'.


def foo():
    bar()


def bar():
    pass
