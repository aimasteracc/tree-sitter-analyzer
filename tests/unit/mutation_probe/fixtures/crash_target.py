"""Crash-on-mutation target (RFC-0029 test-plan item 4).

Hoisting ``path = _make(name)`` before ``with _Ctx() as name:`` makes ``name``
undefined at the hoist site, causing a NameError — a non-assertion crash that
must produce ``unknown / MUTATED_RUN_CRASHED``, not ``constrains``.
"""


class _Ctx:
    def __enter__(self) -> str:
        return "bound"

    def __exit__(self, *a: object) -> bool:
        return False


def get_bound() -> str:
    with _Ctx() as name:
        path = _make(name)
        return path


def _make(s: str) -> str:
    return s + "_path"
