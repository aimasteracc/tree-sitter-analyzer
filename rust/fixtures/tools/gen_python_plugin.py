#!/usr/bin/env python3
"""生成 rust/fixtures/ 下的 PyPI v3.1.2 真实黄金输出(Stage 1 录音脚本)。

设计约束(SPEC §3 / 任务要求):
- 所有产物必须来自真实运行 v3.1.2 解释器,绝不手写期望值;
- 只写 rust/fixtures/ 之内,绝不触碰 Python 源码树或 SPEC.md;
- 固定 cwd 为仓库根,全部用相对路径,避免绝对路径进入 fixtures;
- 唯一归一化:analysis_time -> null(SPEC §3 允许删除/固定的字段)。

用法(在仓库根目录执行):
    /tmp/tsa-v312-venv/bin/python rust/fixtures/tools/gen_python_plugin.py
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 常量:路径 / 版本锚点
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[3]          # .../rust/fixtures/tools -> 仓库根
FIXTURES_ROOT = SCRIPT_PATH.parents[1]      # .../rust/fixtures
PLUGIN_DIR = FIXTURES_ROOT / "python_plugin"
SNIPPETS_DIR = PLUGIN_DIR / "snippets"

CORPUS_PY = "tests/golden/corpus_python.py"                      # 只读解析对象
GOLDEN_EXPECTED = "tests/golden/corpus_python_expected.json"     # 只读复制源
MISSING_FILE = "tests/golden/__nonexistent_fixture__.py"         # 错误路径探针

GIT_COMMIT = "f95da6035a1191add763d254aa36313037dbabe3"
TSA_EXPECTED_VERSION = "3.1.2"

# JST 固定 +09:00 偏移,避免依赖系统 tzdata
JST = timezone(timedelta(hours=9))


def die(message: str) -> None:
    """守卫失败即终止:带前缀打印,避免与被测库的日志混淆。"""
    raise SystemExit(f"[gen_python_plugin] FATAL: {message}")


# ---------------------------------------------------------------------------
# 环境守卫:确认拿到的是 venv 里的 v3.1.2,而不是仓库内源码树
# ---------------------------------------------------------------------------

def guard_environment() -> None:
    """固定 cwd 并校验 tree_sitter_analyzer 解析自当前 venv 且版本为 3.1.2。"""
    # 固定 cwd = 仓库根,保证相对路径与回显的 file_path 确定(SPEC §3)
    if not (REPO_ROOT / CORPUS_PY).is_file():
        die(f"仓库根定位失败:未找到 {REPO_ROOT / CORPUS_PY}")
    os.chdir(REPO_ROOT)

    import tree_sitter_analyzer  # 延迟导入:先完成 cwd 固定再解析

    pkg_path = Path(tree_sitter_analyzer.__file__).resolve()
    version = getattr(tree_sitter_analyzer, "__version__", None)
    if version != TSA_EXPECTED_VERSION:
        die(f"tree_sitter_analyzer 版本为 {version!r},期望 {TSA_EXPECTED_VERSION!r}")
    if not pkg_path.is_relative_to(Path(sys.prefix)):
        die(f"误用仓库外非 venv 安装:{pkg_path}(sys.prefix={sys.prefix})")
    if pkg_path.is_relative_to(REPO_ROOT):
        die(f"误用了仓库内源码树而非 venv 安装:{pkg_path}")
    print(f"[guard] tree_sitter_analyzer {version} @ {pkg_path}")


# ---------------------------------------------------------------------------
# 归一化与写出
# ---------------------------------------------------------------------------

def normalize(obj: Any) -> Any:
    """递归归一化:analysis_time -> null(SPEC §3 唯一允许的时间字段处理)。"""
    if isinstance(obj, dict):
        return {
            key: None if key == "analysis_time" else normalize(value)
            for key, value in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [normalize(item) for item in obj]
    return obj


def write_json(rel_path: Path, payload: Any) -> None:
    """以 UTF-8 / indent=2 写出 JSON,并立即回读校验可解析。"""
    rel_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    rel_path.write_text(text, encoding="utf-8")
    json.loads(rel_path.read_text(encoding="utf-8"))  # 写后即验
    print(f"[write] {rel_path} ({len(text.encode('utf-8'))} bytes)")


# ---------------------------------------------------------------------------
# 步骤 1:逐字节复制仓内黄金计数(基线冻结版本)
# ---------------------------------------------------------------------------

def step1_copy_golden_expected() -> None:
    src = REPO_ROOT / GOLDEN_EXPECTED
    dst = PLUGIN_DIR / "corpus_python_expected.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    # 校验:字节级一致 + 可解析
    if dst.read_bytes() != src.read_bytes():
        die(f"复制不一致:{src} -> {dst}")
    json.loads(dst.read_text(encoding="utf-8"))
    print(f"[copy ] {GOLDEN_EXPECTED} -> {dst}(逐字节一致)")


# ---------------------------------------------------------------------------
# 步骤 2:tree-sitter 直解,统计全部命名节点类型
# ---------------------------------------------------------------------------

def count_named_nodes(source: bytes) -> tuple[dict[str, int], int]:
    """遍历语法树,返回(按类型名排序的命名节点计数,命名节点总数)。"""
    import tree_sitter
    import tree_sitter_python

    language = tree_sitter.Language(tree_sitter_python.language())
    parser = tree_sitter.Parser(language)
    tree = parser.parse(source)
    if tree.root_node.has_error:
        die("corpus 解析出现语法错误,产物不可信")

    counts: dict[str, int] = {}
    total = 0
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.is_named:
            counts[node.type] = counts.get(node.type, 0) + 1
            total += 1
        stack.extend(reversed(node.children))  # 保持先序遍历顺序稳定

    return dict(sorted(counts.items())), total


def dependency_versions() -> dict[str, str]:
    """记录 grammar 侧版本(SPEC §3:每份产物须记录生成侧 grammar 版本)。"""
    from importlib.metadata import version

    return {
        "tree_sitter": version("tree-sitter"),
        "tree_sitter_python": version("tree-sitter-python"),
    }


def step2_node_types() -> None:
    source = (REPO_ROOT / CORPUS_PY).read_bytes()
    counts, total = count_named_nodes(source)
    payload = {
        "source_file": CORPUS_PY,
        "description": "tree_sitter_python 直解 tests/golden/corpus_python.py 的全部命名 AST 节点类型计数",
        "parser": "tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))",
        "versions": dependency_versions(),
        "total_named_nodes": total,
        "distinct_named_node_types": len(counts),
        "named_node_counts": counts,
    }
    write_json(PLUGIN_DIR / "corpus_python_node_types.json", payload)


# ---------------------------------------------------------------------------
# 步骤 3:PythonPlugin 元数据 + analyze_file 全量序列化
# ---------------------------------------------------------------------------

def elements_by_type(result: Any) -> dict[str, list[dict[str, Any]]]:
    """按 element_type 分组序列化元素(函数/类/变量/导入及其完整属性)。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for element in result.elements or []:
        row = element.to_dict() if hasattr(element, "to_dict") else dict(vars(element))
        groups.setdefault(element.element_type, []).append(row)
    return dict(sorted(groups.items()))


