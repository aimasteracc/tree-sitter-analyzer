"""``scripts.wrong_complete.py_oracle`` 的单元测试：每条判定规则一例（不运行 TSA）。"""

from __future__ import annotations

import pytest

from scripts.wrong_complete.py_oracle import python_sites
from scripts.wrong_complete.sites import OTHER, POSSIBLE, TARGET, Target

_BASE = (
    "from typing import Optional, Protocol\n\n\n"
    "class Base:\n"
    "    def run(self):\n"
    "        return self.step()\n\n"
    "    def step(self):\n"
    "        return 0\n\n\n"
    "class Child(Base):\n"
    "    def step(self):\n"
    "        return super().step()\n\n\n"
    "class Other:\n"
    "    def step(self):\n"
    "        return 2\n\n\n"
    "class Port(Protocol):\n"
    "    def step(self): ...\n"
)
#: ``Child.step`` 定义在第 13 行。
_CHILD = Target("pkg/model.py", "step", "Child", 13)
_BASE_STEP = Target("pkg/model.py", "step", "Base", 8)


def _verdicts(
    files: dict[str, str], target: Target
) -> dict[tuple[str, int], tuple[str, str]]:
    return {s.key(): (s.verdict, s.reason) for s in python_sites(files, target)}


def _use(body: str) -> dict[str, str]:
    return {"pkg/__init__.py": "", "pkg/model.py": _BASE, "pkg/use.py": body}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "from .model import Child\n\n\ndef f():\n    return Child().step()\n",
            (TARGET, "constructed"),
        ),
        (
            "from .model import Base\n\n\ndef f():\n    return Base().step()\n",
            (OTHER, "constructed_other"),
        ),
        (
            "from .model import Base\n\n\ndef f(x: Base):\n    return x.step()\n",
            (POSSIBLE, "override_dispatch"),
        ),
        (
            "from .model import Child\n\n\ndef f(x: 'Child'):\n    return x.step()\n",
            (TARGET, "declared"),
        ),
        (
            "from typing import Optional\nfrom .model import Child\n\n\ndef f(x: Optional[Child]):\n    return x.step()\n",
            (TARGET, "declared"),
        ),
        (
            "from .model import Other\n\n\ndef f(x: Other):\n    return x.step()\n",
            (OTHER, "declared_other"),
        ),
        (
            "from .model import Port\n\n\ndef f(x: Port):\n    return x.step()\n",
            (POSSIBLE, "protocol_receiver"),
        ),
        ("def f(x):\n    return x.step()\n", (POSSIBLE, "unresolved_receiver")),
        (
            "from .model import Child as Kid\n\n\ndef f():\n    return Kid().step()\n",
            (TARGET, "constructed"),
        ),
        (
            "from . import model\n\n\ndef f():\n    return model.Child.step(None)\n",
            (TARGET, "class_object"),
        ),
        (
            "from .model import Child\n\n\ndef f():\n    k = Child\n    return k.step(None)\n",
            (TARGET, "class_object"),
        ),
        ("def f():\n    return 'x'.step()\n", (OTHER, "external_or_function_object")),
    ],
    ids=[
        "constructed-target",
        "constructed-base-is-static",
        "declared-base-may-dispatch",
        "string-annotation",
        "optional-annotation",
        "unrelated-declared-type",
        "protocol-receiver",
        "unresolved-receiver",
        "import-alias",
        "module-attribute-class",
        "local-class-alias",
        "builtin-literal",
    ],
)
def test_a_call_in_another_module_is_classified_by_its_receiver(
    body: str, expected: tuple[str, str]
) -> None:
    verdicts = _verdicts(_use(body), _CHILD)
    assert [v for (path, _), v in verdicts.items() if path == "pkg/use.py"] == [
        expected
    ]


def test_self_in_the_base_class_may_dispatch_to_the_override() -> None:
    # #1648 / #1677：``Base.run`` 里的 ``self.step()`` 对子类覆写是可能调用。
    assert _verdicts(_use(""), _CHILD)[("pkg/model.py", 6)] == (
        POSSIBLE,
        "override_dispatch",
    )


