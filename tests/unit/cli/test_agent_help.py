"""Agent-first CLI front door: short --help, --help-all, compact parser errors."""

from __future__ import annotations

import shlex
import subprocess
import sys

import pytest

from tree_sitter_analyzer.cli.agent_help import (
    HELP_ALL_FLAG,
    TOP_TASKS,
    format_agent_help,
    format_parser_error,
    suggest_fix,
)
from tree_sitter_analyzer.cli.argument_parser_builder import create_argument_parser

_MAX_SHORT_HELP_LINES = 60


def _flags() -> set[str]:
    parser = create_argument_parser()
    return {s for a in parser._actions for s in a.option_strings}


def _run_parser(argv: list[str], capsys) -> tuple[int, str, str]:
    parser = create_argument_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(argv)
    out, err = capsys.readouterr()
    return int(exc.value.code or 0), out, err


def test_short_help_fits_the_agent_budget() -> None:
    text = format_agent_help()
    assert len(text.splitlines()) <= _MAX_SHORT_HELP_LINES
    assert len(text) < 3000


def test_every_command_in_the_short_help_uses_real_flags() -> None:
    flags = _flags()
    used = {
        token
        for _question, command in TOP_TASKS
        for token in shlex.split(command)
        if token.startswith("-")
    }
    assert used, "TOP_TASKS must name flags"
    assert used - flags == set()


def test_short_help_names_index_step_and_full_reference() -> None:
    text = format_agent_help()
    assert "--autoindex --autoindex-mode warm" in text
    assert HELP_ALL_FLAG in text
    assert "--callers F" in text
    assert "usage:" in text


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flag_prints_short_help(flag: str, capsys) -> None:
    code, out, _err = _run_parser([flag], capsys)
    assert code == 0
    assert out == format_agent_help()


def test_help_all_prints_the_full_reference(capsys) -> None:
    code, out, _err = _run_parser([HELP_ALL_FLAG], capsys)
    assert code == 0
    assert "--check-scale" in out
    assert "--mutation-probe-timeout" in out
    assert "Examples:" in out


def test_print_help_keeps_the_full_reference() -> None:
    import io

    buf = io.StringIO()
    create_argument_parser().print_help(buf)
    assert "--check-scale" in buf.getvalue()


def test_help_flags_stay_argparse_implicit() -> None:
    parser = create_argument_parser()
    help_actions = [a for a in parser._actions if "--help" in a.option_strings]
    assert len(help_actions) == 1
    assert help_actions[0].option_strings == ["-h", "--help"]


def test_unknown_flag_error_is_short_and_suggests(capsys) -> None:
    code, out, err = _run_parser(["--calers", "x"], capsys)
    assert code == 2
    assert out == ""
    lines = err.splitlines()
    assert len(lines) <= 4
    assert lines[0].endswith("error: unrecognized arguments: --calers")
    assert "Did you mean: tree-sitter-analyzer --callers" in err
    assert "--help" in lines[-1]


def test_flag_typed_without_dashes_suggests_the_flag(capsys) -> None:
    code, _out, err = _run_parser(["callers", "set_live"], capsys)
    assert code == 2
    assert "Did you mean: tree-sitter-analyzer --callers set_live" in err


def test_ambiguous_prefix_keeps_argparse_candidates(capsys) -> None:
    code, _out, err = _run_parser(["--caller", "x"], capsys)
    assert code == 2
    assert "could match --callers" in err
    assert len(err.splitlines()) <= 3


def test_suggestion_never_points_at_help_flags() -> None:
    assert (
        suggest_fix("unrecognized arguments: --help-al", ["--help", HELP_ALL_FLAG], [])
        is None
    )


def test_error_without_suggestion_still_has_next_step() -> None:
    text = format_parser_error("prog", "argument --depth: invalid int value", [], [])
    assert text.splitlines() == [
        "prog: error: argument --depth: invalid int value",
        "Next: 'tree-sitter-analyzer --help' lists the top tasks with exact "
        "commands; 'tree-sitter-analyzer --help-all' lists every flag.",
    ]


def test_parser_construction_does_not_import_search_tools() -> None:
    """--help and parser errors must not pay for the cache/search stack (~1.2 s)."""
    code = (
        "import sys\n"
        "from tree_sitter_analyzer.cli.argument_parser_builder import "
        "create_argument_parser\n"
        "create_argument_parser()\n"
        "heavy = [m for m in ('tree_sitter_analyzer.mcp.tools.symbol_search_tool',"
        " 'tree_sitter_analyzer.mcp.tools.text_search_tool',"
        " 'tree_sitter_analyzer.cache.query') if m in sys.modules]\n"
        "print(','.join(heavy))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == ""


def test_search_defaults_are_re_exported_unchanged() -> None:
    from tree_sitter_analyzer.mcp.tools import search_defaults
    from tree_sitter_analyzer.mcp.tools.symbol_search_tool import (
        DEFAULT_SYMBOL_SEARCH_LIMIT,
        SYMBOL_SEARCH_KINDS,
    )
    from tree_sitter_analyzer.mcp.tools.text_search_tool import (
        DEFAULT_TEXT_SEARCH_LIMIT,
        MAX_TEXT_SEARCH_LIMIT,
    )

    assert (
        DEFAULT_SYMBOL_SEARCH_LIMIT == search_defaults.DEFAULT_SYMBOL_SEARCH_LIMIT == 15
    )
    assert SYMBOL_SEARCH_KINDS is search_defaults.SYMBOL_SEARCH_KINDS
    assert DEFAULT_TEXT_SEARCH_LIMIT == 100
    assert MAX_TEXT_SEARCH_LIMIT == 1000


def test_python_dash_m_uses_the_installed_program_name(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["C:/x/tree_sitter_analyzer/__main__.py"])
    assert create_argument_parser().prog == "tree-sitter-analyzer"


def test_console_script_aliases_keep_their_own_name(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["/usr/bin/code-analyzer"])
    assert create_argument_parser().prog == "code-analyzer"


def test_no_arguments_prints_the_short_help_on_stderr(monkeypatch, capsys) -> None:
    from tree_sitter_analyzer.cli_main import main

    monkeypatch.setattr(sys, "argv", ["cli"])
    with pytest.raises(SystemExit) as exc:
        main()
    out, err = capsys.readouterr()
    assert exc.value.code == 1
    assert out == ""
    assert err.startswith("ERROR: File path not specified.\n")
    assert err.endswith(format_agent_help())
    assert len(err) < 3000


def test_bare_version_fast_path_uses_the_same_program_name(monkeypatch, capsys) -> None:
    from tree_sitter_analyzer import __version__
    from tree_sitter_analyzer.cli_main import _exit_if_bare_version_request

    monkeypatch.setattr(sys, "argv", ["C:/x/tree_sitter_analyzer/__main__.py"])
    with pytest.raises(SystemExit):
        _exit_if_bare_version_request(["--version"])
    assert capsys.readouterr().out == f"tree-sitter-analyzer {__version__}\n"