def run_plugin_analysis(plugin: Any, rel_path: str) -> Any:
    """以 anyio.run 驱动 plugin.analyze_file(任务指定的调用形态)。"""
    import anyio

    from tree_sitter_analyzer.core.request import AnalysisRequest

    request = AnalysisRequest(file_path=rel_path)
    return anyio.run(plugin.analyze_file, rel_path, request)


def step3_plugin_analysis(plugin: Any) -> None:
    result = run_plugin_analysis(plugin, CORPUS_PY)

    raw_queries = plugin.get_supported_queries()
    if isinstance(raw_queries, dict):  # 兼容可能的返回形态变化
        queries_sorted = sorted(raw_queries.keys())
        queries_form = "dict"
    else:
        queries_sorted = sorted(raw_queries)
        queries_form = "list"

    payload = {
        "request": {
            "call": "anyio.run(plugin.analyze_file, file_path, AnalysisRequest(file_path=...))",
            "file_path": CORPUS_PY,
            "cwd": ".",
        },
        "plugin_metadata": {
            "language_name": plugin.get_language_name(),
            "file_extensions": list(plugin.get_file_extensions()),
            "supported_queries_sorted": queries_sorted,
            "supported_queries_return_form": queries_form,
            "supported_queries_count": len(queries_sorted),
            "element_categories": dict(sorted(plugin.get_element_categories().items())),
        },
        "analysis": {
            "line_count": result.line_count,
            "node_count": result.node_count,
            "success": result.success,
            "error_message": result.error_message,
        },
        "to_dict": normalize(result.to_dict()),
        "to_mcp_format": normalize(result.to_mcp_format()),
        "elements_by_type": normalize(elements_by_type(result)),
    }
    write_json(PLUGIN_DIR / "corpus_python_plugin_analysis.json", payload)


