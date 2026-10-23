"""Python 已知答案用例（#1740 / #1758 / #1759 / #1772 / #1773）。"""

from __future__ import annotations

from tests.known_answer.cases import Case

# #1740（rich 形态）：局部类别名 ``_Style = Style`` 与未类型化的属性接收者 ``self.console``。
RICH_ALIAS = Case(
    case_id="py-1740-local-class-alias",
    issue="#1740",
    target_name="from_color",
    owner="Style",
    files={
        "rich/__init__.py": "",
        "rich/style.py": (
            "class Style:\n"
            "    @classmethod\n"
            "    def from_color(cls, color=None):  # target\n"
            "        return cls()\n"
        ),
        "rich/ansi.py": (
            "from .style import Style\n\n\n"
            "def decode(text):\n"
            "    _Style = Style\n"
            "    return _Style.from_color(text)  # gt\n\n\n"
            "def direct(text):\n"
            "    return Style.from_color(text)  # gt listed\n"
        ),
    },
)

RICH_ATTRIBUTE = Case(
    case_id="py-1740-untyped-attribute-receiver",
    issue="#1740",
    target_name="set_alt_screen",
    owner="Console",
    files={
        "rich/__init__.py": "",
        "rich/console.py": (
            "class Console:\n"
            "    def set_alt_screen(self, enable=True):  # target\n"
            "        return enable\n"
        ),
        "rich/live.py": (
            "class Live:\n"
            "    def __init__(self, console):\n"
            "        self.console = console\n\n"
            "    def start(self):\n"
            "        self.console.set_alt_screen(True)  # gt\n"
        ),
        "rich/bound.py": (
            "from .console import Console\n\n\n"
            "def run():\n"
            "    console = Console()\n"
            "    return console.set_alt_screen(False)  # gt listed\n"
        ),
    },
)

# #1758（rich ``Live.process_renderables``）：切片拷贝后接收者无类型，同文件声明了抽象方法。
UNRESOLVED_OVERRIDE = Case(
    case_id="py-1758-unresolved-receiver-other-file-override",
    issue="#1758",
    target_name="process_renderables",
    owner="Live",
    files={
        "rich/__init__.py": "",
        "rich/console.py": (
            "from abc import ABC, abstractmethod\n"
            "from typing import List\n\n\n"
            "class RenderHook(ABC):\n"
            "    @abstractmethod\n"
            "    def process_renderables(self, renderables):\n"
            "        raise NotImplementedError\n\n\n"
            "class Console:\n"
            "    def __init__(self):\n"
            "        self._render_hooks: List[RenderHook] = []\n\n"
            "    def render(self, renderables):\n"
            "        render_hooks = self._render_hooks[:]\n"
            "        for hook in render_hooks:\n"
            "            renderables = hook.process_renderables(renderables)  # gt\n"
            "        return renderables\n"
        ),
        "rich/live.py": (
            "from .console import RenderHook\n\n\n"
            "class Live(RenderHook):\n"
            "    def process_renderables(self, renderables):  # target\n"
            "        return renderables\n"
        ),
    },
)

# #1759：声明文件里的计算调用（``_format_map[code](...)``）不能是方法的调用。
COMPUTED_IN_DECLARING_FILE = Case(
    case_id="py-1759-computed-call-in-declaring-file",
    issue="#1759",
    target_name="alt_screen",
    owner="Control",
    files={
        "rich/__init__.py": "",
        "rich/control.py": (
            "_format_map = {1: str, 2: repr}\n\n\n"
            "class Control:\n"
            "    def alt_screen(self, *parameters):  # target\n"
            "        return [_format_map[code](*parameters) for code in (1, 2)]\n\n"
            "    def home(self):\n"
            "        return self.alt_screen(1)  # gt listed\n"
        ),
    },
)


def _protocol_project(*, typed: bool, nested: bool) -> dict[str, str]:
    """#1772 的 pydantic 形态：Protocol 存根 + 注解（或不注解）的分派循环 + 测试里的结构实现。"""
    annotation = ": Iterable[PluginProtocol]" if typed else ""
    impl = (
        "from pkg.use import build\n\n\n"
        "def test_structural():\n"
        "    class Plugin1:\n"
        "        def new_validator(self, schema):  # target\n"
        "            return schema\n\n"
        "    assert build({}, [Plugin1()]) == [{}]\n"
        if nested
        else "from pkg.use import build\n\n\n"
        "class Plugin1:\n"
        "    def new_validator(self, schema):  # target\n"
        "        return schema\n\n\n"
        "def test_structural():\n"
        "    assert build({}, [Plugin1()]) == [{}]\n"
    )
    return {
        "pkg/__init__.py": (
            "from typing import Protocol\n\n\n"
            "class PluginProtocol(Protocol):\n"
            "    def new_validator(self, schema): ...\n"
        ),
        "pkg/use.py": (
            "from typing import Iterable\n\nfrom . import PluginProtocol\n\n\n"
            f"def build(schema, plugins{annotation}):\n"
            "    out = []\n"
            "    for plugin in plugins:\n"
            "        out.append(plugin.new_validator(schema))  # gt\n"
            "    return out\n"
        ),
        "tests/__init__.py": "",
        "tests/test_plugins.py": impl,
    }


PROTOCOL_CASES = tuple(
    Case(
        case_id=f"py-1772-protocol-stub-test-shadow-{'typed' if typed else 'untyped'}-{'nested' if nested else 'module'}",
        issue="#1772",
        target_name="new_validator",
        owner="Plugin1",
        files=_protocol_project(typed=typed, nested=nested),
    )
    for typed in (True, False)
    for nested in (False, True)
)

# #1773：``@overload`` 存根与实现是同一个可调用对象；``self.constrain`` 的兄弟方法都是调用方。
OVERLOAD = Case(
    case_id="py-1773-overload-stubs",
    issue="#1773",
    target_name="constrain",
    owner="_Pipeline",
    files={
        "pydantic/__init__.py": "",
        "pydantic/pipeline.py": (
            "from typing import overload\n\n\n"
            "class _Pipeline:\n"
            "    @overload\n"
            "    def constrain(self, c: int) -> int: ...\n\n"
            "    @overload\n"
            "    def constrain(self, c: str) -> str: ...\n\n"
            "    def constrain(self, c):  # target\n"
            "        return c\n\n"
            "    def gt(self, value):\n"
            "        return self.constrain(value)  # gt listed\n\n"
            "    def lt(self, value):\n"
            "        return self.constrain(value)  # gt listed\n"
        ),
    },
)

PYTHON_CASES: tuple[Case, ...] = (
    RICH_ALIAS,
    RICH_ATTRIBUTE,
    UNRESOLVED_OVERRIDE,
    COMPUTED_IN_DECLARING_FILE,
    *PROTOCOL_CASES,
    OVERLOAD,
)
