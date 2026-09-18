"""NO1-010B E0 参考 transcript 的固定任务规格。"""

from __future__ import annotations

from dataclasses import dataclass

REFERENCE_TASK_ID = "no1-010b/0001-bugfix-dispatch-unknown-route"
_VERIFICATION_ARGV = (
    "uv",
    "run",
    "pytest",
    "tests/",
    "-q",
    "-p",
    "no:cacheprovider",
)


@dataclass(frozen=True)
class ReferenceReplacement:
    """描述一个必须唯一命中的固定文本替换。"""

    path: str
    before: str
    after: str


@dataclass(frozen=True)
class ReferenceEditSpec:
    """绑定一条预注册任务的检索目标、编辑与预期终态。"""

    task_class: str
    repo: str
    allowed_paths: tuple[str, ...]
    oracle: str
    oracle_baseline_reason: str
    verification_argv: tuple[str, ...]
    selected_tests: tuple[str, ...]
    search_symbol: str
    search_path: str
    edit_type: str
    summary: str
    changed_paths: tuple[str, ...]
    replacements: tuple[ReferenceReplacement, ...]
    terminal: tuple[str, str | None]


REFERENCE_EDIT_SPECS = {
    REFERENCE_TASK_ID: ReferenceEditSpec(
        task_class="bugfix",
        repo="fixtures/dispatch_app",
        allowed_paths=("src/dispatch.py", "tests/"),
        oracle="oracles/0001.py",
        oracle_baseline_reason="dispatch-returns-none",
        verification_argv=_VERIFICATION_ARGV,
        selected_tests=(),
        search_symbol="dispatch",
        search_path="src/dispatch.py",
        edit_type="fix_bug",
        summary="unknown route -> 404",
        changed_paths=("src/dispatch.py",),
        replacements=(
            ReferenceReplacement(
                "src/dispatch.py",
                "    return None\n",
                '    return Response(404, "not found")\n',
            ),
        ),
        terminal=("PASS", None),
    ),
    "no1-010b/0003-refactor-extract-route-registry": ReferenceEditSpec(
        task_class="refactor",
        repo="fixtures/dispatch_app",
        allowed_paths=("src/dispatch.py", "src/registry.py", "tests/"),
        oracle="oracles/0003.py",
        oracle_baseline_reason="route-table-inlined",
        verification_argv=_VERIFICATION_ARGV,
        selected_tests=(),
        search_symbol="dispatch",
        search_path="src/dispatch.py",
        edit_type="refactor",
        summary="move route table behind registry.resolve",
        changed_paths=("src/dispatch.py", "src/registry.py"),
        replacements=(
            ReferenceReplacement(
                "src/dispatch.py",
                'ROUTES = {\n    "/": "home",\n    "/health": "ok",\n}\n',
                "from .registry import resolve\n",
            ),
            ReferenceReplacement(
                "src/dispatch.py",
                "    if path in ROUTES:\n        return Response(200, ROUTES[path])\n",
                "    body = resolve(path)\n"
                "    if body is not None:\n"
                "        return Response(200, body)\n",
            ),
            ReferenceReplacement(
                "src/registry.py",
                "\n\ndef resolve(path: str) -> str | None:\n",
                '\n\n_ROUTES = {"/": "home", "/health": "ok"}\n\n\n'
                "def resolve(path: str) -> str | None:\n",
            ),
            ReferenceReplacement(
                "src/registry.py",
                "    return None\n",
                "    return _ROUTES.get(path)\n",
            ),
        ),
        terminal=("PASS", None),
    ),
    "no1-010b/0004-test-selection-dispatch-version": ReferenceEditSpec(
        task_class="test_selection",
        repo="fixtures/dispatch_app",
        allowed_paths=("src/dispatch.py", "tests/"),
        oracle="oracles/0004.py",
        oracle_baseline_reason="version-route-missing",
        verification_argv=_VERIFICATION_ARGV,
        selected_tests=("tests/test_dispatch.py",),
        search_symbol="dispatch",
        search_path="src/dispatch.py",
        edit_type="add_feature",
        summary="add /version route",
        changed_paths=("src/dispatch.py",),
        replacements=(
            ReferenceReplacement(
                "src/dispatch.py",
                '    "/health": "ok",\n',
                '    "/health": "ok",\n    "/version": "1",\n',
            ),
        ),
        terminal=("PASS", None),
    ),
    "no1-010b/0006-bugfix-cancel-unknown-order": ReferenceEditSpec(
        task_class="bugfix",
        repo="fixtures/orders_service",
        allowed_paths=("src/orders.py", "tests/"),
        oracle="oracles/0006.py",
        oracle_baseline_reason="cancel-raises-keyerror",
        verification_argv=_VERIFICATION_ARGV,
        selected_tests=(),
        search_symbol="cancel",
        search_path="src/orders.py",
        edit_type="fix_bug",
        summary="deliberately reject every cancellation",
        changed_paths=("src/orders.py",),
        replacements=(
            ReferenceReplacement(
                "src/orders.py",
                "    del _ORDERS[order_id]\n    return True\n",
                "    return False\n",
            ),
        ),
        terminal=("FAIL", "VERIFICATION_FAILED"),
    ),
    "no1-010b/0007-migration-drop-legacy-total": ReferenceEditSpec(
        task_class="migration",
        repo="fixtures/orders_service",
        allowed_paths=("src/orders.py", "src/totals.py", "tests/"),
        oracle="oracles/0007.py",
        oracle_baseline_reason="legacy-total-still-called",
        verification_argv=_VERIFICATION_ARGV,
        selected_tests=(),
        search_symbol="place",
        search_path="src/orders.py",
        edit_type="refactor",
        summary="migrate place from legacy_total to total",
        changed_paths=("src/orders.py",),
        replacements=(
            ReferenceReplacement(
                "src/orders.py",
                "from .totals import legacy_total\n",
                "from .totals import total\n",
            ),
            ReferenceReplacement(
                "src/orders.py",
                "    amount = legacy_total(quantity, unit_price)\n",
                "    amount = total(quantity, unit_price)\n",
            ),
        ),
        terminal=("PASS", None),
    ),
}
