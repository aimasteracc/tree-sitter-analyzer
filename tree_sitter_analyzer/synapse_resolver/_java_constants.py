"""JDK / common-third-party package prefixes for the Java resolver.

A call whose receiver type resolves to one of these package prefixes is
tagged ``external`` (a *terminal* resolution — the target lives outside
the indexed project and never needs re-resolution) rather than
``unknown`` (which keeps the edge in the backfill re-scan set forever).

Kept in a dedicated module so the literal sets stay out of the resolver
logic and the file-size rule is honoured.
"""

from __future__ import annotations

# Package prefixes that are part of the JDK / Jakarta EE platform. Any FQN
# starting with one of these (``java.util.List``, ``javax.swing.*``,
# ``jakarta.servlet.*``) is platform-provided, not project code.
JDK_PACKAGE_PREFIXES: frozenset[str] = frozenset(
    {
        "java.",
        "javax.",
        "jakarta.",
        "jdk.",
        "sun.",
        "com.sun.",
        "org.w3c.dom.",
        "org.xml.sax.",
        "org.omg.",
    }
)

# Simple type names that live in ``java.lang`` and are usable without an
# explicit import. A receiver matching one of these resolves to
# ``external`` even when no import statement names it.
JAVA_LANG_TYPES: frozenset[str] = frozenset(
    {
        "Object",
        "String",
        "StringBuilder",
        "StringBuffer",
        "CharSequence",
        "Integer",
        "Long",
        "Short",
        "Byte",
        "Double",
        "Float",
        "Boolean",
        "Character",
        "Number",
        "Math",
        "System",
        "Thread",
        "Runnable",
        "Throwable",
        "Exception",
        "RuntimeException",
        "Error",
        "Class",
        "Enum",
        "Iterable",
        "Comparable",
        "Cloneable",
        "Void",
        "Process",
        "ProcessBuilder",
        "Runtime",
        "Package",
        "ClassLoader",
        "StackTraceElement",
    }
)


def is_jdk_prefix(fqn: str) -> bool:
    """True when ``fqn`` begins with a known JDK / platform package prefix."""
    return any(fqn.startswith(prefix) for prefix in JDK_PACKAGE_PREFIXES)


__all__ = ["JAVA_LANG_TYPES", "JDK_PACKAGE_PREFIXES", "is_jdk_prefix"]
