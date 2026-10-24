"""剧本对比用的微型 Python 项目及其问题集 (磁盘紧张时代替 TSA 自身)。

文件少于 on-the-fly 解析上限 (200)，因此无需构建 ``.ast-cache``。
每个问题路径上的名称在项目中只有一个定义 (``__measure__`` 除外，它本来就是
"实现者" 问题的对象)，基于名称的 oracle 因而精确。

用法::

    python benchmarks/agent-tasks/uql_guidance/fixture.py <目标目录>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "unified_query"))

from questions import Question  # noqa: E402

FILES: dict[str, str] = {
    "app/__init__.py": "",
    "app/colors.py": """\
def get_truecolor(value):
    return value % 256


def blend(a, b):
    return get_truecolor(a) + get_truecolor(b)


def to_hex(value):
    return hex(get_truecolor(value))
""",
    "app/render.py": """\
from app.colors import blend


def draw(a, b):
    return blend(a, b)


def paint(a):
    return blend(a, a)


def frame(a):
    return draw(a, a) + paint(a)
""",
    "app/console.py": """\
def set_cursor(x, y):
    return (x, y)


def move_up(n):
    return set_cursor(0, -n)


def move_down(n):
    return set_cursor(0, n)


def home():
    return set_cursor(0, 0)


def clear_line():
    return "\\r"
""",
    "app/measure.py": """\
class Text:
    def __measure__(self):
        return 1


class Panel:
    def __measure__(self):
        return 2


def measure_all(items):
    return sum(item.__measure__() for item in items)
""",
    "app/doc.py": """\
def pad_text(text, width):
    return text.ljust(width)


def fmt_header(title):
    return pad_text(title, 20)


def fmt_body(body):
    return pad_text(body, 40)


def adjust_len(text, width):
    return text[:width]


def export_doc(title, body):
    return fmt_header(title) + fmt_body(body)


def save(title, body):
    return export_doc(title, body)


def cli_main():
    return save("t", "b")
""",
    "tests/__init__.py": "",
    "tests/test_colors.py": """\
from app.colors import blend
from app.render import draw


def test_blend():
    assert blend(1, 2) == 3


def test_draw():
    assert draw(1, 1) == 2
""",
    "tests/test_console.py": """\
from app.console import move_up


def test_move_up():
    assert move_up(1) == (0, -1)
""",
    "tests/test_doc.py": """\
from app.doc import adjust_len, save


def test_save():
    assert save("a", "b")


def test_adjust():
    assert adjust_len("abc", 2) == "ab"
""",
}

QUESTIONS: list[Question] = [
    Question(
        "Q1",
        "callers_tests",
        "Who calls get_truecolor, and which tests cover those callers?",
        {"x": "get_truecolor"},
    ),
    Question(
        "Q2",
        "module_untested",
        "Functions in app/console.py that call set_cursor but have no tests.",
        {"module": "app/console.py", "y": "set_cursor"},
    ),
    Question(
        "Q3",
        "callers_depth",
        "Callers of blend up to two levels, restricted to app/.",
        {"x": "blend", "depth": 2, "prefix": "app/"},
    ),
    Question(
        "Q4",
        "implementers",
        "Classes implementing __measure__, with the functions that call it.",
        {"m": "__measure__"},
    ),
    Question(
        "Q5",
        "impact",
        "Impact of changing export_doc: transitive callers, tests and files.",
        {"x": "export_doc"},
    ),
    Question("Q6", "callers", "Who calls pad_text?", {"x": "pad_text"}),
    Question("Q7", "tests", "Which tests exercise adjust_len?", {"x": "adjust_len"}),
    Question(
        "Q8",
        "callees",
        "Which project functions does export_doc call?",
        {"x": "export_doc", "file": "app/doc.py"},
    ),
]


def write(target: Path) -> None:
    for rel, text in FILES.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    write(Path(sys.argv[1]))
