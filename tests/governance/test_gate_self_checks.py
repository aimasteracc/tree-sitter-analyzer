"""Execute the ``--self-check`` mode of every first-party gate that has one.

RFC-0028 section 3.2 requires a gate with a live surface to carry a self-check
that fails when the gate stops watching, and requirement 4 requires that check to
be reached by a layer that actually runs it. A ``--self-check`` flag that nothing
invokes discharges requirement 1 and violates requirement 4, which is the same
defect shape section 3.2 exists to catch.

Enforcement layer, named per requirement 4: this module sits in
``tests/governance``, which ``pytest.ini`` lists in ``testpaths``, so
``uv run pytest`` collects it directly. It carries no marker, so it is also
selected by the ``reusable-test.yml`` matrix expressions ``-m "not slow and not
e2e and not network and not benchmark and not full_language"``. Pre-commit does
**not** run it; the blocking layer for this module is CI plus the local quick
gate.

The cwd assertions are not decoration. Two of these gates resolved their watch
base against the caller's cwd, so from ``scripts/`` they reported a clean scan of
nothing and exited 0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: A directory inside the repository that is not the repository root. Running the
#: gates from here is what reproduces the cwd-relative defect.
NON_ROOT_CWD = PROJECT_ROOT / "scripts"

#: One entry per gate: script, the interpreter that runs it, and the arguments
#: whose output must not depend on cwd. Every gate that carries a `--self-check`
#: is listed; `codemap-sync-check.sh` is the reference implementation (#1314).
GATES = (
    ("scripts/check_test_encoding.py", sys.executable, ("--baseline",)),
    ("scripts/check_ps_ascii.py", sys.executable, ()),
    ("scripts/check_loose_assertions.py", sys.executable, ("--baseline",)),
    ("scripts/check-test-file-names.sh", "bash", ()),
    ("scripts/check-local-artifacts.sh", "bash", ()),
    ("scripts/codemap-sync-check.sh", "bash", ()),
)

#: The gates whose ordinary mode is cheap enough to run twice on every test run.
CWD_INVARIANT_GATES = tuple(
    entry for entry in GATES if not entry[0].endswith("codemap-sync-check.sh")
)


def _run(
    script: str, interpreter: str, args: tuple[str, ...], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run *script* under *interpreter* from *cwd* and capture everything it reports."""
    return subprocess.run(
        [interpreter, str(PROJECT_ROOT / script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.mark.parametrize(("script", "interpreter", "_args"), GATES)
def test_gate_self_check_succeeds_outside_the_repository_root(
    script: str, interpreter: str, _args: tuple[str, ...]
) -> None:
    """A self-check must pass from any cwd, and must report the surface it saw."""
    result = _run(script, interpreter, ("--self-check",), NON_ROOT_CWD)

    assert result.returncode == 0, (
        f"{script} --self-check failed from {NON_ROOT_CWD}:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The success path prints a summary naming the size of the surface it checked.
    # Requiring output keeps a silent `return 0` from passing as a self-check.
    assert result.stdout.strip(), (
        f"{script} --self-check passed without reporting a surface"
    )


@pytest.mark.parametrize(("script", "interpreter", "args"), CWD_INVARIANT_GATES)
def test_gate_output_does_not_depend_on_the_working_directory(
    script: str, interpreter: str, args: tuple[str, ...]
) -> None:
    """The same tree must produce the same verdict from the root and from ``scripts/``."""
    from_root = _run(script, interpreter, args, PROJECT_ROOT)
    from_non_root = _run(script, interpreter, args, NON_ROOT_CWD)

    assert (from_non_root.returncode, from_non_root.stdout, from_non_root.stderr) == (
        from_root.returncode,
        from_root.stdout,
        from_root.stderr,
    ), (
        f"{script} changed output when run from {NON_ROOT_CWD} instead of {PROJECT_ROOT}:\n"
        f"root:     rc={from_root.returncode} stdout={from_root.stdout!r} "
        f"stderr={from_root.stderr!r}\n"
        f"non-root: rc={from_non_root.returncode} stdout={from_non_root.stdout!r} "
        f"stderr={from_non_root.stderr!r}"
    )
