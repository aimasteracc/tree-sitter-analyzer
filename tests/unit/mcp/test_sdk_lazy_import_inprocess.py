"""#1675: package-init deferral semantics, on throwaway packages in-process."""

from __future__ import annotations

import sys
import textwrap

import pytest

from tree_sitter_analyzer.mcp._sdk_lazy_import import defer_sdk_package_inits

_PKG = "tsa_defer_fixture_pkg"


@pytest.fixture
def fake_packages(tmp_path, monkeypatch):
    """``pkg`` (init sets a name and counts runs) with ``pkg.sub`` and ``pkg.leaf``."""
    root = tmp_path / _PKG
    (root / "sub").mkdir(parents=True)
    (root / "__init__.py").write_text(
        textwrap.dedent(
            """
            import builtins
            builtins.TSA_DEFER_RUNS = getattr(builtins, "TSA_DEFER_RUNS", 0) + 1
            from .sub.thing import VALUE as EXPORTED
            __all__ = ["EXPORTED"]
            """
        ),
        encoding="utf-8",
    )
    (root / "sub" / "__init__.py").write_text("SUB_INIT_RAN = True\n", encoding="utf-8")
    (root / "sub" / "thing.py").write_text("VALUE = 42\n", encoding="utf-8")
    (root / "leaf.py").write_text("LEAF = 'leaf'\n", encoding="utf-8")
    (tmp_path / "tsa_defer_plain_module.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import builtins

    monkeypatch.setattr(builtins, "TSA_DEFER_RUNS", 0, raising=False)
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in (_PKG, "tsa_defer_plain_module"):
            del sys.modules[name]


def test_submodule_imports_do_not_run_the_package_init(fake_packages):
    import builtins

    assert defer_sdk_package_inits((_PKG, f"{_PKG}.sub")) is True
    from tsa_defer_fixture_pkg.sub.thing import VALUE  # noqa: E402

    assert VALUE == 42
    assert builtins.TSA_DEFER_RUNS == 0
    assert "SUB_INIT_RAN" not in vars(sys.modules[f"{_PKG}.sub"])
    # A submodule name resolves by importing it, still without the init.
    assert sys.modules[_PKG].leaf.LEAF == "leaf"
    assert builtins.TSA_DEFER_RUNS == 0


def test_an_init_defined_name_runs_the_init_exactly_once(fake_packages):
    import builtins

    defer_sdk_package_inits((_PKG,))
    package = sys.modules[_PKG]
    assert package.EXPORTED == 42
    assert package.__all__ == ["EXPORTED"]
    assert builtins.TSA_DEFER_RUNS == 1
    with pytest.raises(AttributeError):
        package.not_defined_anywhere  # noqa: B018
    assert builtins.TSA_DEFER_RUNS == 1


def test_missing_name_runs_the_init_then_raises(fake_packages):
    import builtins

    defer_sdk_package_inits((_PKG,))
    with pytest.raises(AttributeError, match="not_defined_anywhere"):
        sys.modules[_PKG].not_defined_anywhere  # noqa: B018
    assert builtins.TSA_DEFER_RUNS == 1
    assert sys.modules[_PKG].EXPORTED == 42


def test_dunder_probes_do_not_run_the_init(fake_packages):
    import builtins

    defer_sdk_package_inits((_PKG,))
    package = sys.modules[_PKG]
    assert not hasattr(package, "__wrapped__")
    assert package.__path__
    assert builtins.TSA_DEFER_RUNS == 0


def test_already_imported_missing_or_plain_modules_are_left_alone(fake_packages):
    import tsa_defer_fixture_pkg  # noqa: F401  (real import runs the init)

    assert defer_sdk_package_inits((_PKG,)) is False
    del sys.modules[_PKG]
    assert defer_sdk_package_inits(()) is False
    assert defer_sdk_package_inits(("tsa_defer_no_such_package",)) is False
    assert defer_sdk_package_inits(("tsa_defer_plain_module",)) is False
    assert "tsa_defer_plain_module" not in sys.modules
    # A child whose parent is not importable is skipped.
    assert (
        defer_sdk_package_inits(("tsa_defer_no_such_package", f"{_PKG}.sub")) is False
    )
