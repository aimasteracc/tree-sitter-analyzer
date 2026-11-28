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


def _posix_shell() -> str:
    """A POSIX shell that can actually run the gates, or ``""`` if none can.

    On Windows, ``bash`` on PATH is WSL's launcher, which answers "Windows
    Subsystem for Linux has no installed distributions" on a runner without WSL
    and exits non-zero. Git for Windows ships the shell the pre-commit hooks run
    under, so prefer it there — the same path
    ``tests/unit/mcp/test_verification_command.py`` already uses.
    """
    candidates = ["bash"]
    if sys.platform == "win32":
        candidates = [
            "C:/Program Files/Git/bin/bash.exe",
            "C:/Program Files (x86)/Git/bin/bash.exe",
            *candidates,
        ]
    for candidate in candidates:
        try:
            probe = subprocess.run(
                [candidate, "-c", "exit 0"],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except OSError:
            continue
        if probe.returncode == 0:
            return candidate
    return ""


#: Resolved once: the shell the three `.sh` gates are exercised under.
BASH = _posix_shell()

#: One entry per gate: script, the interpreter that runs it, and the arguments
#: whose output must not depend on cwd. Every gate that carries a `--self-check`
#: is listed; `codemap-sync-check.sh` is the reference implementation (#1314).
GATES = (
    ("scripts/check_test_encoding.py", sys.executable, ("--baseline",)),
    ("scripts/check_ps_ascii.py", sys.executable, ()),
    ("scripts/check_loose_assertions.py", sys.executable, ("--baseline",)),
    ("scripts/check-test-file-names.sh", BASH, ()),
    ("scripts/check-local-artifacts.sh", BASH, ()),
    ("scripts/codemap-sync-check.sh", BASH, ()),
)

#: Gates whose ordinary mode ``ast.parse``s the whole test tree (~1450 files).
#: Run twice on the real tree they take 15-25 s per run on an idle machine and
#: crossed the 30 s limit on slow runners (ubuntu 3.10 run 40099198915; macOS
#: shard 1/2 run 42071993107). They are exercised on a small fixture repository
#: instead (see ``test_whole_tree_gate_output_does_not_depend_on_the_working_directory``);
#: the real tree is still covered by their ``--self-check`` cases.
WHOLE_TREE_GATES = frozenset(
    {"scripts/check_test_encoding.py", "scripts/check_loose_assertions.py"}
)

#: The gates whose ordinary mode is cheap enough to run twice on every test run.
CWD_INVARIANT_GATES = tuple(
    entry
    for entry in GATES
    if not entry[0].endswith("codemap-sync-check.sh")
    and entry[0] not in WHOLE_TREE_GATES
)

#: The whole-tree gates, in the shape the fixture test parametrises over.
FIXTURE_TREE_GATES = tuple(entry for entry in GATES if entry[0] in WHOLE_TREE_GATES)


def test_a_posix_shell_is_available_for_the_shell_gates() -> None:
    """The `.sh` gates must be exercised, not quietly skipped.

    An unresolved shell would make every `.sh` case below unrunnable; passing
    here without one would turn the whole module into a check that cannot fail.
    """
    assert BASH, (
        "no usable POSIX shell: `bash` was not found, or (on Windows) it is WSL's "
        "launcher with no distribution installed. Git for Windows provides one at "
        "C:/Program Files/Git/bin/bash.exe."
    )


#: Test files planted in the fixture repository: one encoding-unsafe call and one
#: placeholder assertion each, so both whole-tree gates report a non-empty scan.
_FIXTURE_TESTS = {
    "tests/test_a.py": (
        "from pathlib import Path\n\n\n"
        "def test_a() -> None:\n"
        "    value = Path('x').read_text()\n"
        "    assert value is not None\n"
    ),
    "tests/unit/test_b.py": (
        "def test_b() -> None:\n"
        "    with open('y') as handle:\n"
        "        data = handle.read()\n"
        "    assert data is not None\n"
    ),
    "tests/unit/test_c.py": "def test_c() -> None:\n    assert 1 + 1 == 2\n",
}

#: What each whole-tree gate must print for the fixture: a non-zero count, so an
#: empty scan (the cwd-relative defect) cannot pass as a clean one.
_FIXTURE_EXPECTED_STDOUT = {
    "scripts/check_test_encoding.py": (
        "encoding-unsafe text calls in tests/: 2 across 2 files\n"
    ),
    "scripts/check_loose_assertions.py": "2\n",
}


def _build_fixture_repo(root: Path, script: str) -> Path:
    """A minimal repository holding a copy of *script* and ``_FIXTURE_TESTS``."""
    target = root / script
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((PROJECT_ROOT / script).read_bytes())
    for name, body in _FIXTURE_TESTS.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\n", encoding="utf-8"
    )
    return target


@pytest.mark.parametrize(("script", "interpreter", "args"), FIXTURE_TREE_GATES)
def test_whole_tree_gate_output_does_not_depend_on_the_working_directory(
    script: str, interpreter: str, args: tuple[str, ...], tmp_path: Path
) -> None:
    """Same proof as below for the gates that parse every test file, on a bounded tree.

    The gates anchor their scan to the script's own repository, so a copy placed
    in a fixture repository scans the fixture. Running it from the fixture root
    and from the fixture ``scripts/`` still reproduces the cwd-relative defect
    (it would report an empty scan from ``scripts/``), without parsing the
    ~1450 real test files twice.
    """
    fixture_script = _build_fixture_repo(tmp_path, script)

    outcomes = [
        subprocess.run(
            [interpreter, str(fixture_script), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        for cwd in (tmp_path, tmp_path / "scripts")
    ]
    from_root, from_non_root = outcomes

    assert (from_root.returncode, from_root.stdout, from_root.stderr) == (
        0,
        _FIXTURE_EXPECTED_STDOUT[script],
        "",
    )
    assert (from_non_root.returncode, from_non_root.stdout, from_non_root.stderr) == (
        from_root.returncode,
        from_root.stdout,
        from_root.stderr,
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
