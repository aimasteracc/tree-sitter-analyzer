"""Conservative libc free-function tier for the C resolver (RFC-0010).

The RFC-0008 lesson is MANDATORY here: a bare name is classified ``stdlib``
ONLY when it is (near-)exclusively a libc API and very unlikely to be a
user-defined function. C has NO namespace qualifier (no ``std::`` analogue) and
no member-method dispatch, so the *only* classified tier is this libc
free-function name set — and even then every hit is gated on the project NOT
owning a same-named C function (project shadowing wins, see ``c.py``).

PRUNING RATIONALE (precision over recall — an ``unknown`` edge is never a
mis-wire, an over-broad name set is a moat breach):

INCLUDED — near-exclusively libc, rarely a user function name:
  * allocation:   ``malloc`` / ``calloc`` / ``realloc`` (but NOT ``free`` —
    ``free`` is an extremely common user method/function name, e.g. a custom
    allocator's ``free`` or a resource ``free``; dropping it is mandatory).
  * formatted IO: the ``printf`` family (``printf`` / ``fprintf`` /
    ``sprintf`` / ``snprintf`` / ``vsnprintf``) — unspoofably libc.
  * memory ops:   ``memcpy`` / ``memmove`` / ``memset`` / ``memcmp`` — the
    ``mem*`` family is libc-owned by convention.
  * string ops:   ``strlen`` / ``strcmp`` / ``strncmp`` / ``strcpy`` /
    ``strncpy`` / ``strcat`` / ``strncat`` / ``strdup`` / ``strchr`` /
    ``strrchr`` / ``strstr`` — the ``str*`` family is near-exclusively libc.
  * stdio file:   the ``f*`` stdio variants (``fopen`` / ``fclose`` /
    ``fread`` / ``fwrite`` / ``fseek`` / ``ftell`` / ``fgets`` / ``fputs`` /
    ``fflush``) — the ``f``-prefix disambiguates from generic user verbs.

EXCLUDED — collide too heavily with ordinary user code:
  * ``free`` — common user "free this resource" function.
  * bare POSIX verbs ``open`` / ``close`` / ``read`` / ``write`` / ``send`` /
    ``recv`` — ubiquitous user method names.
  * generic verbs ``find`` / ``sort`` / ``init`` / ``exit`` / ``abort`` /
    ``puts`` / ``gets`` / ``getc`` / ``putc`` — too easily user helpers.

An empty tier would also be correct; this small high-confidence core is the
conservative middle ground. Everything not in the set stays ``project`` /
``local`` / ``unknown``.
"""

from __future__ import annotations

# Bare libc free-function names classified ``stdlib`` when the project does NOT
# own a same-named C function. Deliberately small and high-confidence — see the
# module docstring for the include/exclude rationale.
LIBC_FUNCTIONS_C: frozenset[str] = frozenset(
    {
        # allocation (NOT ``free`` — common user name)
        "malloc",
        "calloc",
        "realloc",
        # formatted IO — the printf family
        "printf",
        "fprintf",
        "sprintf",
        "snprintf",
        "vsnprintf",
        # memory ops — the mem* family
        "memcpy",
        "memmove",
        "memset",
        "memcmp",
        # string ops — the str* family
        "strlen",
        "strcmp",
        "strncmp",
        "strcpy",
        "strncpy",
        "strcat",
        "strncat",
        "strdup",
        "strchr",
        "strrchr",
        "strstr",
        # stdio file ops — the f* variants (f-prefix disambiguates from verbs)
        "fopen",
        "fclose",
        "fread",
        "fwrite",
        "fseek",
        "ftell",
        "fgets",
        "fputs",
        "fflush",
    }
)


def is_libc_function(name: str) -> bool:
    """True when ``name`` is a conservatively-classified libc free function.

    A pure membership check against :data:`LIBC_FUNCTIONS_C`. The caller is
    responsible for the project-ownership shadow gate (a project-defined C
    function of the same name must win over this classification).
    """
    if not name:
        return False
    return name in LIBC_FUNCTIONS_C


__all__ = [
    "LIBC_FUNCTIONS_C",
    "is_libc_function",
]
