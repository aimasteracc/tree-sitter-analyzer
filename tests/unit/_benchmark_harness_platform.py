"""Issue #1376：_benchmark_harness_platform 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

import pytest

POSIX_QUALIFICATION_TEST = pytest.mark.skipif(
    "os.name == 'nt'",
    reason="tracked: NO1-008A qualification requires openat/O_NOFOLLOW",
)


def mark_posix_qualification_section_tests(namespace):
    """显式接收调用模块的命名空间，保持原有末尾注册与行号边界。"""
    for name, candidate in tuple(namespace.items()):
        code = getattr(candidate, "__code__", None)
        if (
            name.startswith("test_")
            and code is not None
            and code.co_firstlineno > namespace["_POSIX_QUALIFICATION_SECTION_START"]
        ):
            namespace[name] = POSIX_QUALIFICATION_TEST(candidate)
