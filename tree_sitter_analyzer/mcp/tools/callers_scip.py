"""Opt-in SCIP evidence for ``nav action=callers`` (TS / JS): classify enumerated sites.

TSA blocks ``complete`` on the call sites it cannot bind (``unresolved_inbound_sites``,
``unresolved_sites``, ``name_only_sites``). A SCIP index built by the TypeScript
compiler (scip-typescript) can bind many of them. This module only *classifies*
sites TSA has already enumerated; every other TSA check still runs. The
fail-closed contract:

1. A site is ``proven_target`` when every occurrence of the target's name on
   it resolves to the target or to a trusted other symbol, and at least one to
   the target: its enclosing definition becomes a caller with
   ``confidence_tier: "scip"``.
2. A site is ``proven_other`` when every such occurrence resolves to a trusted
   other symbol (:mod:`callers_scip_trust`): it is dropped and recorded with
   reason ``SCIP_RESOLVED_OTHER``.
3. Anything else stays ``open`` exactly as today: no occurrence, more textual
   occurrences of the name than SCIP reports, two symbols at one position,
   an untrusted class, or an enclosing definition TSA and SCIP disagree on.
4. SCIP never removes a TSA caller. A SCIP reference to the target that TSA
   lists nowhere (not inside a listed caller, not at an open site) is the
   blocker ``SCIP_UNLISTED_REFERENCE`` (check ``scip_agreement``).
5. A stale, absent or undecodable index, or a target SCIP cannot map
   unambiguously, gives no evidence (``scip.status`` / ``scip.target`` say why).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from . import callers_scip_imports as imports
from . import callers_scip_symbols as sym
from .callers_outcomes import NotChecked, Scope, checked
from .callers_scip_index import ROLE_IMPORT, Occurrence
from .callers_scip_source import ScipSource, member_name, open_source
from .callers_scip_trust import TARGET, TRUSTED_OTHER, classify

#: Confidence tier and ``resolution_kind`` of a caller SCIP proves.
SCIP_TIER = "scip"
#: ``reason_code`` of a site SCIP proves calls another symbol.
RESOLVED_OTHER_REASON = "SCIP_RESOLVED_OTHER"
#: ``scip_agreement`` problem: a SCIP reference to the target TSA lists nowhere.
UNLISTED_REASON = "SCIP_UNLISTED_REFERENCE"
#: ``scip_agreement`` could not run (the evidence could not be evaluated).
UNCHECKED_REASON = "SCIP_AGREEMENT_UNCHECKED"
CHECK_NAME = "scip_agreement"
PROVEN_TARGET = "proven_target"
PROVEN_OTHER = "proven_other"
OPEN = "open"
#: Listed entries in the ``scip`` field (totals are kept beside them).
LIST_CAP = 20
MODULE = "<module>"


@dataclass(frozen=True)
class SiteVerdict:
    outcome: str
    why: str
    classes: tuple[str, ...] = ()


@dataclass
class Applied:
    """The site lists after classification (new lists; inputs are not modified)."""

    declaring: list[dict[str, Any]] | None
    excluded: list[dict[str, Any]] | None
    unresolved: list[dict[str, Any]] | None
    unresolved_excluded: list[dict[str, Any]]
    possible: list[dict[str, Any]]
    callers: list[dict[str, Any]]


@dataclass
class ScipLayer:
    """One query's SCIP evidence: classification, added callers, agreement."""

    source: ScipSource
    name: str
    counts: dict[str, int] = field(
        default_factory=lambda: {PROVEN_TARGET: 0, PROVEN_OTHER: 0, OPEN: 0}
    )
    resolved_other: list[dict[str, Any]] = field(default_factory=list)
    unlisted: list[dict[str, Any]] = field(default_factory=list)
    disagreements: list[dict[str, Any]] = field(default_factory=list)
    added: int = 0
    #: Why sites stayed open (``untrusted:<class>``, ``attribution``, ...).
    open_reasons: dict[str, int] = field(default_factory=dict)
    #: TSA's call graph (lazily built), for caller spans and attribution.
    graph: Callable[[], Any] | None = None
    _verdicts: dict[tuple[str, int, str], SiteVerdict] = field(default_factory=dict)
    _import_spans: dict[str, tuple[imports.Span, ...]] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.source.usable

    # -- site classification -------------------------------------------------

    def classify_site(self, file: str, line: int, callee: str | None) -> SiteVerdict:
        key = (file, line, callee or "")
        found = self._verdicts.get(key)
        if found is None:
            found = self._classify(file, line, callee)
            self._verdicts[key] = found
        return found

    def _classify(self, file: str, line: int, callee: str | None) -> SiteVerdict:
        src = self.source
        index, graph, ctx = src.index, src.graph, src.context
        assert index is not None and graph is not None and ctx is not None
        if file not in index.documents or line < 1:
            return SiteVerdict(OPEN, "file_not_indexed")
        lines = src.lines(file)
        span = range(line - 1, line + (callee or "").count("\n"))
        positions: dict[tuple[int, int], set[str]] = {}
        for l0 in span:
            for occ in index.on_line(file, l0):
                if not occ.is_definition and self._names_target(occ, lines):
                    positions.setdefault((occ.line, occ.col), set()).add(occ.symbol)
        if not positions:
            return SiteVerdict(OPEN, "no_occurrence")
        if any(len(symbols) > 1 for symbols in positions.values()):
            return SiteVerdict(OPEN, "ambiguous_occurrence")
        pattern = _name_pattern(self.name)
        textual = sum(len(pattern.findall(lines[l0])) for l0 in span if l0 < len(lines))
        if textual != len(positions):
            return SiteVerdict(OPEN, "occurrence_count_mismatch")
        classes = tuple(
            classify(graph, next(iter(symbols)), ctx, src.lines)
            for symbols in positions.values()
        )
        if all(c in TRUSTED_OTHER for c in classes):
            return SiteVerdict(PROVEN_OTHER, "trusted_other", classes)
        if TARGET in classes and all(
            c == TARGET or c in TRUSTED_OTHER for c in classes
        ):
            return SiteVerdict(PROVEN_TARGET, "resolves_to_target", classes)
        return SiteVerdict(OPEN, "untrusted_class", classes)

    def _names_target(self, occ: Occurrence, lines: list[str]) -> bool:
        if sym.is_local(occ.symbol):
            text = lines[occ.line] if occ.line < len(lines) else ""
            return occ.line == occ.end_line and text[occ.col : occ.end_col] == self.name
        return member_name(occ.symbol) == self.name

    # -- attribution -----------------------------------------------------------

    def attribute(
        self, graph: Any, file: str, line: int, expected: str | None
    ) -> dict[str, Any] | None:
        """The caller entry of a proven site, when TSA and SCIP agree on it."""
        try:
            refs = graph.function_refs_in_file(file)
        except Exception:  # noqa: BLE001 - unreadable graph: no promotion
            return None
        containing = [
            r for r in refs if r.start_line <= line <= (r.end_line or r.start_line)
        ]
        scip_name = self._scip_enclosing(file, line - 1)
        if not containing:
            if scip_name is not None or expected not in (None, "", MODULE):
                return None
            return {
                "file": file,
                "name": MODULE,
                "line": line,
                "end_line": line,
                "scope": "module",
            }
        innermost = min(
            containing, key=lambda r: (r.end_line or r.start_line) - r.start_line
        )
        ties = [
            r
            for r in containing
            if (r.end_line or r.start_line) - r.start_line
            == (innermost.end_line or innermost.start_line) - innermost.start_line
        ]
        if len(ties) != 1 or innermost.name != scip_name:
            return None
        if expected not in (None, "") and expected != innermost.name:
            return None
        return dict(innermost.to_dict())

    def _scip_enclosing(self, file: str, l0: int) -> str | None:
        index = self.source.index
        assert index is not None
        best: tuple[int, str] | None = None
        for occ in index.documents.get(file, ()):
            enc = occ.enclosing
            if not occ.is_definition or enc is None or not enc[0] <= l0 <= enc[2]:
                continue
            if sym.last_kind(occ.symbol) not in ("method", "term"):
                continue
            size = enc[2] - enc[0]
            if best is None or size < best[0]:
                best = (size, member_name(occ.symbol) or "")
        return best[1] if best else None

    # -- applying the evidence ---------------------------------------------------

    def apply(
        self,
        graph: Any,
        *,
        declaring: list[dict[str, Any]] | None,
        excluded: list[dict[str, Any]] | None,
        unresolved: list[dict[str, Any]] | None,
        possible: list[dict[str, Any]],
        call_lines: dict[str, frozenset[int]] | None,
        listed: list[dict[str, Any]],
        target_file: str,
    ) -> Applied:
        added: dict[tuple[str, str, int], dict[str, Any]] = {}
        known = {_identity(c) for c in listed}

        def promote(entry: dict[str, Any] | None) -> bool:
            if entry is None:
                return False
            ident = _identity(entry)
            if ident not in known and ident not in added:
                added[ident] = _scip_caller(entry, target_file)
            return True

        def site_pass(
            sites: list[dict[str, Any]] | None, source: str
        ) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
            if sites is None:
                return None, []
            kept: list[dict[str, Any]] = []
            dropped: list[dict[str, Any]] = []
            for site in sites:
                file, line = str(site.get("file") or ""), int(site.get("line") or 0)
                verdict = self.classify_site(file, line, site.get("callee"))
                if verdict.outcome == PROVEN_TARGET and promote(
                    self.attribute(graph, file, line, site.get("caller"))
                ):
                    self.counts[PROVEN_TARGET] += 1
                    continue
                if verdict.outcome == PROVEN_OTHER:
                    self.counts[PROVEN_OTHER] += 1
                    dropped.append(
                        {**site, "classification": "excluded",
                         "reason_code": RESOLVED_OTHER_REASON}
                    )  # fmt: skip
                    self._record_other(site, source, verdict)
                    continue
                self._note_open(verdict)
                kept.append(site)
            return kept, dropped

        new_declaring, declaring_dropped = site_pass(declaring, "unresolved_sites")
        new_unresolved, unresolved_dropped = site_pass(
            unresolved, "unresolved_inbound_sites"
        )
        new_possible = self._possible_pass(graph, possible, call_lines, promote)
        new_excluded = (
            None
            if excluded is None
            else sorted(
                [*excluded, *declaring_dropped], key=lambda s: (s["file"], s["line"])
            )
        )
        self.added = len(added)
        return Applied(
            new_declaring,
            new_excluded,
            new_unresolved,
            unresolved_dropped,
            new_possible,
            list(added.values()),
        )

    def _possible_pass(
        self,
        graph: Any,
        possible: list[dict[str, Any]],
        call_lines: dict[str, frozenset[int]] | None,
        promote: Callable[[dict[str, Any] | None], bool],
    ) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for caller in possible:
            file = str(caller.get("file") or "")
            start = int(caller.get("line") or 0)
            end = int(caller.get("end_line") or start)
            lines = sorted(
                line
                for line in (call_lines or {}).get(file, ())
                if start <= line <= end
            )
            verdicts = [(line, self.classify_site(file, line, None)) for line in lines]
            proven = [
                line
                for line, v in verdicts
                if v.outcome == PROVEN_TARGET
                and self._same_caller(graph, file, line, caller)
            ]
            if proven and promote(caller):
                self.counts[PROVEN_TARGET] += 1
                continue
            if verdicts and all(v.outcome == PROVEN_OTHER for _l, v in verdicts):
                self.counts[PROVEN_OTHER] += 1
                for line, verdict in verdicts:
                    self._record_other(
                        {"file": file, "line": line, "caller": caller.get("name")},
                        "name_only_sites",
                        verdict,
                    )
                continue
            open_verdicts = [v for _l, v in verdicts if v.outcome != PROVEN_OTHER]
            self._note_open(
                open_verdicts[0] if open_verdicts else SiteVerdict(OPEN, "no_call_line")
            )
            kept.append(caller)
        return kept

    def _note_open(self, verdict: SiteVerdict) -> None:
        self.counts[OPEN] += 1
        if verdict.outcome == PROVEN_TARGET:
            why = "attribution"
        elif verdict.why == "untrusted_class":
            untrusted = sorted(
                {c for c in verdict.classes if c != TARGET and c not in TRUSTED_OTHER}
            )
            why = "untrusted:" + ",".join(untrusted)
        else:
            why = verdict.why
        self.open_reasons[why] = self.open_reasons.get(why, 0) + 1

    def _same_caller(
        self, graph: Any, file: str, line: int, caller: dict[str, Any]
    ) -> bool:
        entry = self.attribute(graph, file, line, str(caller.get("name") or ""))
        return entry is not None and _identity(entry) == _identity(caller)

    def _record_other(
        self, site: dict[str, Any], source: str, verdict: SiteVerdict
    ) -> None:
        self.resolved_other.append(
            {
                "file": site.get("file"),
                "line": site.get("line"),
                "callee": site.get("callee"),
                "list": source,
                "classes": list(verdict.classes),
            }
        )

    # -- agreement -------------------------------------------------------------

    def agreement(
        self,
        callers: Iterable[dict[str, Any]],
        open_lists: Iterable[Iterable[dict[str, Any]] | None],
        excluded: Iterable[dict[str, Any]] | None,
    ) -> tuple[str, ...]:
        """Problem codes of ``scip_agreement``; fills the unlisted / disagreement logs."""
        src = self.source
        index = src.index
        assert index is not None
        spans: dict[str, list[tuple[int, int]]] = {}
        listed_callers = list(callers)
        for caller in listed_callers:
            file, start, end = self.caller_span(caller)
            spans.setdefault(file, []).append((start, end))
        for sites in open_lists:
            for site in sites or ():
                file = str(site.get("file") or "")
                line = int(site.get("line") or 0)
                extra = str(site.get("callee") or "").count("\n")
                spans.setdefault(file, []).append((line, line + extra))
        excluded_lines = {
            (str(s.get("file") or ""), int(s.get("line") or 0)) for s in excluded or ()
        }
        refs = self._target_references()
        for file, occ in refs:
            line = occ.line + 1
            if any(a <= line <= b for a, b in spans.get(file, ())):
                continue
            text = src.lines(file)[occ.line] if occ.line < len(src.lines(file)) else ""
            entry = {"file": file, "line": line, "text": text.strip()[:160]}
            self.unlisted.append(entry)
            if (file, line) in excluded_lines:
                self.disagreements.append(
                    {"kind": "excluded_site_references_target", **entry}
                )
        self._callers_without_reference(listed_callers, refs)
        return (UNLISTED_REASON,) if self.unlisted else ()

    def _target_references(self) -> list[tuple[str, Occurrence]]:
        src = self.source
        index = src.index
        assert index is not None
        out = []
        for target in sorted(src.targets):
            for file, occ in index.references.get(target, ()):
                if occ.roles & ROLE_IMPORT or self._in_import(file, occ):
                    continue
                out.append((file, occ))
        return out

    def _in_import(self, file: str, occ: Occurrence) -> bool:
        """Whether ``occ`` lies inside an import / export-list statement (#1892)."""
        spans = self._import_spans.get(file)
        if spans is None:
            spans = imports.import_spans(file, self.source.lines(file))
            self._import_spans[file] = spans
        return imports.covers(spans, occ.line, occ.col, occ.end_line, occ.end_col)

    def _callers_without_reference(
        self, callers: list[dict[str, Any]], refs: list[tuple[str, Occurrence]]
    ) -> None:
        by_file: dict[str, list[int]] = {}
        for file, occ in refs:
            by_file.setdefault(file, []).append(occ.line + 1)
        for caller in callers:
            if caller.get("resolution_kind") in (SCIP_TIER, "registration"):
                continue
            file, start, end = self.caller_span(caller)
            if not any(start <= line <= end for line in by_file.get(file, ())):
                self.disagreements.append(
                    {
                        "kind": "listed_caller_without_scip_reference",
                        "file": file,
                        "line": start,
                        "name": caller.get("name"),
                    }
                )

    def caller_span(self, caller: dict[str, Any]) -> tuple[str, int, int]:
        """``(file, first line, last line)`` of a listed caller's definition.

        TS / JS caller entries from the SQL path carry no ``end_line``; the end
        then comes from TSA's own definition of that caller, else from SCIP's
        enclosing range of its definition, else the span is the start line only
        (the narrowest: it can only add an unlisted reference, never hide one).
        """
        file = str(caller.get("file") or "").replace("\\", "/")
        start = int(caller.get("line") or 0)
        end = int(caller.get("end_line") or start)
        name = str(caller.get("name") or "")
        if end > start or caller.get("scope") == "module":
            return file, start, end
        found = self._graph_end(file, name, start)
        if found is None:
            found = self._scip_end(file, name, start)
        return file, start, max(end, found or start)

    def _graph_end(self, file: str, name: str, start: int) -> int | None:
        if self.graph is None:
            return None
        try:
            refs = self.graph().function_refs_in_file(file)
        except Exception:  # noqa: BLE001 - unreadable graph: narrower span
            return None
        ends = {
            int(r.end_line or r.start_line)
            for r in refs
            if r.name == name and r.start_line == start
        }
        return ends.pop() if len(ends) == 1 else None

    def _scip_end(self, file: str, name: str, start: int) -> int | None:
        index = self.source.index
        assert index is not None
        ends = set()
        for l0 in (start - 1, start):
            for occ in index.on_line(file, l0):
                enc = occ.enclosing
                if occ.is_definition and enc and member_name(occ.symbol) == name:
                    ends.add(enc[2] + 1)
        return ends.pop() if len(ends) == 1 else None

    # -- reporting ---------------------------------------------------------------

    def report(self) -> dict[str, Any]:
        out = self.source.describe()
        if not self.active:
            return out
        out["sites"] = dict(self.counts)
        if self.open_reasons:
            out["open_reasons"] = dict(sorted(self.open_reasons.items()))
        out["added_callers"] = self.added
        for key, items in (
            ("resolved_other", self.resolved_other),
            ("unlisted_references", self.unlisted),
            ("disagreements", self.disagreements),
        ):
            out[key] = items[:LIST_CAP]
            out[f"{key}_total"] = len(items)
        return out


