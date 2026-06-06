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
# never match a bare *method* name like ``substring`` or ``containsKey`` on an
# inferred JDK receiver, so those call edges fall through to ``unknown``. This
# curated table is consulted by the cascade's language-aware
# ``_try_stdlib_method`` tier — AFTER every project-binding rule — to classify
# such names as ``stdlib`` when (and only when) the project defines no
# compatible-language (Java) method of that name. Grouped by owning type for
# auditability.
#
# CURATION RULE — PRECISION over recall (Codex P2 #326).
# The name tiers carry NO receiver-type evidence (type inference deferred), and
# the project-ownership gate only separates *project* from *not-project* — NOT
# *stdlib* from *third-party/domain*. So precision must come entirely from
# CURATION: a name is KEPT only if a domain object or popular third-party
# library is VERY UNLIKELY to define a method of that exact name — i.e. it is
# distinctively the JDK String / Map / Stream / Optional API.
#
# Bare generic verbs that domain & third-party objects routinely define are
# DELIBERATELY DROPPED, because the tiers cannot tell ``Cache.get`` (Guava, not
# JDK), ``builder.set``, ``repo.add`` or ``domainStream.map`` apart from a JDK
# receiver — they would otherwise be mislabelled ``stdlib``. Dropped names:
# add, addAll, remove, removeAll, removeIf, retainAll, get, set, put, putAll,
# contains, containsAll, values, iterator, hasNext, next, forEach, toArray,
# isEmpty, size, clear, merge, indexOf, lastIndexOf, trim, replace, replaceAll,
# split, concat, matches, map, filter, reduce, sorted, distinct, limit, skip,
# peek, count, min, max. This mirrors STDLIB_METHODS_PY, which likewise excludes
# set / map / filter / put as too-commonly-project-defined.
# ---------------------------------------------------------------------------

# INTERFACE-METHOD NAMES ARE EXCLUDED WHOLESALE (Codex P2 #326, review P1).
# ``stream``/``parallelStream``/``collect``/``map``/``filter``… are
# ``java.util.stream.Stream`` **interface** methods, and
# ``containsKey``/``keySet``/``entrySet``/``computeIfAbsent``/``getOrDefault``…
# are ``java.util.Map`` / ``Collection`` **interface** methods. Every reactive
# library (Reactor ``Flux``/``Mono``), collection wrapper (Guava
# ``ImmutableList``, Spring Data ``Streamable``), and domain type that
# implements those interfaces (a ``Registry<K,V> implements Map``, an
# ``OrderQueue implements Collection``) defines them — and the AST cache does
# NOT index inherited methods from external interfaces, so ``_project_owns``
# returns False and the call would be mislabelled ``stdlib``. Without
# receiver-type evidence at this tier, the ONLY safe names are those that live
# on a ``final`` JDK type with no common interface or popular-library twin.

# java.lang.String — a ``final`` class, so a domain type can never *be* a
# String. Only names that are also distinctively String (not on the
# ``CharSequence`` interface, not adopted by domain value/protocol objects)
# survive: ``charAt``/``chars`` (CharSequence interface), ``startsWith``/
# ``endsWith`` (java.nio.file.Path, domain Url/Version), ``getBytes`` (domain
# Packet/Buffer), ``isBlank`` (domain FormField), ``lines`` (BufferedReader)
# are all DROPPED. Also DROPPED (review HIGH/MEDIUM): ``toUpperCase``/
# ``toLowerCase`` (DDD string value objects — ``Email``/``Username``/``Slug``,
# Spring Data ``SqlIdentifier`` — routinely define them) and ``repeat`` (domain
# scheduler/animation/rule builders: ``Schedule.repeat(3)``).
_JAVA_STRING_METHODS = frozenset(
    {
        "substring",
        "stripLeading",
        "stripTrailing",
        "replaceFirst",
        "codePointAt",
        "toCharArray",
        "intern",
        "formatted",
    }
)

# java.util.Optional — a ``final`` class. Keep only names with no vavr ``Option``
# / domain ``Maybe``/``Result`` twin: vavr uses ``getOrElse``/``getOrElseThrow``
# (not ``orElseGet``/``orElseThrow``) and has no ``ifPresentOrElse``. ``orElse``
# and ``isPresent`` (both on vavr ``Option`` and domain optionals) are DROPPED.
_JAVA_OPTIONAL_METHODS = frozenset(
    {
        "orElseGet",
        "orElseThrow",
        "ifPresent",
        "ifPresentOrElse",
    }
)

STDLIB_METHODS_JAVA: frozenset[str] = _JAVA_STRING_METHODS | _JAVA_OPTIONAL_METHODS


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
# owning library for auditability.
#
# Same PRECISION lens as STDLIB_METHODS_JAVA (Codex P2 #326, review P1/P2): keep
# only the ``assertX`` / ``assumeX`` / ``assertThatX`` family — bare static
# entry-point calls (``assertEquals(a, b)``) that a domain object essentially
# never defines as an instance method. Every RECEIVER-style Mockito/AssertJ name
# is DROPPED because the tier sees no receiver and the names collide with
# production code: ``verify`` (``Signature.verify``/``Certificate.verify``/JWT
# ``Token.verify``), ``when`` (Spring Security / rule-DSL ``rule.when``), ``mock``
# / ``spy`` (custom factories), and the fluent ``isEqualTo``/``isInstanceOf``/
# ``containsExactly``/``hasSize``/``then*``/``do*``/``will*`` (domain value
# objects, builders, state machines). ``fail``/``given`` likewise stay dropped.
# ---------------------------------------------------------------------------

# JUnit 4/5 + AssertJ static assertion entry points (bare ``assertX(...)`` /
# ``assumeX(...)`` / ``assertThatX(...)`` calls — distinctively the test stack).
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
        "assertThat",  # JUnit/Hamcrest/AssertJ assertThat entry point
        "assertThatThrownBy",  # AssertJ
        "assertThatExceptionOfType",  # AssertJ
        "assumeTrue",
        "assumeFalse",
    }
)

EXTERNAL_METHODS_JAVA: frozenset[str] = _JUNIT_METHODS


__all__ = [
    "EXTERNAL_METHODS_JAVA",
    "JAVA_LANG_TYPES",
    "JDK_PACKAGE_PREFIXES",
    "STDLIB_METHODS_JAVA",
    "is_jdk_prefix",
]