# ---------------------------------------------------------------------------
# 步骤 4:api.analyze_file 成功路径 + 缺失文件错误路径
# ---------------------------------------------------------------------------

def step4_api_analysis() -> None:
    from tree_sitter_analyzer.api import analyze_file

    success_result = analyze_file(CORPUS_PY, language="python")

    # 错误路径:缺失文件(v3.1.2 实测抛 FileNotFoundError,须原样记录)
    try:
        returned = analyze_file(MISSING_FILE, language="python")
        missing_case: dict[str, Any] = {
            "raised": False,
            "returned": normalize(returned),
        }
    except Exception as exc:  # noqa: BLE001 - 录音脚本需要捕获任意异常形态
        missing_case = {
            "raised": True,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "exception_repr": repr(exc),
        }

    payload = {
        "request": {
            "call": "tree_sitter_analyzer.api.analyze_file(file_path, language='python')",
            "cwd": ".",
        },
        "success_case": {
            "file_path": CORPUS_PY,
            "result": normalize(success_result),
        },
        "missing_file_case": {
            "file_path": MISSING_FILE,
            **missing_case,
        },
    }
    write_json(PLUGIN_DIR / "api_analyze_corpus_python.json", payload)


# ---------------------------------------------------------------------------
# 步骤 5:边角片段 + 逐片段真实分析
# ---------------------------------------------------------------------------