def _name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w$#])" + re.escape(name) + r"(?![\w$])")


def _identity(caller: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(caller.get("file") or "").replace("\\", "/"),
        str(caller.get("name") or ""),
        int(caller.get("line") or 0),
    )


def _scip_caller(entry: dict[str, Any], target_file: str) -> dict[str, Any]:
    kept: dict[str, Any] = {
        k: entry[k]
        for k in ("file", "name", "line", "end_line", "language", "receiver", "scope")
        if k in entry
    }
    return {
        **kept,
        "callee_resolution": "project",
        "callee_resolved_file": target_file,
        "resolution_kind": SCIP_TIER,
        "via": None,
    }


def open_layer(
    project_root: str | None,
    file_path: str | None,
    func_name: str,
    *,
    qualified: bool,
    graph: Callable[[], Any],
) -> ScipLayer | None:
    """The SCIP layer for one query; ``None`` when SCIP is not opted in."""
    source = open_source(project_root, file_path, func_name, qualified)
    if source is None:
        return None
    bare = func_name.rpartition(".")[2].strip('"')
    layer = ScipLayer(source, bare, graph=graph)
    if source.usable and not _targets_agree(
        source, graph, str(file_path), func_name, qualified
    ):
        source.unmapped = "tsa_definition_mismatch"
    return layer


