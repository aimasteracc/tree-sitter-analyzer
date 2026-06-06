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


# ---------------------------------------------------------------------------
# RFC-0008: well-known JDK stdlib METHOD names (the Java analogue of
# ``STDLIB_METHODS_PY``).
#
# The Java resolver's name/import tiers key on receiver *types* and FQNs; they
# never match a bare *method* name like ``add`` or ``substring`` on an inferred
# JDK receiver, so those call edges fall through to ``unknown``. This curated
# table is consulted by the cascade's language-aware ``_try_stdlib_method``
# tier — AFTER every project-binding rule — to classify such names as
# ``stdlib`` when (and only when) the project defines no compatible-language
# (Java) method of that name. Grouped by owning type for auditability.
# High-recall, NOT exhaustive; conservative — generic names that projects
# commonly define are protected by the project-ownership gate anyway, but names
# that are almost always project-domain (``execute``, ``build``, ``handle``,
# ``process``, ``run``) are deliberately EXCLUDED to avoid false positives.
# ---------------------------------------------------------------------------

# java.util collections (List / Map / Set / Collection / Iterator)
_JAVA_COLLECTION_METHODS = frozenset(
    {
        "add",
        "addAll",
        "remove",
        "removeAll",
        "removeIf",
        "retainAll",
        "get",
        "set",
        "put",
        "putAll",
        "putIfAbsent",
        "getOrDefault",
        "containsKey",
        "containsValue",
        "contains",
        "containsAll",
        "indexOf",
        "lastIndexOf",
        "keySet",
        "entrySet",
        "values",
        "subList",
        "iterator",
        "listIterator",
        "hasNext",
        "next",
        "forEach",
        "stream",
        "parallelStream",
        "toArray",
        "isEmpty",
        "size",
        "clear",
        "computeIfAbsent",
        "computeIfPresent",
        "merge",
    }
)

# java.lang.String / CharSequence
_JAVA_STRING_METHODS = frozenset(
    {
        "substring",
        "trim",
        "strip",
        "stripLeading",
        "stripTrailing",
        "split",
        "replace",
        "replaceAll",
        "replaceFirst",
        "toUpperCase",
        "toLowerCase",
        "charAt",
        "indexOf",
        "lastIndexOf",
        "startsWith",
        "endsWith",
        "concat",
        "matches",
        "chars",
        "codePointAt",
        "toCharArray",
        "getBytes",
        "intern",
        "repeat",
        "lines",
        "formatted",
        "isBlank",
    }
)

# java.util.Optional
_JAVA_OPTIONAL_METHODS = frozenset(
    {
        "orElse",
        "orElseGet",
        "orElseThrow",
        "isPresent",
        "isEmpty",
        "ifPresent",
        "ifPresentOrElse",
        "filter",
        "flatMap",
    }
)

# java.util.stream.Stream / Collectors
_JAVA_STREAM_METHODS = frozenset(
    {
        "map",
        "mapToInt",
        "mapToLong",
        "mapToObj",
        "flatMap",
        "filter",
        "collect",
        "reduce",
        "sorted",
        "distinct",
        "limit",
        "skip",
        "peek",
        "anyMatch",
        "allMatch",
        "noneMatch",
        "findFirst",
        "findAny",
        "count",
        "min",
        "max",
        "boxed",
        "toList",
    }
)

STDLIB_METHODS_JAVA: frozenset[str] = (
    _JAVA_COLLECTION_METHODS
    | _JAVA_STRING_METHODS
    | _JAVA_OPTIONAL_METHODS
    | _JAVA_STREAM_METHODS
)


# ---------------------------------------------------------------------------
# RFC-0008: well-known EXTERNAL (third-party) Java test-framework METHOD names
# (the Java analogue of ``EXTERNAL_METHODS_PY``).
#
# These method names are overwhelmingly associated with the JUnit / Mockito /
# AssertJ test stack and whose appearance as a bare call edge almost certainly
# means a third-party library, not a project-defined method. Consulted by the
# language-aware ``_try_external_method`` tier — placed AFTER
# ``_try_stdlib_method`` — to classify such names ``external`` when (and only
# when) the project owns no compatible-language method of that name. Grouped by
# owning library for auditability. Conservative: generic names projects define
# (``setUp``, ``run``, ``execute``, ``before``, ``after``) are EXCLUDED.
# ---------------------------------------------------------------------------

# JUnit (4 + 5 Assertions / Assertions API)
_JUNIT_METHODS = frozenset(
    {
        "assertEquals",
        "assertNotEquals",
        "assertTrue",
        "assertFalse",
        "assertNull",
        "assertNotNull",
        "assertSame",
        "assertNotSame",
        "assertArrayEquals",
        "assertThrows",
        "assertDoesNotThrow",
        "assertAll",
        "assertTimeout",
        "assertThat",  # JUnit/Hamcrest assertThat
        "fail",
        "assumeTrue",
        "assumeFalse",
    }
)

# Mockito
_MOCKITO_METHODS = frozenset(
    {
        "mock",
        "spy",
        "when",
        "verify",
        "verifyNoInteractions",
        "verifyNoMoreInteractions",
        "thenReturn",
        "thenThrow",
        "thenAnswer",
        "thenCallRealMethod",
        "doReturn",
        "doThrow",
        "doAnswer",
        "doNothing",
        "given",  # BDDMockito.given
        "willReturn",
        "willThrow",
    }
)

# AssertJ (fluent assertions)
_ASSERTJ_METHODS = frozenset(
    {
        "assertThatThrownBy",
        "assertThatExceptionOfType",
        "isEqualTo",
        "isNotEqualTo",
        "isNull",
        "isNotNull",
        "isInstanceOf",
        "containsExactly",
        "hasSize",
        "isTrue",
        "isFalse",
    }
)

EXTERNAL_METHODS_JAVA: frozenset[str] = (
    _JUNIT_METHODS | _MOCKITO_METHODS | _ASSERTJ_METHODS
)


__all__ = [
    "EXTERNAL_METHODS_JAVA",
    "JAVA_LANG_TYPES",
    "JDK_PACKAGE_PREFIXES",
    "STDLIB_METHODS_JAVA",
    "is_jdk_prefix",
]
