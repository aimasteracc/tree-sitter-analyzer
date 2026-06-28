"""Trace impact graph walker helpers — Phase 3 REQ-CLEAN-005.

Extracted from trace_impact_tool.py.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ....cache.fingerprint import _SOURCE_EXTS

# Globs for ripgrep -g flag (mirrors the trace_impact_tool.py original)
_SOURCE_EXT_GLOBS: tuple[str, ...] = tuple(f"**/*{ext}" for ext in _SOURCE_EXTS)


def _filter_source_matches(
    matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """H4 fix: drop hits whose file extension is not in ``_SOURCE_EXTS``.

    The ``-g`` flag passed to ripgrep already restricts the search at the
    boundary; this is a belt-and-braces filter so that ``call_count`` is
    honest even when ``-g`` is bypassed (e.g. a future change adds
    ``--no-ignore`` or a custom glob). The cost is O(n) over hits that
    have already been parsed once.
    """
    if not matches:
        return matches
    return [match for match in matches if _is_source_file(match.get("file", ""))]


def _is_source_file(file_path: str) -> bool:
    """Return ``True`` if ``file_path`` ends with a known source extension."""
    if not file_path:
        return False
    lower = file_path.lower()
    return any(lower.endswith(ext) for ext in _SOURCE_EXTS)


# J7 (round-22): even after H4's extension filter, docstring and comment
# hits inside ``.py``/``.ts``/etc still inflate ``source_call_count`` — a
# line like ``"""ARCH-A4 regression: BaseMCPTool.set_project_path..."""``
# is counted as a caller. Heuristic-based classification (regex + triple-
# quote state) is good enough: full AST lookup per hit is too expensive
# for trace_impact, which runs on many matches at once.
_PY_LIKE_EXTS = (".py",)
_C_LIKE_EXTS = (
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".hxx",
)

# Match either a triple-double-quote or triple-single-quote token at any
# position on the line. We don't try to handle prefix strings (``r"""``,
# ``f"""``) specially — the leading prefix is fine, we just look at the
# triple-quote run itself.
_PY_TRIPLE_QUOTE_RE = re.compile(r'(?:"""|\'\'\')')


def _python_non_code_lines(text: str) -> set[int]:
    # Heuristic Python-comment / docstring / import detector. Returns 1-based
    # line numbers that are NOT genuine call sites:
    #
    # Rules:
    # * Lines whose first non-whitespace character is ``#`` count as comments.
    # * Lines fully inside a triple-quoted string count as docstring text.
    # * The line that opens a triple-quote AND the line that closes it
    #   are both flagged — even if the opener has code before the triple
    #   quote, we err on the side of dropping the hit. False negatives
    #   (treating a real call site as a docstring) are visible to the
    #   caller via the ``raw_match_count`` field, and a slight over-filter
    #   is acceptable per the brief.
    # * Import lines (``from … import …`` / ``import …``) and all
    #   continuation lines of a multi-line import block are flagged (#655):
    #   an import line that mentions a symbol is NOT a call site.
    #
    # Doesn't track escape sequences inside the string — a triple-quote
    # inside a docstring is impossible to write in pure-string form
    # anyway, so a naive token count works.
    non_code: set[int] = set()
    in_triple = False
    in_import = False  # True while inside a multi-line ``from x import (...)``
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        # Count how many triple-quote tokens appear on this line. The
        # state-machine: each triple-quote run toggles the inside-string
        # flag. Open-and-close on the same line cancels out.
        toggles = len(_PY_TRIPLE_QUOTE_RE.findall(line))
        if in_triple:
            # Already inside a docstring → this line is docstring text.
            non_code.add(idx)
            if toggles % 2 == 1:
                in_triple = False
            continue
        if toggles >= 1:
            # Opening (and possibly closing on the same line) — treat
            # the line itself as docstring so opener content like an
            # ARCH-A4 regression docstring header is dropped.
            non_code.add(idx)
            if toggles % 2 == 1:
                in_triple = True
            continue
        # Plain comment line.
        if stripped.startswith("#"):
            non_code.add(idx)
            continue
        # #655: import lines — `from module import symbol` and `import module`
        # are not call sites. Also track multi-line import blocks opened with
        # a ``(`` and closed with ``)`` so that continuation lines like
        # ``    _walk_for_symbols,`` are flagged too.
        if in_import:
            non_code.add(idx)
            if ")" in line:
                in_import = False
            continue
        if stripped.startswith("from ") or stripped.startswith("import "):
            non_code.add(idx)
            # Multi-line import: ``from x import (\n    sym,\n)``
            if "(" in line and ")" not in line.split("#")[0]:
                in_import = True
    return non_code


