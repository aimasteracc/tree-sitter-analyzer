"""Conservative Go classification tiers (RFC-0010, first wave).

The RFC-0008 lesson is MANDATORY here: include a name in a classified tier
ONLY if it is (near-)exclusively that API and unlikely to be a user symbol.
For Go we classify by the *package qualifier* of a call (``fmt.Println`` →
package ``fmt``), not by the bare method name — Go stdlib calls are always
``package.Func`` and the package identifier is a far more reliable signal
than the function name. An over-broad set would mis-classify third-party or
domain calls; precision beats recall, so an ``unknown`` edge is correct and a
mis-classified one is the exact CodeGraph failure this project avoids.

``STDLIB_PACKAGES_GO`` is therefore a small, hand-audited set of canonical
Go standard-library top-level package names. A ``pkg.Func`` call classifies
as ``stdlib`` ONLY when ``pkg`` is in this set AND the project does not itself
define a symbol named ``pkg`` (shadowing preserved).

``EXTERNAL_PACKAGES_GO`` is intentionally EMPTY for the first PR: there is no
package qualifier that is (near-)exclusively one third-party library and
never a user import alias, so everything non-stdlib stays ``unknown`` rather
than risk a mis-classification. An empty tier is correct (RFC-0010).
"""

from __future__ import annotations

import re

#: Canonical Go standard-library top-level package names. Kept deliberately
#: small and unambiguous — each is a well-known stdlib package whose short
#: identifier is very unlikely to collide with a project-defined symbol. When
#: in doubt a package is LEFT OUT (stays ``unknown``), never guessed in.
STDLIB_PACKAGES_GO: frozenset[str] = frozenset(
    {
        "fmt",
        "errors",
        "strings",
        "strconv",
        "bytes",
        "bufio",
        "sort",
        "unicode",
        "math",
        "time",
        "context",
        "sync",
        "regexp",
        "encoding",
        "json",
        "io",
        "os",
        "path",
        "filepath",
        "reflect",
        "runtime",
        "flag",
        "log",
        "net",
        "http",
        "url",
        "utf8",
        "atomic",
        "rand",
        "bits",
    }
)

#: Empty for the first PR — see module docstring. No Go third-party package
#: qualifier is safe to classify as ``external`` without receiver/import
#: evidence, so everything non-stdlib stays ``unknown``.
EXTERNAL_PACKAGES_GO: frozenset[str] = frozenset()


#: One Go ``import`` spec: optional local name (alias / ``.`` / ``_``) on the
#: SAME line, immediately before a double-quoted module path. Anchored so the
#: local name must sit right against the quote (``jsonx "encoding/json"``) — a
#: stray keyword like ``import`` on its own line is never captured as an alias.
_GO_IMPORT_SPEC = re.compile(r'(?:(?P<local>[A-Za-z_.][\w.]*)[ \t]+)?"(?P<path>[^"]+)"')

#: Strips the leading ``import`` keyword (and an optional ``(``) so the keyword
#: is never mistaken for an import alias when it abuts the first spec on one
#: line (``import "fmt"``).
_GO_IMPORT_KEYWORD = re.compile(r"\bimport\b\s*\(?")

#: Matches, in priority order, ONE of: an interpreted string literal
#: (``"..."`` with escapes), a raw string literal (`` `...` ``), a ``//`` line
#: comment, or a ``/* ... */`` block comment. Alternation order matters — a
#: string is matched BEFORE a comment so a ``//`` that lives inside a path like
#: ``"net/http"`` is never mistaken for the start of a comment. Comments are
#: replaced with a space (so a commented spec leaves no quoted path behind);
#: string literals are preserved verbatim. Used to strip Go comments before the
#: import-spec matcher runs (Codex P2: a commented ``// "net/http"`` must not
#: leak an ``http`` qualifier).
_GO_STRING_OR_COMMENT = re.compile(
    r'"(?:\\.|[^"\\])*"'  # interpreted string literal
    r"|`[^`]*`"  # raw string literal
    r"|//[^\n]*"  # line comment
    r"|/\*.*?\*/",  # block comment (non-greedy, spans newlines)
    re.DOTALL,
)


def _strip_go_comments(raw: str) -> str:
    """Remove Go ``//`` and ``/* */`` comments, preserving string literals.

    A ``//`` or ``/* */`` that lives INSIDE a double-quoted (or raw) string is
    not a comment, so the matcher consumes whole string literals first and only
    replaces genuine comments (with a space). This prevents a commented-out
    import path (``// "net/http"``) from being matched as a real import spec.
    """

    def _repl(m: re.Match[str]) -> str:
        token = m.group(0)
        # A matched string literal is kept verbatim; a comment becomes a space.
        return token if token[:1] in ('"', "`") else " "

    return _GO_STRING_OR_COMMENT.sub(_repl, raw)


def parse_go_import_block(raw: str) -> dict[str, str]:
    """Parse a Go import-block string into ``{qualifier -> stdlib package}``.

    ``raw`` is the verbatim text the indexer stores for a ``kind='import'``
    symbol, e.g. ``'import "fmt"'`` or
    ``'import (\\n\\t"fmt"\\n\\tjsonx "encoding/json"\\n)'``.

    Only STDLIB imports that expose a *usable package qualifier* are returned:

    * a plain import (``"net/http"``) maps the package's final path segment
      (``http``) to its stdlib head (``http``) — the qualifier used in code;
    * an aliased import (``jsonx "encoding/json"``) maps the alias (``jsonx``)
      to the stdlib head (``json``);
    * blank (``_ "net/http"``) and dot (``. "strings"``) imports are EXCLUDED
      — they expose no ``pkg.Func`` qualifier, so they must not enable stdlib
      classification of a same-named variable.

    Non-stdlib imports are excluded too (the stdlib tier is the only consumer).
    The mapping is conservative by construction: a variable that merely shares
    a stdlib package's name but is never imported never appears here, so the
    resolver leaves it ``unknown`` (RFC-0008 precision-over-recall).
    """
    out: dict[str, str] = {}
    # Strip Go comments FIRST (string-literal aware) so a commented-out spec
    # (``// "net/http"``) leaves no quoted path for the matcher to capture.
    uncommented = _strip_go_comments(raw or "")
    # Drop every ``import`` keyword (and trailing ``(``) so it can never be
    # captured as a same-line alias for the first spec.
    cleaned = _GO_IMPORT_KEYWORD.sub(" ", uncommented)
    for m in _GO_IMPORT_SPEC.finditer(cleaned):
        local = m.group("local")
        path = m.group("path")
        if not path:
            continue
        # Final path segment is Go's default package identifier.
        package = path.rsplit("/", 1)[-1]
        if package not in STDLIB_PACKAGES_GO:
            continue
        if local in (".", "_"):
            # dot import injects names into file scope (no qualifier); blank
            # import is side-effect only — neither yields a usable ``pkg.Func``.
            continue
        qualifier = local if local else package
        out[qualifier] = package
    return out


__all__ = [
    "EXTERNAL_PACKAGES_GO",
    "STDLIB_PACKAGES_GO",
    "parse_go_import_block",
]