SNIPPETS: dict[str, str] = {
    "async_gen.py": '''"""异步生成器与 yield 形态。"""


async def counter(start: int, stop: int):
    """异步生成器:依次产出 [start, stop) 的整数。"""
    current = start
    while current < stop:
        yield current
        current += 1


async def relay(source):
    """转发另一个异步迭代器产出的值。"""
    async for item in source:
        yield item


def numbers():
    """普通生成器:使用 yield from 委托。"""
    yield from range(3)


class AsyncPipeline:
    """消费异步生成器的管道。"""

    async def collect(self, source):
        """把异步生成器的产出收集为列表。"""
        results = []
        async for value in source:
            results.append(value)
        return results


async def main() -> None:
    """驱动上述异步生成器。"""
    pipeline = AsyncPipeline()
    doubled = [n async for n in counter(0, 5)]
    await pipeline.collect(counter(0, 3))
    return doubled
''',
    "decorators_class.py": '''"""类上的装饰器形态。"""

from dataclasses import dataclass


def audit(action: str):
    """自定义装饰器工厂:记录审计动作。"""

    def wrap(func):
        def inner(*args, **kwargs):
            return func(*args, **kwargs)

        return inner

    return wrap


class Registry:
    """演示内建与自定义装饰器的类。"""

    _created = 0

    def __init__(self, name: str) -> None:
        self.name = name
        Registry._created += 1

    @property
    def display_name(self) -> str:
        """展示用的大写名称。"""
        return self.name.upper()

    @display_name.setter
    def display_name(self, value: str) -> None:
        self.name = value.lower()

    @staticmethod
    def created_count() -> int:
        """已创建的实例数。"""
        return Registry._created

    @classmethod
    def reset(cls) -> None:
        """重置实例计数。"""
        cls._created = 0


@dataclass
class Point:
    """数据类:坐标点。"""

    x: float
    y: float
    label: str = "origin"


@audit("compute")
def distance(point: Point) -> float:
    """被自定义装饰器修饰的函数。"""
    return (point.x ** 2 + point.y ** 2) ** 0.5
''',
    "abc_exceptions.py": '''"""抽象基类与异常层级。"""

from abc import ABC, abstractmethod


class Storage(ABC):
    """抽象存储后端。"""

    @abstractmethod
    def load(self, key: str):
        """按键读取值。"""

    @abstractmethod
    def save(self, key: str, value) -> None:
        """按键持久化值。"""


class ReadOnlyStorage(Storage):
    """只实现 load 的具体存储。"""

    def load(self, key: str):
        return {"status": "read-only"}


class AnalyzerError(Exception):
    """分析器失败的基础错误。"""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class ParseError(AnalyzerError):
    """源码无法解析时抛出。"""


class ValidationError(AnalyzerError):
    """输入校验失败时抛出。"""


def validate(data: dict) -> None:
    """缺失键时抛出 ValidationError。"""
    if "name" not in data:
        raise ValidationError("missing name", code=2)
''',
    "imports_constants.py": '''"""导入形态与模块级常量(仅解析,不执行)。"""

import os
import sys as system
from collections import OrderedDict
from typing import Any, Dict, List as PyList
from os import path as ospath
from . import sibling
from .helpers import util
from math import *

MAX_RETRIES: int = 3
DEFAULT_TIMEOUT: float = 30.0
APP_NAME = "tsa-fixture"
_FLAGS = frozenset({"fast", "safe"})

__version__ = "1.2.3"
__all__ = ["APP_NAME", "MAX_RETRIES"]

cache: Dict[str, PyList[Any]] = {}
enabled: bool = True
''',
    "complexity.py": '''"""控制流形态:复杂度公式涉及的全部决策节点。"""


def classify(value: int) -> str:
    """if / elif / else 阶梯 + 三元表达式。"""
    if value < 0:
        label = "negative"
    elif value == 0:
        label = "zero"
    elif value < 10:
        label = "small"
    else:
        label = "large"
    parity = "even" if value % 2 == 0 else "odd"
    return f"{label}/{parity}"


def scan(items: list) -> dict:
    """for / while / 布尔运算 / 各类推导式。"""
    found = {}
    for index, item in enumerate(items):
        if item and isinstance(item, (int, float)):
            found[index] = item
    cursor = 0
    while cursor < len(items) and items[cursor] is not None:
        cursor += 1
    squares = [x * x for x in items if x is not None]
    lookup = {x: i for i, x in enumerate(items)}
    unique = {abs(x) for x in squares}
    total = sum(x for x in squares if x > 0)
    return found if not lookup or len(squares) > 0 else lookup


def risky(text) -> str:
    """try / except / else / finally。"""
    try:
        result = text.strip()
    except AttributeError as error:
        result = str(error)
    except (TypeError, ValueError):
        result = ""
    else:
        result = result or "empty"
    finally:
        done = True
    return result


def route(command: str) -> str:
    """match / case 分派。"""
    match command:
        case "start" | "run":
            state = "running"
        case "stop":
            state = "stopped"
        case str() as name if name.isupper():
            state = "signal"
        case _:
            state = "unknown"
    return state
''',
}


def step5_edge_cases(plugin: Any) -> None:
    SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    cases = []
    for filename in sorted(SNIPPETS):
        rel_path = f"rust/fixtures/python_plugin/snippets/{filename}"
        (SNIPPETS_DIR / filename).write_text(SNIPPETS[filename], encoding="utf-8")
        print(f"[write] {rel_path} ({len(SNIPPETS[filename].encode('utf-8'))} bytes)")

        result = run_plugin_analysis(plugin, rel_path)
        source = (REPO_ROOT / rel_path).read_bytes()
        named_counts, named_total = count_named_nodes(source)
        cases.append(
            {
                "file": rel_path,
                "analysis": {
                    "line_count": result.line_count,
                    "node_count": result.node_count,
                    "success": result.success,
                    "error_message": result.error_message,
                },
                "to_dict": normalize(result.to_dict()),
                "elements_by_type": normalize(elements_by_type(result)),
                "named_node_counts": named_counts,
                "total_named_nodes": named_total,
            }
        )

    payload = {
        "description": "5 个聚焦片段的 PythonPlugin().analyze_file 真实输出(片段由生成脚本落盘)",
        "request": {
            "call": "anyio.run(plugin.analyze_file, file_path, AnalysisRequest(file_path=...))",
            "cwd": ".",
        },
        "versions": dependency_versions(),
        "cases": cases,
    }
    write_json(PLUGIN_DIR / "edge_cases_analysis.json", payload)