def _is_symbol_only_in_strings(line: str, symbol: str) -> bool:
    """Return True if every occurrence of ``symbol`` in ``line`` is inside an
    inline string literal (single or double quoted, not triple-quoted).

    Used as a per-match heuristic (#655): if the only reason a line shows up
    in ripgrep results is that the symbol name appears inside a string
    argument (e.g. ``reason="my_func is not ready"``), it is NOT a call site.

    Algorithm: walk the line character by character, tracking whether we are
    inside a single-quoted or double-quoted string. For each position where
    ``symbol`` starts, record whether we are inside a string at that point.
    If ALL occurrences of ``symbol`` are inside strings → return True.
    Returns False (not filtered) when symbol is absent (safety default).
    """
    if not symbol or symbol not in line:
        return False

    in_str: str | None = None  # None = outside string; '"' or "'" = inside
    is_fstring = False  # current string was opened with an f/F prefix
    brace_depth = 0  # {...} replacement-field depth inside an f-string
    idx = 0
    sym_len = len(symbol)
    sym_positions_in_str: list[bool] = []

    while idx < len(line):
        ch = line[idx]

        if in_str is None:
            # Check for triple-quote open — not handled here (triple-quoted
            # strings are caught by _python_non_code_lines); skip to avoid
            # treating the first char of ''' as a single-quote open.
            if line[idx : idx + 3] in ('"""', "'''"):
                # Skip the rest of the line — triple-quote on same line
                # (which _python_non_code_lines already flags). Just treat
                # everything to the right as non-code.
                remaining_has_sym = symbol in line[idx:]
                if remaining_has_sym:
                    # All occurrences from here are inside a triple-quote region.
                    sym_positions_in_str.extend([True] * line[idx:].count(symbol))
                break
            if ch in ('"', "'"):
                in_str = ch
                # f/F prefix (possibly combined with r/b) → replacement
                # fields {...} carry real code (Codex P2 on #655):
                # `f"{my_func(x)}"` is a genuine call, must not be filtered.
                prefix = line[max(0, idx - 2) : idx].lower()
                is_fstring = "f" in prefix
                brace_depth = 0
                idx += 1
                continue
        else:
            # Inside an f-string replacement field — this is CODE, not string.
            if is_fstring and brace_depth > 0:
                if ch == "}":
                    brace_depth -= 1
                    idx += 1
                    continue
                if ch == "{":
                    brace_depth += 1
                    idx += 1
                    continue
                # fall through to the symbol-position check below (in code)
            else:
                # Inside the literal text of a single-line string.
                if ch == "\\" and idx + 1 < len(line):
                    # Skip escaped character.
                    idx += 2
                    continue
                if is_fstring and ch == "{":
                    if line[idx : idx + 2] == "{{":  # escaped brace, literal '{'
                        idx += 2
                        continue
                    brace_depth += 1
                    idx += 1
                    continue
                if ch == in_str:
                    in_str = None
                    is_fstring = False
                    idx += 1
                    continue

        # Check whether symbol starts at this position. A symbol inside an
        # f-string {...} field counts as in-code (in_string=False).
        if line[idx : idx + sym_len] == symbol:
            in_code = in_str is None or (is_fstring and brace_depth > 0)
            sym_positions_in_str.append(not in_code)
            idx += sym_len
            continue

        idx += 1

    if not sym_positions_in_str:
        return False  # symbol not found after walk — don't filter
    return all(sym_positions_in_str)


def _c_like_non_code_lines(text: str) -> set[int]:
    """Return 1-based line numbers that are ``//`` comments or inside ``/* */`` blocks.

    Tracks ``/* ... */`` state across lines. Doesn't try to honour string
    literals (``"http://example.com"`` will look like ``//`` to this
    scanner) — acceptable per the J7 brief, which prefers a heuristic
    over per-hit AST lookups.
    """
    non_code: set[int] = set()
    in_block = False
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if in_block:
            non_code.add(idx)
            if "*/" in line:
                in_block = False
                # If after closing the block there's only whitespace,
                # the line stays purely comment. If real code follows
                # ``*/``, treating the line as non-code is a small
                # over-filter — acceptable.
            continue
        if stripped.startswith("//"):
            non_code.add(idx)
            continue
        if "/*" in line:
            non_code.add(idx)
            # Check whether the block also closes on the same line.
            close_idx = line.find("*/", line.find("/*") + 2)
            if close_idx == -1:
                in_block = True
    return non_code


@lru_cache(maxsize=512)
def _file_non_code_lines(file_path: str) -> frozenset[int]:
    """Read ``file_path`` once and compute the set of comment/docstring lines.

    Cached so a single ``trace_impact`` call with N hits across M files
    pays the file-read cost M times, not N times. The cache is process-
    local; in MCP-server mode the same files get read again on a fresh
    invocation, which is fine — they're typically already in the OS page
    cache.
    """
    lower = file_path.lower()
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        # File disappeared / unreadable → assume nothing is non-code so
        # we don't accidentally hide every hit.
        return frozenset()
    if lower.endswith(_PY_LIKE_EXTS):
        return frozenset(_python_non_code_lines(text))
    if lower.endswith(_C_LIKE_EXTS):
        return frozenset(_c_like_non_code_lines(text))
    return frozenset()


