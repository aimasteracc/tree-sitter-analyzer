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


__all__ = ["EXTERNAL_PACKAGES_GO", "STDLIB_PACKAGES_GO"]