# ---------------------------------------------------------------------------
# 步骤 6:MANIFEST.json
# ---------------------------------------------------------------------------

def pip_freeze() -> tuple[str, list[str]]:
    """优先 venv 内 pip,其次 uv pip freeze;返回(所用命令, 包清单)。"""
    candidates = [
        [sys.executable, "-m", "pip", "list", "--format=freeze"],
        ["uv", "pip", "freeze", "--python", sys.executable],
    ]
    for command in candidates:
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            continue
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode == 0 and lines:
            return " ".join(command), lines
    die("无法获取 venv 包清单(pip 与 uv 均不可用)")


def step6_manifest() -> None:
    freeze_command, freeze_lines = pip_freeze()
    manifest_rel = FIXTURES_ROOT / "MANIFEST.json"

    # 文件清单:fixtures 下全部文件(含本清单自身,写出后即存在)
    files = sorted(
        f"rust/fixtures/{path.relative_to(FIXTURES_ROOT).as_posix()}"
        for path in FIXTURES_ROOT.rglob("*")
        if path.is_file()
    )
    if "rust/fixtures/MANIFEST.json" not in files:
        files.append("rust/fixtures/MANIFEST.json")
        files.sort()

    payload = {
        "tsa_version": TSA_EXPECTED_VERSION,
        "git_commit": GIT_COMMIT,
        "generated_at_jst": datetime.now(JST).isoformat(timespec="seconds"),
        "generator": {
            "script": "rust/fixtures/tools/gen_python_plugin.py",
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "invocation": (
                "/tmp/tsa-v312-venv/bin/python rust/fixtures/tools/gen_python_plugin.py"
                " (cwd = 仓库根)"
            ),
        },
        "grammar_versions": dependency_versions(),
        "pip_freeze": {
            "command": freeze_command,
            "packages": freeze_lines,
        },
        "normalization_rules": [
            "analysis_time(任意层级)一律置为 null;不做其他改写(SPEC §3)",
            "固定 cwd 为仓库根,所有 file_path 用相对路径,产物不含绝对路径",
            "named_node_counts 按类型名排序;元素按 element_type 分组、保持抽取顺序",
            "corpus_python_expected.json 为仓内黄金文件的逐字节只读副本",
            "片段源码内嵌于生成脚本,先落盘再走同一 analyze_file 录音路径",
        ],
        "files": files,
    }
    write_json(manifest_rel, payload)


# ---------------------------------------------------------------------------
# 终验:fixtures 下所有 JSON 必须可解析且非空
# ---------------------------------------------------------------------------

def final_verification() -> None:
    json_files = sorted(FIXTURES_ROOT.rglob("*.json"))
    if not json_files:
        die("终验失败:fixtures 下没有任何 JSON")
    for path in json_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data:
            die(f"终验失败:{path} 内容为空")
        print(f"[verify] {path.relative_to(REPO_ROOT)} OK")
    print(f"[verify] 共 {len(json_files)} 个 JSON 全部解析通过")


def main() -> None:
    guard_environment()

    from tree_sitter_analyzer.languages.python_plugin import PythonPlugin

    plugin = PythonPlugin()

    step1_copy_golden_expected()
    step2_node_types()
    step3_plugin_analysis(plugin)
    step4_api_analysis()
    step5_edge_cases(plugin)
    step6_manifest()
    final_verification()
    print("[done] 全部 v3.1.2 黄金产物生成完毕")


if __name__ == "__main__":
    main()
