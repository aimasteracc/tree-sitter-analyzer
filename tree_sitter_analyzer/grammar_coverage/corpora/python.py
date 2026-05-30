"""Built-in Python corpus for grammar coverage auto-discovery."""

CORPUS: str = '''\
from __future__ import annotations
import os
import sys
from typing import Optional

CONSTANT = 42
_private: int = 0

type Point = tuple[int, int]


@decorator
def simple_function(x: int, y: int = 0) -> int:
    """Docstring."""
    assert x >= 0, "x must be non-negative"
    global _private
    _private = x
    while x > 0:
        x -= 1
        if x == 5:
            continue
        if x == 2:
            break
    return x + y


@decorator1
@decorator2
class MyClass(BaseClass):
    class_var: int = 0

    def __init__(self, value: int) -> None:
        self.value = value

    @property
    def prop(self) -> int:
        return self.value

    @staticmethod
    def static_method() -> None:
        pass

    @classmethod
    def class_method(cls) -> "MyClass":
        return cls(0)

    def nested(self) -> None:
        nonlocal_val = 0
        def inner() -> None:
            nonlocal nonlocal_val
            nonlocal_val = 1
        inner()


async def async_func(items: list[int]) -> None:
    await some_coroutine()
    async for item in items:
        async with context() as ctx:
            pass


def with_types(x: int, *args: str, **kwargs: bool) -> Optional[str]:
    if x > 0:
        return str(x)
    elif x == 0:
        return None
    else:
        raise ValueError("negative")


result = [x * 2 for x in range(10) if x % 2 == 0]
gen = (x for x in range(10))
d = {k: v for k, v in enumerate(range(5))}
s = {x for x in range(5)}

try:
    risky()
except ValueError as e:
    pass
except (TypeError, RuntimeError):
    raise
finally:
    cleanup()

with open("file") as f:
    data = f.read()

match command:
    case "quit":
        sys.exit(0)
    case "hello":
        print("hi")
    case _:
        pass

lam = lambda x, y: x + y

x = 10
del x
'''

# Python 2 legacy statements: tree-sitter-python grammar includes exec_statement /
# print_statement to support Python 2 code analysis.
# Python 3 interpreter cannot execute these, but tree-sitter parser recognises them.
CORPUS_EXTRA: list[bytes] = [
    b'exec "import os"\n',
    b'print "hello"\n',
    b'print "a", "b"\n',
]
