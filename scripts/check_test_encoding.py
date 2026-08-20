#!/usr/bin/env python3
"""Block new locale-dependent text I/O in tests (encoding ratchet).

Why this exists
---------------
A test that opens a text file without an explicit ``encoding`` inherits the
*runner's* locale. On a UTF-8 runner it passes; on a cp932 / latin-1 runner it
raises ``UnicodeDecodeError`` — and, worse, that decode error happens on the
line that was supposed to make an assertion, so it **masks the real check**
instead of reporting it.

Measured 2026-08-19 on a Japanese-locale Windows box against CI-green
``develop``: 6 failures in ``tests/unit/test_claim_registry.py`` and 5 in
``tests/contracts/`` were nothing but this, e.g.

    UnicodeDecodeError: 'cp932' codec can't decode byte 0xef in position 0

(0xef at position 0 is the UTF-8 BOM of ``README.md``.) Every one of those test
ids passes on GitHub's UTF-8 runners, so CI could not see the defect at all,
and each one cost a developer a stash-and-re-measure cycle to rule out.

Ratchet, not a cleanup
----------------------
There are ~2267 pre-existing encoding-unsafe calls across ~326 test files.
Rewriting them all would be a 300-file diff with no behavioural payoff, so the
baseline is grandfathered exactly like ``check_loose_assertions.py`` does: this
checks only lines a commit **adds**. The baseline can shrink opportunistically
and can never grow.

Usage
-----
    python scripts/check_test_encoding.py --staged      # pre-commit
    python scripts/check_test_encoding.py --diff <ref>  # CI / PR range
    python scripts/check_test_encoding.py --baseline    # count only, exit 0

Exit codes: 0 = OK (``--baseline`` always 0), 1 = new violations found.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess  # nosec B404 - git plumbing only, fixed argv
import sys
from dataclasses import dataclass
from pathlib import Path

TEXT_METHODS = frozenset({"read_text", "write_text"})
TESTS_DIR = "tests"


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    call: str

    def render(self) -> str:
        return f"  {self.path}:{self.line}: {self.call} has no explicit encoding="


def _mode_of(node: ast.Call) -> str:
    """Best-effort literal mode string for an ``open()`` call."""
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        return str(node.args[1].value)
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return ""


def _violations_in_source(path: str, source: str) -> list[Violation]:
    """Find text I/O calls in *source* that do not pin an encoding."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        if "encoding" in keywords:
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in TEXT_METHODS:
            found.append(Violation(path, node.lineno, f"{func.attr}()"))
        elif isinstance(func, ast.Name) and func.id == "open":
            # Binary mode carries no encoding, so it is always safe.
            if "b" not in _mode_of(node):
                found.append(Violation(path, node.lineno, "open()"))
    return found


def _parse_added_line_ranges(diff_text: str) -> dict[str, set[int]]:
    """Parse ``git diff -U0`` output into added line numbers per new path."""
    added: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            added.setdefault(current, set())
        elif line.startswith("+++ "):
            current = None  # /dev/null (deletion) or unexpected form
        elif line.startswith("@@") and current is not None:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2)) if match.group(2) is not None else 1
                added[current].update(range(start, start + count))
    return added


def _git_diff(extra: list[str]) -> str:
    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "diff", *extra, "--unified=0", "--diff-filter=AMR", "--", TESTS_DIR],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout


def _check_added(added: dict[str, set[int]], label: str) -> int:
    violations: list[Violation] = []
    for name, lines in added.items():
        if not lines or not name.endswith(".py"):
            continue
        path = Path(name)
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        violations.extend(
            found
            for found in _violations_in_source(name, source)
            if found.line in lines
        )

    if not violations:
        return 0

    print(
        f"Encoding ratchet: {len(violations)} new locale-dependent text "
        f"call(s) in the {label}.\n",
        file=sys.stderr,
    )
    for violation in sorted(violations, key=lambda v: (v.path, v.line)):
        print(violation.render(), file=sys.stderr)
    print(
        "\nA text read/write without encoding= inherits the runner's locale, so "
        "the test\npasses on UTF-8 CI and dies with UnicodeDecodeError on a "
        "cp932/latin-1 box -\nmasking the assertion it was meant to make. Pass "
        'encoding="utf-8" explicitly\n(or use read_bytes()/write_bytes() if the '
        "payload is genuinely binary).",
        file=sys.stderr,
    )
    return 1


def baseline_violations(tests_dir: Path) -> list[Violation]:
    """Every encoding-unsafe text call under *tests_dir* (grandfathered)."""
    found: list[Violation] = []
    for path in sorted(tests_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8", errors="replace")
        found.extend(_violations_in_source(path.as_posix(), source))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true", help="check staged diff")
    group.add_argument("--diff", metavar="REF", help="check diff against REF")
    group.add_argument(
        "--baseline", action="store_true", help="report the grandfathered count"
    )
    args = parser.parse_args(argv)

    if args.baseline:
        violations = baseline_violations(Path(TESTS_DIR))
        files = {violation.path for violation in violations}
        print(
            f"encoding-unsafe text calls in {TESTS_DIR}/: "
            f"{len(violations)} across {len(files)} files"
        )
        return 0

    if args.staged:
        return _check_added(
            _parse_added_line_ranges(_git_diff(["--cached"])), "staged diff"
        )
    return _check_added(
        _parse_added_line_ranges(_git_diff([f"{args.diff}...HEAD"])), "PR diff"
    )


if __name__ == "__main__":
    sys.exit(main())
