# Fixture: stdlib call should be tagged but not entered.
# `Path('x')` calls `pathlib.Path` — the resolver must:
#   1) tag the edge callee_resolution='stdlib',
#   2) leave callee_symbol_id IS NULL (we do not index the stdlib), and
#   3) NOT insert a row for `Path` into ast_symbol_rows.
from pathlib import Path


def make_path():
    Path("x")