def test_self_in_the_base_class_binds_the_base_method() -> None:
    assert _verdicts(_use(""), _BASE_STEP)[("pkg/model.py", 6)] == (TARGET, "self")


def test_super_binds_the_parent_method() -> None:
    assert _verdicts(_use(""), _BASE_STEP)[("pkg/model.py", 14)] == (TARGET, "super")


def test_a_reference_in_a_dispatch_table_is_a_site() -> None:
    body = "from .model import Child\n\nTABLE = {'a': Child().step}\n\n\ndef f():\n    return TABLE['a']()\n"
    sites = [s for s in python_sites(_use(body), _CHILD) if s.file == "pkg/use.py"]
    assert [(s.line, s.kind, s.verdict) for s in sites] == [(3, "reference", TARGET)]


def test_getattr_with_the_literal_name_is_a_possible_reference() -> None:
    body = "def f(x):\n    return getattr(x, 'step')()\n"
    sites = [s for s in python_sites(_use(body), _CHILD) if s.file == "pkg/use.py"]
    assert [(s.line, s.kind, s.verdict) for s in sites] == [(2, "reference", POSSIBLE)]


def test_comments_and_strings_are_not_sites() -> None:
    body = "def f(x):\n    # x.step() is documented here\n    return 'x.step()'\n"
    assert [s for s in python_sites(_use(body), _CHILD) if s.file == "pkg/use.py"] == []


@pytest.mark.parametrize(
    ("body", "line", "reason"),
    [
        (
            "from .tools import tool\n\n\ndef f():\n    return tool(1)\n",
            5,
            "module_function",
        ),
        (
            "from .tools import tool as t2\n\n\ndef f():\n    return t2(1)\n",
            5,
            "function_alias",
        ),
        (
            "from . import tools\n\n\ndef f():\n    return tools.tool(1)\n",
            5,
            "module_attribute",
        ),
        (
            "import pkg.tools as tt\n\n\ndef f():\n    return tt.tool(1)\n",
            5,
            "module_attribute",
        ),
        (
            "from .tools import tool\n\nalias = tool\n\n\ndef f():\n    return alias(1)\n",
            7,
            "function_alias",
        ),
    ],
    ids=[
        "direct",
        "import-as",
        "module-attribute",
        "import-module-as",
        "assignment-alias",
    ],
)
def test_a_module_function_is_reached_through_its_aliases(
    body: str, line: int, reason: str
) -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/tools.py": "def tool(x):\n    return x\n",
        "pkg/use.py": body,
    }
    verdicts = _verdicts(files, Target("pkg/tools.py", "tool", None, 1))
    assert verdicts[("pkg/use.py", line)] == (TARGET, reason)


def test_a_same_named_function_elsewhere_is_other() -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/tools.py": "def tool(x):\n    return x\n",
        "pkg/more.py": "def tool(x):\n    return x\n",
        "pkg/use.py": "from .more import tool\n\n\ndef f():\n    return tool(1)\n",
    }
    assert _verdicts(files, Target("pkg/tools.py", "tool", None, 1)) == {
        ("pkg/use.py", 5): (OTHER, "other_function")
    }


def test_a_star_import_keeps_an_unbound_bare_call_possible() -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/tools.py": "def tool(x):\n    return x\n",
        "pkg/use.py": "from external_lib import *\n\n\ndef f():\n    return tool(1)\n",
    }
    assert _verdicts(files, Target("pkg/tools.py", "tool", None, 1)) == {
        ("pkg/use.py", 5): (POSSIBLE, "unknown_callable")
    }


def test_an_attribute_typed_in_init_is_resolved() -> None:
    body = (
        "from .model import Child\n\n\n"
        "class Holder:\n"
        "    def __init__(self):\n"
        "        self.child = Child()\n\n"
        "    def go(self):\n"
        "        return self.child.step()\n"
    )
    assert _verdicts(_use(body), _CHILD)[("pkg/use.py", 9)] == (TARGET, "constructed")