def _targets_agree(
    source: ScipSource,
    graph: Callable[[], Any],
    file_path: str,
    func_name: str,
    qualified: bool,
) -> bool:
    """Every SCIP target sits in a TSA definition of the target, one to one."""
    try:
        refs = graph().function_refs_in_file(file_path.replace("\\", "/"))
    except Exception:  # noqa: BLE001 - unreadable graph: no evidence
        return False
    owner, _, bare = func_name.rpartition(".")
    owner = owner.rpartition(".")[2]
    wanted = [
        r
        for r in refs
        if r.name == bare.strip('"') and (not qualified or (r.receiver or "") == owner)
    ]
    index = source.index
    assert index is not None
    rel = file_path.replace("\\", "/")
    if not wanted:
        return False
    matched: set[tuple[int, str]] = set()
    for target in source.targets:
        # Overload signatures share the implementation's symbol: the symbol
        # agrees when one of its definitions sits in exactly one TSA definition.
        homes = set()
        for occ in index.documents.get(rel, ()):
            if not occ.is_definition or occ.symbol != target:
                continue
            line = occ.line + 1
            hits = [
                r
                for r in wanted
                if r.start_line <= line <= (r.end_line or r.start_line)
            ]
            if len(hits) == 1:
                homes.add((hits[0].start_line, hits[0].name))
        if len(homes) != 1:
            return False
        matched |= homes
    return len(matched) == len(wanted)


