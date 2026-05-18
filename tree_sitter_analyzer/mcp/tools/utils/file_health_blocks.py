"""Fallback block scanning for file-health smell detection."""

from __future__ import annotations


def find_long_blocks_heuristic(
    lines: list[str], threshold: int = 50
) -> list[tuple[str, int, int]]:
    """Fallback long block detection using indentation heuristics."""
    results: list[tuple[str, int, int]] = []
    tracker = _BlockTracker()

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith(("def ", "async def ")):
            if tracker.active and tracker.block_lines > threshold:
                results.append(tracker.snapshot())
            after_def = stripped.split("def ", 1)[-1] if "def " in stripped else ""
            tracker.start(
                name=after_def.split("(")[0].strip() if after_def else f"block_{i}",
                start=i,
                indent=len(line) - len(line.lstrip()),
            )
            continue

        if tracker.active:
            tracker.process_line()
            if tracker.ended_at(stripped, line) and tracker.block_lines > threshold:
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
        """Check if the current block has ended at this line."""
        if not stripped:
            return False
        current_indent = len(line) - len(line.lstrip())
        if current_indent != self.def_indent:
            return False
        if not stripped.startswith(("def ", "async def ", "class ", "@")):
            return False
        self.active = False
        return True
