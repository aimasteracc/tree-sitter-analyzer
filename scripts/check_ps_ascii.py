#!/usr/bin/env python3
"""check_ps_ascii.py — block commits that put non-ASCII bytes inside a
`shell: powershell` run block in .github/**/*.yml.

Why: GitHub Actions writes the inline `run:` block to a .ps1 on the
runner. The default Windows runner shell `powershell` is Windows
PowerShell 5.1, which reads .ps1 as cp1252 by default. UTF-8 emoji
from the YAML source get mojibake'd into multi-byte garbage that breaks
PowerShell's string scanner — error TerminatorExpectedAtEndOfString.

Fix at write time: ASCII-only inside `shell: powershell` blocks. If you
really need Unicode, switch to `shell: pwsh` (PowerShell Core, UTF-8
by default).

This script walks every YAML file under .github/, finds each step that
declares `shell: powershell` and an associated `run: |` literal block,
then flags any non-ASCII byte in that block.

Exits 0 clean, 1 if a violation is found.
"""

from __future__ import annotations

import glob
import re
import sys

ASCII_HI = re.compile(r"[^\x00-\x7F]")
# Allow optional inline YAML comment after the value
# (`shell: powershell  # comment` is legal YAML).
SHELL_PS_RE = re.compile(r"^(\s*)shell:\s*powershell\s*(#.*)?$")
SHELL_OTHER_RE = re.compile(r"^(\s*)shell:\s+(?!powershell\s*(#.*)?$)")
RUN_BLOCK_RE = re.compile(r"^(\s*)run:\s*[|>][-+]?\s*(#.*)?$")
# Known gap: `run: *some_anchor` (YAML alias expansion) is not scanned.
# Aliases are rare in GitHub Actions YAML; if you introduce one,
# inline the script instead so this scanner can see it.


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def find_powershell_run_blocks(text: str) -> list[tuple[int, int]]:
    """Return (start_line, end_line) inclusive 0-indexed ranges of every
    `run: |` block whose owning step has `shell: powershell`.

    The shell line can appear before OR after the run line in YAML, so
    we make two passes: collect run-block ranges by indent, then check
    each block's sibling `shell:` value.
    """
    lines = text.splitlines()
    blocks: list[tuple[int, int, int]] = []  # (start, end, step_indent)

    i = 0
    while i < len(lines):
        m = RUN_BLOCK_RE.match(lines[i])
        if not m:
            i += 1
            continue
        run_indent = len(m.group(1))
        start = i + 1
        end = start
        # block ends when a line at or below run_indent appears
        while end < len(lines):
            ln = lines[end]
            if ln.strip() == "":
                end += 1
                continue
            if indent(ln) <= run_indent:
                break
            end += 1
        blocks.append((start, end - 1, run_indent))
        i = end

    # For each block, decide whether its owning step uses powershell.
    # The step's keys (`run:`, `shell:`, `name:`, `with:`...) all share
    # the same `run_indent`. Walk forwards and backwards from the run
    # line searching for a sibling `shell:` line at exactly run_indent.
    ps_ranges: list[tuple[int, int]] = []
    for start, end, run_indent in blocks:
        run_header_line = start - 1
        is_ps = False
        # Walk backwards
        j = run_header_line - 1
        while j >= 0:
            ln = lines[j]
            if ln.strip() == "":
                j -= 1
                continue
            ind = indent(ln)
            if ind < run_indent:
                # Left the step
                break
            if ind == run_indent:
                if SHELL_PS_RE.match(ln):
                    is_ps = True
                    break
                if SHELL_OTHER_RE.match(ln):
                    break
                # Some other sibling key, keep walking.
            j -= 1
        # Walk forwards past the run block
        if not is_ps:
            k = end + 1
            while k < len(lines):
                ln = lines[k]
                if ln.strip() == "":
                    k += 1
                    continue
                ind = indent(ln)
                if ind < run_indent:
                    break
                if ind == run_indent:
                    if SHELL_PS_RE.match(ln):
                        is_ps = True
                        break
                    if SHELL_OTHER_RE.match(ln):
                        break
                k += 1
        if is_ps:
            ps_ranges.append((start, end))
    return ps_ranges


def scan_file(path: str) -> list[tuple[int, int, str]]:
    """Return [(line_no_1based, col_1based, line_text), ...] for every
    non-ASCII byte found inside a `shell: powershell` run block."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    ranges = find_powershell_run_blocks(text)
    lines = text.splitlines()
    hits: list[tuple[int, int, str]] = []
    for start, end in ranges:
        for ln_idx in range(start, end + 1):
            if ln_idx >= len(lines):
                break
            ln = lines[ln_idx]
            m = ASCII_HI.search(ln)
            if m:
                hits.append((ln_idx + 1, m.start() + 1, ln))
    return hits


def main() -> int:
    yaml_paths = sorted(
        set(
            glob.glob(".github/workflows/*.yml")
            + glob.glob(".github/workflows/*.yaml")
            + glob.glob(".github/actions/**/action.yml", recursive=True)
            + glob.glob(".github/actions/**/action.yaml", recursive=True)
        )
    )
    total_hits = 0
    for path in yaml_paths:
        hits = scan_file(path)
        for line_no, col, ln in hits:
            print(
                f"{path}:{line_no}:{col}: non-ASCII byte inside "
                f"`shell: powershell` run block: {ln.rstrip()}"
            )
            total_hits += 1
    if total_hits:
        sys.stderr.write(
            "\nERROR: non-ASCII bytes detected inside one or more "
            "`shell: powershell` run blocks.\n\n"
            "Windows PowerShell 5.1 reads inline scripts as cp1252 and "
            "chokes on UTF-8 emoji/Unicode (TerminatorExpectedAtEndOfString).\n"
            "Either:\n"
            "  1. Replace the non-ASCII characters with ASCII equivalents\n"
            "     (e.g. ✅ -> [OK], ❌ -> ::error::, em-dash -> ASCII dash).\n"
            "  2. Switch the step to `shell: pwsh` (PowerShell Core, "
            "UTF-8 by default).\n\n"
            "See docs/POSTMORTEM_v1.13.md § 5 for the incident this "
            "rule guards against.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
