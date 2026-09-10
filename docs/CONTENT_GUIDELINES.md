# Content Guidelines — external-facing publications

Rules for anything produced by or for this project that is meant to be read
*outside* the repository: README variants, `docs/articles/*`, launch-plan copy,
GitHub repository metadata (description, topics), and any social/forum post
drafts prepared under a development cycle. Code-contribution rules live in
[CONTRIBUTING.md](CONTRIBUTING.md); this file is about what we *say*, not how
we ship code.

## Prohibited citations

### "Quality score 6.2/12" (Claude Skills)

**Never cite a "6.2/12" (or equivalently-phrased) Claude Skills quality score
in any externally published content.**

- The number is commonly attributed to SkillsBench (arXiv:2602.12670), but
  **that paper does not contain this figure** — the citation is unattributable.
  Repeating it would launder an unverifiable claim through this project's
  credibility.
- This applies regardless of who or what produced the draft (human or AI) and
  regardless of whether the number is used to praise or criticize a tool.
- Before marking any draft **publish-ready**, search it for `6.2/12` (and
  close variants — `6.2 / 12`, "6.2 out of 12") and remove the citation if
  found. This is a hard gate, not a style preference.

If a future contributor wants to make a claim about Claude Skills quality,
find and cite a real, checkable source, or measure it directly (the way this
project measures its own claims — see `benchmarks/codegraph_compare/`).

## General principle

Every quantitative claim in externally published content should be
reproducible by a reader: link to the benchmark, script, or query that
produced it (see `benchmarks/codegraph_compare/GAUNTLET.md` for the pattern).
An unattributable number is worse than no number — it converts a correctness
project's credibility into a liability the moment someone checks the source
and it isn't there.

## Related

- [`benchmarks/codegraph_compare/GAUNTLET.md`](../benchmarks/codegraph_compare/GAUNTLET.md) — methodology-annotated benchmark claims, the model to follow for any new quantitative claim.
- [`docs/articles/`](articles/) — published/publish-ready long-form content this guideline applies to.
