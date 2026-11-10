"""Agent-first front door for the CLI: short ``--help`` and actionable usage errors.

``--help`` used to print every flag (~1,400 lines, ~83k chars, ~20k tokens), and
every argparse error printed ~280 lines of usage before the one line that
mattered. An agent with no prior knowledge pays that on its first call. This
module keeps the first screen to the top tasks -> exact commands, points to
``--help-all`` for the full reference, and turns parser errors into one short
message with a suggestion and a next step.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any

HELP_ALL_FLAG = "--help-all"

# (question, command). Every flag used here must exist in the real parser;
# tests/unit/cli/test_agent_help.py enforces that so this table cannot rot.
TOP_TASKS: tuple[tuple[str, str], ...] = (
    ("Who calls F? Is the list complete?", "--callers F"),
    ("What does F call?", "--callees F"),
    (
        "Where is S defined? (body inlined)",
        "--codegraph-navigate S --codegraph-navigate-mode definition",
    ),
    ("What breaks if I change F?", "--codegraph-impact F"),
    ("Which tests cover F?", "--test-map F"),
    ("Outline a file (compact)", "FILE --table signatures"),
    ("Read lines 10-40 of a file", "FILE --partial-read --start-line 10 --end-line 40"),
    ("Is it safe to edit FILE?", "FILE --safe-to-edit --edit-type refactor"),
    (
        "Call path A -> B (bare names)",
        "--call-path --call-path-source A --call-path-target B",
    ),
    ("Find a symbol by name", "--symbol-search NAME"),
    ("Find an exact text line", "--text-search TEXT"),
    ("Hot spots to refactor", "--hotspot"),
    ("Project overview", "--overview"),
    ("Health grade of a file", "FILE --file-health"),
    ("Impact of my uncommitted diff", "--change-impact"),
)

PROG_NAME = "tree-sitter-analyzer"
_QUESTION_WIDTH = 38


def program_name(argv0: str) -> str | None:
    """``tree-sitter-analyzer`` under ``python -m``; ``None`` keeps argparse's name.

    ``python -m tree_sitter_analyzer`` makes argparse call itself ``__main__.py``,
    and agents copy the name from errors and usage lines. Installed console
    scripts and their aliases (code-analyzer, java-analyzer) keep their own name.
    """
    return PROG_NAME if os.path.basename(argv0) == "__main__.py" else None


def _task_lines() -> list[str]:
    return [
        f"  {question:<{_QUESTION_WIDTH}} {PROG_NAME} {command}"
        for question, command in TOP_TASKS
    ]


def format_agent_help() -> str:
    """The short, task-first help printed by ``-h`` / ``--help``."""
    lines = [
        f"usage: {PROG_NAME} [FILE] [--flag VALUE ...]   (full reference: {HELP_ALL_FLAG})",
        "",
        f"{PROG_NAME}: code intelligence for AI agents (CLI twin of the MCP server).",
        "Run from the project root. Output is JSON on stdout.",
        "",
        "First, once per repository (makes graph answers complete and fast):",
        f"  {PROG_NAME} --autoindex --autoindex-mode warm",
        "",
        "Top tasks -> exact command (F, S, A, B = function / symbol names):",
        *_task_lines(),
        "",
        "Reading an answer:",
        "  verdict              INFO / REVIEW / CAUTION / UNSAFE / NOT_FOUND",
        "  completeness         complete = certified; unknown = read open_sites",
        "                       before you claim something has no callers",
        "  agent_summary        summary_line + next_step: do that next",
        "",
        "More:",
        f"  {PROG_NAME} {HELP_ALL_FLAG}        every flag (full reference, ~1,400 lines)",
        f"  {PROG_NAME} --capabilities    every MCP facade/action: preconditions, cost",
        f"  {PROG_NAME} --agent-workflow  phase-by-phase workflow pack",
        f"  {PROG_NAME} --list-queries    query keys for FILE --query-key KEY",
        f"  {PROG_NAME} --version",
    ]
    return "\n".join(lines) + "\n"


class AgentHelpAction(argparse.Action):
    """``-h`` / ``--help``: print the short agent-first help and exit 0."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: str = argparse.SUPPRESS,
        help: str | None = None,  # noqa: A002 - argparse keyword
        **_: object,
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        parser._print_message(format_agent_help(), sys.stdout)
        parser.exit()


class FullHelpAction(argparse.Action):
    """``--help-all``: print the complete argparse reference and exit 0."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: str = argparse.SUPPRESS,
        help: str | None = None,  # noqa: A002 - argparse keyword
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        parser.print_help()
        parser.exit()


def _unknown_tokens(message: str) -> list[str]:
    prefix = "unrecognized arguments: "
    if not message.startswith(prefix):
        return []
    return message[len(prefix) :].split()


def suggest_fix(
    message: str, option_strings: Iterable[str], argv: Sequence[str]
) -> str | None:
    """A concrete corrected command fragment for a parser error, or ``None``."""
    long_options = sorted(
        {
            o
            for o in option_strings
            if o.startswith("--") and o not in ("--help", HELP_ALL_FLAG)
        }
    )
    # ``callers X`` / ``test-map X``: a flag typed without its dashes.
    if argv and not argv[0].startswith("-") and f"--{argv[0]}" in long_options:
        return " ".join([f"--{argv[0]}", *argv[1:]])
    for token in _unknown_tokens(message):
        if not token.startswith("--"):
            continue
        flag = token.split("=", 1)[0]
        close = difflib.get_close_matches(flag, long_options, n=3, cutoff=0.6)
        if close:
            return " or ".join(close)
    return None


def format_parser_error(
    prog: str, message: str, option_strings: Iterable[str], argv: Sequence[str]
) -> str:
    """One short error block: what failed, a suggestion, and where to look next."""
    lines = [f"{prog}: error: {message}"]
    suggestion = suggest_fix(message, option_strings, argv)
    if suggestion:
        lines.append(f"Did you mean: {PROG_NAME} {suggestion}")
    lines.append(
        f"Next: '{PROG_NAME} --help' lists the top tasks with exact commands; "
        f"'{PROG_NAME} {HELP_ALL_FLAG}' lists every flag."
    )
    return "\n".join(lines) + "\n"
