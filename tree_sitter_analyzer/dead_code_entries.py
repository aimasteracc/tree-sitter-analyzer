"""Functions the runtime or a framework calls without a project call site.

Split out of :mod:`.dead_code_analyzer` (#1941) so the entry-point rules are one
module the dead-code surfaces share: test files and test functions, known entry
names (``main``), and implicit callbacks (dunders, visitor methods, the IPython
rich-display protocol).
"""

from __future__ import annotations

import re

from .call_graph import FunctionRef

_KNOWN_ENTRY_PATTERNS = {
    "python": re.compile(
        r"^(main|__main__|setup|run|app|create_app|wsgi|asgi"
        r"|pytest_configure|unittest_main)$"
    ),
    "javascript": re.compile(r"^(main|start|bootstrap|run|handler|exports\.default)$"),
    "typescript": re.compile(r"^(main|start|bootstrap|run|handler)$"),
    "java": re.compile(r"^(main|init|destroy|doGet|doPost|service)$"),
    "go": re.compile(r"^(main|init|TestMain)$"),
    "c": re.compile(r"^(main|WinMain)$"),
    "cpp": re.compile(r"^(main|WinMain)$"),
    # Added alongside call_graph.py's language-parity fix (Codex P1 #1157):
    # rust/csharp/kotlin/swift all have one unambiguous entry-point
    # convention. ruby/php/lua are intentionally NOT added here — they
    # execute top-level script code directly rather than via a single named
    # entry function, so a regex guess would be as likely to be wrong as
    # right; dead-code detection for those three remains a known follow-up.
    "rust": re.compile(r"^(main)$"),
    "csharp": re.compile(r"^(Main)$"),
    "kotlin": re.compile(r"^(main)$"),
    "swift": re.compile(r"^(main)$"),
}

_TEST_FILE_PATTERNS = re.compile(
    r"(?:^test_|_test\.|\.test\.|\.spec\.|_spec\.|tests?/|Test\.py$)",
    re.IGNORECASE,
)

_PY_DUNDER = re.compile(r"^__\w+__$")
# 框架按命名约定分派的方法（``ast.NodeVisitor`` / docutils 访问器、``http.server``
# 处理器）：源码里从不按名字调用。#1941：IPython / Jupyter 按名字调用的富显示协议
# （``_repr_html_``、``_repr_mimebundle_``）同理。
_PY_CONVENTION_CALLBACK = re.compile(
    r"^(?:visit_\w+|depart_\w+|do_[A-Z]+|_repr_[a-z]+_)$"
)
# #1941：测试运行器按名字收集的测试函数。
_PY_TEST_FUNCTION = re.compile(r"^test", re.IGNORECASE)


def _is_test_file(file_path: str) -> bool:
    return bool(_TEST_FILE_PATTERNS.search(file_path.replace("\\", "/")))


def _is_known_entry(name: str, language: str) -> bool:
    pattern = _KNOWN_ENTRY_PATTERNS.get(language)
    if pattern:
        return bool(pattern.match(name))
    return False


def is_entry_point(func: FunctionRef, *, include_test_files: bool = False) -> bool:
    """A function the runtime or a framework calls without a project call site.

    Test files (unless analysed as code, ``include_test_files``), known entry
    names (``main``) and implicit callbacks (dunders, visitor methods). #1941:
    with ``include_test_files`` a test runner's ``test_*`` functions still are.
    """
    if _is_test_file(func.file_path):
        if not include_test_files or _PY_TEST_FUNCTION.match(func.name):
            return True
    return _is_known_entry(func.name, func.language) or _is_implicit_entry(func)


def _is_implicit_entry(func: FunctionRef) -> bool:
    """#1790：由运行时隐式调用的方法（``__init__`` / ``__call__`` /
    ``__post_init__`` / JS ``constructor`` ...）没有显式调用点，但不是死代码。"""
    if func.language == "python":
        return bool(
            _PY_DUNDER.match(func.name) or _PY_CONVENTION_CALLBACK.match(func.name)
        )
    if func.language in ("javascript", "typescript"):
        return func.name == "constructor"
    return False
