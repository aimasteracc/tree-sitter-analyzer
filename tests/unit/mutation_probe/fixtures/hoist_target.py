"""Hoist-mutation target (RFC-0029 test-plan item 1).

compute() wraps _work() inside a context manager.  Hoisting the assignment
before the `with` block does not change the return value — demonstrating that
a test checking only the return value does NOT constrain the code.
"""

_calls: list[int] = []


class _Tracker:
    def __enter__(self) -> "_Tracker":
        return self

    def __exit__(self, *a: object) -> bool:
        return False


def compute() -> int:
    tracker = _Tracker()
    with tracker:
        value = _work()
        _calls.append(value)
    return value


def _work() -> int:
    return 42
