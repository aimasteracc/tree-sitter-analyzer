"""Fail-closed README quantitative-claim scanner."""

from __future__ import annotations

import html
import re
import unicodedata

_README_CLAIMS_BEGIN = "<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->"
_README_CLAIMS_END = "<!-- END GENERATED QUANTITATIVE CLAIMS -->"
_LANGUAGE_INVENTORY_BEGIN = "<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->"
_LANGUAGE_INVENTORY_END = "<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->"
_FENCE = re.compile(r"^\s*(?:>\s*)?(`{3,}|~{3,})")
_MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HTML_IMAGE = re.compile(
    r'<img\b[^>]*\balt\s*=\s*(?:"([^"]*)"|\'([^\']*)\')[^>]*>',
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<[^>]*>")
_MARKDOWN_ESCAPE = re.compile(r"\\([^\w\s])")
# Exact controlled spans are replaced with a non-numeric sentinel.  The rest of
# the paragraph is still scanned, so an allowed inventory/version token cannot
# camouflage a rate, measurement, or comparative claim beside it.
_SAFE_SENTINEL = " TSA_SAFE_SPAN "
_SAFE_SPANS = (
    re.compile(r"\b8 MCP tools\b", re.IGNORECASE),
    re.compile(r"\btriage 8 tools\b", re.IGNORECASE),
    re.compile(r"\bAll 8 tools read\b", re.IGNORECASE),
    re.compile(r"\b323 CLI flags\b", re.IGNORECASE),
    re.compile(r"\b(?:FTS5|BM25)\b"),
    re.compile(r"\bE[0-4]\b"),
    re.compile(r"(?<![\w@])@o93\b", re.IGNORECASE),
    re.compile(r"\b(?:RFC|GH|issue)[- #]\d+\b", re.IGNORECASE),
    re.compile(r"\bcommit\s+`?[0-9a-f]{7,40}`?\b", re.IGNORECASE),
    re.compile(r"\bStep\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # A heading/list exclusion consumes only its numbering, never following text.
    re.compile(r"^\s*#{1,6}\s+\d+[.:]\s*"),
    re.compile(r"^\s*\d+[.)]\s+"),
    re.compile(r"\bv\d+(?:\.(?:\d+|x)){1,2}\b", re.IGNORECASE),
    re.compile(r"\bversion\s+v?\d+(?:\.\d+){1,2}\b", re.IGNORECASE),
    re.compile(r"\buv\s*[><=]+\s*\d+(?:\.\d+){1,2}\b", re.IGNORECASE),
)
_PYTHON_VERSION_SPAN = re.compile(
    r"\bPython(?:\s+version)?\s+v?\d+(?:\.\d+){1,2}(?:\+|\s*(?:or|and)\s+(?:newer|later))?",
    re.IGNORECASE,
)
_NUMBER_WORD = (
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|"
    r"billion|trillion|dozen|score|couple|several|many|few|half|quarter|third|"
    r"single|double|triple|quadruple|twice)"
)
# A quantity next to any ordinary word is rejected rather than relying on a
# necessarily incomplete noun allowlist.  This intentionally favors false
# positives: README prose can reword non-quantitative uses or add a narrowly
# governed complete phrase exclusion.
_WORD_QUANTITY_CONTEXT = re.compile(
    rf"\b(?:a[-\s]+)?{_NUMBER_WORD}"
    rf"(?:[-\s]+(?:and[-\s]+)?{_NUMBER_WORD})*"
    rf"(?:[-\s]+(?:as|the))?[-\s]+[A-Za-z][A-Za-z_-]*\b",
    re.IGNORECASE,
)
_ONE_SHOT = re.compile(r"\bone[- ]shot\b", re.IGNORECASE)
_NUMBER_FOLD = re.compile(rf"\b{_NUMBER_WORD}(?:[- ]?fold|[- ]?倍)\b", re.IGNORECASE)
_RATE_OR_MEASUREMENT = re.compile(
    r"\b(?:per\s+[A-Za-z][A-Za-z_-]*|milliseconds?|seconds?|minutes?|hours?|"
    r"days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_COMPARATIVE = re.compile(
    r"\b(?:faster|slower|higher|lower|fewer|more|better|worse|speedups?)\b",
    re.IGNORECASE,
)


def _generated_language_section() -> str | None:
    """Return canonical language output only when its generator is installed."""
    try:
        from scripts.generate_language_support_inventory import render_markdown
    except Exception:  # Generator/load failures disable the exclusion.
        return None
    return render_markdown(compact=True).rstrip()


def _marker_regions(
    readme: str, expected_claims: str
) -> tuple[list[tuple[int, int]], list[str]]:
    """Validate sole ordered, non-nested generated sections."""
    violations: list[str] = []
    exclusions: list[tuple[int, int]] = []
    generated_language = _generated_language_section()
    if generated_language is not None:
        start = readme.find(generated_language)
        if start != -1 and readme.find(generated_language, start + 1) == -1:
            exclusions.append((start, start + len(generated_language)))
    if readme.count(_README_CLAIMS_BEGIN) != 1 or readme.count(_README_CLAIMS_END) != 1:
        violations.append("README_CLAIM_MARKERS_INVALID")
    if (
        readme.count(_LANGUAGE_INVENTORY_BEGIN) != 1
        or readme.count(_LANGUAGE_INVENTORY_END) != 1
    ):
        violations.append("README_LANGUAGE_MARKERS_INVALID")
    if violations:
        return exclusions, violations

    claim_start = readme.index(_README_CLAIMS_BEGIN)
    claim_finish = readme.index(_README_CLAIMS_END)
    lang_start = readme.index(_LANGUAGE_INVENTORY_BEGIN)
    lang_finish = readme.index(_LANGUAGE_INVENTORY_END)
    if claim_finish < claim_start:
        violations.append("README_CLAIM_MARKERS_ORDER")
    if lang_finish < lang_start:
        violations.append("README_LANGUAGE_MARKERS_ORDER")
    claim_end = claim_finish + len(_README_CLAIMS_END)
    lang_end = lang_finish + len(_LANGUAGE_INVENTORY_END)
    if max(claim_start, lang_start) < min(claim_end, lang_end):
        violations.append("README_GENERATED_MARKERS_NESTED")
    if violations:
        return [], violations
    if readme[claim_start:claim_end] != expected_claims:
        violations.append("README_CLAIM_SECTION_DRIFT")

    exclusions.append((claim_start, claim_end))
    if generated_language is None or readme[lang_start:lang_end] != generated_language:
        violations.append("README_LANGUAGE_SECTION_UNVERIFIED")
    else:
        exclusions.append((lang_start, lang_end))
    return exclusions, violations


def _remove_exact_exclusions(line: str) -> str:
    result = _PYTHON_VERSION_SPAN.sub(_SAFE_SENTINEL, line)
    for pattern in _SAFE_SPANS:
        result = pattern.sub(_SAFE_SENTINEL, result)
    return result


def _normalize_markdown(text: str) -> str:
    normalized = html.unescape(text)
    normalized = _HTML_IMAGE.sub(
        lambda match: match.group(1) or match.group(2), normalized
    )
    previous = None
    while previous != normalized:
        previous = normalized
        normalized = _MARKDOWN_LINK.sub(lambda match: match.group(1), normalized)
    normalized = _HTML_TAG.sub("", normalized)
    normalized = _MARKDOWN_ESCAPE.sub(r"\1", normalized)
    normalized = re.sub(r"[*_~]+", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _has_unicode_numeric(text: str) -> bool:
    """Recognize every Unicode character with a numeric value (Nd, No, Nl, etc.)."""
    for character in text:
        try:
            unicodedata.numeric(character)
        except (TypeError, ValueError):
            continue
        return True
    return False


def _is_quantitative_marketing(text: str) -> bool:
    """Apply the conservative policy gate; this is not a formal proof."""
    has_quantity = bool(
        _has_unicode_numeric(text)
        or _WORD_QUANTITY_CONTEXT.search(text)
        or _ONE_SHOT.search(text)
        or _NUMBER_FOLD.search(text)
    )
    if has_quantity:
        return True
    # Measurements/rates left after a safe span was replaced must still fail.
    # Comparative wording is likewise rejected when it survives an exclusion.
    return bool(
        _RATE_OR_MEASUREMENT.search(text)
        or _COMPARATIVE.search(text)
        or re.search(r"\bsub[- ]second\b", text, re.IGNORECASE)
    )


def scan_readme_claims(readme: str, expected_claims: str) -> tuple[str, ...]:
    """Reject malformed exclusions and unregistered quantitative marketing."""
    regions, violations = _marker_regions(readme, expected_claims)
    lines = readme.splitlines(keepends=True)
    offset = 0
    fence: tuple[str, int] | None = None
    paragraphs: list[tuple[int, list[str]]] = []
    paragraph_start = 0
    paragraph_lines: list[str] = []

    def flush() -> None:
        nonlocal paragraph_start, paragraph_lines
        if paragraph_lines:
            paragraphs.append((paragraph_start, paragraph_lines))
            paragraph_lines = []

    for number, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip("\r\n")
        start, end = offset, offset + len(line)
        offset += len(raw_line)
        if any(
            start >= region_start and end <= region_end
            for region_start, region_end in regions
        ):
            flush()
            continue
        fence_match = _FENCE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif re.fullmatch(
                rf"\s*(?:>\s*)?{re.escape(fence[0])}{{{fence[1]},}}\s*", line
            ):
                fence = None
            flush()
            continue
        if fence is not None:
            continue
        cleaned = _remove_exact_exclusions(line)
        if not cleaned.strip():
            flush()
            continue
        if not paragraph_lines:
            paragraph_start = number
        paragraph_lines.append(cleaned)
    flush()
    if fence is not None:
        violations.append("README_FENCE_UNBALANCED")
    for number, paragraph in paragraphs:
        normalized = _normalize_markdown(" ".join(paragraph))
        if _is_quantitative_marketing(normalized):
            violations.append(f"README_UNREGISTERED_QUANTITATIVE_CLAIM:{number}")
    return tuple(dict.fromkeys(violations))
