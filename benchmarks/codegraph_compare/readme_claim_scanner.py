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
_FENCED_QUANTITY_SENTINEL = " TSAFENCEDQUANTITY "
_SAFE_SPANS = (
    re.compile(r"\b8 MCP tools\b", re.IGNORECASE),
    re.compile(r"\btriage 8 tools\b", re.IGNORECASE),
    re.compile(r"\bAll 8 tools read\b", re.IGNORECASE),
    re.compile(r"8 MCP ツール|8 個の(?:ツール|ファサード)"),
    re.compile(r"8 个(?: MCP 工具|工具)"),
    re.compile(r"13 言語は `?pipeline_registered|13 种语言为 `?pipeline_registered"),
    re.compile(r"5 言語 gap|5 语言 gap"),
    re.compile(r"1 ワークフロー|一个工作流"),
    re.compile(r"\b323 CLI flags\b", re.IGNORECASE),
    re.compile(r"323 の CLI フラグ|323 个 CLI flag", re.IGNORECASE),
    re.compile(r"\b(?:FTS5|BM25)\b"),
    re.compile(r"\bE[0-4]\b"),
    re.compile(r"\bE2E\b", re.IGNORECASE),
    re.compile(r"(?<![\w@])@o93\b", re.IGNORECASE),
    re.compile(r"\b(?:RFC|GH|issue)[- #]\d+\b", re.IGNORECASE),
    re.compile(r"\bcommit\s+`?[0-9a-f]{7,40}`?\b", re.IGNORECASE),
    re.compile(r"\bStep\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # Structural heading/list numbers are handled by
    # ``_remove_controlled_structural_marker`` so large claim-bearing values survive.
    re.compile(r"\bv\d+(?:\.(?:\d+|x)){1,2}\b", re.IGNORECASE),
    re.compile(r"\bversion\s+v?\d+(?:\.\d+){1,2}\b", re.IGNORECASE),
    re.compile(r"\buv\s*[><=]+\s*\d+(?:\.\d+){1,2}\b", re.IGNORECASE),
    re.compile(r"≥\s*\d+(?:\.(?:\d+|x)){1,2}\b", re.IGNORECASE),
    re.compile(r"`python3 --version`", re.IGNORECASE),
)
_PYTHON_VERSION_SPAN = re.compile(
    r"\bPython(?:\s+version)?\s+v?\d+(?:\.\d+){1,2}(?:\+|\s*(?:or|and)\s+(?:newer|later))?",
    re.IGNORECASE,
)
_NUMBER_WORD = (
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|"
    r"billion|trillion|dozen|score|couple|pair|hundreds|thousands|millions|"
    r"billions|trillions|dozens|scores|couples|pairs|several|many|few|half|quarter|third|"
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
_QUANTITATIVE_SUPERLATIVE = re.compile(
    r"\b(?:"
    r"fastest|slowest|"
    r"(?:highest|lowest)\s+(?:(?:measured|observed|overall|average|mean|peak)\s+)?"
    r"(?:throughput|latency|accuracy|performance|speed|rate|score|memory|time|cost|usage|use)|"
    r"(?:most|least)\s+(?:efficient|performant|accurate|memory(?:[- ]efficient)?|"
    r"resource(?:[- ]efficient)?|throughput|latency|performance|speed|usage|use)|"
    r"(?:best|worst)\s+(?:measured\s+)?(?:throughput|latency|accuracy|performance|"
    r"speed|rate|score|memory|time|cost|usage|use)"
    r")\b",
    re.IGNORECASE,
)


def _generated_language_sections() -> tuple[str, ...]:
    """Return canonical trilingual outputs; generator failures disable exclusions."""
    try:
        from scripts.generate_language_support_inventory import render_markdown

        return tuple(
            render_markdown(compact=True, locale=locale).rstrip()
            for locale in ("en", "ja", "zh")
        )
    except Exception:
        return ()


def _marker_regions(
    readme: str, expected_claims: str
) -> tuple[list[tuple[int, int]], list[str]]:
    """Validate sole ordered, non-nested generated sections."""
    violations: list[str] = []
    exclusions: list[tuple[int, int]] = []
    generated_languages = _generated_language_sections()
    for generated_language in generated_languages:
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
    if readme[lang_start:lang_end] not in generated_languages:
        violations.append("README_LANGUAGE_SECTION_UNVERIFIED")
    else:
        exclusions.append((lang_start, lang_end))
    return exclusions, violations


_STRUCTURAL_MARKER = re.compile(
    r"^(?P<prefix>\s*(?:#{1,6}\s+)?)"
    r"(?P<number>\d{1,2})(?P<suffix>[.):]\s+)"
)
_FENCED_OPTION_VALUE = re.compile(
    r"--[a-z][a-z0-9-]*(?:=|\s+)\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)


def _remove_controlled_structural_marker(line: str) -> str:
    """Remove only conventional 1-99 Markdown structure numbering."""
    match = _STRUCTURAL_MARKER.match(line)
    if match is None:
        return line
    return _SAFE_SENTINEL + line[match.end() :]


def _remove_exact_exclusions(line: str, *, fenced: bool = False) -> str:
    result = _remove_controlled_structural_marker(line)
    result = _PYTHON_VERSION_SPAN.sub(_SAFE_SENTINEL, result)
    for pattern in _SAFE_SPANS:
        result = pattern.sub(_SAFE_SENTINEL, result)
    if fenced:
        # Numeric CLI option values are configuration, not public benchmark claims.
        # The distinct sentinel still counts as a quantity when claim prose remains
        # on the same rendered line, preventing an option from camouflaging it.
        result = _FENCED_OPTION_VALUE.sub(_FENCED_QUANTITY_SENTINEL, result)
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


_CJK_QUANTITY = re.compile(
    r"(?:[零〇一二两兩三四五六七八九十百千万萬亿億兆数數]+|半)"
    r"(?:倍|个|個|種|种|言語|语言|語言|ファイル|文件|秒|分|時間|小时|小時|件|冊|仓库|リポジトリ)"
)


def _has_unicode_numeric(text: str) -> bool:
    """Recognize Unicode numeric categories without treating ordinary CJK as numbers."""
    return any(unicodedata.category(character).startswith("N") for character in text)


def _is_quantitative_marketing(text: str) -> bool:
    """Apply the conservative policy gate; this is not a formal proof."""
    has_quantity = bool(
        _has_unicode_numeric(text)
        or _CJK_QUANTITY.search(text)
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
        or _QUANTITATIVE_SUPERLATIVE.search(text)
        or re.search(r"\bsub[- ]second\b", text, re.IGNORECASE)
    )


_FENCED_CLAIM_CONTEXT = re.compile(
    r"\b(?:answers?|files?|requests?|repositories?|languages?|"
    r"throughput|latency|accuracy|performance|speed|rate|score|memory|time|cost|"
    r"usage|use|processed|processes?|handled|handles?|supports?|indexes?|indexed|"
    r"analy[sz](?:e[sd]?|ing)|resolves?|delivers?|finishes?|TSA|tree-sitter-analyzer)\b",
    re.IGNORECASE,
)


def _is_fenced_quantitative_marketing(text: str) -> bool:
    """Scan rendered fence prose without treating source/configuration as prose."""
    has_quantity = bool(
        _FENCED_QUANTITY_SENTINEL.strip() in text
        or _has_unicode_numeric(text)
        or _CJK_QUANTITY.search(text)
        or _WORD_QUANTITY_CONTEXT.search(text)
        or _ONE_SHOT.search(text)
        or _NUMBER_FOLD.search(text)
    )
    has_claim_context = bool(_FENCED_CLAIM_CONTEXT.search(text))
    if _QUANTITATIVE_SUPERLATIVE.search(text):
        return True
    if _COMPARATIVE.search(text):
        numeric_comparison = re.search(
            r"(?:\d|[×倍]|fold)\S*(?:\s+\S+){0,2}\s+"
            r"(?:faster|slower|higher|lower|fewer|more|better|worse)",
            text,
            re.IGNORECASE,
        )
        return bool(has_claim_context or numeric_comparison)
    if re.search(r"\bsub[- ]second\b", text, re.IGNORECASE):
        return has_claim_context
    return bool(has_quantity and has_claim_context)


def scan_readme_claims(readme: str, expected_claims: str) -> tuple[str, ...]:
    """Reject malformed exclusions and unregistered quantitative marketing."""
    regions, violations = _marker_regions(readme, expected_claims)
    lines = readme.splitlines(keepends=True)
    offset = 0
    fence: tuple[str, int] | None = None
    paragraphs: list[tuple[int, list[str], bool]] = []
    paragraph_start = 0
    paragraph_lines: list[str] = []
    paragraph_fenced = False

    def flush() -> None:
        nonlocal paragraph_start, paragraph_lines, paragraph_fenced
        if paragraph_lines:
            paragraphs.append((paragraph_start, paragraph_lines, paragraph_fenced))
            paragraph_lines = []
            paragraph_fenced = False

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
        cleaned = _remove_exact_exclusions(line, fenced=fence is not None)
        if not cleaned.strip():
            flush()
            continue
        if not paragraph_lines:
            paragraph_start = number
            paragraph_fenced = fence is not None
        paragraph_lines.append(cleaned)
        # Code examples are independent rendered lines.  Keeping them separate
        # prevents unrelated command tokens from combining into a prose claim.
        if fence is not None:
            flush()
    flush()
    if fence is not None:
        violations.append("README_FENCE_UNBALANCED")
    for number, paragraph, fenced_paragraph in paragraphs:
        normalized = _normalize_markdown(" ".join(paragraph))
        is_marketing = (
            _is_fenced_quantitative_marketing(normalized)
            if fenced_paragraph
            else _is_quantitative_marketing(normalized)
        )
        if is_marketing:
            violations.append(f"README_UNREGISTERED_QUANTITATIVE_CLAIM:{number}")
    return tuple(dict.fromkeys(violations))