def scip_check(
    layer: ScipLayer,
    ledger: Any,
    scope: Scope,
    *,
    callers: Iterable[dict[str, Any]],
    open_lists: Iterable[Iterable[dict[str, Any]] | None],
    excluded: Iterable[dict[str, Any]] | None,
) -> Any:
    """Record ``scip_agreement`` on ``ledger`` (or mark it not applicable)."""
    if not layer.active:
        src = layer.source
        why = src.status if src.unmapped is None else f"target_{src.unmapped}"
        return ledger.skip(CHECK_NAME, why)
    ledger = ledger.enable(CHECK_NAME)
    try:
        problems = layer.agreement(callers, open_lists, excluded)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ledger.record(CHECK_NAME, NotChecked(UNCHECKED_REASON))
    return ledger.record(CHECK_NAME, checked(scope, *problems))


def restrict_open_sites(
    bound: dict[str, Any], layer: ScipLayer | None
) -> dict[str, Any]:
    """An exhaustive ``open_sites`` bound cannot hold past an unlisted SCIP reference."""
    if layer is None or not layer.unlisted or bound.get("enumerated") is not True:
        return bound
    return {"enumerated": False, "reason": UNLISTED_REASON}


def unlisted_step(func_name: str, layer: ScipLayer) -> str | None:
    """next_step naming the SCIP references no TSA caller or open site covers."""
    if not layer.unlisted:
        return None
    named = "; ".join(f"{r['file']}:{r['line']}" for r in layer.unlisted[:3])
    more = len(layer.unlisted) - 3
    tail = f"; and {more} more" if more > 0 else ""
    return (
        f"The SCIP index references {func_name!r} at {len(layer.unlisted)} "
        f"place(s) that no listed caller or open site covers (`scip."
        f"unlisted_references`): {named}{tail}. Read them: each is a caller or "
        "a use the index did not attribute."
    )


__all__ = [
    "CHECK_NAME",
    "LIST_CAP",
    "OPEN",
    "PROVEN_OTHER",
    "PROVEN_TARGET",
    "RESOLVED_OTHER_REASON",
    "SCIP_TIER",
    "UNCHECKED_REASON",
    "UNLISTED_REASON",
    "Applied",
    "ScipLayer",
    "SiteVerdict",
    "open_layer",
    "restrict_open_sites",
    "scip_check",
    "unlisted_step",
]
