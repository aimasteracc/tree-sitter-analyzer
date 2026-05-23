"""Fallback block scanning for file-health smell detection."""

from __future__ import annotations


def find_long_blocks_heuristic(
    lines: list[str], threshold: int = 50
) -> list[tuple[str, int, int]]:
    """Fallback long block detection using indentation heuristics.

    r37d4 (dogfood): skip lines inside triple-quoted strings so embedded
    corpus / fixture code in Python modules (e.g. a Ruby ``def self.X``
    inside a triple-quoted BUILTIN_CORPUS entry) is no longer reported as
    a long Python method. The detector was hitting a 303-line false
    positive in ``grammar_coverage/discovery_corpus.py`` for that reason.
    """
    results: list[tuple[str, int, int]] = []
    tracker = _BlockTracker()
    string_state = _TripleQuoteTracker()

    for i, line in enumerate(lines):
        # Update the multi-line string state BEFORE the def-check below so
        # lines inside triple-quoted strings are skipped wholesale.
        in_string = string_state.update(line)
        stripped = line.strip()
        current_indent = len(line) - len(line.lstrip())

        # A def at a deeper indent than the current tracker is a NESTED
        # def — keep counting it toward the outer block instead of
        # resetting the tracker. Only treat dedented-or-same-level defs
        # as block boundaries.
        is_top_level_def = (
            not in_string
            and stripped.startswith(("def ", "async def "))
            and (not tracker.active or current_indent <= tracker.def_indent)
        )

        if is_top_level_def:
            if tracker.active and tracker.block_lines > threshold:
                results.append(tracker.snapshot())
            after_def = stripped.split("def ", 1)[-1] if "def " in stripped else ""
            tracker.start(
                name=after_def.split("(")[0].strip() if after_def else f"block_{i}",
                start=i,
                indent=current_indent,
            )
            continue

        if tracker.active:
            tracker.process_line()
            if (
                not in_string
                and tracker.ended_at(stripped, line)
                and tracker.block_lines > threshold
            ):
                results.append(tracker.snapshot())

    if tracker.active and tracker.block_lines > threshold:
        results.append(tracker.snapshot())

    results.sort(key=lambda item: -item[2])
    return results


class _BlockTracker:
    """Track a fallback function block while scanning source lines."""

    def __init__(self) -> None:
        """Initialize block tracker state."""
        self.active = False
        self.def_name = ""
        self.def_start = 0
        self.def_indent = 0
        self.block_lines = 0

    def start(self, name: str, start: int, indent: int) -> None:
        """Start tracking a new function block."""
        self.active = True
        self.def_name = name
        self.def_start = start
        self.def_indent = indent
        self.block_lines = 1

    def snapshot(self) -> tuple[str, int, int]:
        """Return a snapshot of the current block."""
        return (self.def_name, self.def_start + 1, self.block_lines)

    def process_line(self) -> None:
        """Process a line within a tracked block."""
        self.block_lines += 1

    def ended_at(self, stripped: str, line: str) -> bool:
        """Check if the current block has ended at this line.

        The block ends when we see a sibling-or-shallower def/class/decorator
        — i.e. a line at the same OR less indent than the def we are
        tracking that opens a new top-level construct. Lines at deeper
        indent (nested defs, body code) keep the tracker active. The
        ``stripped`` argument is re-stripped defensively so callers may
        pass either the pre-stripped form or the raw line.
        """
        # Defensive: callers in tests sometimes pass the raw line as both
        # arguments. Always work from the canonical lstripped form so
        # leading whitespace doesn't poison startswith() checks.
        stripped = stripped.lstrip()
        if not stripped:
            return False
        current_indent = len(line) - len(line.lstrip())
        if current_indent > self.def_indent:
            return False
        if not stripped.startswith(("def ", "async def ", "class ", "@")):
            return False
        self.active = False
        return True


class _TripleQuoteTracker:
    """Track whether the current line is inside a triple-quoted string.

    Counts triple-quote markers on each line and toggles an "inside"
    flag whenever they appear. ``update(line)`` returns ``True`` when
    the *post-update* state is "inside a string" (i.e. the next
    def-keyword we see on this line should be ignored). The heuristic
    is intentionally simple — it doesn't track backslash-escaped
    quotes — because the false positives we're targeting are large
    corpus dictionaries, not edge-case string syntax.
    """

    def __init__(self) -> None:
        self.inside = False
        self.delimiter = ""

    def update(self, line: str) -> bool:
        """Advance the tracker for ``line`` and return the resulting state.

        We process delimiter occurrences left-to-right so a one-line
        triple-quoted literal closes itself without leaving us inside.
        """
        i = 0
        while i < len(line):
            if not self.inside:
                if line.startswith('"""', i):
                    self.inside = True
                    self.delimiter = '"""'
                    i += 3
                    continue
                if line.startswith("'''", i):
                    self.inside = True
                    self.delimiter = "'''"
                    i += 3
                    continue
                i += 1
                continue
            if line.startswith(self.delimiter, i):
                self.inside = False
                self.delimiter = ""
                i += 3
                continue
            i += 1
        return self.inside
