# Fixture: qualified call through a module alias.
# `from . import b as bb` binds the module object as `bb`; the call
# `bb.baz()` must resolve to the function `baz` defined in `b.py`.
# Expected resolution: callee_resolution='project',
# callee_resolved_file ends with 'b.py'.
from . import b as bb


def use_alias():
    bb.baz()