def _filter_comment_docstring_matches(
    matches: list[dict[str, Any]],
    symbol: str = "",
) -> list[dict[str, Any]]:
    """Drop hits whose line is inside a comment, docstring, import, or string.

    Called AFTER ``_filter_source_matches`` so we only pay the file-read
    cost for hits that survived the extension filter. The filters together
    give an honest ``source_call_count``:

    * Extension filter (H4): drops markdown / CHANGELOG hits.
    * Comment/docstring/import filter (J7 + #655): drops hits inside
      ``#`` / ``//`` / ``/* */`` / Python triple-quoted strings / import
      lines.
    * Inline-string filter (#655): for Python files, drops hits where the
      symbol appears only inside a string literal (e.g. in a ``reason=``
      argument to ``pytest.mark.xfail``).  Requires ``symbol`` to be
      provided; when omitted or empty the filter is skipped.
    """
    if not matches:
        return matches
    kept: list[dict[str, Any]] = []
    for match in matches:
        file_path = match.get("file", "")
        line_no = match.get("line")
        if not file_path or not isinstance(line_no, int):
            kept.append(match)
            continue
        non_code = _file_non_code_lines(file_path)
        if line_no in non_code:
            continue
        # #655: inline string-literal filter for Python files. If ``symbol``
        # is provided and the match line is a Python file, check whether
        # every occurrence of the symbol on that line is inside a quoted
        # string. If so, it is not a call site.
        if symbol and file_path.lower().endswith(_PY_LIKE_EXTS):
            line_text = match.get("text", "")
            if line_text and _is_symbol_only_in_strings(line_text, symbol):
                continue
        kept.append(match)
    return kept


def _get_impact_level(count: int) -> dict[str, str]:
    """
    Return a severity dict for a given caller count.

    Args:
        count: Number of callers found for a symbol

    Returns:
        Dictionary with level, badge, and guidance keys
    """
    if count == 0:
        return {
            "level": "none",
            "badge": "✅ NO CALLERS",
            "guidance": "Safe to modify or delete.",
        }
    elif count <= 5:
        # r37s (dogfood): hardcoded ``caller(s)`` is a placeholder for
        # unknown plurality. We already KNOW count here (1-5), so render
        # proper singular/plural English ("1 caller" / "3 callers").
        caller_word = "caller" if count == 1 else "callers"
        return {
            "level": "low",
            "badge": "⚠️ LOW IMPACT",
            "guidance": f"{count} {caller_word} found. Review before modifying.",
        }
    elif count <= 20:
        return {
            "level": "medium",
            "badge": "🔶 MEDIUM IMPACT",
            "guidance": (
                f"{count} callers found. "
                "Check all call sites before changing the signature."
            ),
        }
    else:
        return {
            "level": "high",
            "badge": f"🚨 HIGH IMPACT — {count} CALLERS",
            "guidance": (
                f"{count} callers across the codebase. "
                "Do NOT modify signature without updating all callers. "
                "Consider deprecation strategy."
            ),
        }


def _build_trace_impact_globs(
    language_extensions: list[str],
    exclude_patterns: list[str],
) -> tuple[list[str], list[str]]:
    """Build (include_globs, exclude_globs) for ripgrep.

    r37bw: extracted from ``execute``. Adds common exclude patterns
    (node_modules, .git, vendor, __pycache__, *.min.{js,css}) and either
    language-specific extensions or the project-wide source extension
    set (H4 fix).
    """
    exclude_globs = list(exclude_patterns)
    exclude_globs.extend(
        [
            "**/node_modules/**",
            "**/.git/**",
            "**/vendor/**",
            "**/__pycache__/**",
            "**/*.min.js",
            "**/*.min.css",
        ]
    )
    include_globs: list[str] = []
    if language_extensions:
        for ext in language_extensions:
            include_globs.append(f"**/*{ext}")
    else:
        # H4: restrict to source extensions even without language detection.
        include_globs.extend(_SOURCE_EXT_GLOBS)
    return include_globs, exclude_globs


def _classify_rg_error(rc: int, stderr: bytes | None) -> dict[str, Any] | None:
    """Map ripgrep exit code to an error envelope, or ``None`` on success/no-match.

    r37bw: extracted from ``execute``. rc=127 means rg missing, rc=124
    means timeout, anything other than 0/1 is a real failure. rc=0/1
    return ``None`` so the caller continues to result parsing.
    """
    if rc == 127:
        return {
            "success": False,
            "error": (
                "ripgrep (rg) is not installed. Please install ripgrep "
                "to use trace_impact."
            ),
            "usages": [],
            "call_count": 0,
        }
    if rc == 124:
        return {
            "success": False,
            "error": (
                "Search timed out. Try narrowing the search scope or "
                "excluding more directories."
            ),
            "usages": [],
            "call_count": 0,
        }
    if rc not in (0, 1):
        error_msg = (
            stderr.decode("utf-8", errors="replace") if stderr else "Unknown error"
        )
        return {
            "success": False,
            "error": f"Search failed: {error_msg}",
            "usages": [],
            "call_count": 0,
        }
    return None
